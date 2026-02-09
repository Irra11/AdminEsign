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
from pymongo import MongoClient
from datetime import datetime, timedelta, timezone
from bakong_khqr import KHQR

app = Flask(__name__)
# Allow CORS for all domains so your frontend can connect
CORS(app, resources={r"/*": {"origins": "*"}})

# ==========================================
# 1. CONFIGURATION & CREDENTIALS
# ==========================================
SHOP_LOGO_URL = "https://i.pinimg.com/736x/93/1a/b7/931ab7b0393dab7b07fedb2b22b70a89.jpg"

# 🔴 Telegram Bot Settings
TELE_TOKEN = "8379666289:AAEiYiFzSf4rkkP6g_u_13vbrv0ILi9eh4o"
TELE_CHAT_ID = "5007619095"

# 🔴 Resend Email Settings
RESEND_API_KEY = "re_M8VwiPH6_CYEbbqfg6nG737BEqR9nNWD5"
resend.api_key = RESEND_API_KEY

# 🔴 Admin Password
ADMIN_PASSWORD = "Irra@4455$" 

# 🔴 Database Connection
MONGO_URI = "mongodb+srv://Esign:Kboy%40%404455@cluster0.4havjl6.mongodb.net/?appName=Cluster0"

try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client['irra_esign_db']
    orders_col = db['orders']
    print("✅ MongoDB Connected")
except Exception as e:
    print(f"❌ MongoDB Failed: {e}")
    orders_col = None

# 🔴 BAKONG KHQR SETTINGS (Using the valid JWT Token)
BAKONG_TOKEN = "rbkcv6NTBBcPumzAJ4GDzBX6P8iKdnCZeeqFQUJF8ns79Y" 
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
    except Exception as e:
        print(f"Telegram Error: {e}")

@app.route('/')
def status():
    return jsonify({"status": "Backend Live", "time": get_khmer_time()})

# ==========================================
# 3. PAYMENT ROUTES (KHQR)
# ==========================================

