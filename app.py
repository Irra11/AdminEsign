import os
import uuid
import requests
import resend  # ត្រូវដំឡើង: pip install resend
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
from pymongo import MongoClient
from datetime import datetime, timedelta, timezone
from bson import ObjectId

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# --- ១. ការកំណត់ LOGO, API KEY, PASSWORD និង TELEGRAM ---
SHOP_LOGO_URL = "https://i.pinimg.com/736x/93/1a/b7/931ab7b0393dab7b07fedb2b22b70a89.jpg"
RESEND_API_KEY = "re_M8VwiPH6_CYEbbqfg6nG737BEqR9nNWD5"
resend.api_key = RESEND_API_KEY
ADMIN_PASSWORD = "Irra@4455$" 

# ព័ត៌មាន Telegram Bot
TELE_TOKEN = "8379666289:AAEiYiFzSf4rkkP6g_u_13vbrv0ILi9eh4o"
TELE_CHAT_ID = "5007619095"

# --- ២. DATABASE SETUP ---
MONGO_URI = "mongodb+srv://Esign:Kboy%40%404455@cluster0.4havjl6.mongodb.net/?appName=Cluster0"
client = MongoClient(MONGO_URI)
db = client['irra_esign_db']
orders_col = db['orders']

# --- ៣. FOLDER SETUP ---
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- មុខងារជំនួយ (Helpers) ---
def get_khmer_time():
    khmer_tz = timezone(timedelta(hours=7))
    return datetime.now(khmer_tz).strftime("%d-%b-%Y %I:%M %p")

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{TELE_TOKEN}/sendMessage"
    payload = {"chat_id": TELE_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram Alert Error: {e}")

@app.route('/')
def status():
    return jsonify({"status": "Backend Live", "time": get_khmer_time()})

@app.route('/uploads/<filename>')
def serve_receipt(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --- ៤. មុខងារបញ្ជាទិញ (Customer Side) ---
@app.route('/verify-payment', methods=['POST'])
def verify_payment():
    try:
        email = request.form.get('email')
        udid = request.form.get('udid')
        price = request.form.get('price', '10')
        plan = request.form.get('plan', 'Standard')
        file = request.files.get('receipt')
        
        order_id = str(uuid.uuid4())[:8].upper()
        filename = secure_filename(f"{order_id}_{file.filename}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        order_data = {
            "order_id": order_id, 
            "email": email, 
            "udid": udid,
            "price": price,
            "plan": plan,
            "status": "pending", 
            "download_link": None, 
            "receipt_url": f"/uploads/{filename}",
            "timestamp": get_khmer_time()
        }
        orders_col.insert_one(order_data)

        receipt_link = f"{request.host_url.replace('http://', 'https://')}uploads/{filename}"
        alert_msg = (
            f"🔔 <b>NEW ORDER</b>\n"
            f"🆔 ID: <code>{order_id}</code>\n"
            f"📧 {email}\n"
            f"📱 UDID: <code>{udid}</code>\n"
            f"🖼️ <a href='{receipt_link}'>View Receipt</a>"
        )
        send_telegram_alert(alert_msg)
        return jsonify({"success": True, "order_id": order_id})
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)}), 500

# --- ៥. មុខងារ Admin ---
@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.json
    if data and data.get('password') == ADMIN_PASSWORD:
        return jsonify({"success": True}), 200
    return jsonify({"success": False}), 401

@app.route('/api/orders', methods=['GET'])
def get_orders():
    if request.headers.get('x-admin-password') != ADMIN_PASSWORD:
        return jsonify({"error": "Unauthorized"}), 401
    all_orders = list(orders_col.find().sort("_id", -1))
    for o in all_orders: o['_id'] = str(o['_id'])
    return jsonify(all_orders)

@app.route('/api/update-order', methods=['POST'])
def update_order():
    if request.headers.get('x-admin-password') != ADMIN_PASSWORD:
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.json
    oid = data.get('order_id')
    new_email = data.get('email')
    new_link = data.get('link') # ទទួលយក link ជំនួស udid
    
    orders_col.update_one(
        {"order_id": oid}, 
        {"$set": {"email": new_email, "download_link": new_link}}
    )
    return jsonify({"success": True})

