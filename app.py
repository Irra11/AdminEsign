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
import struct
from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
from datetime import datetime, timedelta, timezone

# Only use Bakong library for checking status, not generating (to avoid connection errors)
from bakong_khqr import KHQR 

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# ==========================================
# 1. SETTINGS & CREDENTIALS
# ==========================================
# Replace this with a FRESH Token if the current one is expired
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

khqr = KHQR(BAKONG_TOKEN)

# ==========================================
# 2. KHQR OFFLINE GENERATOR (NO INTERNET NEEDED)
# ==========================================
def crc16(data: bytes):
    crc = 0xFFFF
    for byte in data:
        x = ((crc >> 8) ^ byte) & 0xFF
        x ^= x >> 4
        crc = ((crc << 8) ^ (x << 12) ^ (x << 5) ^ x) & 0xFFFF
    return crc

def generate_khqr_offline(bank_account, amount, merchant_name, merchant_city, bill_number):
    # This manually builds the KHQR string so it never fails due to connection errors
    # Tag 29: Merchant Account Information (Bakong GUID + Account ID)
    # Bakong GUID: 0006bakong 0110<bakong_account_id>
    
    # 1. Build Merchant Account Info
    # Bakong global unique identifier
    bakong_guid = "0006bakong" 
    # Account ID Tag
    acc_tag = f"01{len(bank_account):02}{bank_account}"
    root_tag_29_content = bakong_guid + acc_tag
    tag_29 = f"29{len(root_tag_29_content):02}{root_tag_29_content}"

    # 2. Build Other Tags
    tag_00 = "000201" # Payload Format Indicator
    tag_01 = "010212" # Point of Initiation (12 = Dynamic)
    tag_52 = "52045812" # Merchant Category Code (General)
    tag_53 = "5303840"  # Currency (840 = USD)
    
    # Amount
    amt_str = f"{amount:.2f}"
    tag_54 = f"54{len(amt_str):02}{amt_str}"
    
    tag_58 = f"5802KH" # Country Code
    
    name_limit = merchant_name[:25]
    tag_59 = f"59{len(name_limit):02}{name_limit}"
    
    city_limit = merchant_city[:15]
    tag_60 = f"60{len(city_limit):02}{city_limit}"
    
    # Bill Number (Tag 62 -> Subtag 01)
    bill_sub = f"01{len(bill_number):02}{bill_number}"
    tag_62 = f"62{len(bill_sub):02}{bill_sub}"

    # 3. Assemble without CRC
    raw_qr = tag_00 + tag_01 + tag_29 + tag_52 + tag_53 + tag_54 + tag_58 + tag_59 + tag_60 + tag_62 + "6304"
    
    # 4. Calculate CRC
    crc_val = crc16(raw_qr.encode('utf-8'))
    crc_hex = f"{crc_val:04X}"
    
    return raw_qr + crc_hex

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
# 3. ROUTES
# ==========================================

@app.route('/')
def status():
    return jsonify({"status": "Live", "mode": "Offline QR Gen"})

@app.route('/api/create-payment', methods=['POST'])
def create_payment_qr():
    try:
        data = request.json
        udid = data.get('udid')
        email = data.get('email')
        
        # Unique IDs
        order_id = str(uuid.uuid4())[:8].upper()
        bill_no = f"TRX{int(time.time())}"[-15:] # Max 25 chars usually
        
        # 1. Generate QR String LOCALLY (No Bakong Connection Required)
        qr_string = generate_khqr_offline(
            bank_account=MY_BANK_ACCOUNT,
            amount=10.00,
            merchant_name=MERCHANT_NAME,
            merchant_city=MERCHANT_CITY,
            bill_number=bill_no
        )
        
        # 2. Generate MD5 for checking later
        # Manual MD5 generation to avoid library dependency
        md5_hash = hashlib.md5(qr_string.encode('utf-8')).hexdigest()
        
        # 3. Create QR Image
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(qr_string)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

        # 4. Save to DB
        order_data = {
            "order_id": order_id,
            "email": email,
            "udid": udid,
            "price": "10.00",
            "status": "pending_payment",
            "md5": md5_hash,
            "qr_string": qr_string,
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
        # Check DB first
        order = orders_col.find_one({"md5": md5})
        if not order:
            return jsonify({"status": "NOT_FOUND"})
        
        if order.get('status') == 'paid':
            return jsonify({"status": "PAID"})

        # Try Checking Bakong API
        # We wrap this in try/except so connection errors don't crash the server
        try:
            paid_list = khqr.check_bulk_payments([md5])
            
            if md5 in paid_list:
                orders_col.update_one({"md5": md5}, {"$set": {"status": "paid"}})
                
                msg = (
                    f"✅ <b>PAYMENT RECEIVED</b>\n"
                    f"🆔 Order: <code>{order['order_id']}</code>\n"
                    f"📧 Email: {order['email']}\n"
                    f"📱 UDID: <code>{order['udid']}</code>\n"
                    f"💰 Amount: $10.00"
                )
                send_telegram_alert(msg)
                return jsonify({"status": "PAID"})
                
        except Exception as api_error:
            # If Bakong API is down, we just return UNPAID (client keeps polling)
            print(f"Bakong API Error: {api_error}")
            return jsonify({"status": "UNPAID", "api_error": "Connection Failed"})

        return jsonify({"status": "UNPAID"})

    except Exception as e:
        return jsonify({"status": "ERROR", "msg": str(e)}), 500

# ==========================================
# ADMIN ROUTES (Keep these the same)
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
    all_orders = list(orders_col.find().sort("_id", -1))
    for o in all_orders: o['_id'] = str(o['_id'])
    return jsonify(all_orders)

@app.route('/api/send-email', methods=['POST'])
def api_send_email():
    if request.headers.get('x-admin-password') != ADMIN_PASSWORD:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    oid = data.get('order_id')
    download_link = data.get('link')
    is_failed = data.get('type') == 'failed'

    order = orders_col.find_one({"order_id": oid})
    if not order: return jsonify({"success": False}), 404

    try:
        subject = "Order Rejected" if is_failed else "Order Completed - Irra Esign"
        html = f"<p>Your download link: <a href='{download_link}'>{download_link}</a></p>" if not is_failed else "<p>Order rejected.</p>"
        
        resend.Emails.send({
            "from": "Irra Store <admin@irra.store>",
            "to": [order['email']],
            "subject": subject,
            "html": html
        })
        
        status = "failed" if is_failed else "completed"
        orders_col.update_one({"order_id": oid}, {"$set": {"status": status, "download_link": download_link}})
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
