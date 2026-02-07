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
CORS(app, resources={r"/*": {"origins": "*"}})

# ==========================================
# 1. SETTINGS & CREDENTIALS
# ==========================================
# Bakong Config (From your snippet)
BAKONG_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJkYXRhIjp7ImlkIjoiNGZiMDQwYzA3MWZhNGEwNiJ9LCJpYXQiOjE3NzA0ODM2NTYsImV4cCI6MTc3ODI1OTY1Nn0.5smV48QjYaLTDwzbjbNKBxAK5s615LvZG91nWbA7ZwY"
MY_BANK_ACCOUNT = "bora_roeun3@aclb" 

# Initialize KHQR
khqr = KHQR(BAKONG_TOKEN)

# Email & Admin Config
RESEND_API_KEY = "re_M8VwiPH6_CYEbbqfg6nG737BEqR9nNWD5"
resend.api_key = RESEND_API_KEY
ADMIN_PASSWORD = "Irra@4455$" 

# Telegram Config
TELE_TOKEN = "8379666289:AAEiYiFzSf4rkkP6g_u_13vbrv0ILi9eh4o"
TELE_CHAT_ID = "5007619095"

# Database Config
MONGO_URI = "mongodb+srv://Esign:Kboy%40%404455@cluster0.4havjl6.mongodb.net/?appName=Cluster0"
client = MongoClient(MONGO_URI)
db = client['irra_esign_db']
orders_col = db['orders']

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
        print(f"Telegram Alert Error: {e}")

# ==========================================
# 3. PAYMENT ROUTES (Integrated)
# ==========================================

@app.route('/api/create-payment', methods=['POST'])
def create_payment():
    try:
        data = request.json
        udid = data.get('udid')
        email = data.get('email')
        
        # 1. Generate Bill Number & Order ID
        order_id = str(uuid.uuid4())[:8].upper()
        bill_no = f"TRX-{int(time.time())}"
        
        # 2. Create KHQR String (Using your Logic)
        # Note: Changing to USD and 10.00 to match your product price
        qr_string = khqr.create_qr(
            bank_account=MY_BANK_ACCOUNT,
            merchant_name='Irra Esign',
            merchant_city='Phnom Penh',
            amount=10.00,       
            currency='USD',     
            store_label='Store1',
            phone_number='85512345678',
            bill_number=bill_no,
            terminal_label='POS-01',
            static=False
        )
        
        # 3. Generate MD5 for checking status
        md5_hash = khqr.generate_md5(qr_string)
        
        # 4. Generate QR Image
        qr_img = qrcode.QRCode(version=1, box_size=10, border=4)
        qr_img.add_data(qr_string)
        qr_img.make(fit=True)
        img = qr_img.make_image(fill_color="black", back_color="white")
        
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

        # 5. Save to MongoDB
        order_data = {
            "order_id": order_id,
            "email": email,
            "udid": udid,
            "price": "10.00",
            "md5": md5_hash,
            "bill_no": bill_no,
            "status": "pending_payment",
            "timestamp": get_khmer_time()
        }
        orders_col.insert_one(order_data)

        print(f"✅ Created QR. Order: {order_id} | MD5: {md5_hash}")

        return jsonify({
            "success": True,
            "order_id": order_id,
            "qr_image": img_base64,
            "md5": md5_hash
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/check-payment/<md5>', methods=['GET'])
def check_payment(md5):
    try:
        print(f"🔍 Checking: {md5}")

        # 1. Check Status via Bakong API
        paid_list = khqr.check_bulk_payments([md5])
        
        if md5 in paid_list:
            print(f"🎉 PAYMENT SUCCESS: {md5}")
            
            # 2. Update Database
            order = orders_col.find_one({"md5": md5})
            
            if order and order.get('status') != 'paid':
                orders_col.update_one({"md5": md5}, {"$set": {"status": "paid"}})
                
                # 3. Send Telegram Alert
                msg = (
                    f"✅ <b>PAYMENT RECEIVED</b>\n"
                    f"🆔 Order: <code>{order['order_id']}</code>\n"
                    f"📧 Email: {order['email']}\n"
                    f"📱 UDID: <code>{order['udid']}</code>\n"
                    f"💰 Amount: $10.00"
                )
                send_telegram_alert(msg)
                
            return jsonify({"status": "PAID"})
        
        else:
            return jsonify({"status": "UNPAID"})

    except Exception as e:
        print(f"❌ API Error: {str(e)}")
        return jsonify({"status": "ERROR", "msg": str(e)}), 500

# ==========================================
# 4. ADMIN & EMAIL ROUTES (Existing)
# ==========================================

@app.route('/')
def status():
    return jsonify({"status": "Server Running", "time": get_khmer_time()})

@app.route('/api/send-email', methods=['POST'])
def api_send_email():
    if request.headers.get('x-admin-password') != ADMIN_PASSWORD:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    oid = data.get('order_id')
    download_link = data.get('link')
    
    order = orders_col.find_one({"order_id": oid})
    if not order: return jsonify({"success": False, "msg": "Order not found"}), 404

    try:
        html_body = f"""
        <h1>Order Completed</h1>
        <p>Your certificate is ready.</p>
        <p><b>UDID:</b> {order['udid']}</p>
        <a href="{download_link}">Download Here</a>
        """
        resend.Emails.send({
            "from": "Irra Store <admin@irra.store>",
            "to": [order['email']],
            "subject": "Your iOS Certificate",
            "html": html_body
        })
        
        orders_col.update_one({"order_id": oid}, {"$set": {"status": "completed", "download_link": download_link}})
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
