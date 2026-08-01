import requests
from flask import Flask, render_template, request, redirect, flash, url_for, Response, jsonify, session, send_from_directory
import sqlite3
import cv2
import time
import os
import smtplib
from email.mime.text import MIMEText
from werkzeug.utils import secure_filename
from ultralytics import YOLO
from picamera2 import Picamera2
from datetime import datetime

#toyyibpay
TOYYIBPAY_SECRET = ''
TOYYIBPAY_CATEGORY = ''

MAIL_SMTP_HOST = 'smtp.gmail.com'
MAIL_SMTP_PORT = 587
MAIL_SENDER = os.environ.get('MAIL_SENDER', '2023213936@student.uitm.edu.my')
MAIL_APP_PASSWORD = os.environ.get('MAIL_APP_PASSWORD', '')
DEVELOPER_EMAIL = os.environ.get('DEVELOPER_EMAIL', '2023213936@student.uitm.edu.my')

def notify_new_item_registered(item_name, price_kg):
    if not MAIL_APP_PASSWORD:
        print("Email notification skipped: MAIL_APP_PASSWORD not set.")
        return

    subject = f"[AgroScale] New item registered: {item_name}"
    body = (
        f"A new item has been registered in the system.\n\n"
        f"Item Name : {item_name}\n"
        f"Price/Kg  : {price_kg}\n"
        f"Time      : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"Action needed: collect training images and retrain/fine-tune the "
        f"YOLO model to recognize this new item."
    )

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = MAIL_SENDER
    msg['To'] = DEVELOPER_EMAIL

    try:
        with smtplib.SMTP(MAIL_SMTP_HOST, MAIL_SMTP_PORT) as server:
            server.starttls()
            server.login(MAIL_SENDER, MAIL_APP_PASSWORD)
            server.sendmail(MAIL_SENDER, [DEVELOPER_EMAIL], msg.as_string())
        print(f"Notification email sent for new item: {item_name}")
    except Exception as e:
        print(f"Failed to send notification email: {e}")

from hx711py.hx711_reader import get_weight

app = Flask(__name__)
app.secret_key = 'agroscale_secret_code'

# config & setup
UPLOAD_FOLDER = 'static/uploads/profile_photos'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure upload directory exists at startup
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# database
def get_db_connection():
    conn = sqlite3.connect('agroDatabase')
    conn.row_factory = sqlite3.Row
    return conn

# load yolo model
try:
    model = YOLO('yolo/agroscale_model_ncnn_model')
    print("YOLO Model Loaded Successfully")
except Exception as e:
    print(f"Model Error: {e}")
    model = None

current_detected_item = None

# camera setup
try:
    picam2 = Picamera2()
    config = picam2.create_video_configuration(
        main={"size": (640, 480), "format": "RGB888"}
    )
    picam2.configure(config)
    picam2.start()
    time.sleep(2)
    print("Camera Ready")
except Exception as e:
    print(f"Camera Error: {e}")

# video stream
def generate_frames():
    global current_detected_item

    while True:
        try:
            frame = picam2.capture_array()

            if model:
                results = model(frame, conf=0.5, verbose=False)
                r = results[0]

                if len(r.boxes) > 0:
                    class_id = int(r.boxes.cls[0].item())
                    current_detected_item = r.names[class_id]
                else:
                    current_detected_item = None

                annotated = r.plot()
            else:
                annotated = frame  # Fallback if model failed to load

            ret, buffer = cv2.imencode('.jpg', annotated)
            if not ret:
                continue

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' +
                   buffer.tobytes() + b'\r\n')

        except Exception as e:
            print(f"Frame Error: {e}")
            time.sleep(0.1)  # Brief pause on error to prevent CPU thrashing

