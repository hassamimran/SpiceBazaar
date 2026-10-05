
from flask import Flask, render_template, request, redirect, url_for, jsonify, session, flash, Response
import sqlite3, os, hashlib, csv, io
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__)

def pk_time():
    """Current Pakistan Standard Time (UTC+5) as string."""
    from datetime import timezone
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

app.secret_key = "satrang_spiceflow_pk_2024_secret"
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spiceflow.db")


# ─────────────────────────────────────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()

    # Users table
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT,
            phone TEXT,
            role TEXT DEFAULT 'Staff',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Spices table — now per-user (user_id column)
    c.execute("""
        CREATE TABLE IF NOT EXISTS spices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            category TEXT,
            img_url TEXT,
            stock_20 INTEGER DEFAULT 0,
            stock_50 INTEGER DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    # Orders table — per-user
    c.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            order_number TEXT UNIQUE,
            customer_name TEXT,
            phone TEXT,
            city TEXT,
            salesman TEXT,
            total_amount REAL DEFAULT 0,
            status TEXT DEFAULT 'Pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    # Order items
    c.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            spice_id INTEGER,
            qty_20 INTEGER DEFAULT 0,
            qty_50 INTEGER DEFAULT 0,
            FOREIGN KEY(order_id) REFERENCES orders(id),
            FOREIGN KEY(spice_id) REFERENCES spices(id)
        )
    """)

    # Stock log — per-user
    c.execute("""
        CREATE TABLE IF NOT EXISTS stock_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            spice_id INTEGER,
            spice_name TEXT,
            packet_type TEXT,
            adjustment INTEGER,
            action TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(spice_id) REFERENCES spices(id)
        )
    """)

    conn.commit()
    conn.close()


def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()


SAMPLE_SPICES = [
    ("Lal Mirch (Red Chili)",    "Hot & Spicy",  "https://lh3.googleusercontent.com/aida-public/AB6AXuBFOCFh1ax1pTd9xmgrS5keeMDfqxyuDaizFOpMyYt0gKyMZbPPH49pPwk-AouubAkr9CQQi_i4Cnhd-9X2zn2L8bO7FdCYlGP0nA6YZvxKpYHn_IHdh6jeRZF5nyS1279sOc25PeK02FfHpaaSdaDpoyyuY7vcBC6g4aCd7PZOtfr3YwQ8r2xeVpXnXyT8UsU9ZgI6D1YBF9G48B9wGruFLkmixI7Q_F9zPOssNHmp1MDb9S-QIIolTIeXPDw0OWnU81Otn9Oa3YDh", 50, 30),
    ("Haldi (Turmeric)",         "Essentials",   "https://lh3.googleusercontent.com/aida-public/AB6AXuBTy77q_WZW1jUHmzXl3H6Y6R2MbEmen0nhsnQYzROSfk4VK4NSdPL8-tmrwbzFZ3ebMHepmkMblIqfTVZsJNC--AqWL-0kg7RR_2DhreYYCj6xM2T1JqSXdSHft94We3JQQoh14dK3eWF2FgVUGiTkC-1_i2vJ6J_5uydTkquRC_oNR6-InPCjBDLJUKqevaJIu-LtDy4SjxSD76HLEINRBfHzqYztOYrWe46eFmaAZPrhBQjFEEMpNqIJThZ659w9aQTINjTUvPug", 12, 4),
    ("Zeera (Cumin)",            "Seeds",        "https://lh3.googleusercontent.com/aida-public/AB6AXuC1Y-gfX_PLPb8xAZZpdG0SFAGEaj8gSp-ksLQ9ZXMR0KHUdrdkCxUeJM_v1sqQD071FMxe3vHxlEcICeDOzMnZ78_NtSk3xZBlrKxtwQv7wfwmiAfX-04Um5BZBJB4YVuRvCOOWCOu1mKh_YJgDJiznup9Yy-PS7XTexXL0HJqbq0SKWLa_nTCShkTFYWwaMzt2J9Txcey68Hn9SnrncQiylulNMthHXkowjwZzflMcZNhO03v4_kfBbuDx5GVRqXwY29_jDjoG6jO", 124, 88),
    ("Dhaniya (Coriander)",      "Seeds",        "https://lh3.googleusercontent.com/aida-public/AB6AXuCL9ZY2TcdxkIlu92ZlrQ41RmC-uS1X78IJegWYzAPn3m_pdO4y7iCw0zjXwy6plgCB9WhZnh7BWRQpHGp_vAn_H2DKSIL_MXy0Pkus4Be9v8Y7b4TYcWyB9pKbLJCW4RQg9t4Ptr-vEXFNQ6nEisvdEeXZ0w2HJ1f_gXPXkFgbiM81V1_rHLY0cc_mWjnqh8bLwqbsVz_pJIZEeH6qaAaQMLs9zn6KY0yl6mTFCZArSo59UOE3dEXrITChs7-jPDs0ZFd3NGBR_xHG", 80, 45),
    ("Garam Masala",             "Blends",       "https://lh3.googleusercontent.com/aida-public/AB6AXuBFOCFh1ax1pTd9xmgrS5keeMDfqxyuDaizFOpMyYt0gKyMZbPPH49pPwk-AouubAkr9CQQi_i4Cnhd-9X2zn2L8bO7FdCYlGP0nA6YZvxKpYHn_IHdh6jeRZF5nyS1279sOc25PeK02FfHpaaSdaDpoyyuY7vcBC6g4aCd7PZOtfr3YwQ8r2xeVpXnXyT8UsU9ZgI6D1YBF9G48B9wGruFLkmixI7Q_F9zPOssNHmp1MDb9S-QIIolTIeXPDw0OWnU81Otn9Oa3YDh", 35, 20),
    ("Kali Mirch (Black Pepper)","Spices",       "https://lh3.googleusercontent.com/aida-public/AB6AXuCfMmqtp2TZZpD0c3NO3BUZ-GPVxF1br1ro4uegqRnfiZQz3znhxr9BRR1E9zeLI7B4TpMi6MfKLhiRfjRN_beYwlgrvL1YWDqdjKIzKIWWH8K1MWoTntBU70GzaUXJ4svKfvcQfLf-mPmxDo6DVIVzGPTHxS6ic2MqKDh_Dgz7Z8kWDdfb2YlmGJ3tbrJNab6lLHHHvjZNfkqH3hIFLJtXtnYX0GgB8ytBcgpDxnBkD9wMWsA6N9f9AP4kP2O0ip4rI2vf6VmV4yhX", 2, 110),
    ("Kashmiri Mirch",           "Hot & Spicy",  "https://lh3.googleusercontent.com/aida-public/AB6AXuCmJtb_oTMD92yJ_E4tD1GXdTpSPS1TOMCA4nuxfmrcp9NH_dRPTHh7uA6z7mQKDcvBnGlzJsOaCuru-thTk8ndljADSNAi2nHjQHnhqSuQiWn3xwmgZNQqxn0Brhi0JxXIHVzAeBdki9u2FvxQe3n_onGKyop1JFjbhQcqbk1qhDs5SY0H6hTYWv1lS1kzTWxZVr0BboXSu5lu0TJEmLaR6RxXPNXdOfpDmwVFwfvHI2fMjNWiSiP0RSDvzzMxrPFMwqE6pb8EQeTU_c", 8, 45),
    ("Hari Elaichi (Cardamom)",  "Aromatics",    "https://lh3.googleusercontent.com/aida-public/AB6AXuB5TvX8Ju3gfo6EwEV6mnZfB96ewAPf83cEsOS-t4H9hZAJcUwHus2w5rhMr8TjAoWLU92edCnxyhxTkKjpRlR2jPKN3cyl3mELmtaSM-TpAsO5RshZIL0SYUV_KkWPp5xibsv-8KruJzhZ60-I0r3GoesVY5A3ptNCpzMlObE1OGANuf3MHF5M6qG27RR9t6xKT_DL9WFVuWNEyypGYuRsR6waPIe-G_O1UapdEAuXv4ILSn3XTqcD84plKBXUE_ReNA_4_nGFB0Lk", 56, 32),
]



