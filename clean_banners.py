#!/usr/bin/env python3
"""Clean all old banner settings from shop.db"""
import sqlite3

conn = sqlite3.connect('shop.db')
cur = conn.cursor()

# Delete all banner settings
cur.execute("DELETE FROM settings WHERE key LIKE 'btn:banner%'")
deleted = cur.rowcount

conn.commit()
conn.close()

print(f"Done: Removed {deleted} old banner settings")
print("Now upload banners for each button again.")
print("Each banner will be saved to a separate file (banner_<uuid>.jpg)")

