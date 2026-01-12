from flask import Flask, request, render_template_string, Response, send_file, redirect
from functools import wraps
import csv
from datetime import datetime
import threading
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# --- CONFIGURATION ---
PORT = 5001
CSV_FILE = 'finance_log.csv'
DATA_LOCK = threading.RLock()

# --- SECURITY LOADING ---
SECRET_BASE_URL = os.getenv('SECRET_BASE_URL')
USERNAME = os.getenv('TRACKER_USER')
PASSWORD = os.getenv('TRACKER_PASSWORD')
ADMIN_PASSWORD = os.getenv('TRACKER_ADMIN_PASSWORD')

# [FIX 1] Soft Loading: If .env is missing the lists, use these defaults instead of crashing.
_sources_str = os.getenv('PAYMENT_SOURCES', '')
_expenses_str = os.getenv('EXPENSE_ACCOUNTS', '')

if _sources_str:
    PAYMENT_SOURCES = [s.strip() for s in _sources_str.split(',')]
else:
    PAYMENT_SOURCES = []

if _expenses_str:
    EXPENSE_ACCOUNTS = [s.strip() for s in _expenses_str.split(',')]
else:
    EXPENSE_ACCOUNTS = []

# [FIX 2] Updated Security Check: We only crash if the CRITICAL passwords are missing.
if not all([SECRET_BASE_URL, USERNAME, PASSWORD, ADMIN_PASSWORD]):
    raise ValueError("CRITICAL ERROR: Core secrets (URL/User/Pass) not found in .env file.")

# --- CSS ---
CSS = """
<style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; padding: 20px; max-width: 850px; margin: 0 auto; background: #f4f4f9; color: #333; }
    .card { background: white; padding: 25px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); margin-bottom: 25px; }
    h2 { margin-top: 0; font-size: 1.25rem; color: #2c3e50; }
    input, select, button { width: 100%; padding: 12px; margin: 8px 0; border: 1px solid #e1e4e8; border-radius: 6px; box-sizing: border-box; font-size: 16px; }
    button { color: white; border: none; font-weight: 600; cursor: pointer; transition: opacity 0.2s; }
    button:hover { opacity: 0.9; }
    .btn-green { background-color: #2ecc71; }
    .btn-blue { background-color: #3498db; }
    .btn-purple { background-color: #9b59b6; }
    .btn-red { background-color: #e74c3c; width: auto; padding: 6px 12px; font-size: 0.8em; }
    table { width: 100%; border-collapse: collapse; font-size: 0.9em; }
    th { text-align: left; padding: 12px 8px; border-bottom: 2px solid #eee; color: #7f8c8d; font-weight: 600; }
    td { padding: 12px 8px; border-bottom: 1px solid #f1f1f1; vertical-align: middle; }
    .nav { margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; font-size: 0.9em; }
    a { text-decoration: none; color: #3498db; font-weight: 600; margin-left: 15px; }
    .risk-high { color: #e67e22; background: #fdf2e9; padding: 2px 6px; border-radius: 4px; border: 1px solid #f5c6cb; font-size: 0.8em; }
</style>
"""

# --- DASHBOARD TEMPLATE ---
INDEX_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Finance Tracker</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    {{ css|safe }}
</head>
<body>
    <div class="nav">
        <span>👤 {{ user }}</span>
        <div>
            <a href="{{ base_url }}/manage">📋 Admin / Audit</a>
            <a href="{{ base_url }}/download_csv" target="_blank">⬇ CSV</a>
        </div>
    </div>

    <div class="card" style="border-left: 5px solid #9b59b6;">
        <h2>💵 Log Income</h2>
        <form action="{{ base_url }}/log_income" method="POST">
            <input type="date" name="date" required value="{{ today }}">
            <div style="display:flex; gap:10px;">
                <input type="text" name="student" placeholder="Student Name / Description" required style="flex:2;">
                <input type="number" step="0.01" name="amount" placeholder="$25.00" value="25.00" required style="flex:1;">
            </div>
            
            <label style="font-size:0.85em; color:#666; font-weight:bold;">Payment Method</label>
            <select name="source">
                {% for source in sources %}
                <option value="{{ source }}">{{ source }}</option>
                {% endfor %}
            </select>
            
            <button type="submit" class="btn-purple">Log Income</button>
        </form>
    </div>

    <div class="card" style="border-left: 5px solid #3498db;">
        <h2>💰 Log Expense</h2>
        <form action="{{ base_url }}/log_expense" method="POST">
            <input type="date" name="date" required value="{{ today }}">
            <input type="text" name="item" placeholder="Item / Description" required>
            <div style="display:flex; gap:10px;">
                <input type="number" step="0.01" name="cost" placeholder="Cost ($)" required style="flex:1;">
                <select name="category" style="flex:1;">
                    <option value="Supplies">Supplies</option>
                    <option value="Equipment">Equipment</option>
                    <option value="Software">Software</option>
                    <option value="Fees">Fees</option>
                    <option value="Travel">Travel</option>
                </select>
            </div>
            <select name="source">
                <option value="" disabled selected>Paid via...</option>
                {% for acc in accounts %}
                <option value="{{ acc }}">{{ acc }}</option>
                {% endfor %}
            </select>
            <button type="submit" class="btn-blue">Log Expense</button>
        </form>
    </div>

    <div class="card" style="border-left: 5px solid #2ecc71;">
        <h2>🚗 Log Mileage</h2>
        <form action="{{ base_url }}/log_mileage" method="POST">
            <input type="date" name="date" required value="{{ today }}">
            <input type="text" name="student" placeholder="Destination" required>
            <input type="number" step="0.1" name="miles" placeholder="Miles (Round Trip)" required>
            <button type="submit" class="btn-green">Log Trip</button>
        </form>
    </div>

    {% if message %}
    <div style="text-align: center; margin-top: 20px; padding: 15px; background: #e8f5e9; border-radius: 8px; color: #2e7d32;">
        <strong>✅ {{ message }}</strong>
        {% if tax_info %}<br><span style="font-size: 0.9em; opacity: 0.8;">{{ tax_info }}</span>{% endif %}
    </div>
    {% endif %}
