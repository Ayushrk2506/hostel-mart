import os
import sqlite3
import qrcode
import random
import hashlib
import string
from datetime import datetime
from flask import flash
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, jsonify, flash
)
from email_utils import send_otp_email  # Your email sending helper

app = Flask(__name__)
app.secret_key = 'supersecretkey'
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


UPI_ID = "9019531019@ybl"

# --- DB Connection ---
def get_db_connection():
    conn = sqlite3.connect('database.db')  # no more ../
    conn.row_factory = sqlite3.Row
    return conn
def save_password_for_email(email, password):
    conn = get_db_connection()
    conn.execute("UPDATE customers SET password = ? WHERE email = ?", (password, email))
    conn.commit()
    conn.close()


# --- Utility: Generate OTP ---
def generate_otp(length=6):
    return ''.join(random.choices(string.digits, k=length))

# --- Utility: Validate OTP for Signup ---
def valid_otp_for_email(email, entered_otp):
    signup_data = session.get("signup_data")
    if signup_data and signup_data.get("email") == email:
        return signup_data.get("otp") == entered_otp
    return False

# --- Require login for cart/order related operations ---
@app.before_request
def require_login_for_cart_ops():
    protected_endpoints = {
        "add_to_cart", "add_bulk_to_cart", "cart",
        "update_cart_quantity", "order"
    }
    if request.endpoint in protected_endpoints:
        if "user" not in session:
            flash("You must be logged in to add items to the cart or place orders.", "error")
            return redirect(url_for("login"))


# --- New Colorful Landing Page ---
@app.route("/")
def homepage():
    return render_template("homepage.html")

# --- Old Homepage (Now moved to /shop) ---
@app.route("/shop")
def index():
    conn = get_db_connection()
    items = conn.execute("SELECT * FROM products").fetchall()
    conn.close()

    cart = session.get("cart", {})
    cart_quantities = {int(k): v["quantity"] for k, v in cart.items()}

    user = session.get("user")

    return render_template("index.html", items=items, cart=cart,
                           cart_quantities=cart_quantities, user=user)


# --- Customer Signup Step 1: Enter Details & Send OTP ---
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form["name"].strip()
        mobile = request.form["mobile"].strip()
        email = request.form["email"].strip()

        # Validate uniqueness of mobile
        conn = get_db_connection()
        exists = conn.execute("SELECT * FROM customers WHERE mobile = ?", (mobile,)).fetchone()
        conn.close()
        if exists:
            flash("⚠️ Account already linked with this phone number.", "error")
            return redirect(url_for("signup"))

        otp = generate_otp()
        session["signup_data"] = {"name": name, "mobile": mobile, "email": email, "otp": otp}

        # Send OTP email
        try:
            send_otp_email(email, otp)
        except Exception as e:
            flash("Failed to send OTP email. Try again later.", "error")
            return redirect(url_for("signup"))

        return redirect(url_for("verify_signup_otp"))

    return render_template("signup.html")

# --- Customer Signup Step 2: Verify OTP ---
@app.route('/verify_signup_otp', methods=['GET', 'POST'])
def verify_signup_otp():
    signup_data = session.get("signup_data", {})
    email = signup_data.get("email")

    if request.method == 'POST':
        entered_otp = request.form['otp']

        if valid_otp_for_email(email, entered_otp):
            # ✅ Save all signup data for final account creation
            session['verified_signup'] = {
                "name": signup_data.get("name"),
                "mobile": signup_data.get("mobile"),
                "email": email
            }

            return redirect(url_for('create_password'))
        else:
            error = "Invalid OTP, please try again."
            return render_template('verify_signup_otp.html', email=email, error=error)

    return render_template('verify_signup_otp.html', email=email)




# Add this route in your app.py (alongside your other routes)

@app.route('/resend_signup_otp', methods=['POST'])
def resend_signup_otp():
    email = request.form.get('email')
    if not email:
        flash("Email not found. Please signup again.", "error")
        return redirect(url_for('signup'))

    # Generate a new 6-digit OTP
    new_otp = str(random.randint(100000, 999999))

    # Update the session data with new OTP
    signup_data = session.get('signup_data', {})
    signup_data['otp'] = new_otp
    signup_data['email'] = email
    session['signup_data'] = signup_data

    # Send the new OTP email (make sure you imported your email utility function)
    from email_utils import send_otp_email
    send_otp_email(email, new_otp)

    flash("OTP resent to your email.", "info")
    return redirect(url_for('verify_signup_otp'))

