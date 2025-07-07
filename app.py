from flask import Flask, render_template, request, redirect, jsonify, url_for, flash, session
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import os
import hashlib  # For simple password hashing

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "your_secret_key_here")

# Google Sheets setup
SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# Safe path to service account file (works locally and in deployment)
SERVICE_ACCOUNT_FILE = os.path.join(os.path.dirname(__file__), "service-account.json")
CREDS = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPE)

client = gspread.authorize(CREDS)
spreadsheet = client.open_by_key("14gdbzzP2YnreA7PnYF7RWgjRmkuilAIdHZCnuzUNyaE")

worksheet_ratelist = spreadsheet.worksheet("Ratelist")
worksheet_garage = spreadsheet.worksheet("GarageList")
worksheet_users = spreadsheet.worksheet("Users")  # Users sheet for login/register

# Helper function to get or create outlet-specific worksheet
def get_outlet_worksheet(base_sheet_name, outlet):
    """
    Returns a worksheet object for the given outlet.
    Sheet name pattern: base_sheet_name + '_' + outlet
    Creates new sheet with headers copied from base_sheet_name if not exist.
    """
    sheet_name = f"{base_sheet_name}_{outlet}"
    try:
        return spreadsheet.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        base_sheet = spreadsheet.worksheet(base_sheet_name)
        headers = base_sheet.row_values(1)
        new_sheet = spreadsheet.add_worksheet(title=sheet_name, rows="1000", cols=str(len(headers)))
        new_sheet.append_row(headers, value_input_option="USER_ENTERED")
        return new_sheet
# -----------------------------------
# Helper functions - NEW SECTION
# -----------------------------------

def hash_password(password: str) -> str:
    # Simple SHA256 hashing (you can improve this with salt etc.)
    return hashlib.sha256(password.encode()).hexdigest()

def check_user_exists(username):
    users = worksheet_users.get_all_records()
    for user in users:
        if user.get("Username") == username:  # Use capitalized key as per sheet header
            return True
    return False

def verify_user(username, password):
    users = worksheet_users.get_all_records()
    hashed = hash_password(password)
    for user in users:
        if user.get("Username") == username and user.get("Password") == hashed:
            return True
    return False

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "username" not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

# ----------------------------------
# Example updated route using outlet sheet for purchase save
# ----------------------------------

@app.route('/')
@login_required  # Protect dashboard, only logged-in users can access
def dashboard():
    return render_template("index.html")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username').strip()
        password = request.form.get('password').strip()

        if verify_user(username, password):
            session['username'] = username
            
            # Fetch outlet from Users sheet for this username
            users = worksheet_users.get_all_records()
            user_outlet = next((u.get("Outlet", "").strip() for u in users if u.get("Username") == username), "")
            session['outlet'] = user_outlet
            
            flash(f"Welcome {username}, you are logged in!", "success")
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid username or password", "error")
            return redirect(url_for('login'))

    return render_template("login.html")
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        outlet = request.form.get('outlet', '').strip()

        if not (username and email and password and outlet):
            flash("All fields are required.", "error")
            return redirect(url_for('register'))

        # Check if username already exists
        users = worksheet_users.get_all_records()
        if any(user.get("Username", "").strip() == username for user in users):
            flash("Username already exists. Please choose another.", "error")
            return redirect(url_for('register'))

        hashed_password = hash_password(password)

        # Append new user row: Username, Email, Password(hashed), Outlet
        worksheet_users.append_row([username, email, hashed_password, outlet], value_input_option="USER_ENTERED")

        flash("Registration successful! Please log in.", "success")
        return redirect(url_for('login'))

    # GET request just render register form
    return render_template("register.html")
@app.route('/logout')
def logout():
    session.pop('username', None)
    flash("You have been logged out.", "info")
    return redirect(url_for('login'))

# Now update your routes to also handle Outlet where needed,
# and protect routes with login_required decorator

@app.route('/purchase')
@login_required
def purchase():
    records = worksheet_ratelist.get_all_records()
    products = [
        {"name": str(row.get("PRODUCT", "")).strip(), "price": row.get("DP")}
        for row in records if row.get("PRODUCT") and isinstance(row.get("DP"), (int, float))
    ]
    # Get distinct outlets from Users sheet for dropdown in forms
    users_data = worksheet_users.get_all_records()
    outlets = sorted({user.get("Outlet", "").strip() for user in users_data if user.get("Outlet")})
    return render_template("purchase.html", products=products, outlets=outlets)