# --- ៦. មុខងារផ្ញើ Email ជាមួយ Template ថ្មី ---
@app.route('/api/send-email', methods=['POST'])
def api_send_email():
    # ១. ឆែកការអនុញ្ញាត (Security Check)
    if request.headers.get('x-admin-password') != ADMIN_PASSWORD:
        return jsonify({"error": "Unauthorized"}), 401

    # ២. ទទួលទិន្នន័យពី Frontend
    data = request.json
    oid = data.get('order_id')
    download_link = data.get('link')
    is_failed = data.get('type') == 'failed' # ឆែកមើលថាជាករណី "បរាជ័យ" ឬទេ

    # ៣. ស្វែងរកទិន្នន័យក្នុង MongoDB
    order = orders_col.find_one({"order_id": oid})
    if not order: 
        return jsonify({"success": False, "msg": "Order not found"}), 404

    # ៤. រៀបចំទិន្នន័យសម្រាប់បង្ហាញក្នុង Email
    price = order.get('price', '10.00')
    plan = order.get('plan', 'Standard Package')
    udid = order.get('udid', 'N/A')
    email_user = order.get('email', 'Valued Customer')
    user_name = email_user.split('@')[0] # យកឈ្មោះមុខ @ មកហៅឱ្យស្និទ្ធស្នាល

    # ៥. កំណត់ស្ទីលតាមស្ថានភាព (ជោគជ័យ ឬ បរាជ័យ)
    if is_failed:
        theme_color = "#e74c3c" # ពណ៌ក្រហម
        subject_text = "Order Rejected - Payment Verification Failed"
        status_title = "Order Failed"
        status_desc = "Payment Issue Detected"
        main_message = "We regret to inform you that your order could not be processed because your payment verification was unsuccessful."
        button_text = "Contact Support on Telegram"
        action_url = "https://t.me/irra_11" # លីងទៅតេឡេក្រាមអ្នក
    else:
        theme_color = "#27ae60" # ពណ៌បៃតង
        subject_text = "Order Completed - Device Registration Enabled"
        status_title = "Order Completed"
        status_desc = "Device Registration Enabled"
        main_message = "We are pleased to inform you that your order has been successfully completed and your device registration has been enabled."
        button_text = "Download Certificate"
        action_url = download_link

    # ៦. រៀបចំ HTML Template
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <link href="https://fonts.googleapis.com/css2?family=Hanuman:wght@400;700&family=Inter:wght@400;600&display=swap" rel="stylesheet">
    </head>
    <body style="margin: 0; padding: 0; background-color: #f4f7f6; font-family: 'Inter', sans-serif; color: #333;">
        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="padding: 30px 0;">
            <tr>
                <td align="center">
                    <table width="100%" style="max-width: 600px; background-color: #ffffff; border-radius: 20px; overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.05); border-spacing: 0;">
                        <!-- Header Section -->
                        <tr>
                            <td align="center" style="background-color: {theme_color}; padding: 40px 20px;">
                                <div style="display: inline-block; padding: 5px; background: rgba(255,255,255,0.2); border-radius: 50%; margin-bottom: 15px;">
                                    <img src="{SHOP_LOGO_URL}" width="70" height="70" style="display: block; border-radius: 50%; border: 3px solid #ffffff;">
                                </div>
                                <h2 style="margin: 0; color: #ffffff; font-size: 20px; letter-spacing: 0.5px;">{status_title}</h2>
                                <p style="margin: 5px 0 0 0; color: #ffffff; opacity: 0.9; font-size: 13px;">{status_desc}</p>
                            </td>
                        </tr>
                        
                        <!-- Content Section -->
                        <tr>
                            <td style="padding: 40px 30px;">
                                <h3 style="margin: 0 0 15px 0; color: #2c3e50;">Dear {user_name},</h3>
                                <p style="font-size: 15px; line-height: 1.6; color: #555;">{main_message}</p>
                                
                                <table width="100%" style="margin-top: 25px; border-collapse: collapse; font-size: 14px;">
                                    <tr><td colspan="2" style="padding: 10px 0; border-bottom: 2px solid #f4f7f6; font-weight: bold; color: {theme_color}; text-transform: uppercase;">Transaction Details</td></tr>
                                    <tr><td style="padding: 12px 0; color: #777;">Payment Amount:</td><td align="right" style="font-weight: 600;">${price}</td></tr>
                                    <tr><td style="padding: 12px 0; color: #777;">Method:</td><td align="right" style="font-weight: 600;">ABA KHQR (Verified)</td></tr>
                                    
                                    <tr><td colspan="2" style="padding: 25px 0 10px 0; border-bottom: 2px solid #f4f7f6; font-weight: bold; color: {theme_color}; text-transform: uppercase;">Order Information</td></tr>
                                    <tr><td style="padding: 12px 0; color: #777;">Order ID:</td><td align="right" style="font-weight: 600;">#{oid}</td></tr>
                                    <tr><td style="padding: 12px 0; color: #777;">Package:</td><td align="right" style="font-weight: 600;">{plan}</td></tr>
                                    <tr><td style="padding: 12px 0; color: #777;">Device UDID:</td><td align="right" style="font-size: 11px; font-family: monospace; background: #f8f9fa; padding: 4px 8px; border-radius: 4px;">{udid}</td></tr>
                                    <tr style="background-color: #f9f9f9;"><td style="padding: 15px 10px; font-weight: bold; font-size: 16px;">Total:</td><td align="right" style="padding: 15px 10px; font-weight: 800; font-size: 20px; color: #2c3e50;">${price}</td></tr>
                                </table>

                                <!-- Button Action -->
                                <div style="text-align: center; margin-top: 40px;">
                                    <a href="{action_url}" style="background-color: {theme_color}; color: #ffffff; padding: 18px 35px; text-decoration: none; border-radius: 12px; font-weight: bold; font-size: 16px; box-shadow: 0 5px 15px rgba(0,0,0,0.1);">{button_text}</a>
                                </div>

                                <div style="margin-top: 50px; padding-top: 25px; border-top: 1px solid #eeeeee; text-align: center;">
                                    <p style="margin: 0; font-size: 13px; color: #999;">
                                        Support: <a href="https://t.me/irra_11" style="color: {theme_color}; text-decoration: none; font-weight: bold;">Contact via Telegram</a><br><br>
                                        <i>This is an automated message, please do not reply.</i>
                                    </p>
                                </div>
                            </td>
                        </tr>
                        
                        <!-- Footer Section -->
                        <tr>
                            <td align="center" style="background-color: #f9f9f9; padding: 20px; color: #aaa; font-size: 11px;">
                                © 2026 Irra Esign. All rights reserved.
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

    # ៧. ផ្ញើតាមរយៈ Resend
    try:
        resend.Emails.send({
            "from": "Irra Store <admin@irra.store>",
            "to": [order['email']],
            "subject": subject_text,
            "html": html_body
        })
        
        # ៨. Update ស្ថានភាពក្នុង Database
        new_status = "failed" if is_failed else "completed"
        orders_col.update_one({"order_id": oid}, {"$set": {"download_link": download_link if not is_failed else None, "status": new_status}})
        
        # ៩. Telegram Success Alert
        status_emoji = "❌" if is_failed else "✅"
        send_telegram_alert(f"{status_emoji} <b>EMAIL SENT ({new_status.upper()})</b>\nID: {oid}\nTo: {order['email']}")
        
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)}), 500

@app.route('/api/delete-order/<order_id>', methods=['DELETE'])
def delete_order(order_id):
    if request.headers.get('x-admin-password') != ADMIN_PASSWORD:
        return jsonify({"error": "Unauthorized"}), 401
    orders_col.delete_one({"order_id": order_id})
    return jsonify({"success": True})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)



