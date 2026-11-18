from database import get_db_connection

conn = get_db_connection()

accounts = conn.execute(
    "SELECT * FROM accounts"
).fetchall()

categories = conn.execute(
    "SELECT * FROM categories"
).fetchall()

print("ACCOUNTS:")
for account in accounts:
    print(dict(account))

print("\nCATEGORIES:")
for category in categories:
    print(dict(category))

conn.close()