def seed_spices_for_user(conn, user_id):
    """Give a brand-new user their own starter spice inventory."""
    conn.executemany(
        "INSERT INTO spices (user_id, name, category, img_url, stock_20, stock_50) VALUES (?,?,?,?,?,?)",
        [(user_id,) + s for s in SAMPLE_SPICES]
    )


@app.template_filter('pkt')
def pkt_filter(dt_str):
    """Convert UTC datetime to Pakistan Standard Time (UTC+5) and format nicely."""
    if not dt_str:
        return ''
    s = str(dt_str).strip()[:19]
    dt = None
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            dt = datetime.strptime(s, fmt)
            break
        except:
            continue
    if dt is None:
        return s[:16]
    pkt = dt + timedelta(hours=5)  # UTC → PKT
    return pkt.strftime('%d %b %Y, %I:%M %p')

init_db()


def seed_demo_account():
    """Create demo account spicebazaar@gmail.com with full dummy data."""
    conn = get_db()
    # Check if demo account exists
    existing = conn.execute("SELECT id FROM users WHERE email=?", ('spicebazaar@gmail.com',)).fetchone()
    if existing:
        conn.close()
        return
    # Create demo user
    conn.execute(
        "INSERT INTO users (email, password_hash, full_name, phone, role) VALUES (?,?,?,?,?)",
        ('spicebazaar@gmail.com', hash_pw('bazaar123'), 'Spice Bazaar ', '03001234567', 'Admin')
    )
    conn.commit()
    user = conn.execute("SELECT * FROM users WHERE email=?", ('spicebazaar@gmail.com',)).fetchone()
    u = user['id']
    # Seed spices
    seed_spices_for_user(conn, u)
    conn.commit()
    # Seed 15 dummy orders
    import random as _r
    _spices = conn.execute("SELECT * FROM spices WHERE user_id=?", (u,)).fetchall()
    _customers = [
        ("Ali Hassan","03001234567","Lahore"),
        ("Fatima Khan","03111234567","Karachi"),
        ("Usman Malik","03211234567","Islamabad"),
        ("Ayesha Raza","03311234567","Faisalabad"),
        ("Bilal Ahmed","03411234567","Multan"),
        ("Sara Qureshi","03501234567","Lahore"),
        ("Hamza Sheikh","03601234567","Rawalpindi"),
        ("Zara Hussain","03701234567","Sialkot"),
        ("Omar Farooq","03211111111","Gujranwala"),
        ("Nida Butt","03111111111","Lahore"),
        ("Tariq Jameel","03001111111","Karachi"),
        ("Sana Mirza","03311111111","Peshawar"),
        ("Kamran Akbar","03451234567","Lahore"),
        ("Hina Shahid","03211234568","Karachi"),
        ("Zubair Iqbal","03331234567","Islamabad"),
    ]
    _salesmen = ["Ahmed Raza","Zain Ali","Hassan Butt","Imran Shah"]
    _statuses = ["Delivered","Delivered","Delivered","Delivered","Dispatched","Packing","Pending"]
    _dates = [
        "2026-04-02 10:15:00","2026-04-05 11:30:00","2026-04-09 14:20:00",
        "2026-04-14 09:45:00","2026-04-19 16:10:00","2026-04-24 13:00:00",
        "2026-05-03 10:00:00","2026-05-08 13:25:00","2026-05-13 15:40:00",
        "2026-05-18 11:55:00","2026-05-23 14:30:00","2026-05-28 09:10:00",
        "2026-06-01 09:20:00","2026-06-03 12:45:00","2026-06-05 15:30:00",
    ]
    for _i, _date in enumerate(_dates):
        _cust = _customers[_i % len(_customers)]
        _onum = f"#ORD-U{u}-{9900+_i+1}"
        _chosen = _r.sample(list(_spices), min(_r.randint(2,4), len(_spices)))
        _total = sum(_r.randint(1,8)*20 + _r.randint(0,4)*50 for _ in _chosen)
        conn.execute(
            "INSERT INTO orders (user_id,order_number,customer_name,phone,city,salesman,total_amount,status,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (u, _onum, _cust[0], _cust[1], _cust[2], _salesmen[_i%4], _total, _statuses[_i%7], _date)
        )
        _oid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        for _sp in _chosen:
            conn.execute("INSERT INTO order_items (order_id,spice_id,qty_20,qty_50) VALUES (?,?,?,?)",
                        (_oid, _sp['id'], _r.randint(1,8), _r.randint(0,4)))
    conn.commit()
    conn.close()
    print("✅ Demo account created: spicebazaar@gmail.com / bazaar123")

