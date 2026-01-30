import sqlite3

conn = sqlite3.connect('wallets.db')
cursor = conn.cursor()

try:
    cursor.execute("ALTER TABLE wallets ADD COLUMN total_spins INTEGER DEFAULT 0")
    print("Added total_spins")
except sqlite3.OperationalError:
    print("total_spins already exists")

try:
    cursor.execute("ALTER TABLE wallets ADD COLUMN max_win REAL DEFAULT 0.0")
    print("Added max_win")
except sqlite3.OperationalError:
    print("max_win already exists")

conn.commit()
conn.close()
print("DB updated. Restart main.py.")