# --- Customer Signup Step 3: Create Password ---
@app.route('/create_password', methods=['GET', 'POST'])
def create_password():
    signup_info = session.get('verified_signup')
    if not signup_info:
        flash("Please verify your email OTP first.")
        return redirect(url_for('signup'))

    if request.method == 'POST':
        password = request.form['password']
        confirm = request.form['confirm_password']

        if password != confirm:
            error = "Passwords do not match."
            return render_template('create_password.html', error=error)

        name = signup_info["name"]
        mobile = signup_info["mobile"]
        email = signup_info["email"]

        # ✅ Save full customer into DB
        conn = get_db_connection()
        conn.execute("INSERT INTO customers (name, mobile, email, password) VALUES (?, ?, ?, ?)",
                     (name, mobile, email, password))
        conn.commit()

        user = conn.execute("SELECT * FROM customers WHERE mobile = ?", (mobile,)).fetchone()
        conn.close()

        # ✅ Login user
        session["user"] = {
            "id": user["id"],
            "name": user["name"],
            "mobile": user["mobile"],
            "email": user["email"]
        }

        # ✅ Clear verification sessions
        session.pop("verified_signup", None)
        session.pop("signup_data", None)

        # ✅ Flash greeting message
        flash(f"👋 Hello {user['name']}, welcome to Hostel Mart!", "success")

        # ✅ Show account created success page
        return render_template("password_created.html", user_name=user["name"])

    return render_template("create_password.html")




@app.route("/account_created")
def account_created():
    return render_template("account_created.html")

# --- Customer Login ---
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        mobile = request.form["mobile"]
        password = request.form["password"]

        conn = get_db_connection()
        user = conn.execute("SELECT * FROM customers WHERE mobile = ?", (mobile,)).fetchone()
        conn.close()

        if not user:
            error = "No account detected with this Phone Number."
            return render_template("login.html", error=error)

        if user["password"] != password:
            error = "Incorrect password."
            return render_template("login.html", error=error)

        # Store user session
        session["user"] = {
            "id": user["id"],
            "name": user["name"],
            "mobile": user["mobile"],
            "email": user["email"]
        }

        flash(f"👋 Hello {user['name']}, welcome to Hostel Mart!", "success")
        return render_template("login_success.html", user_name=user["name"])

    return render_template("login.html")

@app.route("/profile")
def profile():
    user = session.get("user")
    if not user:
        flash("Please log in to view your profile.")
        return redirect(url_for("login"))

    conn = get_db_connection()

    orders = conn.execute("""
        SELECT o.id AS order_id, o.order_code, o.room, o.payment, o.status, o.order_time,
               COALESCE(SUM(oi.quantity * oi.price), 0) AS total_amount
        FROM orders o
        LEFT JOIN order_items oi ON o.id = oi.order_id
        WHERE o.mobile = ?
        GROUP BY o.id
        ORDER BY o.order_time DESC
    """, (user["mobile"],)).fetchall()

    conn.close()
    return render_template("profile.html", user=user, orders=orders)



# --- Customer Logout ---
@app.route("/logout")
def logout():
    session.pop("user", None)
    flash("Logged out successfully.", "success")
    return redirect(url_for("index"))



# --- Forgot Password Step 1: Enter Details & Send OTP ---
@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    step = "verify_user"
    data = session.get("forgot_password_data")

    if request.method == "POST":
        if "otp" in request.form:
            # Step 2: User is submitting OTP
            entered_otp = request.form["otp"].strip()
            if data and entered_otp == data["otp"]:
                return redirect(url_for("reset_password"))
            else:
                flash("Incorrect OTP. Please try again.", "error")
                step = "verify_otp"
        else:
            # Step 1: User is submitting name, mobile, email
            name = request.form["name"].strip()
            mobile = request.form["mobile"].strip()
            email = request.form["email"].strip()

            conn = get_db_connection()
            user = conn.execute("SELECT * FROM customers WHERE mobile = ? AND email = ? AND name = ?", (mobile, email, name)).fetchone()
            conn.close()

            if not user:
                flash("User details not found. Please check and try again.", "error")
            else:
                otp = generate_otp()
                session["forgot_password_data"] = {"mobile": mobile, "email": email, "otp": otp}
                try:
                    send_otp_email(email, otp)
                    flash("OTP sent to your email.", "success")
                    step = "verify_otp"
                except Exception:
                    flash("Failed to send OTP email. Try again later.", "error")

    return render_template("forgot_password.html", step=step, email=data["email"] if data else None)



