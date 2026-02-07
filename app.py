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
from bakong_khqr import KHQR  # Required

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# ==========================================
# 1. CREDENTIALS (UPDATE TOKEN!)
# ==========================================
# ⚠️ PASTE NEW TOKEN HERE. If expired, QR generation will CRASH.
BAKONG_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJkYXRhIjp7ImlkIjoiNGZiMDQwYzA3MWZhNGEwNiJ9LCJpYXQiOjE3NzA0ODM2NTYsImV4cCI6MTc3ODI1OTY1Nn0.5smV48QjYaLTDwzbjbNKBxAK5s615LvZG91nWbA7ZwY"

MY_BANK_ACCOUNT = "bora_roeun3@aclb" 
MERCHANT_NAME = "Irra Esign"
MERCHANT_CITY = "Phnom Penh"

RESEND_API_KEY = "re_M8VwiPH6_CYEbbqfg6nG737BEqR9nNWD5"
resend.api_key = RESEND_API_KEY
ADMIN_PASSWORD = "Irra@4455$" 
TELE_TOKEN = "8379666289:AAEiYiFzSf4rkkP6g_u_13vbrv0ILi9eh4o"
TELE_CHAT_ID = "5007619095"

MONGO_URI = "mongodb+srv://Esign:Kboy%40%404455@cluster0.4havjl6.mongodb.net/?appName=Cluster0"
client = MongoClient(MONGO_URI)
db = client['irra_esign_db']
orders_col = db['orders']

# Initialize Bakong Library
khqr = KHQR(BAKONG_TOKEN)

# ==========================================
# 2. HELPER FUNCTIONS
# ==========================================
def get_khmer_time():
    khmer_tz = timezone(timedelta(hours=7))
    return datetime.now(khmer_tz).strftime("%d-%b-%Y %I:%M %p")

def send_telegram_alert(message):
    try:
        requests.post(f"https://api.telegram.org/bot{TELE_TOKEN}/sendMessage", 
                     json={"chat_id": TELE_CHAT_ID, "text": message, "parse_mode": "HTML"}, timeout=5)
    except: pass

# ==========================================
# 3. ROUTES
# ==========================================
@app.route('/')
def home():
    return jsonify({"status": "Online", "mode": "Bakong Library Active"})

@app.route('/api/create-payment', methods=['POST'])
def create_payment_qr():
    try:
        data = request.json
        udid = data.get('udid', 'N/A')
        email = data.get('email', 'N/A')
        
        # 🟢 PRICE SET TO $1.00
        price_amount = 1.00
        
        order_id = str(uuid.uuid4())[:8].upper()
        bill_no = f"TRX{int(time.time())}"[-15:]
        
        # 1. ONLINE GENERATION (Uses Bakong API)
        # If Token is invalid, this line will error out
        try:
            qr_string = khqr.create_qr(
                bank_account=MY_BANK_ACCOUNT,
                merchant_name=MERCHANT_NAME,
                merchant_city=MERCHANT_CITY,
                amount=price_amount,
                currency='USD',
                store_label='Esign Store',
                bill_number=bill_no,
                terminal_label='POS-WEB',
                static=False
            )
        except Exception as bakong_err:
            print(f"❌ BAKONG GEN FAILED: {str(bakong_err)}")
            return jsonify({"success": False, "error": "Bakong Token Expired or Connection Failed"}), 500
        
        # 2. Generate MD5
        md5_hash = khqr.generate_md5(qr_string)
        
        # 3. Create Image
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(qr_string)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

        # 4. Save to DB
        orders_col.insert_one({
            "order_id": order_id,
            "email": email,
            "udid": udid,
            "price": f"{price_amount:.2f}",
            "status": "pending_payment",
            "md5": md5_hash,
            "timestamp": get_khmer_time()
        })

        return jsonify({"success": True, "order_id": order_id, "md5": md5_hash, "qr_image": img_base64})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/check-payment/<md5>', methods=['GET'])
def check_payment_status(md5):
    try:
        order = orders_col.find_one({"md5": md5})
        if not order: return jsonify({"status": "NOT_FOUND"})
        if order.get('status') == 'paid': return jsonify({"status": "PAID"})

        try:
            # Check with Bakong
            response = khqr.check_bulk_payments([md5])
            print(f"Checking {md5} -> Bakong: {response}")

            if response and md5 in response:
                orders_col.update_one({"md5": md5}, {"$set": {"status": "paid"}})
                send_telegram_alert(f"✅ <b>PAID $1.00</b>\n🆔 {order['order_id']}\n📧 {order['email']}")
                return jsonify({"status": "PAID"})
            
            return jsonify({"status": "UNPAID"})

        except Exception as api_err:
            print(f"❌ BAKONG CHECK ERROR: {str(api_err)}")
            return jsonify({"status": "UNPAID", "error": "API Error"})

    except Exception as e:
        return jsonify({"status": "ERROR", "msg": str(e)}), 500

# ==========================================
# ADMIN ROUTES
# ==========================================
@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    if request.json.get('password') == ADMIN_PASSWORD: return jsonify({"success": True})
    return jsonify({"success": False}), 401

@app.route('/api/orders', methods=['GET'])
def get_orders():
    if request.headers.get('x-admin-password') != ADMIN_PASSWORD: return jsonify({"error": "Unauthorized"}), 401
    orders = list(orders_col.find().sort("_id", -1))
    for o in orders: o['_id'] = str(o['_id'])
    return jsonify(orders)

@app.route('/api/send-email', methods=['POST'])
def api_send_email():
    if request.headers.get('x-admin-password') != ADMIN_PASSWORD: return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    try:
        order = orders_col.find_one({"order_id": data.get('order_id')})
        if order:
            resend.Emails.send({
                "from": "Irra Store <admin@irra.store>",
                "to": [order['email']],
                "subject": "Order Completed",
                "html": f"<p>Download: <a href='{data.get('link')}'>Click Here</a></p>"
            })
            orders_col.update_one({"order_id": data.get('order_id')}, {"$set": {"status": "completed", "download_link": data.get('link')}})
            return jsonify({"success": True})
    except Exception as e: return jsonify({"success": False, "msg": str(e)}), 500
    return jsonify({"success": False}), 404

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
