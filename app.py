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
# Allow all origins to prevent CORS errors
CORS(app, resources={r"/*": {"origins": "*"}})

# ==========================================
# 1. CREDENTIALS & SETTINGS
# ==========================================
# 🔴 Telegram Settings
TELE_TOKEN = "8379666289:AAEiYiFzSf4rkkP6g_u_13vbrv0ILi9eh4o"
TELE_CHAT_ID = "5007619095"

# 🔴 Resend Email Settings
RESEND_API_KEY = "re_M8VwiPH6_CYEbbqfg6nG737BEqR9nNWD5"
resend.api_key = RESEND_API_KEY

# 🔴 Admin Password
ADMIN_PASSWORD = "Irra@4455$" 

# 🔴 Database Connection
MONGO_URI = "mongodb+srv://Esign:Kboy%40%404455@cluster0.4havjl6.mongodb.net/?appName=Cluster0"
client = MongoClient(MONGO_URI)
db = client['irra_esign_db']
orders_col = db['orders']

# 🔴 Bakong KHQR Settings (Your Valid Token)
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

# A. Create Payment QR
@app.route('/api/create-payment', methods=['POST'])
def create_payment():
    try:
        data = request.json
        udid = data.get('udid')
        email = data.get('email')
        
        # Generate IDs
        order_id = str(uuid.uuid4())[:8].upper()
        bill_no = f"TRX-{int(time.time())}"
        
        # 1. Create QR Data ($10.00 USD)
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
        
        # 2. Get MD5 for checking
        md5_hash = khqr.generate_md5(qr_string)
        
        # 3. Convert to Image
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(qr_string)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

        # 4. Save to MongoDB
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

        print(f"✅ Created QR. MD5: {md5_hash}")

        return jsonify({
            "success": True,
            "order_id": order_id,
            "md5": md5_hash,
            "qr_image": img_base64
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

# B. Check Status (Auto - Polls every 2s)
@app.route('/api/check-payment/<md5>', methods=['GET'])
def check_payment(md5):
    try:
        print(f"🔍 Checking: {md5}")
        
        # 1. Ask Bakong API
        paid_list = khqr.check_bulk_payments([md5])
        
        # 2. If Bakong says PAID
        if md5 in paid_list:
            print(f"🎉 PAYMENT SUCCESS: {md5}")
            
            order = orders_col.find_one({"md5": md5})
            
            # Update DB only if not already updated
            if order and order.get('status') != 'paid':
                orders_col.update_one({"md5": md5}, {"$set": {"status": "paid"}})
                
                # Send Success Telegram
                msg = (
                    f"✅ <b>PAYMENT SUCCESS (AUTO)</b>\n"
                    f"🆔 Order: <code>{order['order_id']}</code>\n"
                    f"📧 Email: {order['email']}\n"
                    f"💰 Amount: $10.00"
                )
                send_telegram_alert(msg)
                
            return jsonify({"status": "PAID"})
            
        print("⏳ Status: Not Paid Yet")
        return jsonify({"status": "UNPAID"})

    except Exception as e:
        print(f"❌ Error: {e}")
        return jsonify({"status": "ERROR", "msg": str(e)}), 500

# C. Manual Confirmation (User clicks Button)
@app.route('/api/confirm-manual', methods=['POST'])
def confirm_manual():
    try:
        data = request.json
        order_id = data.get('order_id')
        
        order = orders_col.find_one({"order_id": order_id})
        
        if order:
            # Update status to 'verification_pending'
            orders_col.update_one(
                {"order_id": order_id}, 
                {"$set": {"status": "verification_pending"}}
            )
            
            # Send ALERT to Admin Telegram
            msg = (
                f"⚠️ <b>MANUAL VERIFICATION REQUIRED</b>\n"
                f"User claims they paid. Please check your Bank App!\n\n"
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

# Send Email Logic
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
    # Use PORT environment variable for Render
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