# --- Forgot Password Step 3: Reset Password ---
@app.route("/reset_password", methods=["GET", "POST"])
def reset_password():
    data = session.get("forgot_password_data")
    if not data:
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        new_password = request.form["new_password"].strip()
        confirm_password = request.form["confirm_password"].strip()

        if new_password != confirm_password:
            flash("Passwords do not match.", "error")
            return redirect(url_for("reset_password"))

        if len(new_password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return redirect(url_for("reset_password"))

        # Save password as plain text (you requested to remove hashing)
        plain_password = new_password

        conn = get_db_connection()
        conn.execute("UPDATE customers SET password = ? WHERE mobile = ?", (plain_password, data["mobile"]))
        conn.commit()
        conn.close()

        session.pop("forgot_password_data", None)
        flash("Password reset successful! Please login.", "success")
        return redirect(url_for("login"))

    return render_template("reset_password.html")





# --- Add Single Item to Cart (legacy JS flow) ---
@app.route("/add_to_cart/<int:item_id>", methods=["POST"])
def add_to_cart(item_id):
    quantity = int(request.form["quantity"])
    cart = session.get("cart", {})

    if str(item_id) in cart:
        cart[str(item_id)]["quantity"] += quantity
    else:
        conn = get_db_connection()
        product = conn.execute("SELECT name, offer_price FROM products WHERE id = ?", (item_id,)).fetchone()
        conn.close()
        if product:
            cart[str(item_id)] = {
                "name": product["name"],
                "price": product["offer_price"],
                "quantity": quantity
            }

    session["cart"] = cart
    session.modified = True
    return "", 204

# --- Add Bulk Items to Cart ---
@app.route("/add_bulk_to_cart", methods=["POST"])
def add_bulk_to_cart():
    data = request.get_json()
    cart = session.get("cart", {})

    conn = get_db_connection()
    for item_id_str, qty in data.items():
        item_id = int(item_id_str)
        product = conn.execute("SELECT name, offer_price FROM products WHERE id = ?", (item_id,)).fetchone()
        if product:
            if str(item_id) in cart:
                cart[str(item_id)]["quantity"] += qty
            else:
                cart[str(item_id)] = {
                    "name": product["name"],
                    "price": product["offer_price"],
                    "quantity": qty
                }

    conn.close()
    session["cart"] = cart
    session.modified = True
    return "", 204

# --- Cart Page ---
@app.route("/cart")
def cart():
    conn = get_db_connection()
    cart = session.get("cart", {})
    cart_details = []
    total_offer = 0
    total_mrp = 0

    for item_id, item in cart.items():
        product = conn.execute("SELECT * FROM products WHERE id = ?", (item_id,)).fetchone()
        if product:
            subtotal = product["offer_price"] * item["quantity"]
            cart_details.append({
                "id": product["id"],
                "name": product["name"],
                "qty": item["quantity"],
                "offer_price": product["offer_price"],
                "mrp": product["mrp"],
                "subtotal": subtotal,
                "image": product["image"]
            })
            total_offer += subtotal
            total_mrp += product["mrp"] * item["quantity"]

    savings = total_mrp - total_offer
    conn.close()
    return render_template("cart.html", cart_details=cart_details, total_offer=total_offer, savings=savings)

# --- Cart Quantity Update ---
@app.route("/update_cart_quantity", methods=["POST"])
def update_cart_quantity():
    item_id = request.form["item_id"]
    action = request.form["action"]
    cart = session.get("cart", {})

    if item_id in cart:
        if action == "increment":
            cart[item_id]["quantity"] += 1
        elif action == "decrement":
            cart[item_id]["quantity"] -= 1
            if cart[item_id]["quantity"] <= 0:
                del cart[item_id]

    session["cart"] = cart
    return redirect("/cart")

# --- Order Form ---
@app.route("/order", methods=["GET", "POST"])
def order():
    cart = session.get("cart", {})

    if not cart:
        flash("🛒 Your cart is empty. Please add items before placing an order.", "error")
        return redirect("/cart")

    conn = get_db_connection()
    cart_details = []
    total_offer = 0

    for item_id, item in cart.items():
        product = conn.execute("SELECT * FROM products WHERE id = ?", (item_id,)).fetchone()
        if product:
            subtotal = product["offer_price"] * item["quantity"]
            cart_details.append({
                "id": product["id"],
                "name": product["name"],
                "qty": item["quantity"],
                "offer_price": product["offer_price"],
                "subtotal": subtotal,
                "image": product["image"]
            })
            total_offer += subtotal

    if request.method == "POST":
        name = request.form["name"]
        room = request.form["room"]
        mobile = request.form["mobile"]
        payment = request.form["payment"]
        order_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Generate Order ID: phone(10) + padded room + 3-digit random
        room_padded = room.zfill(4)
        rand_int = random.randint(100, 999)
        order_code = f"{mobile}{room_padded}{rand_int}"

        # Ensure unique order_code
        existing = conn.execute("SELECT * FROM orders WHERE order_code = ?", (order_code,)).fetchone()
        while existing:
            rand_int = random.randint(100, 999)
            order_code = f"{mobile}{room_padded}{rand_int}"
            existing = conn.execute("SELECT * FROM orders WHERE order_code = ?", (order_code,)).fetchone()

        # Insert order
        conn.execute("""
            INSERT INTO orders (order_code, name, room, mobile, payment, order_time, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (order_code, name, room, mobile, payment, order_time, "Pending"))

        order_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        for item_id, item in cart.items():
            conn.execute("""
                INSERT INTO order_items (order_id, product_id, quantity, price)
                VALUES (?, ?, ?, ?)
            """, (order_id, item_id, item["quantity"], item["price"]))

            conn.execute("UPDATE products SET quantity = quantity - ? WHERE id = ?",
                         (item["quantity"], item_id))

        conn.commit()
        conn.close()
        session.pop("cart", None)

        import math
        if payment == "prepaid":
            delivery_charge = 0
            final_amount = total_offer
            return redirect(url_for("payment_qr", amount=final_amount, order_code=order_code))
        else:
            delivery_charge = 5 if total_offer <= 50 else math.ceil(total_offer * 0.10)
            final_amount = total_offer + delivery_charge

            return render_template("order_cod_summary.html",
                                   order_code=order_code,
                                   cart_details=cart_details,
                                   delivery_charge=delivery_charge,
                                   final_amount=final_amount)

    return render_template("order_form.html", cart_details=cart_details, total_offer=total_offer)


# --- Dynamic UPI QR Code ---
@app.route("/payment_qr")
def payment_qr():
    amount = request.args.get("amount")
    order_code = request.args.get("order_code")

    if not amount or not order_code:
        flash("Missing payment information.", "error")
        return redirect("/shop")

    # Generate QR with passed amount
    upi_link = f"upi://pay?pa={UPI_ID}&pn=HostelMart&am={amount}&cu=INR"
    qr_img = qrcode.make(upi_link)
    qr_path = os.path.join(app.config["UPLOAD_FOLDER"], "qr.png")
    qr_img.save(qr_path)

    # Fetch order summary for display
    conn = get_db_connection()
    order = conn.execute("SELECT * FROM orders WHERE order_code = ?", (order_code,)).fetchone()
    order_items = []
    total_offer = 0

    if order:
        items = conn.execute(
            "SELECT oi.*, p.name, p.offer_price FROM order_items oi JOIN products p ON oi.product_id = p.id WHERE order_id = ?",
            (order["id"],)
        ).fetchall()
        for item in items:
            subtotal = item["offer_price"] * item["quantity"]
            order_items.append({
                "name": item["name"],
                "qty": item["quantity"],
                "offer_price": item["offer_price"],
                "subtotal": subtotal
            })
            total_offer += subtotal
    else:
        conn.close()
        flash("Invalid order code.", "error")
        return redirect("/shop")

    conn.close()

    final_amount = float(amount)  # Passed from order route

    summary = {
        "items": order_items,
        "total_offer": total_offer,
        "delivery_charge": 0,
        "final_amount": final_amount
    }

    return render_template(
        "payment_qr.html",
        amount=final_amount,
        qr_file="uploads/qr.png",
        summary=summary,
        order_code=order_code,
        user=session.get("user"),
        timer_minutes=5
    )


@app.route('/regenerate_qr')
def regenerate_qr():
    order_code = request.args.get('order_code')
    if not order_code:
        flash("Invalid request. Order code missing.", "error")
        return redirect('/')

    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Get order
    order = c.execute("SELECT id FROM orders WHERE order_code = ?", (order_code,)).fetchone()
    if not order:
        conn.close()
        flash("Order not found.", "error")
        return redirect('/')

    # Get item details
    order_items_raw = c.execute("""
        SELECT p.name, oi.quantity, p.offer_price
        FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        WHERE oi.order_id = ?
    """, (order["id"],)).fetchall()
    conn.close()

    # Calculate final amount
    order_items = []
    total_offer = 0
    for item in order_items_raw:
        subtotal = item["quantity"] * item["offer_price"]
        total_offer += subtotal
        order_items.append({
            "name": item["name"],
            "qty": item["quantity"],
            "offer_price": item["offer_price"],
            "subtotal": subtotal
        })

    final_amount = total_offer  # No delivery charge for prepaid

    # Generate QR
    qr_data = f"upi://pay?pa={UPI_ID}&pn=HostelMart&am={final_amount}&cu=INR&tn={order_code}"
    qr_img = qrcode.make(qr_data)
    qr_filename = f"{order_code}_qr.png"
    qr_path = os.path.join("static", qr_filename)
    qr_img.save(qr_path)

    summary = {
        "items": order_items,
        "total_offer": total_offer,
        "delivery_charge": 0,
        "final_amount": final_amount
    }

    return render_template("payment_qr.html",
                           qr_file=qr_filename,
                           amount=final_amount,
                           order_code=order_code,
                           summary=summary,
                           user=session.get("user"))


# --- Admin Login ---
from flask import flash, redirect, url_for

@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        pin = request.form.get('pin')
        if pin == '6388':
            session['admin_logged_in'] = True  # ✅ Corrected session key
            return redirect(url_for('admin_dashboard'))  # ✅ Matches your actual dashboard route
        else:
            flash("Incorrect PIN")
            return redirect(url_for('admin_login'))
    return render_template('admin_login.html')



# --- Admin Dashboard ---
@app.route("/dashboard")
def admin_dashboard():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))
    return render_template("admin_dashboard.html")


@app.route("/inventory")
def inventory_page():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))
    
    conn = get_db_connection()
    inventory = conn.execute("SELECT * FROM products").fetchall()
    conn.close()
    
    return render_template("inventory.html", inventory=inventory)

@app.route("/add_item", methods=["GET", "POST"])
def add_item():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        mrp = request.form.get("mrp")
        offer_price = request.form.get("offer_price")
        quantity = request.form.get("quantity")

        # Image handling
        image_file = request.files.get("image")
        image_filename = None

        if image_file and image_file.filename != "":
            # Secure filename
            ext = os.path.splitext(image_file.filename)[1]
            image_filename = f"{name.replace(' ', '_')}_{random.randint(1000, 9999)}{ext}"
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
            image_file.save(image_path)
            image_filename = f"uploads/{image_filename}"  # save relative path for database

        conn = get_db_connection()
        conn.execute("""
            INSERT INTO products (name, description, mrp, offer_price, quantity, image)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, description, mrp, offer_price, quantity, image_filename))
        conn.commit()
        conn.close()

        flash("✅ New item added successfully.", "success")
        return redirect(url_for("inventory_page"))

    return render_template("add_item.html")


