from flask import Flask, request, render_template_string, Response, send_file, redirect
from functools import wraps
import csv
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# --- CONFIGURATION ---
PORT = 5001
CSV_FILE = 'finance_log.csv'
SECRET_BASE_URL = os.getenv('SECRET_BASE_URL', '/tracker83')
USERNAME = os.getenv('TRACKER_USER', 'admin')
PASSWORD = os.getenv('TRACKER_PASSWORD', 'password')

# --- ADMIN CREDENTIALS ---
# If TRACKER_ADMIN_PASSWORD is not set in .env, it defaults to the standard password.
ADMIN_PASSWORD = os.getenv('TRACKER_ADMIN_PASSWORD', PASSWORD) 

# --- CSS ---
CSS = """
<style>
    body { font-family: sans-serif; padding: 20px; max-width: 800px; margin: 0 auto; background: #f4f4f9; }
    .card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); margin-bottom: 20px; }
    input, select, button { width: 100%; padding: 10px; margin: 5px 0; border: 1px solid #ddd; border-radius: 4px; box-sizing: border-box; }
    button { background: #28a745; color: white; border: none; font-weight: bold; cursor: pointer; }
    button:hover { background: #218838; }
    .btn-blue { background-color: #007bff; }
    .btn-purple { background-color: #6f42c1; }
    .btn-red { background-color: #dc3545; width: auto; padding: 5px 10px; font-size: 0.8em; }
    .btn-red:hover { background-color: #c82333; }
    h2 { margin-top: 0; }
    h3 { margin-bottom: 10px; border-bottom: 2px solid #eee; padding-bottom: 5px; color: #333; }
    .nav { margin-bottom: 15px; font-size: 0.9em; color: #666; display: flex; justify-content: space-between; align-items: center; }
    a { text-decoration: none; color: #007bff; font-weight: bold; margin-left: 15px; }
    a:hover { text-decoration: underline; }
    
    table { width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 0.85em; }
    th, td { text-align: left; padding: 8px; border-bottom: 1px solid #ddd; }
    th { background-color: #f8f9fa; color: #555; }
    tr:hover { background-color: #f1f1f1; }
    
    /* Category Colors for Visual Pop */
    .tag-income { color: #28a745; font-weight: bold; }
    .tag-expense { color: #dc3545; font-weight: bold; }
    .tag-mileage { color: #007bff; font-weight: bold; }
</style>
"""

# --- DASHBOARD TEMPLATE ---
INDEX_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Lessons Finance Tracker</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    {{ css|safe }}
</head>
<body>
    <div class="nav">
        <span>User: {{ user }}</span>
        <div>
            <a href="{{ base_url }}/manage">📝 Manage Log</a>
            <a href="{{ base_url }}/download_csv" target="_blank">⬇ Download CSV</a>
        </div>
    </div>

    <div class="card">
        <h2>💵 Log Income</h2>
        <form action="{{ base_url }}/log_income" method="POST">
            <input type="date" name="date" required value="{{ today }}">
            <input type="text" name="student" placeholder="Student Name" required>
            <input type="number" step="0.01" name="amount" placeholder="Amount Rec'd ($)" value="25.00" required>
            <button type="submit" class="btn-purple">Save Payment (+ Calculate Tax)</button>
        </form>
    </div>

    <div class="card">
        <h2>🚗 Log Mileage</h2>
        <form action="{{ base_url }}/log_mileage" method="POST">
            <input type="date" name="date" required value="{{ today }}">
            <input type="text" name="student" placeholder="Student Name / Destination" required>
            <input type="number" step="0.1" name="miles" placeholder="Miles Driven (Round Trip)" required>
            <button type="submit">Save Trip</button>
        </form>
    </div>

    <div class="card">
        <h2>💰 Log Expense</h2>
        <form action="{{ base_url }}/log_expense" method="POST">
            <input type="date" name="date" required value="{{ today }}">
            <input type="text" name="item" placeholder="Item (e.g. Guitar Strings)" required>
            <input type="number" step="0.01" name="cost" placeholder="Cost ($)" required>
            <select name="category">
                <option value="Supplies">Supplies (Consumables)</option>
                <option value="Equipment">Equipment (Assets)</option>
                <option value="Travel">Gas/Travel</option>
                <option value="Software">Software/Services</option>
            </select>
            <button type="submit" class="btn-blue">Save Expense</button>
        </form>
    </div>
    
    {% if message %}
    <div style="text-align: center; margin-top: 20px;">
        <p style="color: green; font-weight: bold; font-size: 1.2em;">✅ {{ message }}</p>
        {% if tax_info %}
        <p style="color: #666; font-size: 0.9em;">{{ tax_info }}</p>
        {% endif %}
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
    <title>Manage Log</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    {{ css|safe }}