@app.route('/sales')
@login_required
def sales():
    ratelist = worksheet_ratelist.get_all_records()
    garage = worksheet_garage.get_all_records()
    battery_prices = {}

    for row in ratelist:
        product = str(row.get("PRODUCT", "")).strip()
        if product:
            dp = float(row.get("DP") or 0)
            old = float(row.get("OLD") or 0)
            mrp = float(row.get("MRP") or 0)
            battery_prices[product] = {
                "DP": dp,
                "MRP": mrp,
                "OldPrice": old,
                "FreeReplacementLoss": dp - old
            }

    for row in garage:
        product = str(row.get("PRODUCT", "")).strip()
        if product:
            battery_prices.setdefault(product, {})
            battery_prices[product]["GarageMRP"] = float(row.get("MRP") or 0)
            battery_prices[product]["GarageDP"] = float(row.get("DP") or 0)

    free_replacement_loss_list = []
    for product, data in battery_prices.items():
        loss = data.get("FreeReplacementLoss", 0)
        dp = data.get("DP", 0)
        old = data.get("OldPrice", 0)
        ah = next((r.get("AH") for r in ratelist if r.get("PRODUCT") == product), "")
        free_replacement_loss_list.append({
            "PRODUCT": product,
            "AH": ah,
            "DP": dp,
            "OLD": old,
            "LOSS": loss
        })

    users_data = worksheet_users.get_all_records()
    outlets = sorted({user.get("Outlet", "").strip() for user in users_data if user.get("Outlet")})

    return render_template("sales.html", battery_prices=battery_prices, outlets=outlets,
                           free_replacement_loss_list=free_replacement_loss_list)
@app.route('/stock')
@login_required
def stock():
    user_outlet = session.get("outlet", "").strip()

    # Get outlet-specific worksheets for purchase and sales
    worksheet_purchased_outlet = get_outlet_worksheet("purchaseddata", user_outlet)
    worksheet_sales_outlet = get_outlet_worksheet("salesdata", user_outlet)

    purchase_data = worksheet_purchased_outlet.get_all_records()
    sales_data = worksheet_sales_outlet.get_all_records()

    stock_dict = {}

    for row in purchase_data:
        battery = row.get('Battery Type') or row.get('battery')
        qty = row.get('Quantity') or row.get('Qty')
        outlet = row.get('Outlet', '').strip()
        if battery and qty:
            try:
                stock_dict[battery] = stock_dict.get(battery, 0) + int(qty)
            except:
                continue

    for row in sales_data:
        battery = row.get('New Battery') or row.get('Battery')
        qty = row.get('Quantity') or row.get('Qty')
        outlet = row.get('Outlet', '').strip()
        if battery and qty:
            try:
                stock_dict[battery] = stock_dict.get(battery, 0) - int(qty)
            except:
                continue

    stock_list = [{"battery": k, "quantity": v} for k, v in stock_dict.items()]

    return render_template('stock.html', stock=stock_list)

@app.route('/scrap')
@login_required
def scrap():
    user_outlet = session.get("outlet", "").strip()

    worksheet_scrap_outlet = get_outlet_worksheet("ScrapData", user_outlet)
    scrap_data = worksheet_scrap_outlet.get_all_records()

    ratelist = worksheet_ratelist.get_all_records()

    old_price_lookup = {str(row.get("PRODUCT", "")).strip(): float(row.get("OLD") or 0) for row in ratelist}
    dp_price_lookup = {str(row.get("PRODUCT", "")).strip(): float(row.get("DP") or 0) for row in ratelist}

    scrap_summary = {}
    total_qty = 0
    total_value = 0
    total_loss = 0

    for row in scrap_data:
        battery = row.get("Battery", "").strip()
        source = row.get("Source", "").strip().title()
        qty = int(row.get("Quantity", 0))
        outlet = row.get("Outlet", "").strip()

        old_price = old_price_lookup.get(battery, 0)
        dp_price = dp_price_lookup.get(battery, 0)

        value = qty * old_price
        loss = qty * (dp_price - old_price)

        key = (battery, source, outlet)
        if key not in scrap_summary:
            scrap_summary[key] = {"quantity": 0, "value": 0, "loss": 0}
        scrap_summary[key]["quantity"] += qty
        scrap_summary[key]["value"] += value
        scrap_summary[key]["loss"] += loss

        total_qty += qty
        total_value += value
        total_loss += loss

    scrap_list = [
        {
            "battery": b,
            "source": s,
            "outlet": o,
            "quantity": d["quantity"],
            "value": d["value"],
            "loss": d["loss"]
        }
        for (b, s, o), d in scrap_summary.items()
    ]

    return render_template(
        "scrap.html",
        scrap_list=scrap_list,
        total_qty=total_qty,
        total_value=total_value,
        total_loss=total_loss
    )
