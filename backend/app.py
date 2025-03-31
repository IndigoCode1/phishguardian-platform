# backend/app.py
import os
from flask import Flask, jsonify, request, render_template, redirect, url_for, abort
from datetime import datetime
import mysql.connector
from mysql.connector import Error
from flask_cors import CORS
import uuid
import threading
import markdown

# In-memory storage for tracking tokens (Lost on server restart, this is for demo purposes)
tracking_token_map = {}
map_lock = threading.Lock()

from ai_integration import generate_phishing_email_content, generate_phishing_tips
from email_delivery import send_email

app = Flask(__name__)
CORS(app)

# Database and Base URL Configuration
MYSQL_HOST = os.getenv("MYSQL_HOST", "mysql")
MYSQL_USER = os.getenv("MYSQL_USER", "phishing_user")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "password")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "phishing_db")
MYSQL_PORT = os.getenv("MYSQL_PORT", "3306")
BASE_URL = os.getenv("BASE_URL", "http://localhost:5000")

def get_db_connection():
    """Establishes a connection to the MySQL database."""
    connection = None
    try:
        connection = mysql.connector.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE,
            connect_timeout=10
        )
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
    return connection

@app.route('/')
def index():
    """Index route to check if the service is running."""
    return "AI Phishing Simulation Platform is running."

