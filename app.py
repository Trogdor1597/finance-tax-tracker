from flask import Flask, request, render_template_string, Response, send_file, redirect
from functools import wraps
import csv, sqlite3, io
from datetime import datetime
import os
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# --- CONFIGURATION ---
PORT = 5001
DB_FILE = 'finance.db'

# --- DATABASE & MIGRATION ---
def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_and_migrate_db():
    """Creates DB table and migrates existing CSV data if DB doesn't exist."""
    if not os.path.exists(DB_FILE):
        conn = get_db()
        conn.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT, date TEXT, description TEXT, amount REAL,
                category TEXT, tax_set_aside REAL, net_revenue REAL, source_account TEXT
            )
        ''')
        
        # Migration Logic
        csv_file = 'finance_log.csv'
        if os.path.exists(csv_file):
            print("Migrating CSV to SQLite...")
            with open(csv_file, 'r') as f:
                reader = csv.reader(f)
                next(reader, None) # Skip header
                rows = [r for r in reader if r]
                # Ensure row has 8 columns (pad if necessary)
                rows = [r + [''] * (8 - len(r)) for r in rows]
                conn.executemany('INSERT INTO transactions (type, date, description, amount, category, tax_set_aside, net_revenue, source_account) VALUES (?,?,?,?,?,?,?,?)', rows)
            os.rename(csv_file, csv_file + '.bak')
            print("Migration complete. CSV backed up.")
        
        conn.commit()
        conn.close()

# --- SECURITY LOADING ---
SECRET_BASE_URL = os.getenv('SECRET_BASE_URL')
if SECRET_BASE_URL and SECRET_BASE_URL.startswith('http'):
    SECRET_BASE_URL = urlparse(SECRET_BASE_URL).path

# Normalize: Ensure leading slash, remove trailing slash. If root, make empty.
SECRET_BASE_URL = (SECRET_BASE_URL or '').strip().rstrip('/')
if SECRET_BASE_URL and not SECRET_BASE_URL.startswith('/'):
    SECRET_BASE_URL = '/' + SECRET_BASE_URL

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
if not all([USERNAME, PASSWORD, ADMIN_PASSWORD]): # SECRET_BASE_URL can be empty (root)
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
        <a href="{{ base_url or '/' }}" style="margin-left:0;">⬅ Back</a>
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
@app.before_request
def enforce_security():
    """Global Security Guard: CSRF & Headers"""
    # 1. CSRF Protection for all POST requests
    if request.method == 'POST':
        origin = request.headers.get('Origin')
        referrer = request.headers.get('Referer')
        if origin and urlparse(origin).netloc != request.host:
            return Response("Security Check Failed: Origin Mismatch", 403)
        if referrer and urlparse(referrer).netloc != request.host:
            return Response("Security Check Failed: Referrer Mismatch", 403)

@app.after_request
def add_security_headers(response):
    """Tell browsers to enforce HTTPS and prevent framing."""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    # HSTS: Tell browser to ONLY use HTTPS for the next year
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self' 'unsafe-inline'; form-action 'self';"
    return response

def sanitize_for_csv(text):
    """Prevents CSV Injection (Excel formulas)"""
    text = str(text)
    if text.startswith(('=', '+', '-', '@')):
        return f"'{text}"
    return text

# --- DATABASE LOGIC ---
def write_transaction(data):
    conn = get_db()
    conn.execute('''
        INSERT INTO transactions (type, date, description, amount, category, tax_set_aside, net_revenue, source_account)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', data)
    conn.commit()
    conn.close()

def read_transactions():
    conn = get_db()
    # Order by Date DESC, then ID DESC to show newest first
    cur = conn.execute('SELECT * FROM transactions ORDER BY date DESC, id DESC')
    rows = cur.fetchall()
    conn.close()
    return rows

def delete_transaction(txn_id):
    conn = get_db()
    conn.execute('DELETE FROM transactions WHERE id = ?', (txn_id,))
    conn.commit()
    conn.close()

# --- ROUTES ---
if SECRET_BASE_URL:
    @app.route('/')
    @requires_auth
    def root():
        return redirect(SECRET_BASE_URL)

@app.route(SECRET_BASE_URL if SECRET_BASE_URL else '/')
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
    db_rows = read_transactions()
    
    # Map DB rows to the list format expected by the template
    indexed_rows = []
    for r in db_rows:
        # Reconstruct list: [Type, Date, Desc, Amount, Cat, Tax, Net, Source]
        row_list = [r['type'], r['date'], r['description'], r['amount'], r['category'], r['tax_set_aside'], r['net_revenue'], r['source_account']]
        indexed_rows.append({'id': r['id'], 'row': row_list})
    
    # Sort into Lists
    income = [r for r in indexed_rows if r['row'][0] == 'Income']
    expenses = [r for r in indexed_rows if r['row'][0] == 'Expense']
    mileage = [r for r in indexed_rows if r['row'][0] == 'Mileage']
    
    return render_template_string(
        MANAGE_TEMPLATE,
        css=CSS,
        income=income,
        expenses=expenses,
        mileage=mileage,
        base_url=SECRET_BASE_URL
    )

@app.route(f'{SECRET_BASE_URL}/delete_row/<int:txn_id>', methods=['POST'])
@requires_admin
def delete_row(txn_id):
    delete_transaction(txn_id)
    return redirect(f'{SECRET_BASE_URL}/manage')

# --- LOGGING ---
@app.route(f'{SECRET_BASE_URL}/log_income', methods=['POST'])
@requires_auth
def log_income():
    date = request.form['date']
    student = request.form['student']
    amount = float(request.form['amount'])
    source_key = request.form['source']
    
    # Calculate tax for CSV record (hidden in UI)
    tax = round(amount * 0.20, 2)
    revenue = round(amount - tax, 2)
    
    # Writes 8 columns
    write_transaction(['Income', date, student, amount, 'Lesson', tax, revenue, source_key])
    
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
    write_transaction([
        'Expense', 
        request.form['date'], 
        request.form['item'], 
        float(request.form['cost']), 
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
    write_transaction([
        'Mileage', 
        request.form['date'], 
        request.form['student'], 
        float(request.form['miles']), 
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
    # Generate CSV from DB on the fly
    rows = read_transactions()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Type', 'Date', 'Description', 'Amount', 'Category', 'Tax_Set_Aside', 'Net_Revenue', 'Source_Account'])
    for r in rows:
        writer.writerow([r['type'], r['date'], sanitize_for_csv(r['description']), r['amount'], r['category'], r['tax_set_aside'], r['net_revenue'], r['source_account']])
    
    mem = io.BytesIO()
    mem.write(output.getvalue().encode('utf-8'))
    mem.seek(0)
    return send_file(mem, as_attachment=True, download_name=f"finance_log_{datetime.now().strftime('%Y-%m-%d')}.csv", mimetype='text/csv')

# Ensure DB is ready when imported by Gunicorn
init_and_migrate_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)
