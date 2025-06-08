from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.utils import secure_filename
import os
import sqlite3
from hashlib import sha256
from math import ceil

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# === DATABASE INITIALIZATION ===
def init_db():
    if not os.path.exists('instance'):
        os.mkdir('instance')
    with sqlite3.connect('instance/app.db') as conn:
        cur = conn.cursor()
        with open('schema.sql', 'r') as f:
            cur.executescript(f.read())
        conn.commit()

# === DB CONNECTION ===
def get_db():
    conn = sqlite3.connect('instance/app.db')
    conn.row_factory = sqlite3.Row
    return conn

# === PASSWORD HASHING ===
def hash_password(password):
    return sha256(password.encode()).hexdigest()

# === PAGINATION SETTINGS ===
ITEMS_PER_PAGE = 10

# === HOME PAGE & PRODUCT LISTING ===
@app.route('/')
def index():
    db = get_db()
    q = request.args.get('q', '').strip()
    min_price = request.args.get('min_price')
    max_price = request.args.get('max_price')
    page = int(request.args.get('page', 1))

    # Base query and params
    query = "SELECT * FROM products WHERE 1=1"
    count_query = "SELECT COUNT(*) FROM products WHERE 1=1"
    params = []

    # Filtering
    if q:
        query += " AND (name LIKE ? OR description LIKE ?)"
        count_query += " AND (name LIKE ? OR description LIKE ?)"
        like_q = f"%{q}%"
        params.extend([like_q, like_q])
    if min_price and min_price.isdigit():
        query += " AND price >= ?"
        count_query += " AND price >= ?"
        params.append(int(min_price))
    if max_price and max_price.isdigit():
        query += " AND price <= ?"
        count_query += " AND price <= ?"
        params.append(int(max_price))

    # Count total for pagination
    total_items = db.execute(count_query, params).fetchone()[0]
    total_pages = ceil(total_items / ITEMS_PER_PAGE)

    # Pagination limit
    offset = (page - 1) * ITEMS_PER_PAGE
    query += " LIMIT ? OFFSET ?"
    params.extend([ITEMS_PER_PAGE, offset])

    products = db.execute(query, params).fetchall()

    return render_template('index.html', products=products, page=page, total_pages=total_pages, q=q, min_price=min_price, max_price=max_price)

# === REGISTER ===
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        db = get_db()
        username = request.form['username']
        password = request.form['password']
        # Always create a user with role 'user' only
        db.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                   (username, password, 'user'))
        db.commit()
        flash("Registered successfully. Please login.")
        return redirect(url_for('login'))
    return render_template('register.html')
# === LOGIN ===
ADMIN_SECRET_PASSWORD="noonehavethepowertohackthisasjaishreeramyafirhanumanjimeresaathhai"

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()

        if user and user['password'] == password:
            # If password matches admin secret, user is admin
            if password == ADMIN_SECRET_PASSWORD:
                session['role'] = 'admin'
                # Optional: update DB role to admin permanently
                db.execute("UPDATE users SET role='admin' WHERE id=?", (user['id'],))
                db.commit()
            else:
                session['role'] = user['role']

            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('index'))

        flash("Invalid credentials")
    return render_template('login.html')
# === LOGOUT ===
@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully")
    return redirect(url_for('index'))

# === ADMIN DASHBOARD ===
@app.route('/admin')
def admin_dashboard():
    db = get_db()

    # Get counts and sums
    total_users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_products_count = db.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    total_orders = db.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    total_sales = db.execute("SELECT SUM(total_price) FROM orders WHERE status='completed'").fetchone()[0] or 0

    # Get all products for display in table
    product_list = db.execute("SELECT * FROM products").fetchall()

    return render_template(
        'admin_dashboard.html',
        users=total_users,
        products=product_list,
        products_count=total_products_count,
        orders=total_orders,
        sales=total_sales
    )
# === ADD PRODUCT ===
@app.route('/admin/add', methods=['GET', 'POST'])
def add_product():
    if session.get('role') != 'admin':
        flash("Admin access required")
        return redirect(url_for('login'))
    if request.method == 'POST':
        name = request.form['name']
        price = request.form['price']
        description = request.form['description']
        category = request.form['category']
        file = request.files['image']
        if not name or not price or not file:
            flash("Name, price and image are required")
            return redirect(url_for('add_product'))

        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        db = get_db()
        db.execute("INSERT INTO products (name, price, description, image, category) VALUES (?, ?, ?, ?, ?)",
                   (name, float(price), description, filename, category))
        db.commit()
        flash("Product added successfully")
        return redirect(url_for('admin_dashboard'))
    return render_template('admin_add_product.html')

# === PRODUCT DETAILS PAGE ===
@app.route('/product/<int:product_id>')
def product_detail(product_id):
    db = get_db()
    product = db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    if not product:
        flash("Product not found")
        return redirect(url_for('index'))
    # For simplicity, mock reviews can be added later
    return render_template('product_detail.html', product=product)

# === CART SYSTEM ===
@app.route('/cart')
def cart():
    if 'user_id' not in session:
        flash("Login required to view cart")
        return redirect(url_for('login'))
    db = get_db()
    user_id = session['user_id']
    cart_items = db.execute("""SELECT c.id as cart_id, p.* , c.quantity FROM cart c 
                              JOIN products p ON c.product_id = p.id 
                              WHERE c.user_id=?""", (user_id,)).fetchall()
    return render_template('cart.html', cart_items=cart_items)