@app.route('/campaigns', methods=['POST'])
def create_campaign():
    """Creates a new phishing campaign."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    campaign_name = data.get("name")
    scenario = data.get("scenario", "")
    start_time_str = data.get("start_time")
    recipients = data.get("recipients")

    if not campaign_name or not start_time_str or not recipients:
        return jsonify({"error": "Missing required fields"}), 400

    try:
        start_time = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return jsonify({"error": "Invalid start_time format. Use YYYY-MM-DD HH:MM:SS"}), 400

    conn = get_db_connection()
    if conn is None:
        return jsonify({"error": "Database connection failed"}), 500

    cursor = None
    try:
        cursor = conn.cursor()
        campaign_query = "INSERT INTO campaigns (name, scenario, start_time) VALUES (%s, %s, %s)"
        cursor.execute(campaign_query, (campaign_name, scenario, start_time))
        campaign_id = cursor.lastrowid

        recipient_query = "INSERT INTO recipients (campaign_id, name, email) VALUES (%s, %s, %s)"
        recipient_data = []
        for recipient in recipients:
            r_name = recipient.get("name")
            r_email = recipient.get("email")
            if r_name and r_email:
                recipient_data.append((campaign_id, r_name, r_email))
            else:
                raise ValueError("Invalid recipient data")

        cursor.executemany(recipient_query, recipient_data)
        conn.commit()
        return jsonify({"message": "Campaign created", "campaign_id": campaign_id}), 201

    except (Error, ValueError) as e:
        if conn: conn.rollback()
        print(f"Error creating campaign: {e}")
        return jsonify({"error": f"Failed to create campaign: {e}"}), 500
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

@app.route('/campaigns/<int:campaign_id>', methods=['GET'])
def get_campaign_details(campaign_id):
    """Retrieves details for a specific campaign."""
    conn = get_db_connection()
    if conn is None:
        return jsonify({"error": "Database connection failed"}), 500

    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM campaigns WHERE campaign_id = %s", (campaign_id,))
        campaign = cursor.fetchone()
        if not campaign:
            return jsonify({"error": "Campaign not found"}), 404

        cursor.execute("SELECT recipient_id, name, email FROM recipients WHERE campaign_id = %s", (campaign_id,))
        recipients = cursor.fetchall()
        campaign['recipients'] = recipients

        event_query = """
            SELECT te.event_id, te.recipient_id, r.name, r.email, te.event_type, te.event_timestamp, te.ip_address
            FROM tracking_events te
            JOIN recipients r ON te.recipient_id = r.recipient_id
            WHERE te.campaign_id = %s ORDER BY te.event_timestamp DESC
        """
        cursor.execute(event_query, (campaign_id,))
        events = cursor.fetchall()
        for event in events:
            if event.get('event_timestamp'):
                 event['event_timestamp'] = event['event_timestamp'].isoformat()
        campaign['events'] = events

        if campaign.get('start_time'): campaign['start_time'] = campaign['start_time'].isoformat()
        if campaign.get('created_at'): campaign['created_at'] = campaign['created_at'].isoformat()

        return jsonify(campaign), 200
    except Error as e:
        print(f"Error retrieving campaign details: {e}")
        return jsonify({"error": "Failed to fetch campaign details"}), 500
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

@app.route('/track/<tracking_token>', methods=['GET'])
def track_link_click(tracking_token):
    """Handles clicks on tracking links and renders the fake login page."""
    tracking_info = None
    with map_lock:
        tracking_info = tracking_token_map.get(tracking_token)

    if not tracking_info:
        print(f"Tracking token not found in map: {tracking_token}")
        abort(404, description="Invalid or expired tracking token")

    campaign_id = tracking_info['campaign_id']
    recipient_id = tracking_info['recipient_id']

    conn = get_db_connection()
    if conn is None:
        abort(500, description="Database connection failed")

    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)
        # Log click event if not already logged for this combo
        check_click_query = "SELECT event_id FROM tracking_events WHERE campaign_id = %s AND recipient_id = %s AND event_type = 'click'"
        cursor.execute(check_click_query, (campaign_id, recipient_id))
        existing_click = cursor.fetchone()

        if not existing_click:
             click_query = "INSERT INTO tracking_events (campaign_id, recipient_id, event_type, ip_address) VALUES (%s, %s, %s, %s)"
             cursor.execute(click_query, (campaign_id, recipient_id, "click", request.remote_addr))
             conn.commit()

        return render_template('fake_login.html', tracking_token=tracking_token)

    except Error as e:
        if conn: conn.rollback()
        print(f"Error logging click event: {e}")
        abort(500, description="Error processing tracking link")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

@app.route('/submit/<tracking_token>', methods=['POST'])
def fake_login_submit(tracking_token):
    """Handles fake credential submissions and shows feedback."""
    tracking_info = None
    with map_lock:
        tracking_info = tracking_token_map.get(tracking_token)

    if not tracking_info:
        print(f"Tracking token not found in map: {tracking_token}")
        return "Invalid or expired tracking token.", 400

    campaign_id = tracking_info['campaign_id']
    recipient_id = tracking_info['recipient_id']

    conn = get_db_connection()
    if conn is None:
        return render_template('submission_error.html', error_message="Database connection failed.")

    cursor = None
    feedback_tips_html = ""
    try:
        cursor = conn.cursor(dictionary=True)
        # Log submission event if not already logged
        check_submission_query = "SELECT event_id FROM tracking_events WHERE campaign_id = %s AND recipient_id = %s AND event_type = 'submission'"
        cursor.execute(check_submission_query, (campaign_id, recipient_id))
        existing_submission = cursor.fetchone()

        if not existing_submission:
             submission_query = "INSERT INTO tracking_events (campaign_id, recipient_id, event_type, ip_address) VALUES (%s, %s, %s, %s)"
             cursor.execute(submission_query, (campaign_id, recipient_id, "submission", request.remote_addr))
             conn.commit()
             print(f"Submission logged for campaign {campaign_id}, recipient {recipient_id}")
        else:
             print(f"Duplicate submission attempt for campaign {campaign_id}, recipient {recipient_id}")

        try:
            feedback_tips_raw = generate_phishing_tips()
            feedback_tips_html = markdown.markdown(feedback_tips_raw)
        except Exception as ai_err:
            print(f"Error calling generate_phishing_tips: {ai_err}")
            feedback_tips_html = "<p>Could not load phishing tips at this time. Remember to always be cautious with emails asking for personal information or containing suspicious links.</p>"

        return render_template('submission_feedback.html', tips_html=feedback_tips_html)

    except Error as e:
        if conn: conn.rollback()
        print(f"Error logging submission event: {e}")
        return render_template('submission_error.html', error_message="Error processing submission.")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

@app.route('/admin/dashboard/<int:campaign_id>', methods=['GET'])
def admin_dashboard(campaign_id):
    """Displays the report dashboard for a specific campaign."""
    conn = get_db_connection()
    if conn is None:
        return "Database connection failed", 500

    cursor = None
    report = {}
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) as total FROM recipients WHERE campaign_id = %s", (campaign_id,))
        total_recipients = cursor.fetchone()['total']

        cursor.execute("SELECT COUNT(DISTINCT recipient_id) as clicks FROM tracking_events WHERE campaign_id = %s AND event_type = 'click'", (campaign_id,))
        total_clicks = cursor.fetchone()['clicks']

        cursor.execute("SELECT COUNT(DISTINCT recipient_id) as submissions FROM tracking_events WHERE campaign_id = %s AND event_type = 'submission'", (campaign_id,))
        total_submissions = cursor.fetchone()['submissions']

        report = {
            "total_recipients": total_recipients,
            "total_clicks": total_clicks,
            "total_submissions": total_submissions,
            "click_rate": round((total_clicks / total_recipients * 100), 2) if total_recipients > 0 else 0,
            "submission_rate": round((total_submissions / total_recipients * 100), 2) if total_recipients > 0 else 0
        }
    except Error as e:
        print(f"Error fetching report: {e}")
        report = { "total_recipients": "N/A", "total_clicks": "N/A", "total_submissions": "N/A", "click_rate": "N/A", "submission_rate": "N/A" }
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    return render_template("admin_dashboard.html", campaign_id=campaign_id, report=report)

@app.route('/campaigns/send/<int:campaign_id>', methods=['POST'])
def send_campaign_emails(campaign_id):
    conn = get_db_connection()
    if conn is None: return jsonify({"error": "Database connection failed"}), 500

    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT scenario FROM campaigns WHERE campaign_id = %s", (campaign_id,))
        campaign = cursor.fetchone()
        if not campaign: return jsonify({"error": "Campaign not found"}), 404

        cursor.execute("SELECT recipient_id, name, email FROM recipients WHERE campaign_id = %s", (campaign_id,))
        recipients = cursor.fetchall()
        if not recipients: return jsonify({"message": "No recipients found."}), 200

        emails_sent_count = 0
        emails_failed_count = 0

        for recipient in recipients:
            try:
                email_content = generate_phishing_email_content(campaign["scenario"], recipient["name"])
                tracking_token = str(uuid.uuid4())
                tracking_url = f"{BASE_URL}/track/{tracking_token}"

                with map_lock:
                    tracking_token_map[tracking_token] = {
                        'campaign_id': campaign_id,
                        'recipient_id': recipient["recipient_id"]
                    }

                # Replace placeholder
                body_with_link = email_content["body"].replace("{{TRACKING_LINK}}", f'<a href="{tracking_url}">{tracking_url}</a>')

                final_body_html = body_with_link.replace('\n', '<br>')

                # Send the email with HTML line breaks
                success = send_email(recipient["email"], email_content["subject"], final_body_html)

                if success: emails_sent_count += 1
                else: emails_failed_count += 1

            except Exception as inner_e:
                 print(f"Error processing recipient {recipient['email']} for campaign {campaign_id}: {inner_e}")
                 emails_failed_count += 1

        print(f"Current tracking map size: {len(tracking_token_map)}")
        return jsonify({
            "message": f"Campaign email processing complete. Sent: {emails_sent_count}, Failed: {emails_failed_count}"
        }), 200

    except Error as e:
        print(f"Error sending campaign emails: {e}")
        return jsonify({"error": f"Failed to send campaign emails: {e}"}), 500
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()


if __name__ == '__main__':
    # Debug mode enabled for development, use_reloader=False if using APScheduler
    app.run(debug=True, host='0.0.0.0', port=5000)