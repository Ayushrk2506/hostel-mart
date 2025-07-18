import smtplib
import random
from email.message import EmailMessage

# Sender email credentials
SENDER_EMAIL = "ayushr.cs24@bmsce.ac.in"
APP_PASSWORD = "obfkmlsmvkyrtuop"  # 🔒 Paste your 16-character app password here

def generate_otp():
    """Generate a random 6-digit OTP"""
    return str(random.randint(100000, 999999))

def send_otp_email(receiver_email, otp):
    """Send OTP to a customer's email address"""
    msg = EmailMessage()
    msg['Subject'] = "Your OTP for Hostel Mart"
    msg['From'] = SENDER_EMAIL
    msg['To'] = receiver_email
    msg.set_content(f"Hello,\n\nYour OTP for Hostel Mart is: {otp}\n\nPlease do not share it with anyone.")

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(SENDER_EMAIL, APP_PASSWORD)
            smtp.send_message(msg)
        return True
    except Exception as e:
        print("❌ Email sending failed:", e)
        return False

def send_order_notification_to_admin(customer_name, customer_email, phone, room, items):
    subject = "🛒 New Order Placed - Hostel Mart"
    body = f"""
    A new order has been placed:

    Customer Name: {customer_name}
    Email: {customer_email}
    Phone: {phone}
    Room Number: {room}

    Ordered Items:
    {items}

    -- Hostel Mart Notification System
    """
    send_email("ayushr.cs24@bmsce.ac.in", subject, body)

def send_order_confirmation_to_customer(name, email, mobile, room, cart_details, order_time):
    subject = f"✅ Hostel Mart Order Confirmation - {order_time.split()[0]}"
    
    item_lines = ""
    for item in cart_details:
        item_lines += f"- {item['name']} × {item['qty']} @ ₹{item['offer_price']} = ₹{item['subtotal']}\n"

    body = f"""Hi {name},

Your order has been placed successfully on {order_time}.

🛒 Order Summary:
{item_lines}

📦 Delivery to Room: {room}

🧾 Your Details:
Name: {name}
Email: {email}
Mobile: {mobile}

Thank you for using Hostel Mart!
"""

    send_email(email, subject, body)

def send_order_notification_to_admin(name, email, mobile, room, cart_details):
    item_lines = ""
    for item in cart_details:
        item_lines += f"- {item['name']} x {item['qty']} = ₹{item['offer_price'] * item['qty']}\n"

    message_body = f"""
🛍️ New Order Placed!

👤 Name: {name}
📱 Mobile: {mobile}
📧 Email: {email}
🏠 Room: {room}

🧾 Order Details:
{item_lines}

"""

    try:
        send_email("ayushr.cs24@bmsce.ac.in", "📦 New Order Alert - Hostel Mart", message_body)
        print("✅ Admin notified of new order.")
    except Exception as e:
        print("❌ Failed to send admin email:", e)

def valid_otp_for_email(email, entered_otp):
    signup_data = session.get("signup_data")
    return signup_data and signup_data.get("email") == email and signup_data.get("otp") == entered_otp

def send_order_status_update_to_customer(name, email, order_code, new_status):
    subject = f"📦 Your Hostel Mart Order ({order_code}) is now {new_status}"
    message = f"""Hello {name},

    Your order with order code {order_code} has been updated to:

    📌 Status: {new_status}

    Thank you for shopping with Hostel Mart!
    Hostel Mart Team
    """
    send_email(email, subject, message)

def send_order_status_update_to_customer(name, email, order_code, new_status):
    subject = f"📦 Hostel Mart - Order {order_code} Status Update"
    body = f"""
    Dear {name},

    Your order with code {order_code} has been updated to the following status:

    ➤ Status: {new_status}

    Thank you for shopping with Hostel Mart!
    """

    send_email(to=email, subject=subject, body=body)