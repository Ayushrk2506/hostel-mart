import sqlite3

# Connect to the database
conn = sqlite3.connect('database.db')
cursor = conn.cursor()

# Sample products to insert
sample_products = [
    ("Munch Maxx", "Snacks", 10, 12, 30, "Crunchy chocolate wafer", "uploads/munch.jpg"),
    ("Dark Fantasy Choco Fills", "Snacks", 25, 30, 20, "Delicious chocolate-filled snack", "uploads/dark_fantasy.jpg"),
    ("Bingo Mad Angles", "Chips", 18, 20, 25, "Tangy tomato flavor triangles", "uploads/bingo.jpg"),
    ("Coca-Cola Can", "Drinks", 35, 40, 15, "Chilled Coke in a can", "uploads/coke.jpg")
]

# Insert into products table
cursor.executemany('''
    INSERT INTO products (name, category, offer_price, mrp, quantity, description, image)
    VALUES (?, ?, ?, ?, ?, ?, ?)
''', sample_products)

conn.commit()
conn.close()

print("✅ Sample products inserted successfully!")