</head>
<body>
    <div class="nav">
        <a href="{{ base_url }}" style="margin-left: 0;">⬅ Back to Tracker</a>
        <span style="color: #dc3545; font-weight: bold;">🔒 Admin Mode</span>
    </div>

    <div class="card">
        <h2>📝 Manage Entries</h2>
        <p style="font-size: 0.8em; color: #666;">Entries are sorted by date (Newest First).</p>

        <h3 class="tag-income">💵 Income</h3>
        {% if income %}
        <div style="overflow-x: auto;">
            <table>
                <thead>
                    <tr><th>Date</th><th>Student</th><th>Amount</th><th>Tax</th><th>Net</th><th>Action</th></tr>
                </thead>
                <tbody>
                    {% for item in income %}
                    <tr>
                        <td>{{ item.row[1] }}</td>
                        <td>{{ item.row[2] }}</td>
                        <td>${{ item.row[3] }}</td>
                        <td>${{ item.row[5] }}</td>
                        <td>${{ item.row[6] }}</td>
                        <td>
                            <form action="{{ base_url }}/delete_row/{{ item.id }}" method="POST" onsubmit="return confirm('Delete this income?');">
                                <button type="submit" class="btn-red">Delete</button>
                            </form>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% else %}
        <p style="color:#999; font-style:italic;">No income recorded.</p>
        {% endif %}

        <h3 class="tag-mileage">🚗 Mileage</h3>
        {% if mileage %}
        <div style="overflow-x: auto;">
            <table>
                <thead>
                    <tr><th>Date</th><th>Destination</th><th>Miles</th><th>Action</th></tr>
                </thead>
                <tbody>
                    {% for item in mileage %}
                    <tr>
                        <td>{{ item.row[1] }}</td>
                        <td>{{ item.row[2] }}</td>
                        <td>{{ item.row[3] }} mi</td>
                        <td>
                            <form action="{{ base_url }}/delete_row/{{ item.id }}" method="POST" onsubmit="return confirm('Delete this trip?');">
                                <button type="submit" class="btn-red">Delete</button>
                            </form>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% else %}
        <p style="color:#999; font-style:italic;">No mileage recorded.</p>
        {% endif %}

        <h3 class="tag-expense">💰 Expenses</h3>
        {% if expenses %}
        <div style="overflow-x: auto;">
            <table>
                <thead>
                    <tr><th>Date</th><th>Item</th><th>Cost</th><th>Category</th><th>Action</th></tr>
                </thead>
                <tbody>
                    {% for item in expenses %}
                    <tr>
                        <td>{{ item.row[1] }}</td>
                        <td>{{ item.row[2] }}</td>
                        <td>${{ item.row[3] }}</td>
                        <td>{{ item.row[4] }}</td>
                        <td>
                            <form action="{{ base_url }}/delete_row/{{ item.id }}" method="POST" onsubmit="return confirm('Delete this expense?');">
                                <button type="submit" class="btn-red">Delete</button>
                            </form>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% else %}
        <p style="color:#999; font-style:italic;">No expenses recorded.</p>
        {% endif %}

    </div>
