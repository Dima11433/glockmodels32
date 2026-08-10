#!/usr/bin/env python3
"""
Reset all photos and related settings in shop.db and remove local photos/.
Backs up shop.db to shop.db.bak before changes.
Run: python reset_photos.py
"""
import sqlite3
import shutil
from pathlib import Path

ROOT = Path(__file__).parent
DB = ROOT / "shop.db"
if not DB.exists():
    print("shop.db not found at", DB)
    raise SystemExit(1)
BAK = ROOT / "shop.db.bak"
shutil.copy2(DB, BAK)
print("Backup created:", BAK)

conn = sqlite3.connect(DB)
cur = conn.cursor()
actions = []

# Delete all product photos
cur.execute("DELETE FROM product_photos")
actions.append("Deleted product_photos rows")

# Clear per-button and global banner settings
cur.execute("DELETE FROM settings WHERE key LIKE 'btn:banner%'")
actions.append("Deleted settings with keys LIKE 'btn:banner%'")

# Clear category videos
cur.execute("UPDATE categories SET video_file_id = NULL")
actions.append("Cleared categories.video_file_id")

# Clear mirrors banner
# If mirrors table exists and has banner_file_id column
try:
    cur.execute("UPDATE mirrors SET banner_file_id = NULL")
    actions.append("Cleared mirrors.banner_file_id")
except Exception:
    # ignore if mirrors table/column doesn't exist
    pass

conn.commit()
conn.close()

# Remove local photos files in photos/ directory
photos_dir = ROOT / "photos"
removed = 0
if photos_dir.exists() and photos_dir.is_dir():
    for p in photos_dir.iterdir():
        try:
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
            removed += 1
        except Exception as e:
            print("Failed to remove", p, e)

print("Done. Actions:")
for a in actions:
    print(" -", a)
print(f"Removed {removed} files from {photos_dir}")