</body>
</html>
"""

# --- MANAGE TEMPLATE ---
MANAGE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Admin Audit</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    {{ css|safe }}
</head>
<body>
    <div class="nav">
        <a href="{{ base_url }}" style="margin-left:0;">⬅ Back</a>
        <span style="color: #c0392b; font-weight: bold;">🔒 Admin Audit Mode</span>
    </div>

    <div class="card">
        <h3>Income Audit Trail</h3>
        <div style="overflow-x: auto;">
            <table>
                <thead>
                    <tr><th>Date</th><th>Student</th><th>Source</th><th>Total</th><th>Action</th></tr>
                </thead>
                <tbody>
                    {% for item in income %}
                    <tr>
                        <td>{{ item.row[1] }}</td>
                        <td>{{ item.row[2] }}</td>
                        <td>
                            {% if item.row|length > 7 %}
                                {% if 'Cash' in item.row[7] or 'Check' in item.row[7] or 'Zelle' in item.row[7] or 'Venmo' in item.row[7] %}
                                    <span class="risk-high">⚠️ {{ item.row[7] }}</span>
                                {% else %}
                                    <span style="color:#27ae60; font-size:0.8em;">✓ {{ item.row[7] }}</span>
                                {% endif %}
                            {% else %}
                                <span style="color:#999; font-style:italic; font-size:0.8em;">Legacy</span>
                            {% endif %}
                        </td>
                        <td>${{ item.row[3] }}</td>
                        <td>
                            <form action="{{ base_url }}/delete_row/{{ item.id }}" method="POST" onsubmit="return confirm('Delete?');">
                                <button type="submit" class="btn-red">Del</button>
                            </form>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>

    <div class="card">
        <h3>Mileage Log</h3>
        <table>
            <thead><tr><th>Date</th><th>Destination</th><th>Miles</th><th>Action</th></tr></thead>
            <tbody>
                {% for item in mileage %}
                <tr>
                    <td>{{ item.row[1] }}</td>
                    <td>{{ item.row[2] }}</td>
                    <td>{{ item.row[3] }} mi</td>
                    <td>
                         <form action="{{ base_url }}/delete_row/{{ item.id }}" method="POST" onsubmit="return confirm('Delete?');">
                            <button type="submit" class="btn-red">Del</button>
                        </form>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    
    <div class="card">
        <h3>Recent Expenses</h3>
        <table>
            <thead><tr><th>Date</th><th>Item</th><th>Paid Via</th><th>Cost</th><th>Action</th></tr></thead>
            <tbody>
                {% for item in expenses %}
                <tr>
                    <td>{{ item.row[1] }}</td>
                    <td>{{ item.row[2] }}</td>
                    <td>
                        {% if item.row|length > 7 %}
                            <span style="font-size:0.85em; color:#555;">{{ item.row[7] }}</span>
                        {% else %}
                            <span style="font-size:0.85em; color:#999;">Legacy</span>
                        {% endif %}
                    </td>
                    <td>${{ item.row[3] }}</td>
                    <td>
                         <form action="{{ base_url }}/delete_row/{{ item.id }}" method="POST">
                            <button type="submit" class="btn-red">Del</button>
                        </form>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</body>
</html>
"""

# --- AUTH FUNCTIONS ---
def check_auth(username, password):
    return username == USERNAME and password == PASSWORD

def authenticate():
    return Response('Login Required', 401, {'WWW-Authenticate': 'Basic realm="Tracker"'})

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

def requires_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not (auth.username == USERNAME and auth.password == ADMIN_PASSWORD):
            return Response('Admin Access Required', 401, {'WWW-Authenticate': 'Basic realm="Admin"'})
        return f(*args, **kwargs)
    return decorated

# --- HELPERS ---
def sanitize_for_csv(text):
    """Prevents CSV Injection (Excel formulas)"""
    text = str(text)
    if text.startswith(('=', '+', '-', '@')):
        return f"'{text}"
    return text