seed_demo_account()


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access Spice Bazaar.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def uid():
    """Shorthand: current logged-in user's ID."""
    return session['user_id']


def next_order_number():
    conn = get_db()
    u = uid()
    row = conn.execute("SELECT COUNT(*) FROM orders WHERE user_id=?", (u,)).fetchone()
    conn.close()
    return f"#ORD-U{u}-{9900 + row[0] + 1}"


# ─────────────────────────────────────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    if request.method == "POST":
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE email=? AND password_hash=?",
            (email, hash_pw(password))
        ).fetchone()
        conn.close()
        if user:
            session['user_id']   = user['id']
            session['email']     = user['email']
            session['full_name'] = user['full_name'] or user['email']
            session['role']      = user['role']
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'error')
            return redirect(url_for('login'))
    return render_template("login.html", signup=False)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email     = request.form.get("email", "").strip().lower()
        password  = request.form.get("password", "")
        full_name = request.form.get("full_name", "").strip()
        phone     = request.form.get("phone", "").strip()
        role      = request.form.get("role", "Staff") or "Staff"
        if not email or not password:
            flash('Email and password are required.', 'error')
            return render_template("login.html", signup=True)
        conn = get_db()
        try:
            existing = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
            if existing:
                conn.close()
                flash('Email already registered.', 'error')
                return render_template("login.html", signup=True)
            conn.execute(
                "INSERT INTO users (email, password_hash, full_name, phone, role) VALUES (?,?,?,?,?)",
                (email, hash_pw(password), full_name, phone, role)
            )
            conn.commit()
            new_user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            # Seed this new user's own spice inventory
            seed_spices_for_user(conn, new_user['id'])
            conn.commit()
            conn.close()
            session['user_id']   = new_user['id']
            session['email']     = new_user['email']
            session['full_name'] = new_user['full_name'] or new_user['email']
            session['role']      = new_user['role']
            flash(f"Welcome, {new_user['full_name'] or email}! Your inventory is ready.", 'success')
            return redirect(url_for('dashboard'))
        except Exception as e:
            conn.close()
            flash(f'Could not create account: {str(e)}', 'error')
            return render_template("login.html", signup=True)
    return render_template("login.html", signup=True)


@app.route("/logout")
def logout():
    session.clear()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('login'))


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    return redirect(url_for('dashboard'))


# ── DASHBOARD ────────────────────────────────────────────────────────────────
@app.route("/dashboard")
@login_required
def dashboard():
    import random as _r
    conn = get_db()
    u = uid()

    # ── Stats ────────────────────────────────────────────────────────────────
    total_orders   = conn.execute("SELECT COUNT(*) FROM orders WHERE user_id=?", (u,)).fetchone()[0]
    total_revenue  = conn.execute("SELECT COALESCE(SUM(total_amount),0) FROM orders WHERE user_id=?", (u,)).fetchone()[0]
    pending_orders = conn.execute("SELECT COUNT(*) FROM orders WHERE user_id=? AND status='Pending'", (u,)).fetchone()[0]
    packing_orders = conn.execute("SELECT COUNT(*) FROM orders WHERE user_id=? AND status='Packing'", (u,)).fetchone()[0]
    dispatched     = conn.execute("SELECT COUNT(*) FROM orders WHERE user_id=? AND status='Dispatched'", (u,)).fetchone()[0]
    delivered      = conn.execute("SELECT COUNT(*) FROM orders WHERE user_id=? AND status='Delivered'", (u,)).fetchone()[0]
    total_spices   = conn.execute("SELECT COUNT(*) FROM spices WHERE user_id=?", (u,)).fetchone()[0]
    low_stock      = conn.execute("SELECT COUNT(*) FROM spices WHERE user_id=? AND (stock_20 < 10 OR stock_50 < 10)", (u,)).fetchone()[0]
    total_units    = conn.execute("SELECT COALESCE(SUM(stock_20 + stock_50),0) FROM spices WHERE user_id=?", (u,)).fetchone()[0]
    max_units      = total_spices * 200
    stock_pct      = int((total_units / max_units) * 100) if max_units else 0

    # ── Recent Orders ────────────────────────────────────────────────────────
    raw_recent = conn.execute(
        "SELECT order_number, customer_name, city, total_amount, status, created_at FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 5", (u,)
    ).fetchall()
    recent_orders = []
    for r in raw_recent:
        recent_orders.append({
            'order_number': r['order_number'],
            'customer_name': r['customer_name'],
            'city': r['city'],
            'total_amount': r['total_amount'],
            'status': r['status'],
            'display_time': r['created_at'][:16] if r['created_at'] else '',
        })

    # ── Spice Revenue ─────────────────────────────────────────────────────────
    spice_revenue_rows = conn.execute("""
        SELECT s.name, COALESCE(SUM(oi.qty_20 * 20 + oi.qty_50 * 50), 0) AS rev
        FROM spices s
        LEFT JOIN order_items oi ON s.id = oi.spice_id
        LEFT JOIN orders o ON oi.order_id = o.id AND o.user_id = ?
        WHERE s.user_id = ?
        GROUP BY s.id ORDER BY rev DESC LIMIT 5
    """, (u, u)).fetchall()
    max_spice_rev = max((r['rev'] for r in spice_revenue_rows), default=1) or 1
    spice_revenue = [
        {'name': r['name'], 'rev': r['rev'], 'pct': int((r['rev'] / max_spice_rev) * 100)}
        for r in spice_revenue_rows
    ]

    # ── Monthly Chart ─────────────────────────────────────────────────────────
    monthly_rows = conn.execute("""
        SELECT substr(created_at, 1, 7) AS ym, COALESCE(SUM(total_amount), 0) AS rev
        FROM orders WHERE user_id=?
        GROUP BY substr(created_at, 1, 7)
        ORDER BY substr(created_at, 1, 7) DESC LIMIT 6
    """, (u,)).fetchall()
    monthly_rows = list(reversed(monthly_rows))
    mn = {'01':'Jan','02':'Feb','03':'Mar','04':'Apr','05':'May','06':'Jun',
          '07':'Jul','08':'Aug','09':'Sep','10':'Oct','11':'Nov','12':'Dec'}
    max_monthly = max((r['rev'] for r in monthly_rows), default=1) or 1
    monthly_data = [
        {'month': mn.get(r['ym'][5:7], r['ym']), 'rev': r['rev'], 'pct': int((r['rev'] / max_monthly) * 100)}
        for r in monthly_rows
    ]

    conn.close()
    return render_template("dashboard.html",
        total_revenue=f"Rs. {total_revenue:,.0f}", total_revenue_raw=total_revenue,
        total_orders=total_orders, stock_pct=f"{stock_pct}%",
        pending_orders=pending_orders, packing_orders=packing_orders,
        dispatched=dispatched, delivered=delivered, low_stock=low_stock,
        recent_orders=recent_orders, spice_revenue=spice_revenue, monthly_data=monthly_data,
    )