# toyyibpay qr routes
@app.route('/api/create_qr', methods=['POST'])
def create_qr():
    try:
        data = request.get_json()
        total_amount = data.get('amount', 0) 

        # ToyyibPay requires the amount to be in cents and an integer
        amount_in_cents = int(float(total_amount) * 100)

        # 1. ToyyibPay Sandbox Configuration
        url = 'https://dev.toyyibpay.com/index.php/api/createBill'

        payload = {
            'userSecretKey': TOYYIBPAY_SECRET,
            'categoryCode': TOYYIBPAY_CATEGORY,
            'billName': 'AgroScale POS Payment',
            'billDescription': 'Retail Checkout',
            'billPriceSetting': 1,
            'billPayorInfo': 1,
            'billAmount': amount_in_cents, 
            'billReturnUrl': 'https://ensure-copartner-cyclist.ngrok-free.de',
            'billCallbackUrl': 'https://ensure-copartner-cyclist.ngrok-free.de',
            'billExternalReferenceNo': 'POS-001',
            'billTo': 'AgroScale Customer',
            'billEmail': 'agroscalecustomerservice@gmail.com',
            'billPhone': '0149478735',
            'billSplitPayment': 0,
            'billSplitPaymentArgs': '',
            'billPaymentChannel': '2', # 2 = Restrict to DuitNow QR only
            'billChargeToCustomer': 1
        }

        print(f"Generating DuitNow QR for RM {total_amount}...")
        response = requests.post(url, data=payload)
        
        print("Status Code:", response.status_code)
        print("ToyyibPay Response:", response.text)

        result = response.json()
        
        # 2. Format the response nicely so the JavaScript can easily read it
        if isinstance(result, list) and len(result) > 0 and "BillCode" in result[0]:
            return jsonify({
                "status": "success",
                "bill_code": result[0]["BillCode"]
            }), 200
        else:
            return jsonify({"status": "error", "message": "Invalid response from ToyyibPay"}), 400

    except Exception as e:
        print("Error in create_qr:", e)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/check_payment_status/<bill_code>', methods=['GET'])
def check_payment_status(bill_code):
    payload = {
        'userSecretKey': TOYYIBPAY_SECRET,
        'billCode': bill_code
    }
    
    url = "https://dev.toyyibpay.com/index.php/api/getBillTransactions"
    
    try:
        response = requests.post(url, data=payload)
        
        # Check if response from JSON is valid
        if response.text.strip().startswith('[') or response.text.strip().startswith('{'):
            result = response.json()
            
            if isinstance(result, list) and len(result) > 0:
                status = result[0].get('billpaymentStatus')
                if status == '1':
                    return jsonify({"status": "paid"})
        else:
            pass

    except Exception as e:
        print("Error checking payment:", e)

    # Return pending if not paid yet or if error occurs
    return jsonify({"status": "pending"})

# routes auth&dashboard
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        staff_id = request.form['staffId'].strip().upper()
        password_input = request.form['password']

        conn = get_db_connection()
        # Fetch the user from the database based on the ID entered
        user = conn.execute("SELECT * FROM staff WHERE staffId = ?", (staff_id,)).fetchone()
        conn.close()

        # 1. First, check if the user exists in the database
        if user:
            # 2. If user exists, verify the password
            if user['password'] == password_input:
                
                # Store user info in the session
                session['staffId'] = user['staffId']
                session['staffName'] = user['staffName']
                session['profile_image'] = user['profile_image'] if user['profile_image'] else None

                # 3. Handle Role Assignment dynamically from database
                db_role = str(user['role']).strip().lower()
                
                if db_role == 'admin':
                    session['role'] = 'Admin'
                    return redirect(url_for('admin_dashboard'))
                else:
                    # Every role that isn't 'admin' will be treated as 'Cashier'
                    session['role'] = 'Cashier'
                    return redirect(url_for('home'))
            else:
                # Password does not match
                flash('Invalid Password')
                return redirect(url_for('login'))
        else:
            # User ID not found in database
            flash('Invalid User ID')
            return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/home')
def home():
    if 'staffId' not in session:
        return redirect(url_for('login'))

    return render_template(
        'home.html',
        staff_id=session.get('staffId'),
        staff_name=session.get('staffName'),
        staff_role=session.get('role'),
        profile_image=session.get('profile_image')
    )

