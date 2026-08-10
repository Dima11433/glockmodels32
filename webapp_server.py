"""
Простой HTTP сервер для тестирования Web App
Запуск: python webapp_server.py
Доступ: http://localhost:8000/webapp.html
"""

import http.server
import socketserver
import os
from pathlib import Path

PORT = 8000
HANDLER = http.server.SimpleHTTPRequestHandler

class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Добавляем CORS заголовки для кроссдоменных запросов
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        # Кэш отключаем для разработки
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        super().end_headers()

    def log_message(self, format, *args):
        # Красивый лог
        print(f"[{self.log_date_time_string()}] {format % args}")

    def do_GET(self):
        # Простейший API для разработки: /api/products возвращает категории и товары из shop.db
        if self.path.startswith('/api/products'):
            try:
                import sqlite3, json
                db_path = Path(__file__).parent / 'shop.db'
                conn = sqlite3.connect(str(db_path))
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()

                cur.execute("SELECT id, name FROM categories ORDER BY position, id")
                categories = [dict(row) for row in cur.fetchall()]

                cur.execute("SELECT id, category_id, name, description, price, kind, content_type, content_value, visible FROM products WHERE visible = 1 ORDER BY id")
                products = [dict(row) for row in cur.fetchall()]

                # Attach product photos (file_id or saved path) if any
                # Если у товара нет фото, используем глобальный баннер (если задан)
                cur.execute("SELECT value FROM settings WHERE key IN ('btn:banner:catalog','btn:banner') LIMIT 1")
                fb = cur.fetchone()
                fallback = fb[0] if fb else None
                for p in products:
                    cur.execute("SELECT file_id FROM product_photos WHERE product_id = ? ORDER BY position", (p['id'],))
                    photos = [r[0] for r in cur.fetchall()]
                    if not photos and fallback:
                        photos = [fallback]
                    p['photos'] = photos

                payload = {'categories': categories, 'products': products}
                body = json.dumps(payload, ensure_ascii=False).encode('utf-8')

                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                conn.close()
                return
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))
                return

        return super().do_GET()


os.chdir(Path(__file__).parent)

with socketserver.TCPServer(("", PORT), MyHTTPRequestHandler) as httpd:
    print(f"Web App server started on http://localhost:{PORT}")
    print(f"Open http://localhost:{PORT}/webapp.html")
    print("Press Ctrl+C to stop")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped")