@app.route('/api/create-payment', methods=['POST'])
def create_payment():
    try:
        data = request.json
        udid = data.get('udid')
        email = data.get('email')
        
        # Create a unique Bill Number
        order_id = str(uuid.uuid4())[:8].upper()
        bill_no = f"TRX-{int(time.time())}"
        
        # 1. Generate KHQR String ($10 USD)
        qr_string = khqr.create_qr(
            bank_account=MY_BANK_ACCOUNT,
            merchant_name='Irra Esign',
            merchant_city='Phnom Penh',
            amount=10.00,
            currency='USD', 
            store_label='IrraStore',
            phone_number='85512345678',
            bill_number=bill_no,
            terminal_label='POS-WEB',
            static=False
        )
        
        # 2. Generate MD5 & Deeplink
        md5_hash = khqr.generate_md5(qr_string)
        deeplink = khqr.generate_deeplink(qr_string, callback="https://irraesign.store", appName="Irra Esign", appIconUrl=SHOP_LOGO_URL)
        
        # 3. Generate QR Image (Base64)
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(qr_string)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

        # 4. Save to MongoDB (Pending Status)
        if orders_col is not None:
            orders_col.insert_one({
                "order_id": order_id,
                "email": email,
                "udid": udid,  # Saving UDID here
                "price": "10.00",
                "plan": "Standard",
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
        # 1. Check status with Bakong
        paid_list = khqr.check_bulk_payments([md5])
        
        # 2. If Payment is Successful
        if md5 in paid_list:
            if orders_col is not None:
                order = orders_col.find_one({"md5": md5})
                
                # Only update if not already Paid
                if order and order.get('status') != 'paid':
                    # Update Database
                    orders_col.update_one({"md5": md5}, {"$set": {"status": "paid"}})
                    
                    # 3. SEND UDID TO TELEGRAM BOT
                    msg = (
                        f"✅ <b>NEW PAYMENT SUCCESS</b>\n"
                        f"🆔 Order: <code>{order['order_id']}</code>\n"
                        f"📧 Email: {order['email']}\n"
                        f"📱 UDID: <code>{order['udid']}</code>\n"
                        f"💰 Amount: $10.00 (Paid)\n"
                        f"⏰ Time: {get_khmer_time()}"
                    )
                    send_telegram_alert(msg)
                    
            return jsonify({"status": "PAID"})
            
        return jsonify({"status": "UNPAID"})

    except Exception as e:
        return jsonify({"status": "ERROR", "msg": str(e)}), 500

# ==========================================
# 4. ADMIN & EMAIL ROUTES
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
    # 1. Auth Check
    if request.headers.get('x-admin-password') != ADMIN_PASSWORD:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    oid = data.get('order_id')
    download_link = data.get('link')
    is_failed = data.get('type') == 'failed'

    order = orders_col.find_one({"order_id": oid})
    if not order: return jsonify({"success": False, "msg": "Order not found"}), 404

    # 2. Prepare Data
    price = order.get('price', '10.00')
    plan = order.get('plan', 'Standard Package')
    udid = order.get('udid', 'N/A')
    user_name = order.get('email').split('@')[0]

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
        main_message = "We are pleased to inform you that your order has been successfully completed."
        button_text = "Download Certificate"
        action_url = download_link

    # 3. HTML Template
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <link href="https://fonts.googleapis.com/css2?family=Hanuman:wght@400;700&family=Inter:wght@400;600&display=swap" rel="stylesheet">
    </head>
    <body style="margin: 0; padding: 0; background-color: #f4f7f6; font-family: 'Inter', sans-serif; color: #333;">
        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="padding: 30px 0;">
            <tr>
                <td align="center">
                    <table width="100%" style="max-width: 600px; background-color: #ffffff; border-radius: 20px; overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.05); border-spacing: 0;">
                        <tr>
                            <td align="center" style="background-color: {theme_color}; padding: 40px 20px;">
                                <div style="display: inline-block; padding: 5px; background: rgba(255,255,255,0.2); border-radius: 50%; margin-bottom: 15px;">
                                    <img src="{SHOP_LOGO_URL}" width="70" height="70" style="display: block; border-radius: 50%; border: 3px solid #ffffff;">
                                </div>
                                <h2 style="margin: 0; color: #ffffff; font-size: 20px;">{status_title}</h2>
                                <p style="margin: 5px 0 0 0; color: #ffffff; opacity: 0.9; font-size: 13px;">{status_desc}</p>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 40px 30px;">
                                <h3 style="margin: 0 0 15px 0; color: #2c3e50;">Dear {user_name},</h3>
                                <p style="font-size: 15px; line-height: 1.6; color: #555;">{main_message}</p>
                                <table width="100%" style="margin-top: 25px; border-collapse: collapse; font-size: 14px;">
                                    <tr><td colspan="2" style="padding: 10px 0; border-bottom: 2px solid #f4f7f6; font-weight: bold; color: {theme_color}; text-transform: uppercase;">Transaction Details</td></tr>
                                    <tr><td style="padding: 12px 0; color: #777;">Payment Amount:</td><td align="right" style="font-weight: 600;">${price}</td></tr>
                                    <tr><td style="padding: 12px 0; color: #777;">Method:</td><td align="right" style="font-weight: 600;">ABA KHQR</td></tr>
                                    <tr><td colspan="2" style="padding: 25px 0 10px 0; border-bottom: 2px solid #f4f7f6; font-weight: bold; color: {theme_color}; text-transform: uppercase;">Order Information</td></tr>
                                    <tr><td style="padding: 12px 0; color: #777;">Order ID:</td><td align="right" style="font-weight: 600;">#{oid}</td></tr>
                                    <tr><td style="padding: 12px 0; color: #777;">Package:</td><td align="right" style="font-weight: 600;">{plan}</td></tr>
                                    <tr><td style="padding: 12px 0; color: #777;">Device UDID:</td><td align="right" style="font-size: 11px; font-family: monospace; background: #f8f9fa; padding: 4px 8px; border-radius: 4px;">{udid}</td></tr>
                                </table>
                                <div style="text-align: center; margin-top: 40px;">
                                    <a href="{action_url}" style="background-color: {theme_color}; color: #ffffff; padding: 18px 35px; text-decoration: none; border-radius: 12px; font-weight: bold; font-size: 16px;">{button_text}</a>
                                </div>
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
            "subject": subject_text,
            "html": html_body
        })
        
        new_status = "failed" if is_failed else "completed"
        orders_col.update_one({"order_id": oid}, {"$set": {"download_link": download_link, "status": new_status}})
        send_telegram_alert(f"✅ <b>EMAIL SENT</b> to {order['email']}")
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)

