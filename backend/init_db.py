"""
ChargeHub Database Initialization Script
Creates tables and seeds sample data for the ChargeHub platform.
"""

import os
import sys
import random
import string

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://chargehub:chargehub@localhost:5432/chargehub",
)


def generate_serial_number():
    """Generate a random 16-digit serial number."""
    return "".join(random.choices(string.digits, k=16))


def generate_pin():
    """Generate a random 14-digit PIN."""
    return "".join(random.choices(string.digits, k=14))


# Price mapping: denomination (credit) -> price (what user pays)
# Formula: 10 EGP cash = 7 EGP credit (30% tax/commission)
# So: price = credit / 0.7
DENOMINATION_PRICE_MAP = {
    7.00: 10.00,
    14.00: 20.00,
    21.00: 30.00,
    35.00: 50.00,
    70.00: 100.00,
    105.00: 150.00,
    140.00: 200.00,
    350.00: 500.00,
}

# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

CREATE_TABLES_SQL = """
-- Enable UUID extension if available
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    username        VARCHAR(50) UNIQUE NOT NULL,
    email           VARCHAR(120) UNIQUE NOT NULL,
    password_hash   VARCHAR(256) NOT NULL,
    balance         DECIMAL(10, 2) DEFAULT 0.00 NOT NULL,
    created_at      TIMESTAMP DEFAULT NOW()
);

-- Transactions table
CREATE TABLE IF NOT EXISTS transactions (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type            VARCHAR(20) NOT NULL CHECK (type IN ('recharge', 'card_purchase', 'deposit')),
    operator        VARCHAR(20),
    amount          DECIMAL(10, 2) NOT NULL,
    phone_number    VARCHAR(15),
    status          VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'failed')),
    created_at      TIMESTAMP DEFAULT NOW()
);

-- Cards table
CREATE TABLE IF NOT EXISTS cards (
    id              SERIAL PRIMARY KEY,
    operator        VARCHAR(20) NOT NULL,
    denomination    DECIMAL(10, 2) NOT NULL,
    price           DECIMAL(10, 2) NOT NULL,
    serial_number   VARCHAR(20) UNIQUE NOT NULL,
    pin             VARCHAR(20) NOT NULL,
    is_sold         BOOLEAN DEFAULT FALSE,
    sold_to         INTEGER REFERENCES users(id),
    sold_at         TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_transactions_created_at ON transactions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cards_operator_denomination ON cards(operator, denomination);
CREATE INDEX IF NOT EXISTS idx_cards_is_sold ON cards(is_sold) WHERE is_sold = FALSE;
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
"""


def init_database():
    """Initialize database schema and seed sample data."""
    print("=" * 60)
    print("ChargeHub Database Initialization")
    print("=" * 60)
    print(f"\nConnecting to: {DATABASE_URL.split('@')[-1]}")

    try:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = True
        cur = conn.cursor()

        # Create tables
        print("\n[1/3] Creating tables...")
        cur.execute(CREATE_TABLES_SQL)
        print("  ✓ Tables created successfully")

        # Seed sample cards
        print("\n[2/3] Seeding sample scratch cards...")
        seed_cards(cur)
        print("  ✓ Sample cards inserted")

        # Create admin user
        cur.execute("SELECT id FROM users WHERE email = 'admin@chargehub.com'")
        if not cur.fetchone():
            from werkzeug.security import generate_password_hash
            admin_hash = generate_password_hash("admin123")
            cur.execute(
                "INSERT INTO users (username, email, password_hash, balance) VALUES (%s, %s, %s, %s)",
                ("admin", "admin@chargehub.com", admin_hash, 99999.0),
            )
            print("  ✓ Admin user created (admin@chargehub.com / admin123)")

        # Verify
        print("\n[3/3] Verifying setup...")
        cur.execute("SELECT COUNT(*) FROM cards WHERE is_sold = FALSE")
        card_count = cur.fetchone()[0]
        print(f"  ✓ Available cards in database: {card_count}")

        cur.execute("SELECT COUNT(*) FROM users")
        user_count = cur.fetchone()[0]
        print(f"  ✓ Registered users: {user_count}")

        cur.close()
        conn.close()

        print("\n" + "=" * 60)
        print("Database initialization completed successfully!")
        print("=" * 60)

    except psycopg2.OperationalError as e:
        print(f"\n✗ Failed to connect to database: {e}")
        print("\nMake sure PostgreSQL is running and the DATABASE_URL is correct.")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Initialization failed: {e}")
        sys.exit(1)


def seed_cards(cur):
    """Insert sample scratch cards for all operators and denominations."""
    operators = ["vodafone", "etisalat", "orange", "we"]
    denominations = [7.00, 14.00, 21.00, 35.00, 70.00, 105.00, 140.00, 350.00]
    cards_per_combo = 10  # 10 cards per operator/denomination combination

    # Check if cards already exist
    cur.execute("SELECT COUNT(*) FROM cards")
    existing = cur.fetchone()[0]
    if existing > 0:
        print(f"  → Cards table already has {existing} entries, skipping seed.")
        return

    cards_data = []
    for operator in operators:
        for denomination in denominations:
            price = DENOMINATION_PRICE_MAP[denomination]
            for _ in range(cards_per_combo):
                serial = generate_serial_number()
                pin = generate_pin()
                cards_data.append((operator, denomination, price, serial, pin))

    # Batch insert for performance
    insert_sql = """
        INSERT INTO cards (operator, denomination, price, serial_number, pin)
        VALUES (%s, %s, %s, %s, %s)
    """
    cur.executemany(insert_sql, cards_data)
    print(f"  → Inserted {len(cards_data)} scratch cards")
    print(f"    ({len(operators)} operators × {len(denominations)} denominations × {cards_per_combo} each)")


if __name__ == "__main__":
    init_database()