#ADMIN DASHBOARD
@app.route('/admin')
def admin_dashboard():
    # Make sure only logged-in Admins can access this page
    if session.get('role') != 'Admin':
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    
    # 1. Get total staff count
    staff_count = conn.execute("SELECT COUNT(*) FROM staff").fetchone()[0]
    
    # 2. Get total transaction count from receipts table
    transactions_count = conn.execute("SELECT COUNT(*) FROM receipts").fetchone()[0]
    
    # 3. Get list of all items for the database table
    items_list = conn.execute("SELECT * FROM item").fetchall()
    
    # 4. Get initial sales data for the chart (Defaulting to 'Day' - Last 7 Days)
    query = """
        SELECT DATE(created_at) as chart_date, SUM(total_amount) as total
        FROM receipts
        WHERE DATE(created_at) >= DATE('now', '-7 days')
        GROUP BY DATE(created_at)
        ORDER BY DATE(created_at) ASC
    """
    results = conn.execute(query).fetchall()
    chart_dates = [row['chart_date'] for row in results]
    chart_totals = [row['total'] for row in results]
    
    conn.close()
        
    # Pass all variables to the template
    return render_template('admin.html', 
                           current_user=session, 
                           staff_count=staff_count,
                           transactions_count=transactions_count,
                           items=items_list,
                           chart_dates=chart_dates,
                           chart_totals=chart_totals)

#API FOR CHART FILTER
@app.route('/admin/api/sales_data')
def get_sales_data():
    # Security check
    if session.get('role') != 'Admin':
        return jsonify({'error': 'Unauthorized'}), 403

    # Filter date (day/week/month/year)
    period = request.args.get('period', 'day')
    
    # Capture date from calendar (format: YYYY-MM-DD)
    selected_date = request.args.get('date')
    
    # use current date automatically
    if not selected_date:
        selected_date = datetime.now().strftime('%Y-%m-%d')

    conn = get_db_connection()

    try:
        # Define the SQL query based on exact requirements
        if period == 'day':
            # Last 7 Days grouped by Day 
            query = """
                SELECT DATE(created_at) as chart_date, SUM(total_amount) as total
                FROM receipts
                WHERE DATE(created_at) >= DATE(?, '-7 days') AND DATE(created_at) <= DATE(?)
                GROUP BY DATE(created_at)
                ORDER BY DATE(created_at) ASC
            """
            results = conn.execute(query, (selected_date, selected_date)).fetchall()
            
        elif period == 'week':
            # Last 30 Days grouped by Week Number 
            query = """
                SELECT STRFTIME('%Y-W%W', created_at) as chart_date, SUM(total_amount) as total
                FROM receipts
                WHERE DATE(created_at) >= DATE(?, '-30 days') AND DATE(created_at) <= DATE(?)
                GROUP BY STRFTIME('%Y-W%W', created_at)
                ORDER BY DATE(created_at) ASC
            """
            results = conn.execute(query, (selected_date, selected_date)).fetchall()
            
        elif period == 'month':
            # Last 1 Year grouped by Month 
            query = """
                SELECT STRFTIME('%Y-%m', created_at) as chart_date, SUM(total_amount) as total
                FROM receipts
                WHERE DATE(created_at) >= DATE(?, '-1 year') AND DATE(created_at) <= DATE(?)
                GROUP BY STRFTIME('%Y-%m', created_at)
                ORDER BY STRFTIME('%Y-%m', created_at) ASC
            """
            results = conn.execute(query, (selected_date, selected_date)).fetchall()
            
        elif period == 'year':
            # All Historical Data grouped by Year 
            query = """
                SELECT STRFTIME('%Y', created_at) as chart_date, SUM(total_amount) as total
                FROM receipts
                WHERE DATE(created_at) <= DATE(?)
                GROUP BY STRFTIME('%Y', created_at)
                ORDER BY STRFTIME('%Y', created_at) ASC
            """
            results = conn.execute(query, (selected_date,)).fetchall()
            
        else:
            return jsonify({'error': 'Invalid period'}), 400

        # Format the data into separate lists for Chart.js
        dates = [row['chart_date'] for row in results]
        # Round the totals to 2 decimal places to avoid long floats like 12.00000001
        totals = [round(row['total'], 2) if row['total'] else 0 for row in results]

        return jsonify({
            'dates': dates,
            'totals': totals
        })

    except Exception as e:
        print(f"Error fetching sales data: {e}")
        return jsonify({'dates': [], 'totals': []}), 500
        
    finally:
        conn.close()

