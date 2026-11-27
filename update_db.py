
from database import get_db_connection

conn = get_db_connection()



# Check the existing columns
columns = conn.execute(
    "PRAGMA table_info(transactions)"
).fetchall()

column_names = [column["name"] for column in columns]

print("Existing columns:", column_names)

# Add transaction_type if missing
if "transaction_type" not in column_names:
    conn.execute("""
        ALTER TABLE transactions
        ADD COLUMN transaction_type TEXT
        NOT NULL DEFAULT 'expense'
        CHECK(transaction_type IN ('income', 'expense'))
    """)

# Add custom_category if missing
if "custom_category" not in column_names:
    conn.execute("""
        ALTER TABLE transactions
        ADD COLUMN custom_category TEXT
    """)

conn.commit()

# Verify the updated structure
columns = conn.execute(
    "PRAGMA table_info(transactions)"
).fetchall()

print("\nUpdated columns:")
for column in columns:
    print(column["name"], column["type"])

conn.close()

print("\nDatabase updated successfully!")



