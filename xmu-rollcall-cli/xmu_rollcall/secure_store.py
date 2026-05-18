"""Encrypted SQLite storage for accounts and sessions.

The SQLite database itself is not SQLCipher-encrypted.  Instead, sensitive
fields are encrypted before they are written to SQLite using AES-GCM.  The
random local key is stored separately in the config directory as ``secret.key``
with best-effort user-only permissions.
"""

import base64
import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path

from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes


_CONFIG_DIR = None
_DB_PATH = None
_KEY_PATH = None


def configure(config_dir):
    """Configure storage paths from the package config directory."""
    global _CONFIG_DIR, _DB_PATH, _KEY_PATH
    _CONFIG_DIR = Path(config_dir)
    _DB_PATH = _CONFIG_DIR / "secure_store.sqlite3"
    _KEY_PATH = _CONFIG_DIR / "secret.key"


def _paths():
    if _CONFIG_DIR is None:
        default_dir = Path(os.environ.get("XMU_ROLLCALL_CONFIG_DIR") or (Path.home() / ".xmu_rollcall"))
        configure(default_dir)
    return _CONFIG_DIR, _DB_PATH, _KEY_PATH


def _ensure_dir():
    config_dir, _, _ = _paths()
    config_dir.mkdir(parents=True, exist_ok=True)


def _write_private_file(path, data):
    with open(path, "wb") as f:
        f.write(data)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _load_key():
    """Return the AES key.

    If XMU_ROLLCALL_MASTER_KEY is set, derive a key from it.  Otherwise create
    or load a random local key file.  The environment variable is useful for
    portable backups; the local key is easier for normal CLI use.
    """
    env_key = os.environ.get("XMU_ROLLCALL_MASTER_KEY")
    if env_key:
        return hashlib.sha256(env_key.encode("utf-8")).digest()

    _ensure_dir()
    _, _, key_path = _paths()
    if key_path.exists():
        raw = key_path.read_bytes().strip()
        try:
            key = base64.urlsafe_b64decode(raw)
            if len(key) == 32:
                return key
        except Exception:
            pass

    key = get_random_bytes(32)
    _write_private_file(key_path, base64.urlsafe_b64encode(key))
    return key


def _encrypt(value):
    if value is None:
        value = ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    key = _load_key()
    nonce = get_random_bytes(12)
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    ciphertext, tag = cipher.encrypt_and_digest(value.encode("utf-8"))
    return nonce + tag + ciphertext


def _decrypt(blob, default=""):
    if not blob:
        return default
    try:
        data = bytes(blob)
        nonce = data[:12]
        tag = data[12:28]
        ciphertext = data[28:]
        cipher = AES.new(_load_key(), AES.MODE_GCM, nonce=nonce)
        return cipher.decrypt_and_verify(ciphertext, tag).decode("utf-8")
    except Exception:
        return default


def _connect():
    _ensure_dir()
    _, db_path, _ = _paths()
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL DEFAULT '',
            username BLOB NOT NULL,
            password BLOB NOT NULL,
            rollcall_settings TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    account_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(accounts)").fetchall()
    }
    if "rollcall_settings" not in account_columns:
        conn.execute("ALTER TABLE accounts ADD COLUMN rollcall_settings TEXT NOT NULL DEFAULT '{}'")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            account_id INTEGER PRIMARY KEY,
            cookies BLOB NOT NULL,
            updated_at INTEGER NOT NULL,
            FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE
        )
        """
    )
    return conn


def list_accounts():
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, name, username, password, rollcall_settings FROM accounts ORDER BY id"
        ).fetchall()
    accounts = []
    for row in rows:
        try:
            rollcall_settings = json.loads(row[4] or "{}")
        except ValueError:
            rollcall_settings = {}
        accounts.append({
            "id": row[0],
            "name": row[1] or "",
            "username": _decrypt(row[2]),
            "password": _decrypt(row[3]),
            "rollcall_settings": rollcall_settings,
        })
    return accounts


def _settings_json(account):
    return json.dumps(
        account.get("rollcall_settings") or {},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def upsert_account(account):
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO accounts (id, name, username, password, rollcall_settings)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                username = excluded.username,
                password = excluded.password,
                rollcall_settings = excluded.rollcall_settings
            """,
            (
                int(account.get("id")),
                account.get("name") or "",
                sqlite3.Binary(_encrypt(account.get("username") or "")),
                sqlite3.Binary(_encrypt(account.get("password") or "")),
                _settings_json(account),
            ),
        )


def replace_accounts(accounts):
    with _connect() as conn:
        existing_rows = conn.execute("SELECT id, username FROM accounts").fetchall()
        existing_ids = {row[0] for row in existing_rows}
        existing_usernames = {row[0]: _decrypt(row[1]) for row in existing_rows}
        new_ids = {int(acc.get("id")) for acc in accounts}
        for account_id in existing_ids - new_ids:
            conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        for account in accounts:
            account_id = int(account.get("id"))
            username = account.get("username") or ""
            if account_id in existing_usernames and existing_usernames[account_id] != username:
                conn.execute("DELETE FROM sessions WHERE account_id = ?", (account_id,))
            conn.execute(
                """
                INSERT INTO accounts (id, name, username, password, rollcall_settings)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    username = excluded.username,
                    password = excluded.password,
                    rollcall_settings = excluded.rollcall_settings
                """,
                (
                    account_id,
                    account.get("name") or "",
                    sqlite3.Binary(_encrypt(username)),
                    sqlite3.Binary(_encrypt(account.get("password") or "")),
                    _settings_json(account),
                ),
            )


def save_session(account_id, cookies):
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO sessions (account_id, cookies, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(account_id) DO UPDATE SET
                cookies = excluded.cookies,
                updated_at = excluded.updated_at
            """,
            (int(account_id), sqlite3.Binary(_encrypt(cookies)), int(time.time())),
        )


def load_session(account_id):
    with _connect() as conn:
        row = conn.execute(
            "SELECT cookies FROM sessions WHERE account_id = ?",
            (int(account_id),),
        ).fetchone()
    if not row:
        return None
    text = _decrypt(row[0], default="")
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def has_session(account_id):
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM sessions WHERE account_id = ?",
            (int(account_id),),
        ).fetchone()
    return row is not None


def delete_session(account_id):
    with _connect() as conn:
        conn.execute("DELETE FROM sessions WHERE account_id = ?", (int(account_id),))