#API FOR PAYMENT METHOD CHARTS
@app.route('/admin/api/payment_methods')
def get_payment_methods():
    if session.get('role') != 'Admin':
        return jsonify({'error': 'Unauthorized'}), 403

    # Get date from the calendar filter, default to today if not provided
    selected_date = request.args.get('date')
    if not selected_date:
        selected_date = datetime.now().strftime('%Y-%m-%d')

    conn = get_db_connection()
    try:
        # Group by payment_method for the specific date
        query = """
            SELECT payment_method, SUM(total_amount) as total
            FROM receipts
            WHERE DATE(created_at) = DATE(?)
            GROUP BY payment_method
        """
        results = conn.execute(query, (selected_date,)).fetchall()
        
        # Prepare the data structure
        data = {"Cash": 0, "E-Wallet": 0} 
        
        for row in results:
            method = row['payment_method']
            if method:
                # Ensure the method check aligns with what is saved in DB
                if "cash" in method.lower():
                    data["Cash"] = round(row['total'], 2)
                else:
                    data["E-Wallet"] = round(row['total'], 2)
                    
        return jsonify({
            'labels': list(data.keys()),
            'totals': list(data.values())
        })
    except Exception as e:
        print(f"Error fetching payment methods: {e}")
        return jsonify({'labels': ['Cash', 'E-Wallet'], 'totals': [0, 0]}), 500
    finally:
        conn.close()


#CASHIER RECEIPTS DETAIL
@app.route('/cashier/receipt/<int:receipt_id>')
def cashier_receipt_detail(receipt_id):

    # Security check
    if 'staffId' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()

    try:
        #GET RECEIPTS INFORMATION
        receipt_info = conn.execute("""
            SELECT r.*, s.staffName
            FROM receipts r
            LEFT JOIN staff s
            ON r.staffId = s.staffId
            WHERE r.receiptsId = ?
        """, (receipt_id,)).fetchone()

        # Receipt not found
        if not receipt_info:
            conn.close()
            flash("Receipt not found.")
            return redirect(url_for('home'))

        #GET RECEIPTS ITEM
        items = conn.execute("""
            SELECT *
            FROM receipts_item
            WHERE receiptsId = ?
        """, (receipt_id,)).fetchall()

        conn.close()

        return render_template(
            'cashier_receipt.html',
            receipt=receipt_info,
            items=items,
            current_user=session
        )

    except Exception as e:
        conn.close()
        print(f"Receipt Detail Error: {e}")
        return f"Database Error: {e}"
    
#ITEM MANAGEMENT
@app.route('/admin/registered_items')
def registered_items():
    if session.get('role') != 'Admin':
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    items_list = conn.execute("SELECT * FROM item").fetchall()
    conn.close()
    
    return render_template('registered_items.html', current_user=session, items=items_list)

@app.route('/admin/item/save', methods=['POST'])
def save_item():
    if session.get('role') != 'Admin':
        return redirect(url_for('login'))
        
    item_id = request.form.get('itemId')
    item_name = request.form.get('itemName')
    priceKg = request.form.get('priceKg')
        
    conn = get_db_connection()
    
    is_new_item = not item_id  # True only when adding, not editing

    try:
        if item_id:
            # EDIT EXISTING ITEM: Run update query without the filename check
            conn.execute("""
                UPDATE item 
                SET itemName = ?, priceKg = ? 
                WHERE itemId = ?
            """, (item_name, priceKg, item_id))
        else:
            # ADD NEW ITEM: Let the database auto-generate the itemId
            conn.execute("""
                INSERT INTO item (itemName, priceKg) 
                VALUES (?, ?)
            """, (item_name, priceKg))

        conn.commit()
    except Exception as e:
        print(f"Error saving item: {e}")
    finally:
        conn.close()

    # Notify developer only when a brand new item was registered
    if is_new_item:
        notify_new_item_registered(item_name, priceKg)

    return redirect(url_for('registered_items'))