@app.route("/inventory")
@login_required
def inventory():
    conn = get_db()
    u = uid()
    # Auto-seed spices for existing accounts that have none
    count = conn.execute("SELECT COUNT(*) FROM spices WHERE user_id=?", (u,)).fetchone()[0]
    if count == 0:
        seed_spices_for_user(conn, u)
        conn.commit()
    spices    = conn.execute("SELECT * FROM spices WHERE user_id=? ORDER BY id", (u,)).fetchall()
    stock_log_raw = conn.execute("SELECT spice_name, packet_type, adjustment, action, created_at FROM stock_log WHERE user_id=? ORDER BY id DESC LIMIT 10", (u,)).fetchall()
    stock_log = []
    for r in stock_log_raw:
        d = dict(r)
        try:
            from datetime import datetime, timedelta
            dt = datetime.strptime(d['created_at'][:19], '%Y-%m-%d %H:%M:%S')
            d['created_at'] = (dt + timedelta(hours=5)).strftime('%Y-%m-%d %H:%M')
        except: pass
        stock_log.append(d)
    last_restock = conn.execute("""
        SELECT spice_name, created_at FROM stock_log
        WHERE user_id=? AND action='Restocked' ORDER BY id DESC LIMIT 1
    """, (u,)).fetchone()
    total_variants  = conn.execute("SELECT COUNT(*)*2 FROM spices WHERE user_id=?", (u,)).fetchone()[0]
    low_stock_count = conn.execute("SELECT COUNT(*) FROM spices WHERE user_id=? AND (stock_20 < 10 OR stock_50 < 10)", (u,)).fetchone()[0]
    conn.close()
    return render_template("inventory.html",
        spices=spices, stock_log=stock_log, last_restock=last_restock,
        total_variants=total_variants, low_stock_count=low_stock_count,
    )


@app.route("/inventory/restock", methods=["POST"])
@login_required
def restock():
    spice_id    = request.form.get("spice_id")
    packet_type = request.form.get("packet_type")
    qty         = int(request.form.get("qty", 0))
    if qty <= 0:
        return redirect(url_for("inventory"))
    conn = get_db()
    u = uid()
    spice = conn.execute("SELECT * FROM spices WHERE id=? AND user_id=?", (spice_id, u)).fetchone()
    if spice:
        if packet_type == "20":
            conn.execute("UPDATE spices SET stock_20 = stock_20 + ? WHERE id=? AND user_id=?", (qty, spice_id, u))
        else:
            conn.execute("UPDATE spices SET stock_50 = stock_50 + ? WHERE id=? AND user_id=?", (qty, spice_id, u))
        conn.execute("""
            INSERT INTO stock_log (user_id, spice_id, spice_name, packet_type, adjustment, action)
            VALUES (?,?,?,?,?,?)
        """, (u, spice_id, spice["name"], f"Rs.{packet_type}", qty, "Restocked"))
        conn.commit()
    conn.close()
    return redirect(url_for("inventory"))


@app.route("/inventory/add", methods=["POST"])
@login_required
def add_spice():
    name     = request.form.get("name")
    category = request.form.get("category")
    stock_20 = int(request.form.get("stock_20", 0))
    stock_50 = int(request.form.get("stock_50", 0))
    conn = get_db()
    conn.execute("INSERT INTO spices (user_id, name, category, stock_20, stock_50) VALUES (?,?,?,?,?)",
                 (uid(), name, category, stock_20, stock_50))
    conn.commit()
    conn.close()
    return redirect(url_for("inventory"))


# ── ORDERS ────────────────────────────────────────────────────────────────────
@app.route("/orders")
@login_required
def orders():
    conn   = get_db()
    class ORow:
        def __init__(self, d):
            self.__dict__.update(d)
    raw = conn.execute("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC", (uid(),)).fetchall()
    orders = []
    for r in raw:
        d = dict(r)
        d['display_time'] = d['created_at'][:16] if d.get('created_at') else ''
        orders.append(ORow(d))
    conn.close()
    return render_template("order.html", orders=orders)