</body>
</html>
"""

# --- STANDARD AUTH (Dashboard) ---
def check_auth(username, password):
    return username == USERNAME and password == PASSWORD

def authenticate():
    return Response(
    'Login Required', 401,
    {'WWW-Authenticate': 'Basic realm="Lessons Tracker"'})

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

# --- ADMIN AUTH (Manage/Delete) ---
def check_admin_auth(username, password):
    return username == USERNAME and password == ADMIN_PASSWORD

def authenticate_admin():
    # Different realm forces re-authentication
    return Response(
    'Admin Password Required', 401,
    {'WWW-Authenticate': 'Basic realm="Admin Area - Sensitive Action"'})

def requires_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_admin_auth(auth.username, auth.password):
            return authenticate_admin()
        return f(*args, **kwargs)
    return decorated

# --- CSV LOGIC ---
def write_to_csv(data):
    file_exists = os.path.isfile(CSV_FILE)
    with open(CSV_FILE, 'a', newline='') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['Type', 'Date', 'Description', 'Amount/Miles', 'Category', 'Tax_Set_Aside', 'Net_Revenue'])
        writer.writerow(data)

def read_csv():
    if not os.path.isfile(CSV_FILE):
        return []
    with open(CSV_FILE, 'r') as f:
        reader = csv.reader(f)
        return list(reader)

def delete_row_by_index(index):
    rows = read_csv()
    if 0 <= index < len(rows):
        del rows[index]
        with open(CSV_FILE, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(rows)

# --- ROUTES ---
@app.route('/')
@requires_auth
def root():
    return redirect(SECRET_BASE_URL)

@app.route(SECRET_BASE_URL)
@requires_auth
def index():
    return render_template_string(INDEX_TEMPLATE, css=CSS, today=datetime.now().strftime('%Y-%m-%d'), base_url=SECRET_BASE_URL, user=USERNAME)

# --- ADMIN ROUTES (Uses requires_admin) ---
@app.route(f'{SECRET_BASE_URL}/manage')
@requires_admin
def manage():
    all_rows = read_csv()
    
    indexed_rows = []
    for i, row in enumerate(all_rows):
        if i == 0: continue
        indexed_rows.append({'id': i, 'row': row})
    
    income = [r for r in indexed_rows if r['row'][0] == 'Income']
    mileage = [r for r in indexed_rows if r['row'][0] == 'Mileage']
    expenses = [r for r in indexed_rows if r['row'][0] == 'Expense']
    
    income.sort(key=lambda x: x['row'][1], reverse=True)
    mileage.sort(key=lambda x: x['row'][1], reverse=True)
    expenses.sort(key=lambda x: x['row'][1], reverse=True)
    
    return render_template_string(
        MANAGE_TEMPLATE, 
        css=CSS, 
        income=income, 
        mileage=mileage, 
        expenses=expenses, 
        base_url=SECRET_BASE_URL
    )

@app.route(f'{SECRET_BASE_URL}/delete_row/<int:row_index>', methods=['POST'])
@requires_admin
def delete_row(row_index):
    delete_row_by_index(row_index)
    return redirect(f'{SECRET_BASE_URL}/manage')

# --- LOGGING ROUTES ---
@app.route(f'{SECRET_BASE_URL}/log_income', methods=['POST'])
@requires_auth
def log_income():
    date = request.form['date']
    student = request.form['student']
    amount = float(request.form['amount'])
    tax = round(amount * 0.20, 2)
    revenue = round(amount - tax, 2)
    write_to_csv(['Income', date, student, amount, 'Lesson', tax, revenue])
    return render_template_string(INDEX_TEMPLATE, css=CSS, today=datetime.now().strftime('%Y-%m-%d'), message=f"Payment Saved! (${amount})", tax_info=f"(Tax Aside: ${tax} | Net: ${revenue})", base_url=SECRET_BASE_URL, user=USERNAME)

@app.route(f'{SECRET_BASE_URL}/log_mileage', methods=['POST'])
@requires_auth
def log_mileage():
    write_to_csv(['Mileage', request.form['date'], request.form['student'], request.form['miles'], 'Travel', '', ''])
    return render_template_string(INDEX_TEMPLATE, css=CSS, today=datetime.now().strftime('%Y-%m-%d'), message="Trip Saved!", base_url=SECRET_BASE_URL, user=USERNAME)

@app.route(f'{SECRET_BASE_URL}/log_expense', methods=['POST'])
@requires_auth
def log_expense():
    write_to_csv(['Expense', request.form['date'], request.form['item'], request.form['cost'], request.form['category'], '', ''])
    return render_template_string(INDEX_TEMPLATE, css=CSS, today=datetime.now().strftime('%Y-%m-%d'), message="Expense Saved!", base_url=SECRET_BASE_URL, user=USERNAME)

@app.route(f'{SECRET_BASE_URL}/download_csv')
@requires_auth
def download_csv():
    return send_file(CSV_FILE, as_attachment=True, download_name=f"finance_log_{datetime.now().strftime('%Y-%m-%d')}.csv")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)
