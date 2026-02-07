import os
import uuid
import requests
import resend
import io
import base64
import time
import qrcode
import traceback
import hashlib
from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
from datetime import datetime, timedelta, timezone

# ==========================================
# 1. SAFE IMPORT (Prevents 500 Error if Library is missing)
# ==========================================
try:
    from bakong_khqr import KHQR
    LIBRARY_AVAILABLE = True
except ImportError:
    KHQR = None
    LIBRARY_AVAILABLE = False
    print("⚠️ WARNING: 'bakong_khqr' library not found. Payment checks will be simulated or fail.")

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# ==========================================
# 2. SETTINGS
# ==========================================
# ⚠️ MAKE SURE THIS TOKEN IS NEW ⚠️
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

# ==========================================
# 3. HELPER FUNCTIONS
# ==========================================
def crc16_ccitt(data: bytes):
    crc = 0xFFFF
    for byte in data:
        x = ((crc >> 8) ^ byte) & 0xFF
        x ^= x >> 4
        crc = ((crc << 8) ^ (x << 12) ^ (x << 5) ^ x) & 0xFFFF
    return crc

def generate_khqr_string(bank_acc, name, city, amount, bill_no):
    # Manual KHQR Generation (Works Offline)
    qr = "000201010212"
    bakong_guid = "0006bakong"
    acc_info = f"01{len(bank_acc):02}{bank_acc}"
    tag_29_content = bakong_guid + acc_info
    qr += f"29{len(tag_29_content):02}{tag_29_content}"
    qr += "52045812" + "5303840"
    amt_str = f"{amount:.2f}"
    qr += f"54{len(amt_str):02}{amt_str}"
    qr += "5802KH"
    name = name[:25]
    qr += f"59{len(name):02}{name}"
    city = city[:15]
    qr += f"60{len(city):02}{city}"
    bill_sub = f"01{len(bill_no):02}{bill_no}"
    qr += f"62{len(bill_sub):02}{bill_sub}"
    qr += "6304"
    crc_val = crc16_ccitt(qr.encode('utf-8'))
    return qr + f"{crc_val:04X}"

def get_khmer_time():
    khmer_tz = timezone(timedelta(hours=7))
    return datetime.now(khmer_tz).strftime("%d-%b-%Y %I:%M %p")

def send_telegram_alert(message):
    try:
        url = f"https://api.telegram.org/bot{TELE_TOKEN}/sendMessage"
        payload = {"chat_id": TELE_CHAT_ID, "text": message, "parse_mode": "HTML"}
        requests.post(url, json=payload, timeout=5)
    except:
        pass

# ==========================================
# 4. ROUTES
# ==========================================

@app.route('/')
def home():
    return jsonify({"status": "Online", "library_loaded": LIBRARY_AVAILABLE})

@app.route('/api/create-payment', methods=['POST'])
def create_payment_qr():
    try:
        data = request.json
        udid = data.get('udid', 'N/A')
        email = data.get('email', 'N/A')
        
        order_id = str(uuid.uuid4())[:8].upper()
        bill_no = f"TRX{int(time.time())}"[-15:]
        
        qr_string = generate_khqr_string(MY_BANK_ACCOUNT, MERCHANT_NAME, MERCHANT_CITY, 10.00, bill_no)
        md5_hash = hashlib.md5(qr_string.encode('utf-8')).hexdigest()
        
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(qr_string)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

        orders_col.insert_one({
            "order_id": order_id,
            "email": email,
            "udid": udid,
            "price": "10.00",
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
        # 1. Check Database
        order = orders_col.find_one({"md5": md5})
        if not order: return jsonify({"status": "NOT_FOUND"}), 404
        if order.get('status') == 'paid': return jsonify({"status": "PAID"}), 200

        # 2. Check if Library is available
        if not LIBRARY_AVAILABLE:
            print("❌ Library not found. Cannot check Bakong API.")
            return jsonify({"status": "UNPAID", "error": "Library Missing"}), 200

        # 3. Check Bakong API
        try:
            khqr_chk = KHQR(BAKONG_TOKEN)
            response = khqr_chk.check_bulk_payments([md5])
            
            # LOGS: Print what Bakong says to the console
            print(f"Checking MD5: {md5} | Response: {response}")

            if response and md5 in response:
                orders_col.update_one({"md5": md5}, {"$set": {"status": "paid"}})
                msg = f"✅ <b>PAID</b>\n🆔 {order['order_id']}\n📧 {order['email']}"
                send_telegram_alert(msg)
                return jsonify({"status": "PAID"}), 200
            
            return jsonify({"status": "UNPAID"}), 200

        except Exception as api_err:
            # Catch Bakong Connection Errors so we don't send 500
            print(f"❌ BAKONG API ERROR: {str(api_err)}")
            return jsonify({"status": "UNPAID", "error": "Bakong Conn Error"}), 200

    except Exception as e:
        # Catch unexpected Python errors
        traceback.print_exc() # This prints the big error to the log
        return jsonify({"status": "ERROR", "msg": str(e)}), 500

# ==========================================
# ADMIN ROUTES
# ==========================================
@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    if request.json.get('password') == ADMIN_PASSWORD:
        return jsonify({"success": True})
    return jsonify({"success": False}), 401

@app.route('/api/orders', methods=['GET'])
def get_orders():
    if request.headers.get('x-admin-password') != ADMIN_PASSWORD:
        return jsonify({"error": "Unauthorized"}), 401
    orders = list(orders_col.find().sort("_id", -1))
    for o in orders: o['_id'] = str(o['_id'])
    return jsonify(orders)

@app.route('/api/send-email', methods=['POST'])
def api_send_email():
    if request.headers.get('x-admin-password') != ADMIN_PASSWORD:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    oid = data.get('order_id')
    link = data.get('link')
    order = orders_col.find_one({"order_id": oid})
    if order:
        try:
            resend.Emails.send({
                "from": "Irra Store <admin@irra.store>",
                "to": [order['email']],
                "subject": "Order Completed",
                "html": f"<p>Download: <a href='{link}'>{link}</a></p>"
            })
            orders_col.update_one({"order_id": oid}, {"$set": {"status": "completed", "download_link": link}})
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"success": False, "msg": str(e)}), 500
    return jsonify({"success": False}), 404

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
