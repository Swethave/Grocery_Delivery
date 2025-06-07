from flask import Flask, render_template, request, redirect, session, flash, jsonify
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
import requests 
import json


app = Flask(__name__)
app.secret_key = 'swetha123@'  # Use a secure key in production

# MySQL connection
conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="Swetha123@",  
    database="grocery_deli"
)
# Removed global cursor usage to avoid conflicts

def reverse_geocode(lat, lon):
    url = f"https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat={lat}&lon={lon}"
    headers = {'User-Agent': 'YourAppName/1.0'}  # Nominatim requires a User-Agent header

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        return data.get('display_name', None)
    else:
        print("Reverse geocoding failed:", response.text)
        return None


# Home
@app.route('/')
def index():
    if 'user' in session:
        return render_template('home.html', user=session['user'])
    return render_template('index.html')

# Registration
@app.route('/register', methods=['GET', 'POST'])
def register():
    role = request.args.get('role') or request.form.get('role') or 'buyer'

    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])

        address = request.form.get('address') if role == 'seller' else None
        latitude = request.form.get('latitude') if role == 'seller' else None
        longitude = request.form.get('longitude') if role == 'seller' else None

        with conn.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
            existing_user = cursor.fetchone()

            if existing_user:
                if role == 'seller':
                    cursor.execute("""
                        UPDATE users 
                        SET address = %s, latitude = %s, longitude = %s 
                        WHERE email = %s
                    """, (address, latitude, longitude, email))
                    conn.commit()
                    return render_template('register.html', message='Email already exists. Address updated.', role=role)
                else:
                    return render_template('register.html', message='Email already exists. Please login.', role=role)

            cursor.execute("""
                INSERT INTO users (name, email, password, role, address, latitude, longitude)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (name, email, password, role, address, latitude, longitude))
            conn.commit()

        return render_template('register.html', message='Registered successfully. Please login.', role=role)

    return render_template('register.html', role=role)


# Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password_input = request.form['password']
        role = request.form.get('role')

        with conn.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT id, name, email, password, role FROM users WHERE email = %s", (email,))
            user = cursor.fetchone()

        if user and check_password_hash(user['password'], password_input):
            session['user'] = user  # include role here for admin checks
            if role == 'buyer':
                return redirect('/buyer_view')
            elif role == 'seller':
                return redirect('/seller_dashboard')
            else:
                return redirect('/')

        flash("Invalid email or password.")
        return render_template('login.html', role=role)

    role = None
    if 'seller' in request.args:
        role = 'seller'
    elif 'buyer' in request.args:
        role = 'buyer'

    return render_template('login.html', role=role)


# Seller Dashboard
@app.route('/seller_dashboard')
def seller_dashboard():
    if 'user' not in session:
        return redirect('/login')

    user = session['user']
    products = []

    try:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute("""
                SELECT id, seller_id, name, price, weight, unit, seller_email
                FROM products 
                WHERE seller_email = %s
            """, (user['email'],))
            products = cursor.fetchall()
    except mysql.connector.Error as err:
        print("Database Error:", err)
        flash("Failed to load seller dashboard.")
        products = []

    return render_template('seller_dashboard.html', user=user, products=products)

@app.route('/delete_product_ajax/<int:product_id>', methods=['POST'])
def delete_product_ajax(product_id):
    if 'user' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM products WHERE id = %s", (product_id,))
            conn.commit()
        return jsonify({'success': True})
    except mysql.connector.Error as err:
        print("Database Error:", err)
        return jsonify({'success': False, 'message': str(err)}), 500


@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')

# Add products
@app.route('/add_product', methods=['GET', 'POST'])
def add_product():
    if 'user' not in session:
        return redirect('/login')

    if request.method == 'POST':
        name = request.form['name'].strip()
        price = float(request.form['price'])
        weight = float(request.form['weight'])
        unit = request.form['unit'].strip()
        seller_email = session['user']['email']
        seller_id = session['user']['id']

        try:
            with conn.cursor(dictionary=True) as cursor:
                cursor.execute("""
                    SELECT * FROM products 
                    WHERE name = %s AND seller_email = %s
                """, (name, seller_email))
                existing_product = cursor.fetchone()

                if existing_product:
                    flash('Product name already exists. Please use a different product name.')
                else:
                    cursor.execute("""
                        INSERT INTO products (name, price, weight, unit, seller_email, seller_id)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (name, price, weight, unit, seller_email, seller_id))
                    flash('New product added successfully.')
                conn.commit()
        except mysql.connector.Error as err:
            print("Database Error:", err)
            flash('A database error occurred.')

    return render_template('add_product.html')

# Buyer View
@app.route('/buyer_view')
def buyer_view():
    if 'user' not in session:
        return redirect('/login')

    with conn.cursor(dictionary=True) as cursor:
        cursor.execute("""
            SELECT p.id as product_id, p.name as product_name, p.price, p.weight, p.unit,
                   u.id as seller_id, u.name as seller_name, u.email as seller_email, u.address
            FROM products p
            JOIN users u ON p.seller_id = u.id
            ORDER BY u.name, p.name
        """)
        rows = cursor.fetchall()

    sellers = {}
    for row in rows:
        seller_email = row['seller_email']
        if seller_email not in sellers:
            sellers[seller_email] = {
                'name': row['seller_name'],
                'email': seller_email,
                'location': row['address'] or 'No address',
                'products': []
            }
        if row['weight'] > 0:
            sellers[seller_email]['products'].append({
                'id': row['product_id'],
                'name': row['product_name'],
                'price': row['price'],
                'weight': row['weight'],
                'unit': row['unit']
            })

    return render_template('buyer_view.html', sellers=sellers.values())