@app.route('/cart/add/<int:product_id>', methods=['POST'])
def cart_add(product_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Login required'}), 401
    quantity = int(request.form.get('quantity', 1))
    user_id = session['user_id']
    db = get_db()

    # Check if product already in cart
    existing = db.execute("SELECT quantity FROM cart WHERE user_id=? AND product_id=?", (user_id, product_id)).fetchone()
    if existing:
        db.execute("UPDATE cart SET quantity = quantity + ? WHERE user_id=? AND product_id=?", (quantity, user_id, product_id))
    else:
        db.execute("INSERT INTO cart (user_id, product_id, quantity) VALUES (?, ?, ?)", (user_id, product_id, quantity))
    db.commit()
    flash("Added to cart")
    return redirect(url_for('cart'))

@app.route('/cart/remove/<int:cart_id>', methods=['POST'])
def cart_remove(cart_id):
    if 'user_id' not in session:
        flash("Login required")
        return redirect(url_for('login'))
    db = get_db()
    db.execute("DELETE FROM cart WHERE id=?", (cart_id,))
    db.commit()
    flash("Item removed from cart")
    return redirect(url_for('cart'))

# === WISHLIST ===
@app.route('/wishlist')
def wishlist():
    if 'user_id' not in session:
        flash("Login required to view wishlist")
        return redirect(url_for('login'))
    user_id = session['user_id']
    db = get_db()
    items = db.execute("""SELECT w.id as wish_id, p.* FROM wishlist w
                        JOIN products p ON w.product_id = p.id WHERE w.user_id=?""", (user_id,)).fetchall()
    return render_template('wishlist.html', items=items)

@app.route('/wishlist/add/<int:product_id>', methods=['POST'])
def wishlist_add(product_id):
    if 'user_id' not in session:
        flash("Login required")
        return redirect(url_for('login'))
    user_id = session['user_id']
    db = get_db()
    exists = db.execute("SELECT id FROM wishlist WHERE user_id=? AND product_id=?", (user_id, product_id)).fetchone()
    if not exists:
        db.execute("INSERT INTO wishlist (user_id, product_id) VALUES (?, ?)", (user_id, product_id))
        db.commit()
        flash("Added to wishlist")
    else:
        flash("Already in wishlist")
    return redirect(url_for('wishlist'))

@app.route('/wishlist/remove/<int:wish_id>', methods=['POST'])
def wishlist_remove(wish_id):
    if 'user_id' not in session:
        flash("Login required")
        return redirect(url_for('login'))
    db = get_db()
    db.execute("DELETE FROM wishlist WHERE id=?", (wish_id,))
    db.commit()
    flash("Removed from wishlist")
    return redirect(url_for('wishlist'))

# === CHECKOUT AND ORDERS ===
@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if 'user_id' not in session:
        flash("Login required for checkout")
        return redirect(url_for('login'))
    db = get_db()
    user_id = session['user_id']

    if request.method == 'POST':
        address = request.form['address']
        payment_method = request.form['payment_method']
        if not address or not payment_method:
            flash("Address and payment method are required")
            return redirect(url_for('checkout'))

        cart_items = db.execute("SELECT product_id, quantity FROM cart WHERE user_id=?", (user_id,)).fetchall()
        if not cart_items:
            flash("Cart is empty")
            return redirect(url_for('cart'))

        total_price = 0
        for item in cart_items:
            product = db.execute("SELECT price FROM products WHERE id=?", (item['product_id'],)).fetchone()
            total_price += product['price'] * item['quantity']

        # Insert order
        cur = db.cursor()
        cur.execute("INSERT INTO orders (user_id, address, payment_method, total_price, status) VALUES (?, ?, ?, ?, ?)",
                    (user_id, address, payment_method, total_price, 'pending'))
        order_id = cur.lastrowid

        # Insert order items
        for item in cart_items:
            cur.execute("INSERT INTO order_items (order_id, product_id, quantity) VALUES (?, ?, ?)",
                        (order_id, item['product_id'], item['quantity']))
        # Clear cart
        db.execute("DELETE FROM cart WHERE user_id=?", (user_id,))
        db.commit()

        flash("Order placed successfully! Status: pending")
        return redirect(url_for('order_history'))

    # GET request - show checkout page with cart and address form
    cart_items = db.execute("""SELECT c.quantity, p.* FROM cart c JOIN products p ON c.product_id = p.id WHERE c.user_id=?""", (user_id,)).fetchall()
    return render_template('checkout.html', cart_items=cart_items)

# === ORDER HISTORY ===
@app.route('/orders')
def order_history():
    if 'user_id' not in session:
        flash("Login required")
        return redirect(url_for('login'))
    user_id = session['user_id']
    db = get_db()
    orders = db.execute("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC", (user_id,)).fetchall()
    return render_template('orders.html', orders=orders)

# === PROFILE VIEW AND EDIT ===
@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        flash("Login required")
        return redirect(url_for('login'))
    db = get_db()
    user_id = session['user_id']
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        # Update username and password if provided
        if username:
            db.execute("UPDATE users SET username=? WHERE id=?", (username, user_id))
        if password:
            hashed_pw = hash_password(password)
            db.execute("UPDATE users SET password=? WHERE id=?", (hashed_pw, user_id))
        db.commit()
        flash("Profile updated")
        return redirect(url_for('profile'))
    user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return render_template('profile.html', user=user)

# === Run app ===
if __name__ == '__main__':
    if not os.path.exists('instance'):
        os.mkdir('instance')
    if not os.path.exists('instance/app.db'):
        init_db()
    app.run(host='0.0.0.0', port=3000, debug=True)