# --- CSV LOGIC ---
def write_to_csv(data):
    with DATA_LOCK:
        file_exists = os.path.isfile(CSV_FILE)
        with open(CSV_FILE, 'a', newline='') as f:
            writer = csv.writer(f)
            # Writes the new 8-column header only if file is brand new
            if not file_exists:
                writer.writerow(['Type', 'Date', 'Description', 'Amount', 'Category', 'Tax_Set_Aside', 'Net_Revenue', 'Source_Account'])
            writer.writerow(data)

def read_csv():
    with DATA_LOCK:
        if not os.path.isfile(CSV_FILE): return []
        with open(CSV_FILE, 'r') as f:
            return list(csv.reader(f))

def delete_row_by_index(index):
    with DATA_LOCK:
        rows = read_csv()
        if 0 <= index < len(rows):
            del rows[index]
            with open(CSV_FILE, 'w', newline='') as f:
                csv.writer(f).writerows(rows)

# --- ROUTES ---
@app.route('/')
@requires_auth
def root():
    return redirect(SECRET_BASE_URL)

@app.route(SECRET_BASE_URL)
@requires_auth
def index():
    return render_template_string(
        INDEX_TEMPLATE, 
        css=CSS, 
        today=datetime.now().strftime('%Y-%m-%d'), 
        base_url=SECRET_BASE_URL, 
        user=USERNAME,
        sources=PAYMENT_SOURCES, 
        accounts=EXPENSE_ACCOUNTS
    )

@app.route(f'{SECRET_BASE_URL}/manage')
@requires_admin
def manage():
    all_rows = read_csv()
    # Skip header
    indexed_rows = [{'id': i, 'row': row} for i, row in enumerate(all_rows) if i > 0]
    
    # Sort into Lists
    income = [r for r in indexed_rows if r['row'][0] == 'Income']
    expenses = [r for r in indexed_rows if r['row'][0] == 'Expense']
    mileage = [r for r in indexed_rows if r['row'][0] == 'Mileage']
    
    # Sort by Date (Newest First)
    income.sort(key=lambda x: x['row'][1], reverse=True)
    expenses.sort(key=lambda x: x['row'][1], reverse=True)
    mileage.sort(key=lambda x: x['row'][1], reverse=True)

    return render_template_string(
        MANAGE_TEMPLATE,
        css=CSS,
        income=income,
        expenses=expenses,
        mileage=mileage,
        base_url=SECRET_BASE_URL
    )

@app.route(f'{SECRET_BASE_URL}/delete_row/<int:row_index>', methods=['POST'])
@requires_admin
def delete_row(row_index):
    delete_row_by_index(row_index)
    return redirect(f'{SECRET_BASE_URL}/manage')

# --- LOGGING ---
@app.route(f'{SECRET_BASE_URL}/log_income', methods=['POST'])
@requires_auth
def log_income():
    date = request.form['date']
    student = sanitize_for_csv(request.form['student'])
    amount = float(request.form['amount'])
    source_key = request.form['source']
    
    # Calculate tax for CSV record (hidden in UI)
    tax = round(amount * 0.20, 2)
    revenue = round(amount - tax, 2)
    
    # Writes 8 columns
    write_to_csv(['Income', date, student, amount, 'Lesson', tax, revenue, source_key])
    
    return render_template_string(
        INDEX_TEMPLATE, css=CSS, today=datetime.now().strftime('%Y-%m-%d'),
        message=f"Logged ${amount}",
        tax_info=f"Source: {source_key}",
        base_url=SECRET_BASE_URL, user=USERNAME,
        sources=PAYMENT_SOURCES, accounts=EXPENSE_ACCOUNTS
    )

@app.route(f'{SECRET_BASE_URL}/log_expense', methods=['POST'])
@requires_auth
def log_expense():
    # Writes 8 columns
    write_to_csv([
        'Expense', 
        request.form['date'], 
        sanitize_for_csv(request.form['item']), 
        request.form['cost'], 
        request.form['category'], 
        '', '', 
        request.form.get('source', 'Unknown')
    ])
    return render_template_string(
        INDEX_TEMPLATE, css=CSS, today=datetime.now().strftime('%Y-%m-%d'),
        message="Expense Saved!", base_url=SECRET_BASE_URL, user=USERNAME,
        sources=PAYMENT_SOURCES, accounts=EXPENSE_ACCOUNTS
    )

@app.route(f'{SECRET_BASE_URL}/log_mileage', methods=['POST'])
@requires_auth
def log_mileage():
    # Pad to 8 columns for consistency
    write_to_csv([
        'Mileage', 
        request.form['date'], 
        sanitize_for_csv(request.form['student']), 
        request.form['miles'], 
        'Travel', 
        '', '', 
        'N/A'
    ])
    return render_template_string(
        INDEX_TEMPLATE, css=CSS, today=datetime.now().strftime('%Y-%m-%d'),
        message="Trip Saved!", base_url=SECRET_BASE_URL, user=USERNAME,
        sources=PAYMENT_SOURCES, accounts=EXPENSE_ACCOUNTS
    )

@app.route(f'{SECRET_BASE_URL}/download_csv')
@requires_auth
def download_csv():
    return send_file(CSV_FILE, as_attachment=True, download_name=f"finance_log_{datetime.now().strftime('%Y-%m-%d')}.csv")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)
