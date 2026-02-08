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
from datetime import datetime, timedelta, timezone
from bakong_khqr import KHQR

app = Flask(__name__)
# Allow all origins
CORS(app, resources={r"/*": {"origins": "*"}})

# ==========================================
# 1. CREDENTIALS & SETTINGS
# ==========================================
TELE_TOKEN = "8379666289:AAEiYiFzSf4rkkP6g_u_13vbrv0ILi9eh4o"
TELE_CHAT_ID = "5007619095"

RESEND_API_KEY = "re_M8VwiPH6_CYEbbqfg6nG737BEqR9nNWD5"
resend.api_key = RESEND_API_KEY

ADMIN_PASSWORD = "Irra@4455$" 

MONGO_URI = "mongodb+srv://Esign:Kboy%40%404455@cluster0.4havjl6.mongodb.net/?appName=Cluster0"
client = MongoClient(MONGO_URI)
db = client['irra_esign_db']
orders_col = db['orders']

# YOUR REAL BAKONG TOKEN
BAKONG_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJkYXRhIjp7ImlkIjoiNGZiMDQwYzA3MWZhNGEwNiJ9LCJpYXQiOjE3NzA0ODM2NTYsImV4cCI6MTc3ODI1OTY1Nn0.5smV48QjYaLTDwzbjbNKBxAK5s615LvZG91nWbA7ZwY"
MY_BANK_ACCOUNT = "bora_roeun3@aclb"

khqr = KHQR(BAKONG_TOKEN)

# ==========================================
# 2. HELPER FUNCTIONS
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

# ==========================================
# 3. PAYMENT ROUTES
# ==========================================

@app.route('/api/create-payment', methods=['POST'])
def create_payment():
    try:
        data = request.json
        udid = data.get('udid')
        email = data.get('email')
        
        order_id = str(uuid.uuid4())[:8].upper()
        bill_no = f"TRX-{int(time.time())}"
        
        # 1. Create QR ($10.00 USD)
        qr_string = khqr.create_qr(
            bank_account=MY_BANK_ACCOUNT,
            merchant_name='Irra Esign',
            merchant_city='Phnom Penh',
            amount=10.00,
            currency='USD',
            store_label='Esign Store',
            phone_number='85512345678',
            bill_number=bill_no,
            terminal_label='WEB-POS',
            static=False
        )
        
        # 2. Get MD5
        md5_hash = khqr.generate_md5(qr_string)
        
        # 3. QR Image
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(qr_string)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

        # 4. Save to DB (Admin Panel will see this)
        order_data = {
            "order_id": order_id,
            "email": email,
            "udid": udid,
            "price": "10.00",
            "status": "pending_payment",
            "md5": md5_hash,
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
def check_payment(md5):
    try:
        print(f"🔍 Checking: {md5}")
        
        # 1. Check with Bakong
        paid_list = khqr.check_bulk_payments([md5])
        
        # 2. If Paid
        if md5 in paid_list:
            print(f"🎉 PAYMENT SUCCESS: {md5}")
            
            order = orders_col.find_one({"md5": md5})
            
            # Update DB (Admin Panel updates automatically)
            if order and order.get('status') != 'paid':
                orders_col.update_one({"md5": md5}, {"$set": {"status": "paid"}})
                
                # Send Telegram Alert
                msg = (
                    f"✅ <b>PAYMENT SUCCESS (VERIFIED)</b>\n"
                    f"🆔 Order: <code>{order['order_id']}</code>\n"
                    f"📧 Email: {order['email']}\n"
                    f"📱 UDID: <code>{order['udid']}</code>\n"
                    f"💰 Amount: $10.00"
                )
                send_telegram_alert(msg)
                
            return jsonify({"status": "PAID"})
            
        return jsonify({"status": "UNPAID"})

    except Exception as e:
        print(f"❌ Error: {e}")
        return jsonify({"status": "ERROR", "msg": str(e)}), 500

# ==========================================
# 4. ADMIN & EMAIL ROUTES
# ==========================================
@app.route('/')
def status():
    return jsonify({"status": "Backend Live", "time": get_khmer_time()})

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
    udid = order.get('udid', 'N/A')
    email = order.get('email', 'Customer')

    if is_failed:
        subject = "Order Rejected"
        html_body = f"<p>Order #{oid} Failed. Please contact support.</p>"
    else:
        subject = "Order Completed"
        html_body = f"<p>Order #{oid} Success. <br>Download: <a href='{download_link}'>Click Here</a></p>"

    try:
        resend.Emails.send({
            "from": "Irra Store <admin@irra.store>",
            "to": [email],
            "subject": subject,
            "html": html_body
        })
        
        status = "failed" if is_failed else "completed"
        orders_col.update_one({"order_id": oid}, {"$set": {"download_link": download_link, "status": status}})
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