@app.route("/orders/update-status", methods=["POST"])
@login_required
def update_status():
    order_id = request.form.get("order_id")
    status   = request.form.get("status")
    conn = get_db()
    conn.execute("UPDATE orders SET status=? WHERE id=? AND user_id=?", (status, order_id, uid()))
    conn.commit()
    conn.close()
    return redirect(url_for("orders"))


@app.route("/orders/delete", methods=["POST"])
@login_required
def delete_order():
    order_id = request.form.get("order_id")
    conn = get_db()
    # Only delete if this order belongs to the current user
    order = conn.execute("SELECT id FROM orders WHERE id=? AND user_id=?", (order_id, uid())).fetchone()
    if order:
        conn.execute("DELETE FROM order_items WHERE order_id=?", (order_id,))
        conn.execute("DELETE FROM orders WHERE id=?", (order_id,))
        conn.commit()
    conn.close()
    return redirect(url_for("orders"))


# ── NEW ORDER ─────────────────────────────────────────────────────────────────
@app.route("/new-order")
@login_required
def new_order():
    conn = get_db()
    u = uid()
    # Auto-seed spices for existing accounts that have none
    count = conn.execute("SELECT COUNT(*) FROM spices WHERE user_id=?", (u,)).fetchone()[0]
    if count == 0:
        seed_spices_for_user(conn, u)
        conn.commit()
    # Fix broken Google image URLs → stable Wikipedia URLs
    spices = conn.execute("SELECT * FROM spices WHERE user_id=? ORDER BY id", (u,)).fetchall()
    conn.close()
    return render_template("new-order.html", spices=spices)


@app.route("/new-order/submit", methods=["POST"])
@login_required
def submit_order():
    customer = request.form.get("customer_name", "").strip()
    phone    = request.form.get("phone", "").strip()
    city     = request.form.get("city", "").strip()
    salesman = request.form.get("salesman", "").strip()

    if not customer or not phone or not city:
        return redirect(url_for("new_order"))

    conn   = get_db()
    u      = uid()
    spices = conn.execute("SELECT * FROM spices WHERE user_id=?", (u,)).fetchall()

    total       = 0
    order_items = []

    for spice in spices:
        qty_20 = int(request.form.get(f"qty_20_{spice['id']}", 0))
        qty_50 = int(request.form.get(f"qty_50_{spice['id']}", 0))
        if qty_20 > 0 or qty_50 > 0:
            total += qty_20 * 20 + qty_50 * 50
            order_items.append((spice["id"], qty_20, qty_50))

    if not order_items:
        conn.close()
        return redirect(url_for("new_order"))

    order_num = next_order_number()
    conn.execute("""
        INSERT INTO orders (user_id, order_number, customer_name, phone, city, salesman, total_amount, status, created_at)
        VALUES (?,?,?,?,?,?,?,'Pending',?)
    """, (u, order_num, customer, phone, city, salesman, total, pk_time()))
    order_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    for spice_id, qty_20, qty_50 in order_items:
        conn.execute("""
            INSERT INTO order_items (order_id, spice_id, qty_20, qty_50) VALUES (?,?,?,?)
        """, (order_id, spice_id, qty_20, qty_50))
        conn.execute("UPDATE spices SET stock_20 = MAX(0, stock_20-?) WHERE id=? AND user_id=?", (qty_20, spice_id, u))
        conn.execute("UPDATE spices SET stock_50 = MAX(0, stock_50-?) WHERE id=? AND user_id=?", (qty_50, spice_id, u))
        spice = conn.execute("SELECT name FROM spices WHERE id=?", (spice_id,)).fetchone()
        if qty_20 > 0:
            conn.execute("INSERT INTO stock_log (user_id, spice_id, spice_name, packet_type, adjustment, action) VALUES (?,?,?,?,?,?)",
                         (u, spice_id, spice["name"], "Rs.20", -qty_20, "Sale"))
        if qty_50 > 0:
            conn.execute("INSERT INTO stock_log (user_id, spice_id, spice_name, packet_type, adjustment, action) VALUES (?,?,?,?,?,?)",
                         (u, spice_id, spice["name"], "Rs.50", -qty_50, "Sale"))

    conn.commit()
    conn.close()
    return redirect(url_for("orders"))


