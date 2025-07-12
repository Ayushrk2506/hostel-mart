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
