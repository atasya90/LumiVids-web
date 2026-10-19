"""Database untuk webapp (SQLite)."""
import os
import sqlite3
import time
import hashlib
import secrets

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webapp.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    telegram_id INTEGER DEFAULT 0,
    is_admin INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS balances (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    amount INTEGER NOT NULL,
    kind TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS topup_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    amount INTEGER NOT NULL,
    proof_path TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    prompt TEXT NOT NULL DEFAULT '',
    result_url TEXT NOT NULL DEFAULT '',
    cost INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
"""


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    return conn


def hash_password(pw):
    return hashlib.sha256(f"salt:{pw}".encode()).hexdigest()


def create_user(username, password, is_admin=False):
    conn = _conn()
    try:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, is_admin, created_at)"
            " VALUES (?, ?, ?, ?)",
            (username, hash_password(password), 1 if is_admin else 0, time.time()),
        )
        conn.execute(
            "INSERT OR IGNORE INTO balances (user_id, balance, updated_at) VALUES (?, 0, ?)",
            (cur.lastrowid, time.time()),
        )
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def verify_user(username, password):
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT id, password_hash, is_admin FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    finally:
        conn.close()
    if row and row[1] == hash_password(password):
        return {"id": row[0], "is_admin": bool(row[2])}
    return None


def create_session(user_id):
    token = secrets.token_hex(32)
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
            (token, user_id, time.time()),
        )
        conn.commit()
    finally:
        conn.close()
    return token


def get_user_by_token(token):
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT u.id, u.username, u.is_admin FROM sessions s"
            " JOIN users u ON s.user_id = u.id WHERE s.token = ?",
            (token,),
        ).fetchone()
    finally:
        conn.close()
    if row:
        return {"id": row[0], "username": row[1], "is_admin": bool(row[2])}
    return None


def get_balance(user_id):
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT balance FROM balances WHERE user_id = ?", (user_id,)
        ).fetchone()
    finally:
        conn.close()
    return row[0] if row else 0


def add_balance(user_id, amount, description=""):
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO balances (user_id, balance, updated_at) VALUES (?, ?, ?)"
            " ON CONFLICT(user_id) DO UPDATE SET balance = balance + ?, updated_at = ?",
            (user_id, amount, time.time(), amount, time.time()),
        )
        conn.execute(
            "INSERT INTO transactions (user_id, amount, kind, description, created_at)"
            " VALUES (?, ?, 'credit', ?, ?)",
            (user_id, amount, description, time.time()),
        )
        conn.commit()
    finally:
        conn.close()
    return get_balance(user_id)


def deduct_balance(user_id, amount, description=""):
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT balance FROM balances WHERE user_id = ?", (user_id,)
        ).fetchone()
        if not row or row[0] < amount:
            return False
        conn.execute(
            "UPDATE balances SET balance = balance - ?, updated_at = ? WHERE user_id = ?",
            (amount, time.time(), user_id),
        )
        conn.execute(
            "INSERT INTO transactions (user_id, amount, kind, description, created_at)"
            " VALUES (?, ?, 'debit', ?, ?)",
            (user_id, -amount, description, time.time()),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def create_topup(user_id, amount, proof_path=""):
    conn = _conn()
    try:
        cur = conn.execute(
            "INSERT INTO topup_requests (user_id, amount, proof_path, status, created_at)"
            " VALUES (?, 'pending', ?)",
            (user_id, amount, proof_path, time.time()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_topup(req_id):
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT id, user_id, amount, proof_path, status FROM topup_requests WHERE id = ?",
            (req_id,),
        ).fetchone()
    finally:
        conn.close()
    if row:
        return {"id": row[0], "user_id": row[1], "amount": row[2],
                "proof_path": row[3], "status": row[4]}
    return None


def set_topup_status(req_id, status):
    conn = _conn()
    try:
        conn.execute("UPDATE topup_requests SET status = ? WHERE id = ?", (status, req_id))
        conn.commit()
    finally:
        conn.close()


def pending_topups():
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT t.id, t.user_id, t.amount, t.proof_path, t.created_at, u.username"
            " FROM topup_requests t JOIN users u ON t.user_id = u.id"
            " WHERE t.status = 'pending' ORDER BY t.id",
        ).fetchall()
    finally:
        conn.close()
    return rows


def create_job(user_id, job_type, prompt, cost):
    conn = _conn()
    try:
        cur = conn.execute(
            "INSERT INTO jobs (user_id, job_type, status, prompt, cost, created_at)"
            " VALUES (?, ?, 'pending', ?, ?, ?)",
            (user_id, job_type, prompt, cost, time.time()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_job(job_id, status, result_url=""):
    conn = _conn()
    try:
        conn.execute(
            "UPDATE jobs SET status = ?, result_url = ? WHERE id = ?",
            (status, result_url, job_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_job(job_id):
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT id, user_id, job_type, status, prompt, result_url, cost, created_at"
            " FROM jobs WHERE id = ?", (job_id,),
        ).fetchone()
    finally:
        conn.close()
    if row:
        return {"id": row[0], "user_id": row[1], "job_type": row[2], "status": row[3],
                "prompt": row[4], "result_url": row[5], "cost": row[6], "created_at": row[7]}
    return None


def user_jobs(user_id, limit=20):
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT id, job_type, status, prompt, result_url, cost, created_at FROM jobs"
            " WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    finally:
        conn.close()
    return rows


def format_rp(amount):
    return f"Rp{amount:,}".replace(",", ".")
