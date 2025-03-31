# backend/email_delivery.py
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import os

SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", 1025))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

def send_email(recipient_email, subject, body):
    """Sends an email using the configured SMTP server."""
    if not SMTP_SERVER:
        print("Error: SMTP_SERVER environment variable not set.")
        return False

    msg = MIMEMultipart()
    sender_email = SMTP_USER if SMTP_USER else "phishing-simulation@example.com"
    msg["From"] = sender_email
    msg["To"] = recipient_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html"))

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        # NOTE: Real SMTP servers need TLS/Auth. Uncomment below to use
        # if SMTP_USER and SMTP_PASSWORD:
        #     server.starttls()
        #     server.ehlo()
        #     server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        print(f"Email sent to {recipient_email}")
        return True
    except Exception as e:
        print(f"Failed to send email to {recipient_email}: {e}")
        return False