import os
import uuid
import requests
import resend
import io
import base64
import time
import qrcode
import traceback
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
from pymongo import MongoClient
from datetime import datetime, timedelta, timezone
from bakong_khqr import KHQR  # Import Bakong Library

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# ==========================================
# 1. SETTINGS & CREDENTIALS
# ==========================================
SHOP_LOGO_URL = "https://i.pinimg.com/736x/93/1a/b7/931ab7b0393dab7b07fedb2b22b70a89.jpg"
RESEND_API_KEY = "re_M8VwiPH6_CYEbbqfg6nG737BEqR9nNWD5"
resend.api_key = RESEND_API_KEY
ADMIN_PASSWORD = "Irra@4455$" 

# Telegram
TELE_TOKEN = "8379666289:AAEiYiFzSf4rkkP6g_u_13vbrv0ILi9eh4o"
TELE_CHAT_ID = "5007619095"

# Database
MONGO_URI = "mongodb+srv://Esign:Kboy%40%404455@cluster0.4havjl6.mongodb.net/?appName=Cluster0"
client = MongoClient(MONGO_URI)
db = client['irra_esign_db']
orders_col = db['orders']

# Folder
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ==========================================
# 2. BAKONG KHQR CONFIGURATION
# ==========================================
# Using the token you provided
BAKONG_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJkYXRhIjp7ImlkIjoiNGZiMDQwYzA3MWZhNGEwNiJ9LCJpYXQiOjE3NzA0ODM2NTYsImV4cCI6MTc3ODI1OTY1Nn0.5smV48QjYaLTDwzbjbNKBxAK5s615LvZG91nWbA7ZwY"
MY_BANK_ACCOUNT = "bora_roeun3@aclb" 

khqr = KHQR(BAKONG_TOKEN)

# ==========================================
# 3. HELPER FUNCTIONS
# ==========================================
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

# ==========================================
# 4. BAKONG PAYMENT ROUTES (NEW)
# ==========================================

