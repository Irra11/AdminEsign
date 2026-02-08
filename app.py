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
# 1. CONFIGURATION
# ==========================================
TELE_TOKEN = "8379666289:AAEiYiFzSf4rkkP6g_u_13vbrv0ILi9eh4o"
TELE_CHAT_ID = "5007619095"

RESEND_API_KEY = "re_M8VwiPH6_CYEbbqfg6nG737BEqR9nNWD5"
resend.api_key = RESEND_API_KEY
ADMIN_PASSWORD = "Irra@4455$" 

# Logo for Bakong Deeplink (REQUIRED)
SHOP_LOGO_URL = "https://i.pinimg.com/736x/93/1a/b7/931ab7b0393dab7b07fedb2b22b70a89.jpg"

# Database
MONGO_URI = "mongodb+srv://Esign:Kboy%40%404455@cluster0.4havjl6.mongodb.net/?appName=Cluster0"
try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client['irra_esign_db']
    orders_col = db['orders']
    print("✅ MongoDB Connected")
except:
    print("❌ MongoDB Failed")
    orders_col = None

# BAKONG CONFIG
# ⚠️ If using a Personal Account token, 'check_payment' might still fail or return UNPAID.
# But 'create_payment' will work now because we fixed the missing parameter.
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
    try:
        url = f"https://api.telegram.org/bot{TELE_TOKEN}/sendMessage"
        payload = {"chat_id": TELE_CHAT_ID, "text": message, "parse_mode": "HTML"}
        requests.post(url, json=payload)
    except:
        pass

@app.route('/')
def status():
    return jsonify({"status": "Backend Live", "time": get_khmer_time()})

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
        
        # 1. Generate QR Code Data
        qr_string = khqr.create_qr(
            bank_account=MY_BANK_ACCOUNT,
            merchant_name='Irra Esign',
            merchant_city='Phnom Penh',
            amount=10.00,
            currency='USD',
            store_label='IrraStore',
            phone_number='85512345678',
            bill_number=bill_no,
            terminal_label='POS-01',
            static=False
        )
        
        # 2. Generate MD5
        md5_hash = khqr.generate_md5(qr_string)
        
        # 3. Generate Deeplink (FIXED: Added appIconUrl)
        deeplink = khqr.generate_deeplink(
            qr_string,
            callback="https://irraesign.store",
            appName="Irra Esign",
            appIconUrl=SHOP_LOGO_URL  # <--- THIS WAS MISSING
        )
        
        # 4. Generate Image
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(qr_string)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

        if orders_col is not None:
            orders_col.insert_one({
                "order_id": order_id,
                "email": email,
                "udid": udid,
                "price": "10.00",
                "status": "pending_payment",
                "md5": md5_hash,
                "timestamp": get_khmer_time()
            })

        return jsonify({
            "success": True,
            "order_id": order_id,
            "md5": md5_hash,
            "qr_image": img_base64,
            "deeplink": deeplink
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/check-payment/<md5>', methods=['GET'])
def check_payment(md5):
    try:
        print(f"🔍 Checking MD5: {md5}")

        # 1. Check Status
        # If token is invalid (Personal Account), this might raise an error or return empty
        payment_status = khqr.check_payment(md5)
        print(f"📡 Status: {payment_status}")

        if payment_status == "PAID":
            payment_info = khqr.get_payment(md5)
            
            if orders_col is not None:
                order = orders_col.find_one({"md5": md5})
                if order and order.get('status') != 'paid':
                    orders_col.update_one({"md5": md5}, {"$set": {
                        "status": "paid",
                        "payment_details": payment_info
                    }})
                    
                    sender = payment_info.get('fromAccountId', 'Unknown')
                    amount = payment_info.get('amount', '10.00')
                    msg = (
                        f"✅ <b>PAYMENT RECEIVED</b>\n"
                        f"🆔 Order: <code>{order['order_id']}</code>\n"
                        f"👤 Sender: {sender}\n"
                        f"💰 Amount: ${amount}\n"
                        f"📧 Email: {order['email']}"
                    )
                    send_telegram_alert(msg)

            return jsonify({"status": "PAID", "data": payment_info})
            
        else:
            return jsonify({"status": "UNPAID"})

    except Exception as e:
        print(f"❌ Check Error: {e}")
        # Return flag to show Manual Button on frontend
        return jsonify({"status": "UNPAID", "error": str(e), "require_manual": True})


@app.route('/api/confirm-manual', methods=['POST'])
def confirm_manual():
    try:
        data = request.json
        order_id = data.get('order_id')
        if orders_col is not None:
            orders_col.update_one({"order_id": order_id}, {"$set": {"status": "verification_pending"}})
            
            order = orders_col.find_one({"order_id": order_id})
            if order:
                msg = (
                    f"⚠️ <b>MANUAL CONFIRMATION</b>\n"
                    f"User clicked 'I Have Paid'.\n"
                    f"🆔 Order: <code>{order['order_id']}</code>\n"
                    f"📧 Email: {order['email']}\n"
                    f"👉 Check Bank App & Send File Manually."
                )
                send_telegram_alert(msg)
                
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)})

# ==========================================
# 4. ADMIN & EMAIL
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
    orders_col.update_one({"order_id": data.get('order_id')}, {"$set": {"email": data.get('email'), "download_link": data.get('link')}})
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
    if not order: return jsonify({"success": False}), 404

    try:
        subject = "Order Rejected" if is_failed else "Order Completed"
        html = f"<p>Download: <a href='{download_link}'>Click Here</a></p>" if not is_failed else "<p>Verification Failed.</p>"
        
        resend.Emails.send({
            "from": "Irra Store <admin@irra.store>",
            "to": [order['email']],
            "subject": subject,
            "html": html
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