@app.route('/expense', methods=['GET', 'POST'])
@login_required
def expense():
    user_outlet = session.get("outlet", "").strip()
    worksheet_expense_outlet = get_outlet_worksheet("ExpenseData", user_outlet)

    if request.method == 'POST':
        date = request.form.get('date')
        category = request.form.get('finalCategory')
        description = request.form.get('description')
        amount = request.form.get('amount')

        if not (date and category and description and amount):
            flash("All fields are required.", "error")
            return redirect(url_for('expense'))

        try:
            amount_float = float(amount)
        except ValueError:
            flash("Amount must be a number.", "error")
            return redirect(url_for('expense'))

        worksheet_expense_outlet.append_row([date, category, description, amount_float, user_outlet], value_input_option="USER_ENTERED")
        flash("Expense saved successfully!", "success")
        return redirect(url_for('expense'))

    all_expense_data = worksheet_expense_outlet.get_all_records()
    return render_template('expense.html', expenses=all_expense_data)
@app.route('/profitloss')
@login_required
def profit_loss():
    user_outlet = session.get("outlet", "").strip()

    # Get outlet-specific worksheets dynamically
    worksheet_sales_outlet = get_outlet_worksheet("salesdata", user_outlet)
    worksheet_purchased_outlet = get_outlet_worksheet("purchaseddata", user_outlet)
    worksheet_scrap_outlet = get_outlet_worksheet("ScrapData", user_outlet)
    worksheet_expense_outlet = get_outlet_worksheet("ExpenseData", user_outlet)

    # Fetch data from outlet-specific sheets
    all_sales = worksheet_sales_outlet.get_all_records()
    all_purchases = worksheet_purchased_outlet.get_all_records()
    all_scrap_data = worksheet_scrap_outlet.get_all_records()
    all_expenses_raw = worksheet_expense_outlet.get_all_records()
    ratelist = worksheet_ratelist.get_all_records()  # ratelist remains common

    # Clean expense keys (strip spaces)
    def clean_keys(records):
        return [{k.strip(): v for k, v in row.items()} for row in records]

    expenses = clean_keys(all_expenses_raw)

    # Map PRODUCT to OLD price for scrap calculations from common ratelist
    old_price_map = {
        row.get("PRODUCT", "").strip(): float(row.get("OLD") or 0)
        for row in ratelist if row.get("PRODUCT")
    }

    # Helper to sum amounts from keys
    def parse_amounts(records, keys):
        total = 0
        for r in records:
            for key in r:
                if key.strip().lower() in keys:
                    try:
                        total += float(r[key])
                    except (ValueError, TypeError):
                        pass
        return total

    # Calculate totals
    total_sales = parse_amounts(all_sales, ['final amount', 'final ₹', 'final rupees', 'final'])
    total_purchase = parse_amounts(all_purchases, ['total', 'amount', 'total amount'])
    total_expense = parse_amounts(expenses, ['amount'])

    # Free replacement loss calculation (old battery price * qty)
    total_free_replacement = sum(
        int(r.get("Quantity", 0)) * old_price_map.get(r.get("Battery", "").strip(), 0)
        for r in all_scrap_data if r.get("Source", "").strip().lower() == "free replacement"
    )

    # Gross profit = sum of Profit column in sales
    profit_sum = 0
    for row in all_sales:
        try:
            profit_sum += float(row.get("Profit") or 0)
        except:
            pass

    gross_profit = profit_sum

    # Net profit = gross profit - free replacement loss - expenses
    net_profit = gross_profit - total_free_replacement - total_expense

    return render_template("profitloss.html",
                           total_sales=total_sales,
                           total_purchase=total_purchase,
                           gross_profit=gross_profit,
                           total_free_replacement=total_free_replacement,
                           total_expense=total_expense,
                           net_profit=net_profit,
                           outlet=user_outlet)

