import sqlite3, json

conn = sqlite3.connect('shop.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print('=== CATEGORIES (video_file_id) ===')
cur.execute('SELECT id, name, video_file_id FROM categories')
print(json.dumps([dict(r) for r in cur.fetchall()], ensure_ascii=False, indent=2))

print('\n=== SETTINGS (btn/link) ===')
cur.execute("SELECT key, value FROM settings WHERE key LIKE 'btn:%' OR key LIKE 'link:%' OR key LIKE 'btn:banner%'")
print(json.dumps([dict(r) for r in cur.fetchall()], ensure_ascii=False, indent=2))

print('\n=== PRODUCTS content sample ===')
cur.execute('SELECT id, name, content_type, substr(content_value,1,200) as cv FROM products')
rows = cur.fetchall()
print(json.dumps([{'id': r['id'], 'name': r['name'], 'content_type': r['content_type'], 'content_value': r['cv']} for r in rows], ensure_ascii=False, indent=2))

print('\n=== PRODUCT_PHOTOS rows ===')
cur.execute('SELECT id, product_id, file_id, position FROM product_photos')
print(json.dumps([dict(r) for r in cur.fetchall()], ensure_ascii=False, indent=2))

conn.close()
