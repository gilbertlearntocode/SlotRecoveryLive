import sqlite3

conn = sqlite3.connect('wallets.db')
cursor = conn.cursor()

# Add missing columns if they don't exist
try:
    cursor.execute("ALTER TABLE wallets ADD COLUMN total_wagered REAL DEFAULT 0.0")
    print("Added total_wagered")
except sqlite3.OperationalError:
    print("total_wagered already exists")

try:
    cursor.execute("ALTER TABLE wallets ADD COLUMN total_returned REAL DEFAULT 0.0")
    print("Added total_returned")
except sqlite3.OperationalError:
    print("total_returned already exists")

conn.commit()
conn.close()
print("DB fixed. Restart main.py and try again.")