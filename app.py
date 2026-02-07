import os
import uuid
import requests
import resend
import io
import base64
import time
import qrcode
import traceback
from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError
from datetime import datetime, timedelta, timezone
from bakong_khqr import KHQR

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# ==========================================
# 1. CONFIGURATION & CREDENTIALS
# ==========================================
SHOP_LOGO_URL = "https://i.pinimg.com/736x/93/1a/b7/931ab7b0393dab7b07fedb2b22b70a89.jpg"

# Resend Email Config
RESEND_API_KEY = "re_M8VwiPH6_CYEbbqfg6nG737BEqR9nNWD5"
resend.api_key = RESEND_API_KEY

# Admin Password
ADMIN_PASSWORD = "Irra@4455$" 

# Telegram Config
TELE_TOKEN = "8379666289:AAEiYiFzSf4rkkP6g_u_13vbrv0ILi9eh4o"
TELE_CHAT_ID = "5007619095"

# Bakong KHQR Config
BAKONG_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJkYXRhIjp7ImlkIjoiNGZiMDQwYzA3MWZhNGEwNiJ9LCJpYXQiOjE3NzA0ODM2NTYsImV4cCI6MTc3ODI1OTY1Nn0.5smV48QjYaLTDwzbjbNKBxAK5s615LvZG91nWbA7ZwY"
MY_BANK_ACCOUNT = "bora_roeun3@aclb" 
khqr = KHQR(BAKONG_TOKEN)

# ==========================================
# 2. DATABASE CONNECTION (ROBUST)
# ==========================================
MONGO_URI = "mongodb+srv://Esign:Kboy%40%404455@cluster0.4havjl6.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    client.server_info() # Trigger connection check
    db = client['irra_esign_db']
    orders_col = db['orders']
    print("✅ MongoDB Connected Successfully!")
except Exception as e:
    print("❌ MongoDB Connection Failed:", e)
    db = None
    orders_col = None

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
        print(f"Telegram Error: {e}")

@app.route('/')
def status():
    return jsonify({"status": "Backend Live", "time": get_khmer_time()})

# ==========================================
# 4. PAYMENT ROUTES
# ==========================================

# A. Generate QR Code
@app.route('/api/create-payment', methods=['POST'])
def create_payment():
    try:
        data = request.json
        udid = data.get('udid')
        email = data.get('email')
        
        order_id = str(uuid.uuid4())[:8].upper()
        bill_no = f"TRX-{int(time.time())}"
        
        # Create KHQR
        qr_string = khqr.create_qr(
            bank_account=MY_BANK_ACCOUNT,
            merchant_name='Irra Esign',
            merchant_city='Phnom Penh',
            amount=10.00,       
            currency='USD',     
            store_label='Store1',
            bill_number=bill_no,
            terminal_label='POS-01',
            static=False
        )
        
        # Generate MD5 for polling
        md5_hash = khqr.generate_md5(qr_string)
        
        # Generate Image
        qr_img = qrcode.QRCode(version=1, box_size=10, border=4)
        qr_img.add_data(qr_string)
        qr_img.make(fit=True)
        img = qr_img.make_image(fill_color="black", back_color="white")
        
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

        # Save Initial Order (Pending)
        if orders_col is not None:
            orders_col.insert_one({
                "order_id": order_id,
                "email": email,
                "udid": udid,
                "price": "10.00",
                "status": "pending_scan",
                "md5": md5_hash,
                "timestamp": get_khmer_time()
            })

        return jsonify({
            "success": True,
            "order_id": order_id,
            "md5": md5_hash,
            "qr_image": img_base64
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

# B. Check Status (Auto)
@app.route('/api/check-payment/<md5>', methods=['GET'])
def check_payment(md5):
    try:
        # Check Bakong API
        paid_list = khqr.check_bulk_payments([md5])
        
        if md5 in paid_list:
            order = orders_col.find_one({"md5": md5})
            if order and order.get('status') != 'paid':
                orders_col.update_one({"md5": md5}, {"$set": {"status": "paid"}})
                
                msg = (
                    f"✅ <b>AUTO-PAYMENT RECEIVED</b>\n"
                    f"🆔 Order: <code>{order['order_id']}</code>\n"
                    f"📧 Email: {order['email']}\n"
                    f"💰 Amount: $10.00"
                )
                send_telegram_alert(msg)
            return jsonify({"status": "PAID"})
            
        return jsonify({"status": "UNPAID"})

    except Exception as e:
        return jsonify({"status": "ERROR", "msg": str(e)}), 500

# C. Manual Confirmation (User clicks "I Have Paid")
@app.route('/api/confirm-manual', methods=['POST'])
def confirm_manual():
    try:
        data = request.json
        order_id = data.get('order_id')
        
        if orders_col is not None:
            order = orders_col.find_one({"order_id": order_id})
            if order:
                orders_col.update_one(
                    {"order_id": order_id}, 
                    {"$set": {"status": "verification_pending"}}
                )
                
                # Send Alert to Admin
                msg = (
                    f"⚠️ <b>MANUAL CONFIRMATION</b>\n"
                    f"User clicked 'I Have Paid'. Please check your bank.\n\n"
                    f"🆔 Order: <code>{order['order_id']}</code>\n"
                    f"📧 Email: {order['email']}\n"
                    f"📱 UDID: <code>{order['udid']}</code>\n"
                    f"💰 Price: $10.00"
                )
                send_telegram_alert(msg)
                return jsonify({"success": True})
        
        return jsonify({"success": False, "msg": "Order not found"})
        
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)}), 500

