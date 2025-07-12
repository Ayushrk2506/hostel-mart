import sqlite3

conn = sqlite3.connect('database.db')
cursor = conn.cursor()

# Drop old tables if they exist (clean reset)
cursor.execute("DROP TABLE IF EXISTS orders")
cursor.execute("DROP TABLE IF EXISTS order_items")
cursor.execute("DROP TABLE IF EXISTS products")

# Create products table
cursor.execute('''
CREATE TABLE products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT,
    offer_price INTEGER NOT NULL,
    mrp INTEGER,
    quantity INTEGER,
    description TEXT,
    image TEXT
)
''')

# Create orders table (now includes mobile, order_time, and order_code)
cursor.execute('''
CREATE TABLE orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_code TEXT,
    name TEXT NOT NULL,
    room TEXT NOT NULL,
    mobile TEXT,
    payment TEXT NOT NULL,
    status TEXT DEFAULT 'Order Pending',
    order_time TEXT
)
''')

# Create order_items table
cursor.execute('''
CREATE TABLE order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER,
    product_id INTEGER,
    quantity INTEGER,
    price INTEGER,
    FOREIGN KEY(order_id) REFERENCES orders(id),
    FOREIGN KEY(product_id) REFERENCES products(id)
)
''')

conn.commit()
conn.close()
print("✅ Database initialized successfully!")