# Added methods=['POST'] to match the HTML form submission
@app.route('/admin/registered_items/delete/<item_id>', methods=['POST'])
def delete_item(item_id):
    if session.get('role') != 'Admin':
        return redirect(url_for('login'))

    conn = get_db_connection()
    try:
        conn.execute("DELETE FROM item WHERE itemId = ?", (item_id,))
        conn.commit()
    except Exception as e:
        print(f"Error deleting item: {e}")
    finally:
        conn.close()
    
    return redirect(url_for('registered_items'))
    
#RECEIPTS MANAGEMENT
@app.route('/admin/receipts')
def receipts_list():
    if session.get('role') != 'Admin':
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    # Fetch all receipts and join with staff table to get the staff's name for the dashboard
    receipts_data = conn.execute("""
        SELECT r.*, s.staffName 
        FROM receipts r 
        LEFT JOIN staff s ON r.staffId = s.staffId 
        ORDER BY r.created_at DESC
    """).fetchall()
    conn.close()
    
    return render_template('receipts_list.html', receipts=receipts_data, current_user=session)

@app.route('/admin/receipt/<int:receipt_id>')
def view_receipt(receipt_id):
    if session.get('role') != 'Admin':
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    
    # 1. Get receipts information (Total, Tarikh, Staff)
    receipt_info = conn.execute("""
        SELECT r.*, s.staffName 
        FROM receipts r 
        LEFT JOIN staff s ON r.staffId = s.staffId 
        WHERE r.receiptsId = ?
    """, (receipt_id,)).fetchone()
    
    # 2. get list item from table receipts_item
    items = conn.execute("""
        SELECT * FROM receipts_item 
        WHERE receiptsId = ?
    """, (receipt_id,)).fetchall()
    
    conn.close()
    
    if not receipt_info:
        flash("Receipts Not Found.")
        return redirect(url_for('receipts_list'))
        
    return render_template('receipts_detail.html', 
                           receipt=receipt_info, 
                           items=items, 
                           current_user=session)

#STAFF MANAGEMENT
@app.route('/admin/staff')
def staff_list():
    if session.get('role') != 'Admin':
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    staff_data = conn.execute("SELECT * FROM staff").fetchall()
    conn.close()
    
    # ADDED current_user=session so the navbar profile works correctly
    return render_template('staff_list.html', staff=staff_data, current_user=session)


@app.route('/admin/staff/save', methods=['POST'])
def save_staff():
    if session.get('role') != 'Admin':
        return redirect(url_for('login'))
        
    original_id = request.form.get('originalStaffId')
    staff_name = request.form.get('staffName')
    gender = request.form.get('gender')
    role = request.form.get('role')
    password = request.form.get('password')

    # Handle Profile Image Upload
    file = request.files.get('profilePhoto')
    filename = None
    if file and file.filename != '' and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
    conn = get_db_connection()
    
    try:
        if original_id:
            # Edit existing staff
            if filename:
                conn.execute("""
                    UPDATE staff SET staffName=?, gender=?, role=?,  profile_image=?, password=? WHERE staffId=?
                """, (staff_name, gender, role, filename, password, original_id))
            else:
                conn.execute("""
                    UPDATE staff SET staffName=?, gender=?, role=?, password=? WHERE staffId=?
                """, (staff_name, gender, role, password, original_id))
        else:
            # Add new staff
            prefix = 'A' if role == 'Admin' else 'B'
            cursor = conn.execute(f"SELECT staffId FROM staff WHERE staffId LIKE '{prefix}%' ORDER BY staffId DESC LIMIT 1")
            last_staff = cursor.fetchone()
            
            if last_staff:
                last_id_num = int(last_staff['staffId'][1:])
                new_id = f"{prefix}{last_id_num + 1:03d}"
            else:
                new_id = f"{prefix}001"
                
            conn.execute("""
                INSERT INTO staff (staffId, staffName, gender, role, profile_image, password) VALUES (?, ?, ?, ?, ?, ?)
            """, (new_id, staff_name, gender, role, filename, password))
            
        conn.commit()
    except Exception as e:
        print(f"Error saving staff: {e}")
    finally:
        conn.close()
        
    return redirect(url_for('staff_list'))