@app.route("/delete_item/<int:item_id>")
def delete_item(item_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    conn = get_db_connection()
    conn.execute("DELETE FROM products WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    flash("Item deleted successfully.", "success")
    return redirect(url_for("inventory_page"))


# --- Save Inventory Changes ---
@app.route("/save_inventory", methods=["POST"])
def save_inventory():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    conn = get_db_connection()
    inventory = conn.execute("SELECT * FROM products").fetchall()

    for item in inventory:
        item_id = item["id"]
        conn.execute('''
            UPDATE products
            SET name = ?, description = ?, mrp = ?, offer_price = ?, quantity = ?
            WHERE id = ?
        ''', (
            request.form.get(f"name_{item_id}"),
            request.form.get(f"description_{item_id}"),
            request.form.get(f"mrp_{item_id}"),
            request.form.get(f"offer_price_{item_id}"),
            request.form.get(f"quantity_{item_id}"),
            item_id
        ))

    conn.commit()
    conn.close()
    flash("Inventory updated successfully.", "success")
    return redirect("/inventory")


# --- Update Order Status ---
@app.route("/orders")
def view_orders():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    conn = get_db_connection()
    orders_data = conn.execute("SELECT * FROM orders ORDER BY order_time DESC").fetchall()

    all_orders = []
    for order in orders_data:
        customer = conn.execute("SELECT * FROM customers WHERE mobile = ?", (order["mobile"],)).fetchone()
        
        # ✅ Fetch quantity, price, name
        items = conn.execute(
            "SELECT oi.quantity, oi.price, p.name FROM order_items oi JOIN products p ON oi.product_id = p.id WHERE order_id = ?",
            (order["id"],)
        ).fetchall()

        # ✅ Correct total calculation using actual price
        total = sum(item["quantity"] * item["price"] for item in items)

        all_orders.append({
            "id": order["id"],
            "order_code": order["order_code"],
            "name": order["name"],
            "mobile": order["mobile"],
            "email": customer["email"] if customer else "N/A",
            "room": order["room"],
            "payment": order["payment"],
            "status": order["status"],
            "items": items,
            "total": total
        })

    conn.close()
    return render_template("order.html", orders=all_orders)


@app.route("/delete_order/<int:order_id>", methods=["POST"])
def delete_order(order_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    conn = get_db_connection()
    conn.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))
    conn.execute("DELETE FROM orders WHERE id = ?", (order_id,))
    conn.commit()
    conn.close()
    flash("Order deleted successfully.", "success")
    return redirect(url_for("view_orders"))

@app.route("/update_order_status", methods=["POST"])
def update_order_status():
    order_id = request.form.get("order_id")
    new_status = request.form.get("status")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE orders SET status = ? WHERE id = ?", (new_status, order_id))
    conn.commit()
    conn.close()

    flash("Order status updated successfully.", "success")
    return redirect(url_for("view_orders"))



# --- Customers Information (Admin Only) ---
@app.route("/customers_info")
def customers_info():
    if not session.get("admin_logged_in"):
        flash("Admin login required.", "error")
        return redirect(url_for("admin_login"))

    conn = get_db_connection()
    customers = conn.execute("SELECT * FROM customers").fetchall()
    conn.close()

    return render_template("customers_info.html", customers=customers)

@app.route("/delete_customer/<int:customer_id>", methods=["POST"])
def delete_customer(customer_id):
    if not session.get("admin_logged_in"):
        flash("Admin login required.", "error")
        return redirect(url_for("admin_login"))

    conn = get_db_connection()
    conn.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
    conn.commit()
    conn.close()

    flash("Customer deleted successfully.", "success")
    return redirect(url_for("customers_info"))


# --- Track Order ---
@app.route("/track_order", methods=["GET", "POST"])
def track_order():
    if request.method == "POST":
        order_code = request.form["order_code"].strip()
    else:
        order_code = request.args.get("order_code", "").strip()

    if not order_code:
        flash("No Order ID provided.", "error")
        return redirect(url_for("profile"))

    conn = get_db_connection()
    order = conn.execute("SELECT * FROM orders WHERE order_code = ?", (order_code,)).fetchone()
    if not order:
        flash("Order ID not found.", "error")
        conn.close()
        return redirect(url_for("profile"))

    items = conn.execute(
        "SELECT oi.quantity, oi.price, p.name FROM order_items oi JOIN products p ON oi.product_id = p.id WHERE order_id = ?",
        (order["id"],)
    ).fetchall()
    conn.close()

    return render_template("track_order.html", order=order, items=items)



if __name__ == "__main__":
    app.run(debug=True)
