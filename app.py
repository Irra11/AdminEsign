from flask import Flask, request, jsonify
from flask_cors import CORS
import resend
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient
from bson import ObjectId
import os

# --- ១. ការកំណត់ជាមូលដ្ឋាន (Setup) ---
app = Flask(__name__)
application = app
CORS(app, resources={r"/*": {"origins": "*"}})

# --- ២. ការកំណត់ LOGO, API KEY និង ADMIN PASSWORD ---
# ត្រូវប្រាកដថា SHOP_LOGO_URL ជា Direct Link និងជារូបរាងការ៉េដើម្បីឱ្យចេញរង្វង់មូលស្អាត
SHOP_LOGO_URL = "https://i.pinimg.com/736x/93/1a/b7/931ab7b0393dab7b07fedb2b22b70a89.jpg" 
RESEND_API_KEY = "re_M8VwiPH6_CYEbbqfg6nG737BEqR9nNWD5"
resend.api_key = RESEND_API_KEY
ADMIN_PASSWORD = "Irra@4455$" 

# --- ៣. ការកំណត់ DATABASE (MONGODB) ---
MONGO_URI = "mongodb+srv://irra_admin:irra4455@irra.qasl61f.mongodb.net/?retryWrites=true&w=majority&appName=Irra"
try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client['irra_store_db']
    orders_col = db['orders']
    client.admin.command('ping')
    print("✅ Connected to MongoDB Successfully!")
except Exception as e:
    print(f"❌ MongoDB Connection Error: {e}")

# --- មុខងារជំនួយ (Helpers) ---
def get_khmer_time():
    khmer_tz = timezone(timedelta(hours=7))
    return datetime.now(khmer_tz).strftime("%d-%b-%Y %I:%M %p")

def check_auth():
    client_pass = request.headers.get('x-admin-password')
    return client_pass == ADMIN_PASSWORD

@app.route('/')
def home():
    return f"Irra Store Backend is Online! Time: {get_khmer_time()}"

# --- ៤. Admin Auth API ---
@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.json
    if data and data.get('password') == ADMIN_PASSWORD:
        return jsonify({"status": "success"}), 200
    return jsonify({"status": "error"}), 401

