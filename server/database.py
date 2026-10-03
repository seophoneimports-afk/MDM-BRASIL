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

        # 13. password_resets (Secure OTP Token Recovery)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS password_resets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            email TEXT NOT NULL,
            reset_code TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            used INTEGER DEFAULT 0,
            attempts INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
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
            ('pix_key', '19994783127'),
            ('pix_key_type', 'AUTO'),
            ('pix_merchant_name', 'MDM FRP BRASIL'),
            ('pix_merchant_city', 'AMERICANA'),
            ('google_client_id', ''),
            ('platform_name', 'MDM & FRP BRASIL'),
            ('support_phone', '(19) 99478-3127'),
            ('welcome_bonus_credits', '5'),
            ('homepage_layout', 'cinema_split'),
            ('homepage_card_style', 'glass_neon'),
            ('homepage_sections', '{"hero":true,"slider":true,"ranking":true,"download":true,"pricing":true,"benefits":true}')
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
        if "custom_pix_key" not in cols:
            cursor.execute("ALTER TABLE users ADD COLUMN custom_pix_key TEXT;")
        if "custom_pix_type" not in cols:
            cursor.execute("ALTER TABLE users ADD COLUMN custom_pix_type TEXT DEFAULT 'AUTO';")
        if "custom_pix_name" not in cols:
            cursor.execute("ALTER TABLE users ADD COLUMN custom_pix_name TEXT;")
        if "custom_pix_city" not in cols:
            cursor.execute("ALTER TABLE users ADD COLUMN custom_pix_city TEXT;")

        # Check and migrate columns for devices
        cursor.execute("PRAGMA table_info(devices)")
        dev_cols = [c["name"] for c in cursor.fetchall()]
        if "lock_status" not in dev_cols:
            cursor.execute("ALTER TABLE devices ADD COLUMN lock_status TEXT DEFAULT 'LOCKED';")
        if "operation_id" not in dev_cols:
            cursor.execute("ALTER TABLE devices ADD COLUMN operation_id TEXT;")
        if "latitude" not in dev_cols:
            cursor.execute("ALTER TABLE devices ADD COLUMN latitude REAL;")
        if "longitude" not in dev_cols:
            cursor.execute("ALTER TABLE devices ADD COLUMN longitude REAL;")
        if "accuracy" not in dev_cols:
            cursor.execute("ALTER TABLE devices ADD COLUMN accuracy REAL;")
        if "battery_level" not in dev_cols:
            cursor.execute("ALTER TABLE devices ADD COLUMN battery_level INTEGER;")
        if "network_status" not in dev_cols:
            cursor.execute("ALTER TABLE devices ADD COLUMN network_status TEXT;")
        if "street" not in dev_cols:
            cursor.execute("ALTER TABLE devices ADD COLUMN street TEXT;")
        if "neighborhood" not in dev_cols:
            cursor.execute("ALTER TABLE devices ADD COLUMN neighborhood TEXT;")
        if "city" not in dev_cols:
            cursor.execute("ALTER TABLE devices ADD COLUMN city TEXT;")
        if "state" not in dev_cols:
            cursor.execute("ALTER TABLE devices ADD COLUMN state TEXT;")
        if "last_sync" not in dev_cols:
            cursor.execute("ALTER TABLE devices ADD COLUMN last_sync TIMESTAMP;")

        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_google_id ON users(google_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_user ON credit_transactions(user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_payments_user ON payments(user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_payments_txid ON payments(pix_txid);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);")
        # Auto-restore users & wallets from db_backup.json if needed
        backup_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db_backup.json")
        if os.path.exists(backup_file):
            try:
                import json
                with open(backup_file, "r", encoding="utf-8") as bf:
                    b_data = json.load(bf)
                # Restore users
                for b_user in b_data.get("users", []):
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO users (id, name, email, whatsapp, password_hash, status, google_id, auth_provider, avatar_url)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            b_user.get("id"), b_user.get("name"), b_user.get("email"),
                            b_user.get("whatsapp", ""), b_user.get("password_hash"),
                            b_user.get("status", "active"), b_user.get("google_id"),
                            b_user.get("auth_provider", "local"), b_user.get("avatar_url")
                        )
                    )
                # Restore wallets
                for b_wal in b_data.get("wallets", []):
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO wallets (id, user_id, balance_credits, promotional_credits, total_purchased, total_used)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            b_wal.get("id"), b_wal.get("user_id"), b_wal.get("balance_credits", 5),
                            b_wal.get("promotional_credits", 0), b_wal.get("total_purchased", 0),
                            b_wal.get("total_used", 0)
                        )
                    )
            except Exception as e:
                print("Warning restoring backup:", e)

        # Self-healing: ensure all existing users have wallets and welcome credits so no client is stranded at 0
        cursor.execute("SELECT id, name, email FROM users")
        all_users = cursor.fetchall()
        for u in all_users:
            cursor.execute("SELECT id, balance_credits FROM wallets WHERE user_id = ?", (u["id"],))
            w = cursor.fetchone()
            if not w:
                cursor.execute(
                    "INSERT INTO wallets (user_id, balance_credits, promotional_credits, total_purchased, total_used) VALUES (?, 5, 5, 0, 0)",
                    (u["id"],)
                )
                cursor.execute(
                    """
                    INSERT INTO credit_transactions (wallet_id, user_id, type, amount_credits, previous_balance, new_balance, description, reference_id)
                    VALUES (last_insert_rowid(), ?, 'BONUS', 5, 0, 5, '🎁 Bônus de Boas-Vindas Técnico (5 créditos grátis)', 'WELCOME_AUTO')
                    """,
                    (u["id"],)
                )
            elif w["balance_credits"] == 0:
                cursor.execute("SELECT COUNT(*) as c FROM orders WHERE user_id = ?", (u["id"],))
                ord_c = cursor.fetchone()["c"]
                if ord_c == 0:
                    cursor.execute("UPDATE wallets SET balance_credits = 5, promotional_credits = 5 WHERE id = ?", (w["id"],))
                    cursor.execute(
                        """
                        INSERT INTO credit_transactions (wallet_id, user_id, type, amount_credits, previous_balance, new_balance, description, reference_id)
                        VALUES (?, ?, 'BONUS', 5, 0, 5, '🎁 Bônus de Boas-Vindas Técnico (5 créditos grátis para teste no EXE)', 'WELCOME_AUTO')
                        """,
                        (w["id"], u["id"])
                    )

if __name__ == "__main__":
    init_db()
    print("Database schema initialized successfully.")