@app.route('/admin/staff/delete/<staff_id>', methods=['POST'])
def delete_staff(staff_id):
    if session.get('role') != 'Admin':
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    conn.execute("DELETE FROM staff WHERE staffId = ?", (staff_id,))
    conn.commit()
    conn.close()
    
    return redirect(url_for('staff_list'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# Route to serve uploaded profile photos safely
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

#POS SYSTEM API
@app.route('/api/get_prices')
def get_prices():
    try:
        conn = get_db_connection()
        items = conn.execute("SELECT itemName, priceKg FROM item").fetchall()
        conn.close()

        return jsonify({
            row["itemName"]: float(row["priceKg"])
            for row in items
        })

    except Exception as e:
        print(f"Price API Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/detect')
def detect_item():
    global current_detected_item

    try:
        if not current_detected_item:
            return jsonify({"status": "error", "message": "No object detected"})

        weight = get_weight() or 0

        if weight <= 0:
            return jsonify({"status": "error", "message": "No weight detected"})

        conn = get_db_connection()
        item = conn.execute(
            "SELECT * FROM item WHERE LOWER(itemName)=?",
            (current_detected_item.lower(),)
        ).fetchone()
        conn.close()

        if not item:
            return jsonify({
                "status": "error",
                "message": f"{current_detected_item} not in database"
            })

        price_per_kg = float(item["priceKg"])
        total = float(weight) * price_per_kg

        return jsonify({
            "status": "success",
            "id": item["itemId"] if "itemId" in item.keys() else 0,
            "item": current_detected_item,
            "weight": round(weight, 3),
            "price_per_kg": price_per_kg,
            "price": round(total, 2)
        })

    except Exception as e:
        print(f"Detect Error: {e}")
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/get_item/<item_id>')
def get_item(item_id):
    try:
        conn = get_db_connection()
        item = conn.execute("SELECT * FROM item WHERE itemId = ?", (item_id,)).fetchone()
        conn.close()
        
        if item:
            return jsonify({
                "status": "success",
                "id": item["itemId"],
                "name": item["itemName"],
                "priceKg": float(item["priceKg"])
            })
            
        return jsonify({"status": "error", "message": "Item not found"})
        
    except Exception as e:
        print(f"Get Item Error: {e}")
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/get_all_items', methods=['GET'])
def get_all_items():
    try:
        conn = get_db_connection()
        items = conn.execute("SELECT itemId, itemName, priceKg FROM item").fetchall()
        conn.close()

        items_list = [
            {
                "id": row["itemId"],
                "name": row["itemName"],
                "priceKg": float(row["priceKg"])
            }
            for row in items
        ]

        return jsonify({"status": "success", "items": items_list})
    except Exception as e:
        print(f"Get All Items Error: {e}")
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/get_weight')
def api_get_weight():
    try:
        weight = get_weight() or 0
        if weight > 0:
            return jsonify({"status": "success", "weight": round(float(weight), 3)})
            
        return jsonify({"status": "error", "message": "No weight detected on scale. Please place the item."})
        
    except Exception as e:
        print(f"Get Weight Error: {e}")
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/verify_admin', methods=['POST'])
def verify_admin():
    try:
        data = request.json
        admin_id = data.get('admin_id', '').strip().upper()
        password = data.get('password', '')  # 1. Extract the password

        # 2. Check that BOTH fields are provided
        if not admin_id or not password:
            return jsonify({"success": False, "message": "ID and password are required."})

        conn = get_db_connection()
        user = conn.execute(
            "SELECT * FROM staff WHERE staffId = ?",
            (admin_id,)
        ).fetchone()
        conn.close()

        # 3. Check if user exists AND is an admin (starts with A)
        if user and admin_id.startswith('A'):
            
            # 4. Compare the passwords
            if user['password'] == password:
                return jsonify({"success": True})
            else:
                return jsonify({"success": False, "message": "Incorrect password."})
                
        else:
            return jsonify({"success": False, "message": "Invalid Admin ID or insufficient privileges."})

    except Exception as e:
        print(f"Verify Admin Error: {e}")
        return jsonify({"success": False, "message": str(e)})
        
@app.route('/api/checkout', methods=['POST'])
def checkout():
    try:
        data = request.json

        total = round(float(data.get('total_amount', 0)), 2)
        method = data.get('payment_method')
        items = data.get('items', [])

        staff_id = session.get('staffId', 'Unknown')

        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO receipts (staffId, total_amount, payment_method, created_at)
                VALUES (?, ?, ?, datetime('now', 'localtime'))
            """, (staff_id, total, method))

            receipt_id = cursor.lastrowid

            for item in items:
                cursor.execute("""
                    INSERT INTO receipts_item (itemId, receiptsId, itemName, weight, unitPrice, created_at)
                    VALUES (?, ?, ?, ?, ?, datetime('now', 'localtime'))
                """, (
                    item.get('id'),
                    receipt_id,
                    item.get('name'),
                    float(item.get('weight', 0)),
                    round(float(item.get('unitPrice', 0)), 2)
                ))
            
            conn.commit()

        return jsonify({"status": "success", "receipt_id": receipt_id})

    except Exception as e:
        print(f"Checkout Error: {e}")
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/staff_daily_sales', methods=['GET'])
def staff_daily_sales():
    # Make sure the user is logged in
    if 'staffId' not in session:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    staff_id = session['staffId']
    
    try:
        conn = get_db_connection() 
        
        # Query to get ONLY today's receipts for the logged-in staff
        # Uses 'localtime' to match the timezone used in your checkout route
        rows = conn.execute("""
            SELECT receiptsId, payment_method, total_amount 
            FROM receipts 
            WHERE staffId = ? AND DATE(created_at) = DATE('now', 'localtime')
        """, (staff_id,)).fetchall()
        
        conn.close()
        
        transactions = []
        total_earnings = 0.0
        
        for row in rows:
            amount = float(row['total_amount'])
            total_earnings += amount
            transactions.append({
                "receiptId": row['receiptsId'],
                "payment_method": row['payment_method'],
                "total_amount": amount
            })
            
        return jsonify({
            "status": "success",
            "total_earnings": total_earnings,
            "total_transactions": len(transactions),
            "transactions": transactions
        })
        
    except Exception as e:
        print(f"Error fetching daily sales: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

#USER PROFILE
@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'staffId' not in session:
        return redirect(url_for('login'))

    staff_id = session['staffId']
    conn = get_db_connection()

    if request.method == 'POST':
        staff_name = request.form.get('staffName')
        password = request.form.get('password')
        file = request.files.get('profilePhoto')
        
        filename = session.get('profile_image') # Default to current

        if file and file.filename != '' and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            session['profile_image'] = filename

        conn.execute("""
            UPDATE staff SET staffName=?, password=?, profile_image=? WHERE staffId=?
        """, (staff_name, password, filename, staff_id))
        conn.commit()
        
        session['staffName'] = staff_name
        flash('Profile updated successfully!')
        return redirect(url_for('profile'))

    user = conn.execute("SELECT * FROM staff WHERE staffId = ?", (staff_id,)).fetchone()
    conn.close()
    return render_template('profile.html', user=user)
    
#RUN
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
