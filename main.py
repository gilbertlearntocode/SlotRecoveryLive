from flask import Flask, render_template, jsonify, request, session, redirect, url_for
import random
import sqlite3

app = Flask(__name__)
app.secret_key = 'your-secret-key-here-change-this-for-production'  # Change this!

# SQLite DB for persistent wallets
DB_FILE = 'wallets.db'

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

# Run DB init once on startup
conn = get_db_connection()
conn.execute('''
    CREATE TABLE IF NOT EXISTS wallets (
        username TEXT PRIMARY KEY,
        balance REAL NOT NULL
    )
''')
conn.commit()
conn.close()

# Tuned ~95-96% RTP
SYMBOLS = ['🟢', '🔴', '🟡', '🟣']
WEIGHTS = [30, 10, 5, .8]
PAYOUTS = {0: 4, 1: 8, 2: 16, 3: 888}
MIXED_PURPLE = 10

def spin():
    return [random.choices(range(4), weights=WEIGHTS)[0] for _ in range(3)]

def get_payout(reel):
    if reel[0] == reel[1] == reel[2]:
        return PAYOUTS[reel[0]]

    # Mixed purple: exactly two matching (any color) + one purple
    counts = {}
    for s in reel:
        counts[s] = counts.get(s, 0) + 1

    if counts.get(3, 0) == 1:  # exactly one purple
        # Check if the other two are the same
        non_purple = [s for s in reel if s != 3]
        if len(non_purple) == 2 and non_purple[0] == non_purple[1]:
            return MIXED_PURPLE

    # No mixed low anymore — return 0 for one each green/red/yellow
    return 0

@app.before_request
def load_user():
    if 'username' in session:
        username = session['username']
        conn = get_db_connection()
        row = conn.execute('SELECT balance FROM wallets WHERE username = ?', (username,)).fetchone()
        if row is None:
            balance = 10000.0
            conn.execute('INSERT INTO wallets (username, balance) VALUES (?, ?)', (username, balance))
            conn.commit()
        else:
            balance = row['balance']
        session['balance'] = balance
        conn.close()

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        if username:
            session['username'] = username
            session['spin_history'] = []  # reset on every login
            # DB init happens in before_request
            return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('balance', None)
    return redirect(url_for('login'))

@app.route('/')
def index():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/withdraw', methods=['POST'])
def withdraw():
    if 'username' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    data = request.get_json()
    amount = float(data.get('amount', 0))

    balance = session.get('balance', 0.0)

    if amount <= 0 or amount > balance:
        return jsonify({'error': 'Invalid withdraw amount'}), 400

    new_balance = balance - amount
    session['balance'] = new_balance

    # Save to DB
    conn = get_db_connection()
    conn.execute('UPDATE wallets SET balance = ? WHERE username = ?', (new_balance, session['username']))
    conn.commit()
    conn.close()

    return jsonify({
        'success': True,
        'withdrawn': round(amount, 2),
        'new_balance': round(new_balance, 2)
    })

# House view - admin dashboard
ADMIN_USERNAME = 'house'  # change this
ADMIN_PASSWORD = 'password123'  # CHANGE THIS IMMEDIATELY

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if 'admin_logged_in' not in session:
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
                session['admin_logged_in'] = True
                return redirect(url_for('admin'))
            else:
                return render_template('admin_login.html', error='Wrong credentials')
        return render_template('admin_login.html')
    
    # House stats
    conn = get_db_connection()
    players = conn.execute('SELECT username, balance FROM wallets').fetchall()
    total_balance = sum(p['balance'] for p in players)
    total_house_profit = 10000 * len(players) - total_balance  # assuming all started with 10k, adjust if needed

    # Recent spins log (need to add spin logging table - see below)
    # For now placeholder - add later
    recent_spins = []  # placeholder

    conn.close()

    return render_template('admin.html', players=players, total_house_profit=total_house_profit, recent_spins=recent_spins)

@app.route('/admin/reset_profit', methods=['POST'])
def reset_profit():
    if 'admin_logged_in' not in session:
        return redirect(url_for('admin'))  # or jsonify error if you want
    conn = get_db_connection()
    conn.execute('UPDATE wallets SET total_wagered = 0.0, total_returned = 0.0')
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'House profit reset to 0'})

@app.route('/house-view')
def house_view():
    conn = get_db_connection()
    players = conn.execute('''
        SELECT username, balance, total_wagered, total_returned, 
               COALESCE(total_spins, 0) as total_spins, 
               COALESCE(max_win, 0.0) as max_win 
        FROM wallets
    ''').fetchall()
    total_wagered_all = sum(p['total_wagered'] for p in players)
    total_returned_all = sum(p['total_returned'] for p in players)
    total_house_profit = total_wagered_all - total_returned_all
    all_time_rtp = (total_returned_all / total_wagered_all * 100) if total_wagered_all > 0 else 0
    conn.close()

    return render_template('house_view.html', 
                          players=players, 
                          total_house_profit=total_house_profit,
                          total_wagered=total_wagered_all,
                          total_returned=total_returned_all,
                          all_time_rtp=all_time_rtp)


@app.route('/spin')
def do_spin():
    if 'username' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    bet = float(request.args.get('bet', 1.0))
    balance = session.get('balance', 0.0)

    if bet < 5 or bet > 1000 or bet not in [5, 10, 25, 50, 100, 200, 500, 1000]:
        return jsonify({'error': 'Invalid bet amount'}), 400

    if balance < bet:
        return jsonify({'error': 'Insufficient balance'}), 400

    reel = spin()
    multiplier = get_payout(reel)
    total_return = bet * (multiplier + 1) if multiplier > 0 else 0.0

    new_balance = balance - bet + total_return
    session['balance'] = new_balance

   # Save to DB - update balance + accumulate wagered/returned
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE wallets 
        SET balance = ?,
            total_wagered = total_wagered + ?,
            total_returned = total_returned + ?,
            total_spins = total_spins + 1,
            max_win = CASE 
                WHEN ? > max_win THEN ? 
                ELSE max_win 
            END
        WHERE username = ?
    ''', (new_balance, bet, total_return, total_return, total_return, session['username']))
    conn.commit()
    conn.close()

    

    # Add spin history to session (for graphs) - last 100 spins
    if 'spin_history' not in session:
        session['spin_history'] = []
    session['spin_history'].append({
        'bet': bet,
        'multiplier': multiplier,
        'total_return': total_return,
        'win_loss': total_return - bet  # net win/loss per spin
    })
    if len(session['spin_history']) > 100:
        session['spin_history'] = session['spin_history'][-100:]

    reel_symbols = [SYMBOLS[s] for s in reel]
    return jsonify({
        'reel': ' '.join(reel_symbols),
        'multiplier': round(multiplier, 2),
        'total_return': round(total_return, 2),
        'bet': bet,
        'new_balance': round(new_balance, 2),
        'spin_history': session['spin_history']  # <-- this sends it to JS
    })

import os

@app.route('/full-reset', methods=['POST'])
def full_reset():
    if 'admin_logged_in' not in session:
        return jsonify({'error': 'Not authorized'}), 401

    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
        print("DB file deleted")

    init_db()  # recreate immediately

    for key in list(session.keys()):
        session.pop(key, None)

    return jsonify({'success': True, 'message': 'Full reset complete. Reload page.'})
    
    

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)