@app.route('/api/save_sales', methods=['POST'])
@login_required
def save_sales():
    data = request.get_json()
    outlet = session.get("outlet", "").strip()
    
    worksheet_sales = get_outlet_worksheet("salesdata", outlet)
    worksheet_scrap = get_outlet_worksheet("ScrapData", outlet)
    
    old_batteries = [
        b for b in data.get("oldBatteries", [])
        if b.get("battery", "").strip() and int(b.get("qty", 0)) > 0
    ]

    old_battery_summary = ", ".join([f"{b['battery']} x{b['qty']}" for b in old_batteries])
    old_battery_total_qty = sum(int(b['qty']) for b in old_batteries)
    sale_type = data.get("salesType", "").strip()
    new_battery = data.get("newBattery", "").strip()
    quantity = int(data.get("quantity", 0))
    battery_price = float(data.get("batteryPrice", 0))

    # ratelist and garagelist remain common sheets
    ratelist = worksheet_ratelist.get_all_records()
    garagelist = worksheet_garage.get_all_records()

    ratelist_map = {str(row.get("PRODUCT", "")).strip(): row for row in ratelist}
    garagelist_map = {str(row.get("PRODUCT", "")).strip(): row for row in garagelist}

    profit = 0
    if sale_type.lower() == "customer":
        row = ratelist_map.get(new_battery, {})
        profit = (float(row.get("MRP", 0)) - float(row.get("DP", 0))) * quantity
    elif sale_type.lower() == "garage":
        row = garagelist_map.get(new_battery, {})
        profit = (float(row.get("MRP", 0)) - float(row.get("DP", 0))) * quantity
    elif sale_type.lower() == "dealer":
        profit = 0
    elif "free" in sale_type.lower():
        profit = 0

    row = [
        data.get("saleDate"),
        sale_type,
        new_battery,
        quantity,
        battery_price,
        old_battery_summary,
        old_battery_total_qty,
        data.get("oldBatteryTotal"),
        data.get("totalRupees"),
        data.get("discount"),
        data.get("finalAmount"),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        outlet,
        profit
    ]

    worksheet_sales.append_row(row, value_input_option="USER_ENTERED")

    # Scrap logic
    sale_date = data.get("saleDate")

    for b in old_batteries:
        qty = int(b.get('qty', 0))
        battery_name = b.get('battery', '').strip()
        if qty > 0 and battery_name:
            scrap_row = [sale_date, sale_type, battery_name, qty, outlet]
            worksheet_scrap.append_row(scrap_row, value_input_option="USER_ENTERED")

    if "free" in sale_type.lower() and quantity > 0 and new_battery:
        row = ratelist_map.get(new_battery, {})
        dp = float(row.get("DP", 0))
        old = float(row.get("OLD", 0))
        total_loss = (dp - old) * quantity
        scrap_row = [sale_date, sale_type, new_battery, quantity, outlet, total_loss]
        worksheet_scrap.append_row(scrap_row, value_input_option="USER_ENTERED")

    return jsonify({"message": "Sale Saved!"})

# ----------------------------------
# Example updated route for expense POST save
# ----------------------------------
@app.route('/api/save_bulk_purchase', methods=['POST'])
@login_required
def save_bulk_purchase():
    data = request.get_json()

    purchase_date = data.get("purchaseDate", "")
    vendor = data.get("vendor", "")
    outlet = session.get("outlet", "").strip()
    items = data.get("items", [])

    if not purchase_date or not vendor or not items:
        return jsonify({"error": "Missing fields"}), 400

    # Get outlet-specific purchase worksheet
    worksheet_purchased = get_outlet_worksheet("purchaseddata", outlet)

    for item in items:
        battery_type = item.get("batteryType", "").strip()
        quantity = int(item.get("quantity", 0))
        unit_price = float(item.get("unitPrice", 0))
        total = float(item.get("total", 0))

        if battery_type and quantity > 0:
            row = [
                purchase_date,
                vendor,
                battery_type,
                quantity,
                unit_price,
                total,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                outlet
            ]
            worksheet_purchased.append_row(row, value_input_option="USER_ENTERED")

    return jsonify({"message": "Purchase saved successfully"})
