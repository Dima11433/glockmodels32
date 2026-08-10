import sqlite3

conn = sqlite3.connect('shop.db')
cur = conn.cursor()
cur.execute("SELECT value FROM settings WHERE key IN ('btn:banner:catalog','btn:banner') LIMIT 1")
row = cur.fetchone()
if not row:
    print('No banner found')
    conn.close()
    exit(0)
banner = row[0]
print('Banner:', banner)
# find products without photos
cur.execute('SELECT id FROM products')
prods = [r[0] for r in cur.fetchall()]
count = 0
for pid in prods:
    cur.execute('SELECT COUNT(*) FROM product_photos WHERE product_id = ?', (pid,))
    c = cur.fetchone()[0]
    if c == 0:
        cur.execute('INSERT INTO product_photos (product_id, file_id, position) VALUES (?, ?, ?)', (pid, banner, 0))
        count += 1
conn.commit()
print('Inserted for products:', count)
conn.close()
