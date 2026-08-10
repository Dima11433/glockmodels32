import sqlite3
conn = sqlite3.connect('shop.db')
cur = conn.cursor()
cur.execute("SELECT COUNT(*) as cnt FROM settings WHERE key LIKE 'btn:banner%'")
print('Banner settings count:', cur.fetchone()[0])
cur.execute("SELECT key FROM settings WHERE key LIKE 'btn:banner%'")
rows = cur.fetchall()
for r in rows:
    print('  ', r[0])
conn.close()
