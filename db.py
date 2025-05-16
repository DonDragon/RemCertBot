import sqlite3
from datetime import datetime

def init_db():
    conn = sqlite3.connect("certificates.db")
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS certificates (
        id INTEGER PRIMARY KEY,
        telegram_id INTEGER,
        organization TEXT,
        director TEXT,
        inn TEXT,
        edrpou TEXT,
        valid_from TEXT,
        valid_to TEXT,
        sha1 TEXT UNIQUE,
        filename TEXT,
        uploaded_at TEXT
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS allowed_users (
        telegram_id INTEGER PRIMARY KEY
    )
    ''')
    conn.commit()
    conn.close()

def insert_certificate(cert, telegram_id, filename):
    conn = sqlite3.connect("certificates.db")
    cursor = conn.cursor()
    try:
        cursor.execute('''
        INSERT INTO certificates (
            telegram_id, organization, director, inn, edrpou, valid_from, valid_to,
            sha1, filename, uploaded_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            telegram_id,
            cert["organization"],
            cert["director"],
            cert["inn"],
            cert["edrpou"],
            cert["valid_from"].isoformat(),
            cert["valid_to"].isoformat(),
            cert["sha1"],
            filename,
            datetime.utcnow().isoformat()
        ))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def is_user_allowed(telegram_id):
    conn = sqlite3.connect("certificates.db")
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM allowed_users WHERE telegram_id = ?", (telegram_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def add_user(telegram_id):
    conn = sqlite3.connect("certificates.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO allowed_users (telegram_id) VALUES (?)", (telegram_id,))
    conn.commit()
    conn.close()

def remove_user(telegram_id):
    conn = sqlite3.connect("certificates.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM allowed_users WHERE telegram_id = ?", (telegram_id,))
    conn.commit()
    conn.close()

def list_users():
    conn = sqlite3.connect("certificates.db")
    cursor = conn.cursor()
    cursor.execute("SELECT telegram_id FROM allowed_users")
    users = cursor.fetchall()
    conn.close()
    return [u[0] for u in users]