# ==========================================
# 5. ADMIN & EMAIL ROUTES
# ==========================================
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
    if orders_col is None: return jsonify([])
    
    all_orders = list(orders_col.find().sort("_id", -1))
    for o in all_orders: o['_id'] = str(o['_id'])
    return jsonify(all_orders)

@app.route('/api/update-order', methods=['POST'])
def update_order():
    if request.headers.get('x-admin-password') != ADMIN_PASSWORD:
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.json
    orders_col.update_one(
        {"order_id": data.get('order_id')}, 
        {"$set": {"email": data.get('email'), "download_link": data.get('link')}}
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
    if not order: return jsonify({"success": False, "msg": "Order not found"}), 404

    # Email Logic
    price = order.get('price', '10.00')
    udid = order.get('udid', 'N/A')
    user_name = order.get('email').split('@')[0]

    if is_failed:
        theme_color = "#e74c3c"
        subject_text = "Order Rejected"
        status_title = "Payment Failed"
        status_desc = "Verification Failed"
        main_message = "Your payment could not be verified."
        button_text = "Contact Admin"
        action_url = "https://t.me/irra_11"
    else:
        theme_color = "#27ae60"
        subject_text = "Order Completed"
        status_title = "Order Completed"
        status_desc = "Device Registered"
        main_message = "Your order is complete. Download your certificate below."
        button_text = "Download Certificate"
        action_url = download_link

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <body style="background-color:#f4f7f6;font-family:sans-serif;padding:20px;">
        <div style="max-width:600px;margin:0 auto;background:#fff;border-radius:10px;overflow:hidden;">
            <div style="background:{theme_color};padding:30px;text-align:center;color:#fff;">
                <h2>{status_title}</h2>
                <p>{status_desc}</p>
            </div>
            <div style="padding:30px;">
                <p>Dear {user_name},</p>
                <p>{main_message}</p>
                <div style="background:#f8f9fa;padding:15px;border-radius:5px;margin:20px 0;">
                    <b>UDID:</b> {udid}<br>
                    <b>Total:</b> ${price}
                </div>
                <center><a href="{action_url}" style="background:{theme_color};color:#fff;padding:15px 30px;text-decoration:none;border-radius:5px;display:inline-block;">{button_text}</a></center>
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
        orders_col.update_one({"order_id": oid}, {"$set": {"download_link": download_link, "status": new_status}})
        send_telegram_alert(f"✅ EMAIL SENT ({new_status}) to {order['email']}")
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
