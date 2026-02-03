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
MONGO_URI = "mongodb+srv://Esign:Kboy%40%404455@cluster0.4havjl6.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
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
    """មុខងារសម្រាប់ផ្ញើសារទៅកាន់ Telegram"""
    url = f"https://api.telegram.org/bot{TELE_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELE_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
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
        price = request.form.get('price', '10') # យកតម្លៃពី Web
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

        # Telegram Notification (New Order)
        host_url = request.host_url.replace("http://", "https://")
        receipt_link = f"{host_url.rstrip('/')}/uploads/{filename}"
        
        alert_msg = (
            f"🔔 <b>NEW ORDER RECEIVED</b>\n\n"
            f"🆔 ID: <code>{order_id}</code>\n"
            f"📧 Email: {email}\n"
            f"📱 UDID: <code>{udid}</code>\n"
            f"💰 Price: ${price} ({plan})\n"
            f"⏰ Time: {get_khmer_time()}\n\n"
            f"🖼️ <a href='{receipt_link}'>View Receipt Image</a>"
        )
        send_telegram_alert(alert_msg)
        
        return jsonify({"success": True, "order_id": order_id})
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)}), 500

# --- ៥. មុខងារ Admin (Auth & Orders List) ---
@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.json
    if data and data.get('password') == ADMIN_PASSWORD:
        return jsonify({"success": True}), 200
    return jsonify({"success": False}), 401

@app.route('/api/orders', methods=['GET'])
def get_orders():
    client_pass = request.headers.get('x-admin-password')
    if client_pass != ADMIN_PASSWORD:
        return jsonify({"error": "Unauthorized"}), 401
    
    all_orders = list(orders_col.find().sort("_id", -1))
    for o in all_orders: o['_id'] = str(o['_id'])
    return jsonify(all_orders)

# --- ៦. មុខងារផ្ញើ EMAIL ឆ្លើយតប ---
@app.route('/api/send-email', methods=['POST'])
def api_send_email():
    client_pass = request.headers.get('x-admin-password')
    if client_pass != ADMIN_PASSWORD:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    oid = data.get('order_id')
    download_link = data.get('link')
    
    order = orders_col.find_one({"order_id": oid})
    if not order: return jsonify({"success": False, "msg": "Order not found"}), 404

    # HTML Email Template
    html_body = f"""
    <html>
    <head><link href="https://fonts.googleapis.com/css2?family=Hanuman:wght@400;700&display=swap" rel="stylesheet"></head>
    <body style="margin: 0; padding: 0; background-color: #f4f7f6; font-family: 'Arial', sans-serif;">
        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="padding: 30px 0;">
            <tr>
                <td align="center">
                    <table width="100%" style="max-width: 600px; background-color: #ffffff; border-radius: 25px; overflow: hidden; box-shadow: 0 15px 45px rgba(0,0,0,0.1); border-spacing: 0;">
                        <tr>
                            <td align="center" style="background-color: #27ae60; padding: 50px 20px;">
                                <img src="{SHOP_LOGO_URL}" width="85" height="85" style="border-radius: 50%; border: 3px solid #ffffff;">
                                <h1 style="color: #ffffff; font-size: 24px; font-family: 'Hanuman', serif;">ការបញ្ជាទិញជោគជ័យ ✅</h1>
                                <p style="color: #ffffff; opacity: 0.85;">ID: #{oid}</p>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 45px 40px;">
                                <h2 style="font-family: 'Hanuman', serif;">សូមជម្រាបជូនអតិថិជន!</h2>
                                <p style="font-family: 'Hanuman', serif; line-height: 1.8;">វិញ្ញាបនបត្រ iOS (Certificate) របស់អ្នកត្រូវបានបញ្ចប់។ សូមចុចប៊ូតុងខាងក្រោមដើម្បីទាញយក៖</p>
                                <div style="text-align: center; margin-top: 30px;">
                                    <a href="{download_link}" style="background-color: #27ae60; color: #ffffff; padding: 18px 35px; text-decoration: none; border-radius: 12px; font-weight: bold; display: inline-block;">Download Certificate</a>
                                </div>
                                <p style="margin-top: 40px; font-size: 12px; color: #aaa; text-align: center;">This is an automated message. Do not reply.</p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

    try:
        resend.Emails.send({
            "from": "Irra Store <admin@irra.store>",
            "to": [order['email']],
            "subject": f"Your iOS Certificate is Ready! - {oid}",
            "html": html_body
        })
        
        # Update Status ក្នុង Database
        orders_col.update_one({"order_id": oid}, {"$set": {"download_link": download_link, "status": "completed"}})
        
        # Telegram Notification (Order Completed)
        completion_msg = (
            f"✅ <b>ORDER COMPLETED</b>\n\n"
            f"🆔 ID: <code>{oid}</code>\n"
            f"📧 Sent to: {order['email']}\n"
            f"🔗 Link: <a href='{download_link}'>Download Page</a>\n"
            f"📢 Status: Email Sent Successfully"
        )
        send_telegram_alert(completion_msg)
        
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)}), 500

@app.route('/api/delete-order/<order_id>', methods=['DELETE'])
def delete_order(order_id):
    client_pass = request.headers.get('x-admin-password')
    if client_pass != ADMIN_PASSWORD:
        return jsonify({"error": "Unauthorized"}), 401
    orders_col.delete_one({"order_id": order_id})
    return jsonify({"success": True})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

