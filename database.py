import sqlite3
from pathlib import Path

# ensures that the DB is created besides the database.py regardless of the directory from which the app is run
DB_PATH = Path(__file__).resolve().parent / "expenses.db"

def get_db_connection():
    #open the DB connection, if DB doesn't exist, SQLite creates it
    conn=sqlite3.connect(DB_PATH)
    # Access query results by column name instead of tuples index
    conn.row_factory=sqlite3.Row
    # Enforce FK constraints 
    conn.execute("PRAGMA foreign_keys =ON")
    return conn




def init_db():
    conn = get_db_connection()

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS accounts (
            account_id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS categories (
            category_id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_name TEXT NOT NULL,
            category_type TEXT NOT NULL
                CHECK(category_type IN ('income', 'expense')),
            UNIQUE(category_name, category_type)
        );

        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_date TEXT NOT NULL,
            description TEXT NOT NULL,
            amount REAL NOT NULL CHECK(amount > 0),

            transaction_type TEXT NOT NULL
                CHECK(transaction_type IN ('income', 'expense')),

            category_id INTEGER NOT NULL,
            account_id INTEGER NOT NULL,
            custom_category TEXT,

            FOREIGN KEY (category_id)
                REFERENCES categories(category_id),

            FOREIGN KEY (account_id)
                REFERENCES accounts(account_id)
        );
    """)

    accounts = [
        ("Cash",),
        ("Checking",),
        ("Savings",),
        ("Credit Card",)
    ]

    categories = [
        ("Salary", "income"),
        ("Freelance", "income"),
        ("Gift", "income"),
        ("Other", "income"),

        ("Food & Groceries", "expense"),
        ("Housing", "expense"),
        ("Transportation", "expense"),
        ("Shopping", "expense"),
        ("Utilities", "expense"),
        ("Healthcare", "expense"),
        ("Entertainment", "expense"),
        ("Other", "expense"),
        ('Refund', 'income')
    ]

    conn.executemany("""
        INSERT OR IGNORE INTO accounts (account_name)
        VALUES (?)
    """, accounts)

    conn.executemany("""
        INSERT OR IGNORE INTO categories
            (category_name, category_type)
        VALUES (?, ?)
    """, categories)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print("Database initialized successfully!")