@app.route('/api/get_all_prices', methods=['GET'])
@login_required
def get_all_prices():
    ratelist = worksheet_ratelist.get_all_records()
    garage = worksheet_garage.get_all_records()
    price_map = {}

    # Normalize ratelist
    for row in ratelist:
        product = str(row.get("PRODUCT", "")).strip().upper()
        if product:
            dp = float(str(row.get("DP") or 0).replace(",", "").strip())
            old = float(str(row.get("OLD") or row.get("Old") or 0).replace(",", "").strip())
            mrp = float(str(row.get("MRP") or row.get("M.R.P") or 0).replace(",", "").strip())

            price_map[product] = {
                "DP": dp,
                "MRP": mrp,
                "OldPrice": old,
                "FreeReplacementLoss": dp - old
            }

    # Normalize garage sheet
    for row in garage:
        product = str(row.get("PRODUCT", "")).strip().upper()
        if product:
            price_map.setdefault(product, {})
            price_map[product]["Garage"] = float(str(row.get("SELLING") or 0).replace(",", "").strip())

    return jsonify(price_map)
@app.route('/api/simple_summary')
@login_required
def summary():
    all_sales = worksheet_sales.get_all_records()
    all_purchases = worksheet_purchased.get_all_records()
    user_outlet = session.get("outlet", "").strip()

    sales = [r for r in all_sales if r.get("Outlet", "").strip() == user_outlet]
    purchases = [r for r in all_purchases if r.get("Outlet", "").strip() == user_outlet]

    def total_amount(records, keys):
        total = 0
        for row in records:
            for key in row:
                if key.strip().lower() in keys:
                    try:
                        total += float(row[key])
                    except:
                        pass
        return total

    total_profit = total_amount(sales, ['final amount', 'final ₹', 'final rupees', 'final'])
    total_expense = total_amount(purchases, ['total', 'amount', 'total amount'])
    net_profit = total_profit - total_expense

    return jsonify({
        "profit": total_profit,
        "expense": total_expense,
        "net": net_profit
    })

@app.route('/api/summary')
@login_required
def api_summary():
    # Load data from Google Sheets
    sales = worksheet_sales.get_all_records()
    purchases = worksheet_purchased.get_all_records()
    scrap_data = worksheet_scrap.get_all_records()
    expenses = worksheet_expense.get_all_records()
    ratelist = worksheet_ratelist.get_all_records()

    old_price_map = {
        row.get("PRODUCT", "").strip(): float(row.get("OLD") or 0)
        for row in ratelist if row.get("PRODUCT")
    }

    def parse_amounts(records, keys):
        total = 0
        for r in records:
            for key in r:
                if key.strip().lower() in keys:
                    try:
                        total += float(r[key])
                    except:
                        continue
        return total

    total_sales = parse_amounts(sales, ['final', 'final amount', 'final ₹', 'final rupees'])
    total_purchase = parse_amounts(purchases, ['total', 'amount', 'total amount'])
    total_expense = sum(
        float(e.get("Amount", 0)) for e in expenses if e.get("Amount")
    )
    total_free_replacement = sum(
        int(r.get("Quantity", 0)) * old_price_map.get(r.get("Battery", "").strip(), 0)
        for r in scrap_data if r.get("Source", "").strip().lower() == "free replacement"
    )

    net_profit = total_purchase - total_sales - total_free_replacement - total_expense

    return jsonify({
        "purchase": total_purchase,
        "sales": total_sales,
        "scrap": total_free_replacement,
        "expense": total_expense,
        "net_profit": net_profit
    })

# -------------------------------
# Run Flask app
# -------------------------------

if __name__ == '__main__':
    app.run(debug=True)
