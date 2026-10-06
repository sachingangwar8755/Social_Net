# database.py
# The application now uses SQLite directly through app.py.
# This file is intentionally kept as a small compatibility note
# so the old MySQL database.py does not get used accidentally.

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
