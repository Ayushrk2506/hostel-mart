import os
import qrcode
import random
from datetime import datetime
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, jsonify, flash
)
from email.mime.text import MIMEText
from email_utils import (
    send_otp_email,
    generate_otp,
    send_order_notification_to_admin,
    send_order_confirmation_to_customer,
    send_order_status_update_to_customer,
)

import firebase_admin
from firebase_admin import credentials, firestore

# Initialize Firebase
cred = credentials.Certificate("firebase-key.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# Flask app setup
app = Flask(__name__, instance_relative_config=True)
app.secret_key = 'supersecretkey'
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

UPI_ID = "9019531019@ybl"

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
    # Fetch products from Firestore instead of SQLite
    products_ref = db.collection('products')
    docs = products_ref.stream()
    items = []
    for doc in docs:
        data = doc.to_dict()
        data['id'] = doc.id  # ensure each item has an ID
        items.append(data)

    cart = session.get("cart", {})
    cart_quantities = {int(k): v["quantity"] for k, v in cart.items()}

    user = session.get("user")

    return render_template(
        "index.html",
        items=items,
        cart=cart,
        cart_quantities=cart_quantities,
        user=user
    )


# --- Customer Signup Step 1: Enter Details & Send OTP ---
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form["name"].strip()
        mobile = request.form["mobile"].strip()
        email = request.form["email"].strip()

        # Validate uniqueness of mobile in Firestore
        customers_ref = db.collection('customers')
        duplicate_query = customers_ref.where('mobile', '==', mobile).stream()
        if any(True for _ in duplicate_query):
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

        # ✅ Save full customer into Firestore
        customer_data = {
            "name": name,
            "mobile": mobile,
            "email": email,
            "password": password  # plain text as per your preference
        }
        # Add document with mobile number as ID (optional, or let Firestore generate one)
        doc_ref = db.collection("customers").add(customer_data)
        user_doc = db.collection("customers").document(doc_ref[1].id).get()

        # ✅ Login user
        user = user_doc.to_dict()
        session["user"] = {
            "id": user_doc.id,
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

        # Fetch user document by mobile number from Firestore
        users_ref = db.collection("customers")
        query = users_ref.where("mobile", "==", mobile).limit(1).stream()
        user_docs = list(query)

        if not user_docs:
            error = "No account detected with this Phone Number."
            return render_template("login.html", error=error)

        user_doc = user_docs[0]
        user_data = user_doc.to_dict()

        if user_data.get("password") != password:
            error = "Incorrect password."
            return render_template("login.html", error=error)

        # Store user session
        session["user"] = {
            "id": user_doc.id,
            "name": user_data.get("name"),
            "mobile": user_data.get("mobile"),
            "email": user_data.get("email")
        }

        flash(f"👋 Hello {user_data.get('name')}, welcome to Hostel Mart!", "success")
        return render_template("login_success.html", user_name=user_data.get("name"))

    return render_template("login.html")

@app.route("/profile")
def profile():
    user = session.get("user")
    if not user:
        flash("Please log in to view your profile.")
        return redirect(url_for("login"))

    # 1️⃣ Fetch all orders for this user, ordered by order_time desc
    orders_query = (
        db.collection("orders")
          .where("mobile", "==", user["mobile"])
          .order_by("order_time", direction=firestore.Query.DESCENDING)
          .stream()
    )

    orders = []
    for order_doc in orders_query:
        order_data = order_doc.to_dict()
        order_id = order_doc.id

        # 2️⃣ Grab items from an 'order_items' subcollection under this order
        items_ref = db.collection("orders").document(order_id).collection("order_items")
        items_stream = items_ref.stream()

        total_amount = 0
        items = []
        for item_doc in items_stream:
            item = item_doc.to_dict()
            subtotal = item["quantity"] * item["price"]
            total_amount += subtotal
            items.append({
                "name": item.get("name"),
                "qty": item["quantity"],
                "offer_price": item["price"],
                "subtotal": subtotal
            })

        orders.append({
            "order_id": order_id,
            "order_code": order_data.get("order_code"),
            "room": order_data.get("room"),
            "payment": order_data.get("payment"),
            "status": order_data.get("status"),
            "order_time": order_data.get("order_time"),
            "total_amount": total_amount,
            "items": items
        })

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

            # 🔎 Look up customer doc in Firestore
            cust_docs = (
                db.collection("customers")
                  .where("mobile", "==", mobile)
                  .where("email", "==", email)
                  .where("name", "==", name)
                  .stream()
            )
            user_doc = next(cust_docs, None)

            if not user_doc:
                flash("User details not found. Please check and try again.", "error")
            else:
                otp = generate_otp()
                session["forgot_password_data"] = {
                    "mobile": mobile,
                    "email": email,
                    "otp": otp
                }
                try:
                    send_otp_email(email, otp)
                    flash("OTP sent to your email.", "success")
                    step = "verify_otp"
                except Exception:
                    flash("Failed to send OTP email. Try again later.", "error")

    return render_template(
        "forgot_password.html",
        step=step,
        email=data["email"] if data else None
    )



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

        # 🔄 Update password in Firestore
        users_ref = db.collection("customers")
        query = users_ref.where("mobile", "==", data["mobile"]).stream()
        user_doc = next(query, None)
        if user_doc:
            users_ref.document(user_doc.id).update({"password": new_password})

        # Clear session and continue
        session.pop("forgot_password_data", None)
        flash("Password reset successful! Please login.", "success")
        return redirect(url_for("login"))

    return render_template("reset_password.html")





# --- Add Single Item to Cart (legacy JS flow) ---
@app.route("/add_to_cart/<int:item_id>", methods=["POST"])
def add_to_cart(item_id):
    # Must be logged in
    if "user" not in session:
        return redirect(url_for("login"))

    quantity = int(request.form["quantity"])
    user_id = session["user"]["id"]

    # Reference to this user's cart item in Firestore
    cart_item_ref = db \
        .collection("carts") \
        .document(str(user_id)) \
        .collection("items") \
        .document(str(item_id))

    cart_item = cart_item_ref.get()

    if cart_item.exists:
        # Increment existing quantity
        new_qty = cart_item.to_dict().get("quantity", 0) + quantity
        cart_item_ref.update({"quantity": new_qty})
    else:
        # Fetch product info from Firestore products collection
        prod_ref = db.collection("products").document(str(item_id))
        prod_snap = prod_ref.get()
        if not prod_snap.exists:
            # invalid product id
            return ("", 404)

        prod = prod_snap.to_dict()
        cart_item_ref.set({
            "name": prod["name"],
            "price": prod["offer_price"],
            "quantity": quantity
        })

    return ("", 204)

# --- Add Bulk Items to Cart ---
@app.route("/add_bulk_to_cart", methods=["POST"])
def add_bulk_to_cart():
    if "user" not in session:
        return redirect(url_for("login"))

    user_id = session["user"]["id"]
    data = request.get_json()

    for item_id_str, qty in data.items():
        item_id = int(item_id_str)
        product_ref = db.collection("products").document(str(item_id))
        product_doc = product_ref.get()

        if product_doc.exists:
            product = product_doc.to_dict()
            cart_item_ref = (
                db.collection("carts")
                  .document(str(user_id))
                  .collection("items")
                  .document(str(item_id))
            )

            cart_item = cart_item_ref.get()
            if cart_item.exists:
                # Increment quantity if item already in cart
                existing_qty = cart_item.to_dict().get("quantity", 0)
                cart_item_ref.update({
                    "quantity": existing_qty + qty
                })
            else:
                # Add new item to cart
                cart_item_ref.set({
                    "name": product["name"],
                    "price": product["offer_price"],
                    "quantity": qty
                })

    return "", 204


# --- Cart Page ---
@app.route("/cart")
def cart():
    if "user" not in session:
        flash("Please log in to view your cart.")
        return redirect(url_for("login"))

    user_id = session["user"]["id"]
    cart_items_ref = db.collection("carts").document(str(user_id)).collection("items")
    items_stream = cart_items_ref.stream()

    cart_details = []
    total_offer = 0
    total_mrp = 0

    for item_doc in items_stream:
        item_id = item_doc.id
        cart_item = item_doc.to_dict()

        # Fetch product details from Firestore
        product_ref = db.collection("products").document(item_id)
        product_doc = product_ref.get()

        if product_doc.exists:
            product = product_doc.to_dict()
            quantity = cart_item.get("quantity", 0)
            offer_price = product["offer_price"]
            mrp = product["mrp"]
            subtotal = quantity * offer_price

            cart_details.append({
                "id": int(item_id),
                "name": product["name"],
                "qty": quantity,
                "offer_price": offer_price,
                "mrp": mrp,
                "subtotal": subtotal,
                "image": product.get("image", "")
            })

            total_offer += subtotal
            total_mrp += mrp * quantity

    savings = total_mrp - total_offer

    return render_template(
        "cart.html",
        cart_details=cart_details,
        total_offer=total_offer,
        savings=savings
    )


# --- Cart Quantity Update ---
@app.route("/update_cart_quantity", methods=["POST"])
def update_cart_quantity():
    if "user" not in session:
        return redirect(url_for("login"))

    user_id = session["user"]["id"]
    item_id = request.form["item_id"]
    action = request.form["action"]

    cart_item_ref = db.collection("carts").document(str(user_id)).collection("items").document(item_id)
    cart_item_doc = cart_item_ref.get()

    if cart_item_doc.exists:
        cart_item = cart_item_doc.to_dict()
        quantity = cart_item.get("quantity", 0)

        if action == "increment":
            quantity += 1
            cart_item_ref.update({"quantity": quantity})
        elif action == "decrement":
            quantity -= 1
            if quantity <= 0:
                cart_item_ref.delete()
            else:
                cart_item_ref.update({"quantity": quantity})

    return redirect("/cart")


# --- Order Form ---
@app.route("/order", methods=["GET", "POST"])
def order():
    if "user" not in session:
        flash("Please log in to place an order.", "error")
        return redirect(url_for("login"))

    user = session["user"]
    user_id = user["id"]

    # Fetch cart from Firestore
    cart_items_ref = db.collection("carts").document(str(user_id)).collection("items")
    cart_items = cart_items_ref.stream()

    cart_details = []
    total_offer = 0

    for item_doc in cart_items:
        item = item_doc.to_dict()
        item_id = item_doc.id
        product_ref = db.collection("products").document(item_id)
        product_doc = product_ref.get()

        if product_doc.exists:
            product = product_doc.to_dict()
            quantity = item["quantity"]
            subtotal = product["offer_price"] * quantity
            cart_details.append({
                "id": int(item_id),
                "name": product["name"],
                "qty": quantity,
                "offer_price": product["offer_price"],
                "subtotal": subtotal,
                "image": product.get("image", "")
            })
            total_offer += subtotal

    if not cart_details:
        flash("🛒 Your cart is empty. Please add items before placing an order.", "error")
        return redirect("/cart")

    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        room = request.form["room"]
        mobile = request.form["mobile"]
        payment = request.form["payment"]
        order_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Generate unique order code
        room_padded = room.zfill(4)
        rand_int = random.randint(100, 999)
        order_code = f"{mobile}{room_padded}{rand_int}"
        while db.collection("orders").where("order_code", "==", order_code).limit(1).stream():
            rand_int = random.randint(100, 999)
            order_code = f"{mobile}{room_padded}{rand_int}"

        # Create new order document
        order_ref = db.collection("orders").document()
        order_data = {
            "order_code": order_code,
            "name": name,
            "email": email,  # ✅ include email in Firestore
            "room": room,
            "mobile": mobile,
            "payment": payment,
            "order_time": order_time,
            "status": "Pending"
        }
        order_ref.set(order_data)

        # ✅ Send order email to admin
        send_order_notification_to_admin(
            name=name,
            email=email,
            mobile=mobile,
            room=room,
            cart_details=cart_details
        )

        # ✅ Send order email to customer
        send_order_confirmation_to_customer(
            name=name,
            email=email,
            mobile=mobile,
            room=room,
            cart_details=cart_items,
            order_time=order_time
        )

        
        # Add each cart item to the order + update product stock
        batch = db.batch()
        for item in cart_details:
            item_id = str(item["id"])
            qty = item["qty"]
            price = item["offer_price"]

            # Add item to order_items subcollection
            order_item_ref = order_ref.collection("order_items").document(item_id)
            batch.set(order_item_ref, {
                "product_id": item_id,
                "quantity": qty,
                "price": price
            })

            # Reduce stock
            product_ref = db.collection("products").document(item_id)
            product_doc = product_ref.get()
            if product_doc.exists:
                current_quantity = product_doc.to_dict().get("quantity", 0)
                new_quantity = max(current_quantity - qty, 0)
                batch.update(product_ref, {"quantity": new_quantity})

        # Commit batch changes
        batch.commit()

        # 🧹 Clear user's Firestore cart
        cart_items = cart_items_ref.stream()
        for doc in cart_items:
            doc.reference.delete()

        # Calculate delivery
        import math
        if payment == "prepaid":
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

    # Render GET request with autofilled data
    return render_template(
        "order_form.html",
        cart_details=cart_details,
        total_offer=total_offer,
        name=user["name"],
        email=user["email"],
        mobile=user["mobile"]
    )



# --- Dynamic UPI QR Code ---
@app.route("/payment_qr")
def payment_qr():
    amount = request.args.get("amount")
    order_code = request.args.get("order_code")

    if not amount or not order_code:
        flash("Missing payment information.", "error")
        return redirect("/shop")

    # Generate UPI QR code
    upi_link = f"upi://pay?pa={UPI_ID}&pn=HostelMart&am={amount}&cu=INR"
    qr_img = qrcode.make(upi_link)
    qr_path = os.path.join(app.config["UPLOAD_FOLDER"], "qr.png")
    qr_img.save(qr_path)

    # Fetch order from Firestore using order_code
    order_query = db.collection("orders").where("order_code", "==", order_code).limit(1).stream()
    order_doc = next(order_query, None)

    if not order_doc or not order_doc.exists:
        flash("Invalid order code.", "error")
        return redirect("/shop")

    order_id = order_doc.id
    order_data = order_doc.to_dict()

    # Fetch order items
    order_items_ref = db.collection("orders").document(order_id).collection("order_items")
    items = order_items_ref.stream()

    order_items = []
    total_offer = 0
    for item in items:
        item_data = item.to_dict()
        product_id = item_data["product_id"]
        quantity = item_data["quantity"]
        price = item_data["price"]
        subtotal = quantity * price

        # Fetch product name
        product_doc = db.collection("products").document(str(product_id)).get()
        product_name = product_doc.to_dict()["name"] if product_doc.exists else "Product"

        order_items.append({
            "name": product_name,
            "qty": quantity,
            "offer_price": price,
            "subtotal": subtotal
        })
        total_offer += subtotal

    final_amount = float(amount)
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
        return redirect('/shop')

    db = firestore.client()

    # Find order by order_code
    order_query = db.collection("orders").where("order_code", "==", order_code).limit(1).stream()
    order_doc = next(order_query, None)
    if not order_doc or not order_doc.exists:
        flash("Order not found.", "error")
        return redirect('/shop')

    order_id = order_doc.id

    # Fetch order items
    order_items_ref = db.collection("orders").document(order_id).collection("order_items")
    items = order_items_ref.stream()

    order_items = []
    total_offer = 0

    for item in items:
        item_data = item.to_dict()
        product_id = str(item_data["product_id"])
        quantity = item_data["quantity"]
        price = item_data["price"]

        # Fetch product name
        product_doc = db.collection("products").document(product_id).get()
        product_name = product_doc.to_dict().get("name", "Product") if product_doc.exists else "Product"

        subtotal = quantity * price
        total_offer += subtotal

        order_items.append({
            "name": product_name,
            "qty": quantity,
            "offer_price": price,
            "subtotal": subtotal
        })

    final_amount = total_offer

    # Generate new QR code
    qr_data = f"upi://pay?pa={UPI_ID}&pn=HostelMart&am={final_amount}&cu=INR&tn={order_code}"
    qr_img = qrcode.make(qr_data)
    qr_path = os.path.join(app.config["UPLOAD_FOLDER"], "qr.png")  # always overwrite same file
    qr_img.save(qr_path)

    summary = {
        "items": order_items,
        "total_offer": total_offer,
        "delivery_charge": 0,
        "final_amount": final_amount
    }

    return render_template("payment_qr.html",
                           qr_file="uploads/qr.png",
                           amount=final_amount,
                           order_code=order_code,
                           summary=summary,
                           user=session.get("user"),
                           timer_minutes=5)




# --- Admin Login ---
from flask import flash, redirect, url_for

@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        pin = request.form.get('pin', '').strip()

        if pin == '6388':
            session['admin_logged_in'] = True
            flash("🔐 Admin login successful.", "success")
            return redirect(url_for('admin_dashboard'))
        else:
            flash("❌ Incorrect PIN. Please try again.", "error")
            return redirect(url_for('admin_login'))

    return render_template('admin_login.html')



# --- Admin Dashboard ---
@app.route("/dashboard")
def admin_dashboard():
    if not session.get("admin_logged_in"):
        flash("Please login as admin to access this page.", "error")
        return redirect(url_for("admin_login"))
    return render_template("admin_dashboard.html")


@app.route("/inventory")
def inventory_page():
    if not session.get("admin_logged_in"):
        flash("Please login as admin to access this page.", "error")
        return redirect(url_for("admin_login"))

    db = firestore.client()
    products_ref = db.collection("products").stream()

    inventory = []
    for doc in products_ref:
        product = doc.to_dict()
        product["id"] = doc.id
        inventory.append(product)

    return render_template("inventory.html", inventory=inventory)

@app.route("/add_item", methods=["GET", "POST"])
def add_item():
    if not session.get("admin_logged_in"):
        flash("Please login as admin to access this page.", "error")
        return redirect(url_for("admin_login"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        mrp = float(request.form.get("mrp", 0))
        offer_price = float(request.form.get("offer_price", 0))
        quantity = int(request.form.get("quantity", 0))

        # Handle image upload
        image_file = request.files.get("image")
        image_filename = None

        if image_file and image_file.filename != "":
            ext = os.path.splitext(image_file.filename)[1]
            safe_name = name.replace(" ", "_")
            image_filename = f"{safe_name}_{random.randint(1000, 9999)}{ext}"
            image_path = os.path.join(app.config["UPLOAD_FOLDER"], image_filename)
            image_file.save(image_path)
            image_filename = f"uploads/{image_filename}"

        # Firestore save
        db = firestore.client()
        db.collection("products").add({
            "name": name,
            "description": description,
            "mrp": mrp,
            "offer_price": offer_price,
            "quantity": quantity,
            "image": image_filename
        })

        flash("✅ New item added successfully.", "success")
        return redirect(url_for("inventory_page"))

    return render_template("add_item.html")



@app.route("/delete_item/<int:item_id>")
def delete_item(item_id):
    if not session.get("admin_logged_in"):
        flash("Please login as admin to access this page.", "error")
        return redirect(url_for("admin_login"))

    db = firestore.client()
    products_ref = db.collection("products")
    query = products_ref.where("custom_id", "==", item_id).limit(1).stream()

    doc_to_delete = None
    for doc in query:
        doc_to_delete = doc
        break

    if doc_to_delete:
        doc_to_delete.reference.delete()
        flash("✅ Item deleted successfully.", "success")
    else:
        flash("⚠️ Item not found.", "error")

    return redirect(url_for("inventory_page"))



# --- Save Inventory Changes ---
@app.route("/save_inventory", methods=["POST"])
def save_inventory():
    if not session.get("admin_logged_in"):
        flash("Please login as admin to access this page.", "error")
        return redirect(url_for("admin_login"))

    db = firestore.client()
    products = db.collection("products").stream()

    for doc in products:
        data = doc.to_dict()
        item_id = data.get("custom_id")
        if item_id is None:
            continue  # skip items without a valid custom_id

        updated_data = {
            "name": request.form.get(f"name_{item_id}", data["name"]),
            "description": request.form.get(f"description_{item_id}", data.get("description", "")),
            "mrp": float(request.form.get(f"mrp_{item_id}", data["mrp"])),
            "offer_price": float(request.form.get(f"offer_price_{item_id}", data["offer_price"])),
            "quantity": int(request.form.get(f"quantity_{item_id}", data["quantity"]))
        }

        db.collection("products").document(doc.id).update(updated_data)

    flash("✅ Inventory updated successfully.", "success")
    return redirect("/inventory")



@app.route("/notify_seller", methods=["POST"])
def notify_seller():
    if "user" not in session:
        return "Unauthorized", 403

    product_id = request.form.get("product_id")
    product_ref = db.collection("products").document(product_id)
    product_doc = product_ref.get()

    if not product_doc.exists:
        return "Product not found", 404

    product = product_doc.to_dict()
    product_name = product.get("name", "Unknown Product")

    user = session["user"]
    name = user["name"]
    email = user["email"]
    mobile = user["mobile"]

    subject = f"📢 Product Out of Stock Notification - {product_name}"
    body = f"""
    Admin,

    A customer has requested to be notified when the following product is restocked:

    ➤ Product: {product_name}
    ➤ Customer Name: {name}
    ➤ Email: {email}
    ➤ Mobile: {mobile}

    Regards,
    Hostel Mart
    """

    send_email(to="ayushr.cs24@bmsce.ac.in", subject=subject, body=body)
    return "Notification sent to seller.", 200


# --- Update Order Status ---
@app.route("/orders")
def view_orders():
    if not session.get("admin_logged_in"):
        flash("Please login as admin to access this page.", "error")
        return redirect(url_for("admin_login"))

    db = firestore.client()
    orders_ref = db.collection("orders").order_by("order_time", direction=firestore.Query.DESCENDING)
    orders_docs = orders_ref.stream()

    all_orders = []
    for order_doc in orders_docs:
        order = order_doc.to_dict()
        order_id = order.get("custom_id")

        # Get customer details
        customer_ref = db.collection("customers").document(order["mobile"])
        customer_doc = customer_ref.get()
        customer = customer_doc.to_dict() if customer_doc.exists else None

        # Get order items
        order_items_ref = db.collection("order_items").where("order_id", "==", order_id)
        order_items = list(order_items_ref.stream())

        items = []
        total = 0
        for item_doc in order_items:
            item = item_doc.to_dict()
            product_ref = db.collection("products").document(item["product_id"])
            product_doc = product_ref.get()
            product = product_doc.to_dict() if product_doc.exists else {"name": "Unknown"}

            item_name = product.get("name", "Unknown")
            quantity = item["quantity"]
            price = item["price"]
            total += quantity * price

            items.append({
                "name": item_name,
                "quantity": quantity,
                "price": price
            })

        all_orders.append({
            "id": order_id,
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

    return render_template("order.html", orders=all_orders)



@app.route("/delete_order/<int:order_id>", methods=["POST"])
def delete_order(order_id):
    if not session.get("admin_logged_in"):
        flash("Please login as admin to access this page.", "error")
        return redirect(url_for("admin_login"))

    db = firestore.client()

    # Delete related order_items
    order_items_ref = db.collection("order_items").where("order_id", "==", order_id)
    order_items = order_items_ref.stream()
    for item in order_items:
        item.reference.delete()

    # Delete the order itself
    orders_ref = db.collection("orders").where("custom_id", "==", order_id)
    orders = orders_ref.stream()
    for order in orders:
        order.reference.delete()

    flash("✅ Order deleted successfully.", "success")
    return redirect(url_for("view_orders"))


@app.route("/update_order_status", methods=["POST"])
def update_order_status():
    if not session.get("admin_logged_in"):
        flash("Please login as admin to access this page.", "error")
        return redirect(url_for("admin_login"))

    db = firestore.client()

    order_id = request.form.get("order_id")
    new_status = request.form.get("status")

    # Find the order document by custom_id
    orders_ref = db.collection("orders").where("custom_id", "==", int(order_id))
    results = orders_ref.stream()

    for doc in results:
        doc.reference.update({"status": new_status})

        # ✅ Fetch customer info for email
        order_data = doc.to_dict()
        name = order_data.get("name", "Customer")
        email = order_data.get("email")
        order_code = order_data.get("order_code", "N/A")

        # ✅ Send email if email exists
        if email:
            send_order_status_update_to_customer(name, email, order_code, new_status)

        flash("✅ Order status updated successfully.", "success")
        break
    else:
        flash("⚠️ Order not found.", "error")

    return redirect(url_for("view_orders"))


# --- Customers Information (Admin Only) ---
@app.route("/customers_info")
def customers_info():
    if not session.get("admin_logged_in"):
        flash("Admin login required.", "error")
        return redirect(url_for("admin_login"))

    db = firestore.client()  # ✅ Initialize Firestore client

    # Fetch all customer documents from Firestore
    customers_ref = db.collection("customers")
    customers_docs = customers_ref.stream()

    # Convert documents to list of dicts
    customers = []
    for doc in customers_docs:
        customer = doc.to_dict()
        customer["id"] = doc.id  # Optional: include Firestore document ID
        customers.append(customer)

    return render_template("customers_info.html", customers=customers)


@app.route("/delete_customer/<customer_id>", methods=["POST"])
def delete_customer(customer_id):
    if not session.get("admin_logged_in"):
        flash("Admin login required.", "error")
        return redirect(url_for("admin_login"))

    db = firestore.client()  # ✅ Ensure Firestore client is initialized

    # Delete the customer document from Firestore
    db.collection("customers").document(str(customer_id)).delete()

    flash("✅ Customer deleted successfully.", "success")
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

    # 🔍 Query order with matching order_code
    orders_ref = db.collection("orders").where("order_code", "==", order_code).limit(1).get()
    if not orders_ref:
        flash("Order ID not found.", "error")
        return redirect(url_for("profile"))

    order_doc = orders_ref[0]
    order = order_doc.to_dict()
    order["id"] = order_doc.id  # add ID if needed

    # 🔍 Get items for this order
    order_items_ref = db.collection("order_items").where("order_id", "==", order["id"]).stream()
    items = []
    for doc in order_items_ref:
        item = doc.to_dict()
        # Fetch product name
        product = db.collection("products").document(str(item["product_id"])).get()
        item["name"] = product.to_dict().get("name") if product.exists else "Unknown"
        items.append(item)

    return render_template("track_order.html", order=order, items=items)



if __name__ == "__main__":
    app.run(debug=True)
