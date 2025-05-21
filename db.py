
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
    CREATE TABLE IF NOT EXISTS shared_access (
        owner_id INTEGER NOT NULL,
        viewer_id INTEGER NOT NULL,
        PRIMARY KEY (owner_id, viewer_id)
    )
    ''')
    conn.commit()
    conn.close()

def insert_certificate(cert, telegram_id, filename):
    conn = sqlite3.connect("certificates.db")
    cursor = conn.cursor()
    try:
        # Сначала удаляем все старые сертификаты этой организации от этого пользователя
        cursor.execute(
            "DELETE FROM certificates WHERE telegram_id = ? AND organization = ?",
            (telegram_id, cert["organization"])
        )
        # Теперь вставляем новый сертификат
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

def grant_access(owner_id, viewer_id):
    conn = sqlite3.connect("certificates.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO shared_access (owner_id, viewer_id) VALUES (?, ?)", (owner_id, viewer_id))
    conn.commit()
    conn.close()

def revoke_access(owner_id, viewer_id):
    conn = sqlite3.connect("certificates.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM shared_access WHERE owner_id = ? AND viewer_id = ?", (owner_id, viewer_id))
    conn.commit()
    conn.close()

def get_shared_with(owner_id):
    conn = sqlite3.connect("certificates.db")
    cursor = conn.cursor()
    cursor.execute("SELECT viewer_id FROM shared_access WHERE owner_id = ?", (owner_id,))
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]

def has_view_access(owner_id, viewer_id):
    if owner_id == viewer_id:
        return True
    conn = sqlite3.connect("certificates.db")
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM shared_access WHERE owner_id = ? AND viewer_id = ?", (owner_id, viewer_id))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def get_certificates_for_user(user_id):
    conn = sqlite3.connect("certificates.db")
    cursor = conn.cursor()
    cursor.execute(
    "SELECT organization, director, valid_to FROM certificates WHERE telegram_id = ? ORDER BY valid_to ASC",
        (user_id,)
    )
    result = cursor.fetchall()
    conn.close()
    return result

def get_certificates_shared_with(user_id):
    conn = sqlite3.connect("certificates.db")
    cursor = conn.cursor()
    cursor.execute('''
        SELECT organization, director, valid_to
        FROM certificates
        WHERE telegram_id IN (
            SELECT owner_id FROM shared_access WHERE viewer_id = ?
        )
    ''', (user_id,))
    result = cursor.fetchall()
    conn.close()
    return result


def get_user_language(user_id):
    conn = sqlite3.connect("certificates.db")
    cursor = conn.cursor()
    cursor.execute("SELECT language FROM users WHERE telegram_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else "ua"

def set_user_language(user_id, lang_code):
    conn = sqlite3.connect("certificates.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (telegram_id, language) VALUES (?, ?) ON CONFLICT(telegram_id) DO UPDATE SET language = ?", (user_id, lang_code, lang_code))
    conn.commit()
    conn.close()

def get_all_user_ids():
    conn = sqlite3.connect("certificates.db")
    cursor = conn.cursor()
    cursor.execute("SELECT telegram_id FROM users")
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]