# Admin Dashboard
@app.route('/admin_dashboard')
def admin_dashboard():
    if 'user' not in session or session['user'].get('role') != 'admin':
        return redirect('/login')

    try:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute("""
                SELECT id, name, email, role 
                FROM users
                ORDER BY role, name
            """)
            users = cursor.fetchall()
    except mysql.connector.Error as err:
        print("Database Error:", err)
        users = []

    return render_template('admin_dashboard.html', users=users)

# Update product weight
@app.route('/update_weight', methods=['POST'])
def update_weight():
    print("DEBUG: Request received. JSON =", request.get_json())
    if 'user' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    data = request.get_json()
    product_id = data.get('product_id')
    delta_qty = data.get('delta_qty')

    if product_id is None or delta_qty is None:
        return jsonify({'success': False, 'message': 'Invalid request'}), 400

    try:
        product_id = int(product_id)
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Invalid product ID'}), 400

    print(f"DEBUG: product_id received: {product_id}, delta_qty: {delta_qty}")

    try:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT weight, unit FROM products WHERE id = %s", (product_id,))
            product = cursor.fetchone()

            print(f"DEBUG: product fetched from DB: {product}")

            if not product:
                return jsonify({'success': False, 'message': 'Product not found'}), 404

            current_weight = float(product['weight'])
            unit = product['unit']
            unit_weight = 1

            new_weight = current_weight - (delta_qty * unit_weight)

            if new_weight < 0:
                return jsonify({'success': False, 'message': 'Not enough stock available'}), 400

            cursor.execute("UPDATE products SET weight = %s WHERE id = %s", (new_weight, product_id))
            conn.commit()

        return jsonify({'success': True, 'new_weight': round(new_weight, 2), 'unit': unit})

    except mysql.connector.Error as err:
        print("Database Error:", err)
        return jsonify({'success': False, 'message': 'Database error'}), 500
    
    # Add product to cart (store in session)
@app.route('/add_to_cart/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    if 'cart' not in session:
        session['cart'] = {}

    quantity = int(request.form.get('quantity', 1))
    cart = session['cart']

    if str(product_id) in cart:
        cart[str(product_id)] += quantity
    else:
        cart[str(product_id)] = quantity

    session['cart'] = cart
    flash('Item added to cart')
    return redirect('/buyer_view')

# View Cart
@app.route('/cart')
def view_cart():
    if 'cart' not in session or not session['cart']:
        flash("Your cart is empty.")
        return redirect('/buyer_view')

    cart = session['cart']
    product_ids = list(cart.keys())

    cursor = conn.cursor(dictionary=True)
    format_strings = ','.join(['%s'] * len(product_ids))
    cursor.execute(f"SELECT * FROM products WHERE id IN ({format_strings})", tuple(product_ids))
    products = cursor.fetchall()
    cursor.close()

    cart_items = []
    total = 0
    for product in products:
        qty = cart.get(str(product['id']), 0)
        subtotal = product['price'] * qty
        total += subtotal
        cart_items.append({
            'id': product['id'],
            'name': product['name'],
            'price': product['price'],
            'quantity': qty,
            'subtotal': subtotal
        })

    return render_template('cart.html', cart_items=cart_items, total=total)

# Checkout Page
@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if 'cart' not in session or not session['cart']:
        flash("Your cart is empty.")
        return redirect('/buyer_view')

    estimated_delivery_time = 45

    # Prepare ordered items details to show on success
    ordered_items = []
    cart = session.get('cart', {})
    for pid_str, qty in cart.items():
        # Assuming you have product details in session or elsewhere
        # Replace below dummy data or integrate with your actual product lookup
        product = {'id': pid_str, 'name': f'Product {pid_str}', 'price': 100}  
        ordered_items.append({
            'name': product['name'],
            'quantity': qty,
            'subtotal': product['price'] * qty
        })

    if request.method == 'POST':
        payment_method = request.form.get('payment_method')
        upi_phone = request.form.get('upi_phone')

        if payment_method == 'UPI Payment' and (not upi_phone or upi_phone.strip() == ''):
            flash("Please enter your UPI phone number.")
            return render_template('checkout.html',
                                   estimated_delivery_time=estimated_delivery_time,
                                   show_upi=True,
                                   ordered_items=[])

        # Process order here (e.g. save to DB)

        session.pop('cart', None)
        flash(f"Order placed successfully! Payment method: {payment_method}. Estimated delivery in {estimated_delivery_time} minutes.")
        return render_template('checkout.html',
                               estimated_delivery_time=estimated_delivery_time,
                               order_success=True,
                               ordered_items=ordered_items)

    return render_template('checkout.html', estimated_delivery_time=estimated_delivery_time, show_upi=False, ordered_items=[])

@app.route('/sync_cart', methods=['POST'])
def sync_cart():
    cart_data = request.form.get('cart_data')
    print("Received cart_data:", cart_data)  # Debug print

    if not cart_data:
        flash("Cart data is missing.")
        return redirect('/buyer_view')

    try:
        cart_json = json.loads(cart_data)
    except json.JSONDecodeError as e:
        print("JSON decode error:", e)
        flash("Invalid cart data.")
        return redirect('/buyer_view')
    except Exception as e:
        print("Unexpected error during JSON parsing:", e)
        flash("An error occurred.")
        return redirect('/buyer_view')

    try:
        # Convert to session format
        session_cart = {}
        for product_id, item in cart_json.items():
            session_cart[str(product_id)] = item['quantity']
        session['cart'] = session_cart
    except Exception as e:
        print("Error processing cart JSON:", e)
        flash("An error occurred while syncing cart.")
        return redirect('/buyer_view')

    return redirect('/cart')





# Run server
if __name__ == '__main__':
    app.run(debug=True)