# ── ANALYSIS ──────────────────────────────────────────────────────────────────
@app.route("/analysis")
@login_required
def analysis():
    conn = get_db()
    u = uid()

    total_revenue = conn.execute("SELECT COALESCE(SUM(total_amount),0) FROM orders WHERE user_id=?", (u,)).fetchone()[0]
    total_orders  = conn.execute("SELECT COUNT(*) FROM orders WHERE user_id=?", (u,)).fetchone()[0]
    delivered     = conn.execute("SELECT COUNT(*) FROM orders WHERE user_id=? AND status='Delivered'", (u,)).fetchone()[0]
    pending       = conn.execute("SELECT COUNT(*) FROM orders WHERE user_id=? AND status='Pending'", (u,)).fetchone()[0]

    top_spices = conn.execute("""
        SELECT s.name, COALESCE(SUM(oi.qty_20 + oi.qty_50), 0) AS total_sold,
               COALESCE(SUM(oi.qty_20 * 20 + oi.qty_50 * 50), 0) AS rev
        FROM spices s
        LEFT JOIN order_items oi ON s.id = oi.spice_id
        LEFT JOIN orders o ON oi.order_id = o.id AND o.user_id = ?
        WHERE s.user_id = ?
        GROUP BY s.id ORDER BY rev DESC LIMIT 6
    """, (u, u)).fetchall()

    max_rev = max((r['rev'] for r in top_spices), default=1) or 1
    top_spices_data = [
        {'name': r['name'], 'total_sold': r['total_sold'], 'rev': r['rev'], 'pct': int((r['rev'] / max_rev) * 100)}
        for r in top_spices
    ]

    city_revenue = conn.execute("""
        SELECT city, COALESCE(SUM(total_amount),0) AS rev, COUNT(*) AS orders
        FROM orders WHERE user_id=? GROUP BY city ORDER BY rev DESC LIMIT 5
    """, (u,)).fetchall()

    salesmen = conn.execute("""
        SELECT salesman, COALESCE(SUM(total_amount),0) AS rev, COUNT(*) AS orders
        FROM orders WHERE user_id=? AND salesman != '' AND salesman IS NOT NULL
        GROUP BY salesman ORDER BY rev DESC LIMIT 5
    """, (u,)).fetchall()

    monthly = conn.execute("""
        SELECT substr(created_at, 1, 7) AS ym,
               COALESCE(SUM(total_amount),0) AS rev
        FROM orders WHERE user_id=?
        GROUP BY substr(created_at, 1, 7)
        ORDER BY substr(created_at, 1, 7) DESC LIMIT 6
    """, (u,)).fetchall()
    monthly = list(reversed(monthly))
    month_names2 = {'01':'Jan','02':'Feb','03':'Mar','04':'Apr','05':'May','06':'Jun',
                    '07':'Jul','08':'Aug','09':'Sep','10':'Oct','11':'Nov','12':'Dec'}
    max_monthly = max((r['rev'] for r in monthly), default=1) or 1
    monthly_data = [
        {'month': month_names2.get(r['ym'][5:7], r['ym']), 'rev': r['rev'], 'pct': int((r['rev'] / max_monthly) * 100)}
        for r in monthly
    ]

    qty20_total = conn.execute("""
        SELECT COALESCE(SUM(oi.qty_20),0) FROM order_items oi
        JOIN orders o ON oi.order_id = o.id WHERE o.user_id=?
    """, (u,)).fetchone()[0]
    qty50_total = conn.execute("""
        SELECT COALESCE(SUM(oi.qty_50),0) FROM order_items oi
        JOIN orders o ON oi.order_id = o.id WHERE o.user_id=?
    """, (u,)).fetchone()[0]
    total_qty = qty20_total + qty50_total or 1
    pct_20    = int((qty20_total / total_qty) * 100)
    pct_50    = 100 - pct_20

    weekly_rows = conn.execute("""
        SELECT strftime('%d/%m', created_at) AS day,
               strftime('%Y-%m-%d', created_at) AS full_date,
               COALESCE(SUM(total_amount), 0) AS rev
        FROM orders WHERE user_id=? AND date(created_at) >= date('now', '-7 days')
        GROUP BY strftime('%Y-%m-%d', created_at)
        ORDER BY full_date ASC
    """, (u,)).fetchall()
    max_weekly = max((r['rev'] for r in weekly_rows), default=1) or 1
    weekly_data = [
        {'day': r['day'], 'rev': r['rev'], 'pct': int((r['rev'] / max_weekly) * 100)}
        for r in weekly_rows
    ]

    weekly_pkt = conn.execute("""
        SELECT COALESCE(SUM(oi.qty_20),0) AS w20, COALESCE(SUM(oi.qty_50),0) AS w50
        FROM order_items oi JOIN orders o ON oi.order_id = o.id
        WHERE o.user_id=? AND date(o.created_at) >= date('now', '-7 days')
    """, (u,)).fetchone()
    weekly_20 = weekly_pkt['w20'] if weekly_pkt else 0
    weekly_50 = weekly_pkt['w50'] if weekly_pkt else 0

    weekly_spice_rows = conn.execute("""
        SELECT s.name,
               COALESCE(SUM(oi.qty_20 + oi.qty_50), 0) AS total_sold,
               COALESCE(SUM(oi.qty_20 * 20 + oi.qty_50 * 50), 0) AS rev
        FROM spices s
        LEFT JOIN order_items oi ON s.id = oi.spice_id
        LEFT JOIN orders o ON oi.order_id = o.id AND o.user_id = ?
        WHERE s.user_id = ?
        GROUP BY s.id ORDER BY rev DESC LIMIT 6
    """, (u, u)).fetchall()
    max_w_rev = max((r['rev'] for r in weekly_spice_rows), default=1) or 1
    weekly_spices = [
        {'name': r['name'], 'total_sold': r['total_sold'], 'rev': r['rev'], 'pct': int((r['rev'] / max_w_rev) * 100)}
        for r in weekly_spice_rows
    ]

    packet_rows = conn.execute("""
        SELECT s.name, s.category,
               COALESCE(SUM(oi.qty_20), 0) AS qty_20,
               COALESCE(SUM(oi.qty_50), 0) AS qty_50
        FROM spices s
        LEFT JOIN order_items oi ON s.id = oi.spice_id
        LEFT JOIN orders o ON oi.order_id = o.id AND o.user_id = ?
        WHERE s.user_id = ?
        GROUP BY s.id
        ORDER BY (COALESCE(SUM(oi.qty_20),0) + COALESCE(SUM(oi.qty_50),0)) DESC
    """, (u, u)).fetchall()
    max_pkt = max((r['qty_20'] + r['qty_50'] for r in packet_rows), default=1) or 1
    packet_breakdown = [
        {
            'name': r['name'], 'category': r['category'],
            'qty_20': r['qty_20'], 'qty_50': r['qty_50'],
            'pct_20': int((r['qty_20'] / max_pkt) * 100),
            'pct_50': int((r['qty_50'] / max_pkt) * 100),
        }
        for r in packet_rows
    ]

    conn.close()
    return render_template("analysis.html",
        total_revenue=f"Rs. {total_revenue:,.0f}", total_revenue_raw=total_revenue,
        total_orders=total_orders, delivered=delivered, pending=pending,
        top_spices_data=top_spices_data, city_revenue=city_revenue, salesmen=salesmen,
        monthly_data=monthly_data, pct_20=pct_20, pct_50=pct_50,
        rev_20=qty20_total * 20, rev_50=qty50_total * 50,
        qty20_total=qty20_total, qty50_total=qty50_total,
        weekly_data=weekly_data, weekly_20=weekly_20, weekly_50=weekly_50,
        weekly_spices=weekly_spices, packet_breakdown=packet_breakdown,
    )