@app.route('/api/create-payment', methods=['POST'])
def create_payment_qr():
    try:
        data = request.json
        udid = data.get('udid')
        email = data.get('email')
        
        # Create a unique bill number
        order_id = str(uuid.uuid4())[:8].upper()
        bill_no = f"TRX-{int(time.time())}"
        
        # 1. Generate KHQR String (10.00 USD)
        qr_string = khqr.create_qr(
            bank_account=MY_BANK_ACCOUNT,
            merchant_name='Irra Esign',
            merchant_city='Phnom Penh',
            amount=10.00,       # Set Amount $10
            currency='USD',     # Set Currency USD
            store_label='Esign Store',
            phone_number='85512345678', # Optional: Change to real phone if needed
            bill_number=bill_no,
            terminal_label='POS-WEB',
            static=False
        )
        
        # 2. Generate MD5 for tracking
        md5_hash = khqr.generate_md5(qr_string)
        
        # 3. Create QR Image (Base64)
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(qr_string)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

        # 4. Save "Pending" Order to MongoDB
        order_data = {
            "order_id": order_id,
            "email": email,
            "udid": udid,
            "price": "10.00",
            "plan": "Standard",
            "status": "pending_payment", # Waiting for payment
            "md5": md5_hash,             # Important for checking status
            "timestamp": get_khmer_time()
        }
        orders_col.insert_one(order_data)

        return jsonify({
            "success": True,
            "order_id": order_id,
            "md5": md5_hash,
            "qr_image": img_base64
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/check-payment/<md5>', methods=['GET'])
def check_payment_status(md5):
    try:
        # Check Bakong API
        paid_list = khqr.check_bulk_payments([md5])
        
        if md5 in paid_list:
            # 1. Update Database
            order = orders_col.find_one({"md5": md5})
            
            if order and order.get('status') != 'paid':
                orders_col.update_one({"md5": md5}, {"$set": {"status": "paid"}})
                
                # 2. Send Telegram Alert
                msg = (
                    f"✅ <b>PAYMENT RECEIVED (KHQR)</b>\n"
                    f"🆔 Order: <code>{order['order_id']}</code>\n"
                    f"📧 Email: {order['email']}\n"
                    f"📱 UDID: <code>{order['udid']}</code>\n"
                    f"💰 Amount: $10.00"
                )
                send_telegram_alert(msg)
                
            return jsonify({"status": "PAID"})
            
        return jsonify({"status": "UNPAID"})

    except Exception as e:
        return jsonify({"status": "ERROR", "msg": str(e)}), 500

# ==========================================
# 5. ADMIN & EMAIL ROUTES (EXISTING)
# ==========================================

@app.route('/')
def status():
    return jsonify({"status": "Backend Live with KHQR", "time": get_khmer_time()})

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
    new_link = data.get('link')
    
    orders_col.update_one(
        {"order_id": oid}, 
        {"$set": {"email": new_email, "download_link": new_link}}
    )
    return jsonify({"success": True})

@app.route('/api/delete-order/<order_id>', methods=['DELETE'])
def delete_order(order_id):
    if request.headers.get('x-admin-password') != ADMIN_PASSWORD:
        return jsonify({"error": "Unauthorized"}), 401
    orders_col.delete_one({"order_id": order_id})
    return jsonify({"success": True})

@app.route('/api/send-email', methods=['POST'])
def api_send_email():
    if request.headers.get('x-admin-password') != ADMIN_PASSWORD:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    oid = data.get('order_id')
    download_link = data.get('link')
    is_failed = data.get('type') == 'failed'

    order = orders_col.find_one({"order_id": oid})
    if not order: 
        return jsonify({"success": False, "msg": "Order not found"}), 404

    price = order.get('price', '10.00')
    plan = order.get('plan', 'Standard Package')
    udid = order.get('udid', 'N/A')
    email_user = order.get('email', 'Customer')
    user_name = email_user.split('@')[0]

    if is_failed:
        theme_color = "#e74c3c"
        subject_text = "Order Rejected - Payment Verification Failed"
        status_title = "Order Failed"
        status_desc = "Payment Issue Detected"
        main_message = "We regret to inform you that your order could not be processed."
        button_text = "Contact Support"
        action_url = "https://t.me/irra_11"
    else:
        theme_color = "#27ae60"
        subject_text = "Order Completed - Device Registration Enabled"
        status_title = "Order Completed"
        status_desc = "Device Registration Enabled"
        main_message = "Your order has been successfully completed."
        button_text = "Download Certificate"
        action_url = download_link

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head><style>body{{font-family:sans-serif;}}</style></head>
    <body style="background:#f4f7f6;padding:20px;">
        <div style="max-width:600px;margin:0 auto;background:#fff;border-radius:10px;overflow:hidden;">
            <div style="background:{theme_color};padding:30px;text-align:center;color:#fff;">
                <h2>{status_title}</h2>
                <p>{status_desc}</p>
            </div>
            <div style="padding:30px;">
                <p>Dear {user_name},</p>
                <p>{main_message}</p>
                <table width="100%" style="margin:20px 0;border-collapse:collapse;">
                    <tr><td>Order ID:</td><td><b>#{oid}</b></td></tr>
                    <tr><td>UDID:</td><td><code style="background:#eee;padding:3px;">{udid}</code></td></tr>
                    <tr><td>Amount:</td><td><b>${price}</b></td></tr>
                </table>
                <center><a href="{action_url}" style="background:{theme_color};color:#fff;padding:12px 25px;text-decoration:none;border-radius:5px;">{button_text}</a></center>
            </div>
        </div>
    </body>
    </html>
    """

    try:
        resend.Emails.send({
            "from": "Irra Store <admin@irra.store>",
            "to": [order['email']],
            "subject": subject_text,
            "html": html_body
        })
        
        new_status = "failed" if is_failed else "completed"
        orders_col.update_one({"order_id": oid}, {"$set": {"download_link": download_link if not is_failed else None, "status": new_status}})
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