# --- ៥. មុខងាររក្សាទុក Order (Customer) ---
@app.route('/api/save-order', methods=['POST'])
def save_order():
    try:
        data = request.json
        order = {
            "gmail": data.get('gmailAddress'),
            "skin_name": data.get('product', {}).get('name'),
            "amount": f"${data.get('totalAmount')}",
            "status": "Pending",
            "timestamp": get_khmer_time()
        }
        result = orders_col.insert_one(order)
        return jsonify({"status": "success", "id": str(result.inserted_id)}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# --- ៦. មុខងារ Admin (Orders List, Edit, Delete) ---
@app.route('/api/admin/orders', methods=['GET'])
def get_orders():
    if not check_auth(): return jsonify({"status": "unauthorized"}), 401
    orders = []
    for doc in orders_col.find().sort("_id", -1):
        doc['id'] = str(doc['_id'])
        del doc['_id']
        orders.append(doc)
    return jsonify(orders)

@app.route('/api/admin/edit-order', methods=['POST'])
def edit_order():
    if not check_auth(): return jsonify({"status": "unauthorized"}), 401
    data = request.json
    orders_col.update_one({"_id": ObjectId(data['id'])}, {"$set": {"gmail": data['gmail'], "skin_name": data['skin_name'], "amount": data['amount']}})
    return jsonify({"status": "updated"}), 200

@app.route('/api/admin/delete-order', methods=['POST'])
def delete_order():
    if not check_auth(): return jsonify({"status": "unauthorized"}), 401
    data = request.json
    orders_col.delete_one({"_id": ObjectId(data['id'])})
    return jsonify({"status": "deleted"}), 200

# --- ៧. មុខងារផ្ញើ EMAIL (កែសម្រួល Style ថ្មី Professional) ---
@app.route('/api/admin/send-response', methods=['POST'])
def send_response():
    if not check_auth(): return jsonify({"status": "unauthorized"}), 401
    try:
        data = request.json
        recipient = data.get('gmail')
        message_content = data.get('message')
        email_subject = data.get('subject')
        order_id = data.get('id')

        is_success = 'ជោគជ័យ' in email_subject
        theme_color = "#27ae60" if is_success else "#e74c3c"
        
        # រៀបចំសារឱ្យមានការចុះបន្ទាត់ស្អាត
        formatted_message = message_content.replace('\n', '<br>')

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <link href="https://fonts.googleapis.com/css2?family=Hanuman:wght@400;700&display=swap" rel="stylesheet">
        </head>
        <body style="margin: 0; padding: 0; background-color: #f4f7f6; font-family: 'Arial', sans-serif;">
            <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #f4f7f6; padding: 30px 0;">
                <tr>
                    <td align="center">
                        <table width="100%" style="max-width: 600px; background-color: #ffffff; border-radius: 25px; overflow: hidden; box-shadow: 0 15px 45px rgba(0,0,0,0.1); border-spacing: 0;">
                            <!-- Header Section -->
                            <tr>
                                <td align="center" style="background-color: {theme_color}; padding: 50px 20px;">
                                    <!-- Logo Circle Style -->
                                    <div style="display: inline-block; padding: 5px; background: rgba(255,255,255,0.2); border-radius: 50%; margin-bottom: 20px;">
                                        <img src="{SHOP_LOGO_URL}" width="85" height="85" style="display: block; border-radius: 50%; object-fit: cover; border: 3px solid #ffffff;">
                                    </div>
                                    <h1 style="margin: 0; color: #ffffff; font-size: 24px; font-family: 'Hanuman', serif; font-weight: 700;">{email_subject}</h1>
                                    <p style="margin: 10px 0 0 0; color: #ffffff; opacity: 0.85; font-size: 14px; letter-spacing: 0.5px;">លេខរៀងបញ្ជាទិញ: #{str(order_id)[-6:]}</p>
                                </td>
                            </tr>
                            
                            <!-- Body Section -->
                            <tr>
                                <td style="padding: 45px 40px; background-color: #ffffff;">
                                    <h2 style="margin: 0 0 25px 0; font-size: 20px; color: #333333; font-family: 'Hanuman', serif; font-weight: 700;">សូមជម្រាបជូនអតិថិជន!</h2>
                                    
                                    <div style="font-size: 16px; line-height: 1.8; color: #555555; font-family: 'Hanuman', serif;">
                                        {formatted_message}
                                    </div>

                                    <!-- Action Button -->
                                    <table width="100%" border="0" cellspacing="0" cellpadding="0" style="margin-top: 40px;">
                                        <tr>
                                            <td align="center">
                                                <a href="https://t.me/irra_11" style="background-color: {theme_color}; color: #ffffff; padding: 18px 35px; text-decoration: none; border-radius: 15px; font-weight: bold; display: inline-block; font-size: 16px; box-shadow: 0 5px 15px rgba(0,0,0,0.1);">ទាក់ទងតាម Telegram</a>
                                            </td>
                                        </tr>
                                    </table>

                                    <!-- Divider & Disclaimer -->
                                    <div style="margin-top: 50px; padding-top: 25px; border-top: 1px solid #eeeeee; text-align: center;">
                                        <p style="margin: 0; font-size: 13px; color: #aaaaaa; line-height: 1.6;">
                                            This is an automated message. Please do not reply.<br>
                                        </p>
                                    </div>
                                </td>
                            </tr>
                            
                            <!-- Footer Section -->
                            <tr>
                                <td align="center" style="background-color: #f9f9f9; padding: 25px; color: #999999; font-size: 12px; font-family: 'Arial', sans-serif;">
                                    <p style="margin: 0;">© 2026 <strong>Irra Store</strong>. រក្សាសិទ្ធិគ្រប់យ៉ាង។</p>
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
            r = resend.Emails.send({
                "from": "Irra Store <admin@irra.store>",
                "to": [recipient],
                "subject": email_subject,
                "html": html_body
            })
            new_status = 'Completed' if is_success else 'Failed'
            orders_col.update_one({"_id": ObjectId(order_id)}, {"$set": {"status": new_status}})
            return jsonify({"status": "sent", "resend_id": r.get("id")}), 200
        except Exception as res_err:
            return jsonify({"status": "error", "message": str(res_err)}), 500

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    app.run(host='0.0.0.0', port=port)