# ── CSV EXPORT ────────────────────────────────────────────────────────────────
@app.route("/analysis/export-csv")
@login_required
def export_csv():
    conn = get_db()
    u = uid()

    orders_data = conn.execute("""
        SELECT order_number, customer_name, phone, city, salesman,
               total_amount, status, created_at
        FROM orders WHERE user_id=? ORDER BY id DESC
    """, (u,)).fetchall()

    spice_data = conn.execute("""
        SELECT s.name, s.category,
               COALESCE(SUM(oi.qty_20), 0) AS total_20,
               COALESCE(SUM(oi.qty_50), 0) AS total_50,
               COALESCE(SUM(oi.qty_20 * 20 + oi.qty_50 * 50), 0) AS revenue
        FROM spices s
        LEFT JOIN order_items oi ON s.id = oi.spice_id
        LEFT JOIN orders o ON oi.order_id = o.id AND o.user_id = ?
        WHERE s.user_id = ?
        GROUP BY s.id ORDER BY revenue DESC
    """, (u, u)).fetchall()

    city_data = conn.execute("""
        SELECT city, COUNT(*) AS orders, COALESCE(SUM(total_amount),0) AS revenue
        FROM orders WHERE user_id=? GROUP BY city ORDER BY revenue DESC
    """, (u,)).fetchall()

    salesmen_data = conn.execute("""
        SELECT salesman, COUNT(*) AS orders, COALESCE(SUM(total_amount),0) AS revenue
        FROM orders WHERE user_id=? AND salesman != '' AND salesman IS NOT NULL
        GROUP BY salesman ORDER BY revenue DESC
    """, (u,)).fetchall()

    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["=== SPICEFLOW PAKISTAN - FULL ANALYSIS REPORT ==="])
    writer.writerow([f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"])
    writer.writerow([f"Account: {session.get('full_name', '')} ({session.get('email', '')})"])
    writer.writerow([])
    writer.writerow(["--- ALL ORDERS ---"])
    writer.writerow(["Order No", "Customer", "Phone", "City", "Salesman", "Amount (Rs)", "Status", "Date"])
    for o in orders_data:
        writer.writerow([o['order_number'], o['customer_name'], o['phone'],
                         o['city'], o['salesman'], o['total_amount'], o['status'], o['created_at'][:10]])
    writer.writerow([])
    writer.writerow(["--- SPICE PERFORMANCE ---"])
    writer.writerow(["Spice", "Category", "20Rs Pkts Sold", "50Rs Pkts Sold", "Revenue (Rs)"])
    for s in spice_data:
        writer.writerow([s['name'], s['category'], s['total_20'], s['total_50'], s['revenue']])
    writer.writerow([])
    writer.writerow(["--- CITY-WISE REVENUE ---"])
    writer.writerow(["City", "Orders", "Revenue (Rs)"])
    for c in city_data:
        writer.writerow([c['city'], c['orders'], c['revenue']])
    writer.writerow([])
    writer.writerow(["--- SALESMAN PERFORMANCE ---"])
    writer.writerow(["Salesman", "Orders", "Revenue (Rs)"])
    for s in salesmen_data:
        writer.writerow([s['salesman'], s['orders'], s['revenue']])

    filename = f"spiceflow_report_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    return Response(output.getvalue(), mimetype='text/csv',
                    headers={"Content-Disposition": f"attachment; filename={filename}"})



# ── BILL / INVOICE ────────────────────────────────────────────────────────────
@app.route("/orders/bill/<int:order_id>")
@login_required
def view_bill(order_id):
    conn = get_db()
    u = uid()
    order_raw = conn.execute("SELECT * FROM orders WHERE id=? AND user_id=?", (order_id, u)).fetchone()
    order = None
    if order_raw:
        order = dict(order_raw)
        order['display_time'] = order['created_at'][:16] if order.get('created_at') else ''
    
    if not order:
        conn.close()
        flash("Order not found.", "error")
        return redirect(url_for("orders"))
    items = conn.execute("""
        SELECT s.name, s.category, oi.qty_20, oi.qty_50,
               (oi.qty_20 * 20 + oi.qty_50 * 50) AS subtotal
        FROM order_items oi JOIN spices s ON oi.spice_id = s.id
        WHERE oi.order_id=?
    """, (order_id,)).fetchall()
    user = conn.execute("SELECT * FROM users WHERE id=?", (u,)).fetchone()
    conn.close()
    return render_template("bill.html", order=order, items=items, user=user)


# ── FIX IMAGES (one-time) ─────────────────────────────────────────────────────
@app.route("/fix-images")
@login_required
def fix_images():
    """Visit this URL once to refresh all spice images."""
    IMAGE_MAP = {
        "lal mirch":   "https://images.unsplash.com/photo-1637680248574-eda4f0571a12?w=400&h=300&fit=crop",
        "haldi":       "https://images.unsplash.com/photo-1615485500704-8e990f9900f7?w=400&h=300&fit=crop",
        "turmeric":    "https://images.unsplash.com/photo-1615485500704-8e990f9900f7?w=400&h=300&fit=crop",
        "zeera":       "https://images.unsplash.com/photo-1599909533731-0b4bc7f4b6c9?w=400&h=300&fit=crop",
        "cumin":       "https://images.unsplash.com/photo-1599909533731-0b4bc7f4b6c9?w=400&h=300&fit=crop",
        "dhaniya":     "https://images.unsplash.com/photo-1615484477778-ca3b77940c25?w=400&h=300&fit=crop",
        "coriander":   "https://images.unsplash.com/photo-1615484477778-ca3b77940c25?w=400&h=300&fit=crop",
        "garam":       "https://images.unsplash.com/photo-1596040033229-a9821ebd058d?w=400&h=300&fit=crop",
        "kali mirch":  "https://images.unsplash.com/photo-1506806732259-39c2d0268443?w=400&h=300&fit=crop",
        "black pepper":"https://images.unsplash.com/photo-1506806732259-39c2d0268443?w=400&h=300&fit=crop",
        "kashmiri":    "https://images.unsplash.com/photo-1586201375761-83865001e31c?w=400&h=300&fit=crop",
        "elaichi":     "https://images.unsplash.com/photo-1638286630122-e8b154c37069?w=400&h=300&fit=crop",
        "cardamom":    "https://images.unsplash.com/photo-1638286630122-e8b154c37069?w=400&h=300&fit=crop",
    }
    conn = get_db()
    u = uid()
    spices = conn.execute("SELECT id, name FROM spices WHERE user_id=?", (u,)).fetchall()
    updated = 0
    for s in spices:
        name_lower = s['name'].lower()
        for key, url in IMAGE_MAP.items():
            if key in name_lower:
                conn.execute("UPDATE spices SET img_url=? WHERE id=? AND user_id=?", (url, s['id'], u))
                updated += 1
                break
    conn.commit()
    conn.close()
    flash(f"✅ Updated images for {updated} spices!", "success")
    return redirect(url_for("inventory"))


# ── SEED DUMMY DATA ───────────────────────────────────────────────────────────
@app.route("/seed-demo-data")
@login_required
def seed_demo_data():
    """Seeds 3 months of realistic dummy orders into the database."""
    conn = get_db()
    u = uid()

    # Only seed if user has less than 5 orders
    count = conn.execute("SELECT COUNT(*) FROM orders WHERE user_id=?", (u,)).fetchone()[0]
    if count >= 5:
        conn.close()
        flash("Demo data already exists — you already have orders!", "error")
        return redirect(url_for("dashboard"))

    spices = conn.execute("SELECT * FROM spices WHERE user_id=?", (u,)).fetchall()
    if not spices:
        conn.close()
        flash("No spices found. Go to Inventory first.", "error")
        return redirect(url_for("dashboard"))

    import random
    customers = [
        ("Ali Hassan",     "03001234567", "Lahore"),
        ("Fatima Khan",    "03111234567", "Karachi"),
        ("Usman Malik",    "03211234567", "Islamabad"),
        ("Ayesha Raza",    "03311234567", "Faisalabad"),
        ("Bilal Ahmed",    "03411234567", "Multan"),
        ("Sara Qureshi",   "03501234567", "Lahore"),
        ("Hamza Sheikh",   "03601234567", "Rawalpindi"),
        ("Zara Hussain",   "03701234567", "Sialkot"),
        ("Omar Farooq",    "03211111111", "Gujranwala"),
        ("Nida Butt",      "03111111111", "Lahore"),
        ("Tariq Jameel",   "03001111111", "Karachi"),
        ("Sana Mirza",     "03311111111", "Peshawar"),
    ]
    salesmen = ["Ahmed Raza", "Zain Ali", "Hassan Butt", "Imran Shah"]
    statuses = ["Delivered", "Delivered", "Delivered", "Dispatched", "Packing", "Pending"]

    # Generate orders for Apr, May, Jun
    demo_dates = [
        "2026-04-03 10:15:00", "2026-04-07 11:30:00", "2026-04-12 14:20:00",
        "2026-04-18 09:45:00", "2026-04-23 16:10:00",
        "2026-05-02 10:00:00", "2026-05-08 13:25:00", "2026-05-14 15:40:00",
        "2026-05-20 11:55:00", "2026-05-26 14:30:00",
        "2026-06-01 09:20:00", "2026-06-04 12:45:00",
    ]

    order_count = conn.execute("SELECT COUNT(*) FROM orders WHERE user_id=?", (u,)).fetchone()[0]

    for i, date in enumerate(demo_dates):
        cust = customers[i % len(customers)]
        salesman = salesmen[i % len(salesmen)]
        status = statuses[i % len(statuses)]

        order_count += 1
        order_num = f"#ORD-U{u}-{9900 + order_count}"

        # Pick 2-4 random spices
        chosen = random.sample(list(spices), min(random.randint(2, 4), len(spices)))
        total = 0
        items = []
        for sp in chosen:
            q20 = random.randint(0, 5)
            q50 = random.randint(0, 3)
            if q20 == 0 and q50 == 0:
                q20 = random.randint(1, 5)
            total += q20 * 20 + q50 * 50
            items.append((sp['id'], q20, q50))

        conn.execute("""
            INSERT INTO orders (user_id, order_number, customer_name, phone, city,
                                salesman, total_amount, status, created_at)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (u, order_num, cust[0], cust[1], cust[2], salesman, total, status, date))

        oid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        for spice_id, q20, q50 in items:
            conn.execute("INSERT INTO order_items (order_id, spice_id, qty_20, qty_50) VALUES (?,?,?,?)",
                         (oid, spice_id, q20, q50))

    conn.commit()
    conn.close()
    flash(f"✅ {len(demo_dates)} demo orders added for Apr, May & Jun!", "success")
    return redirect(url_for("dashboard"))

# ── DEBUG ─────────────────────────────────────────────────────────────────────
@app.route("/debug/db")
def debug_db():
    conn = get_db()
    tables = ["users", "spices", "orders", "order_items", "stock_log"]
    data = {t: [dict(r) for r in conn.execute(f"SELECT * FROM {t}").fetchall()] for t in tables}
    conn.close()
    return jsonify(data)


if __name__ == "__main__":
    init_db()
    print("\n✅ SpiceFlow Pakistan running → http://127.0.0.1:5000\n")
    app.run(debug=True)
