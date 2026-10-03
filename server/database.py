import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mdm_platform.db")

_local = threading.local()

def get_db_connection():
    conn = sqlite3.connect(DB_FILE, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

@contextmanager
def db_transaction():
    conn = get_db_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    with db_transaction() as conn:
        cursor = conn.cursor()

        # 1. users
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            whatsapp TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            status TEXT DEFAULT 'active' CHECK(status IN ('active', 'suspended', 'pending')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 2. administrators
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS administrators (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'superadmin' CHECK(role IN ('superadmin', 'support')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 3. wallets
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS wallets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            balance_credits INTEGER DEFAULT 0 CHECK(balance_credits >= 0),
            promotional_credits INTEGER DEFAULT 0 CHECK(promotional_credits >= 0),
            total_purchased INTEGER DEFAULT 0,
            total_used INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        );
        """)

        # 4. credit_transactions
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS credit_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('PURCHASE', 'CONSUMPTION', 'BONUS', 'ADJUSTMENT', 'REFUND')),
            amount_credits INTEGER NOT NULL,
            previous_balance INTEGER NOT NULL,
            new_balance INTEGER NOT NULL,
            description TEXT NOT NULL,
            reference_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (wallet_id) REFERENCES wallets (id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        );
        """)

        # 5. payments
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount_brl REAL NOT NULL,
            credits_amount INTEGER NOT NULL,
            pix_key TEXT NOT NULL,
            pix_txid TEXT UNIQUE NOT NULL,
            pix_copia_e_cola TEXT NOT NULL,
            qr_code_base64 TEXT,
            status TEXT DEFAULT 'PENDING' CHECK(status IN ('PENDING', 'PAID', 'EXPIRED', 'CANCELLED', 'REFUNDED')),
            paid_at TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        );
        """)

        # 6. payment_webhooks
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS payment_webhooks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payment_id INTEGER,
            idempotency_key TEXT UNIQUE NOT NULL,
            raw_payload TEXT NOT NULL,
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT NOT NULL,
            FOREIGN KEY (payment_id) REFERENCES payments (id) ON DELETE SET NULL
        );
        """)

        # 7. devices
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            serial TEXT NOT NULL,
            model TEXT,
            manufacturer TEXT,
            android_version TEXT,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, serial),
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        );
        """)

        # 8. services
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            credit_cost INTEGER DEFAULT 1,
            is_active INTEGER DEFAULT 1
        );
        """)

        # 9. orders
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            device_serial TEXT NOT NULL,
            device_model TEXT,
            service_code TEXT NOT NULL,
            service_name TEXT NOT NULL,
            credit_cost INTEGER NOT NULL,
            operation_id TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'COMPLETED' CHECK(status IN ('COMPLETED', 'FAILED')),
            client_name TEXT,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        );
        """)

        # 10. events (audit logs)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            admin_id INTEGER,
            event_type TEXT NOT NULL,
            details_json TEXT,
            ip_address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 11. sessions
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            admin_id INTEGER,
            token TEXT UNIQUE NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 12. system_settings
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Seed initial services
        cursor.execute("""
        INSERT OR IGNORE INTO services (code, name, credit_cost, is_active)
        VALUES ('FRP_MDM_UNLOCK', 'Desbloqueio & Gestão MDM/FRP (1 Aparelho)', 1, 1);
        """)

        # Seed initial system settings
        default_settings = [
            ('credit_price_brl', '5.00'),
            ('pix_key', '19994827743'),
            ('pix_key_type', 'AUTO'),
            ('pix_merchant_name', 'MDM FRP BRASIL'),
            ('pix_merchant_city', 'AMERICANA'),
            ('google_client_id', ''),
            ('platform_name', 'MDM & FRP BRASIL'),
            ('support_phone', '(19) 99482-7743')
        ]
        for k, v in default_settings:
            cursor.execute("INSERT OR IGNORE INTO system_settings (key, value) VALUES (?, ?);", (k, v))

        # Check and migrate columns for users
        cursor.execute("PRAGMA table_info(users)")
        cols = [c["name"] for c in cursor.fetchall()]
        if "google_id" not in cols:
            cursor.execute("ALTER TABLE users ADD COLUMN google_id TEXT;")
        if "auth_provider" not in cols:
            cursor.execute("ALTER TABLE users ADD COLUMN auth_provider TEXT DEFAULT 'local';")
        if "avatar_url" not in cols:
            cursor.execute("ALTER TABLE users ADD COLUMN avatar_url TEXT;")

        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_google_id ON users(google_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_user ON credit_transactions(user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_payments_user ON payments(user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_payments_txid ON payments(pix_txid);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);")

if __name__ == "__main__":
    init_db()
    print("Database schema initialized successfully.")
