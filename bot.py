import os
import time
import requests
from datetime import datetime
import pytz

# 🩺 SYSTEM CHECK: Scaled-Math Moonshot (v4.2) Loading...
print("🩺 SYSTEM CHECK: Math Fix for Options Multiplier is active.", flush=True)

# --- 1. CONFIGURATION ---
TRADIER_TOKEN = os.getenv("TRADIER_TOKEN")
TRADIER_ACCOUNT_ID = os.getenv("TRADIER_ACCOUNT_ID")
KALSHI_API_KEY = os.getenv("KALSHI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

PROB_EDGE_THRESHOLD = 0.03 
MAX_RISK_PER_TRADE = 200   
EST = pytz.timezone('US/Eastern')

sold_half_tracker = []

# --- 2. CORE FUNCTIONS ---

def send_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try: requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message})
    except: pass

def get_current_spy_price():
    url = "https://sandbox.tradier.com/v1/markets/quotes?symbols=SPY"
    headers = {'Authorization': f'Bearer {TRADIER_TOKEN}', 'Accept': 'application/json'}
    try:
        res = requests.get(url, headers=headers).json()
        quote = res.get('quotes', {}).get('quote', {})
        if isinstance(quote, list): quote = quote[0]
        return float(quote.get('last', 0))
    except: return None

def get_automated_ticker_and_prob():
    spy_price = get_current_spy_price()
    if not spy_price: return None, 0
    spx_approx = spy_price * 10
    date_str = datetime.now(EST).strftime("%y%b%d").upper()
    url = f"https://api.elections.kalshi.com/trade-api/v2/events/KXINX-{date_str}H1600?with_nested_markets=true"
    try:
        res = requests.get(url, timeout=10).json()
        markets = res.get('markets', []) or res.get('event', {}).get('markets', [])
        for m in markets:
            floor = float(m.get('floor_strike', 0))
            cap = float(m.get('cap_strike', 99999))
            if floor <= spx_approx <= cap:
                raw_val = (m.get('last_price_dollars') or m.get('yes_bid_dollars') or m.get('yes_ask_dollars') or 0)
                num_val = float(raw_val)
                prob = num_val / 100.0 if num_val > 1.0 else num_val
                return m['ticker'], prob
    except: return None, 0
    return None, 0

def get_live_positions():
    url = f"https://sandbox.tradier.com/v1/accounts/{TRADIER_ACCOUNT_ID}/positions"
    headers = {'Authorization': f'Bearer {TRADIER_TOKEN}', 'Accept': 'application/json'}
    try:
        res = requests.get(url, headers=headers).json()
        pos = res.get('positions', {}).get('position', [])
        if not pos: return []
        return [pos] if isinstance(pos, dict) else pos
    except: return []

def place_order(symbol, qty, side='buy_to_open'):
    url = f"https://sandbox.tradier.com/v1/accounts/{TRADIER_ACCOUNT_ID}/orders"
    headers = {'Authorization': f'Bearer {TRADIER_TOKEN}', 'Accept': 'application/json'}
    data = {
        'class': 'option', 'symbol': 'SPY', 'option_symbol': symbol,
        'side': side, 'quantity': qty, 'type': 'market', 'duration': 'day'
    }
    try:
        res = requests.post(url, data=data, headers=headers)
        return res.status_code
    except: return 500

# --- 3. THE UPDATED MANAGEMENT BRAIN ---

def manage_positions():
    global sold_half_tracker
    positions = get_live_positions()
    now = datetime.now(EST)
    time_val = now.hour * 100 + now.minute
    
    if not positions:
        sold_half_tracker = [] 
        return

    for p in positions:
        try:
            symbol = p['symbol']
            qty = int(p['quantity'])
            
            # MATH FIX: Tradier cost_basis is total $. 
            # We divide by (qty * 100) to get the per-share cost basis.
            cost_per_share = float(p['cost_basis']) / (qty * 100)
            target_bid = cost_per_share * 2.0
            
            q_url = f"https://sandbox.tradier.com/v1/markets/quotes?symbols={symbol}"
            q_res = requests.get(q_url, headers={'Authorization': f'Bearer {TRADIER_TOKEN}', 'Accept': 'application/json'}).json()
            quote_data = q_res.get('quotes', {}).get('quote', {})
            if isinstance(quote_data, list): quote_data = quote_data[0]
            current_bid = float(quote_data.get('bid', 0))

            print(f"🧐 {symbol[-6:]} | Bid: {current_bid:.2f} | Need: {target_bid:.2f}", flush=True)

            if time_val >= 1555:
                place_order(symbol, qty, 'sell_to_close')
                send_alert(f"💰 KILL-SWITCH: Closing {qty} {symbol}")
                continue

            if current_bid >= target_bid and symbol not in sold_half_tracker:
                sell_qty = max(1, qty // 2)
                status = place_order(symbol, sell_qty, 'sell_to_close')
                if status < 400:
                    sold_half_tracker.append(symbol)
                    send_alert(f"💎 HOUSE MONEY: Sold {sell_qty} of {symbol} at ${current_bid}.")
                
        except Exception as e:
            print(f"⚠️ Management error: {e}", flush=True)

# --- 4. MAIN LOOP ---

def main():
    send_alert("🤖 MATH-FIXED BOT ONLINE: Let's get to work.")
    
    while True:
        try:
            now = datetime.now(EST)
            time_val = now.hour * 100 + now.minute
            print(f"🕒 [{now.strftime('%H:%M:%S')}] Heartbeat: Active.", flush=True)
            
            manage_positions()
            
            if 930 <= time_val < 1555:
                ticker, k_prob = get_automated_ticker_and_prob()
                if ticker:
                    url = "https://sandbox.tradier.com/v1/markets/options/chains"
                    params = {'symbol': 'SPY', 'expiration': now.strftime("%Y-%m-%d"), 'greeks': 'true'}
                    res = requests.get(url, params=params, headers={'Authorization': f'Bearer {TRADIER_TOKEN}', 'Accept': 'application/json'}).json()
                    options = res.get('options', {}).get('option', [])
                    lottos = [o for o in options if o['option_type'] == 'put' and 0.01 <= o['ask'] <= 0.25]
                    
                    if lottos:
                        lotto = sorted(lottos, key=lambda x: x['greeks']['delta'])[0]
                        opt_prob = abs(lotto['greeks']['delta'])
                        gap = k_prob - opt_prob
                        
                        if k_prob > 0:
                            print(f"📊 {ticker[-5:]} | K: {k_prob:.2f} | T: {opt_prob:.2f} | Gap: {gap:.2f}", flush=True)
                        
                        if gap > PROB_EDGE_THRESHOLD:
                            # STRIKE GUARD
                            current_symbols = [pos['symbol'] for pos in get_live_positions()]
                            if lotto['symbol'] not in current_symbols:
                                qty = int(MAX_RISK_PER_TRADE / (lotto['ask'] * 100))
                                if qty > 0:
                                    place_order(lotto['symbol'], qty)
                                    send_alert(f"🚀 ENTRY: {qty} {lotto['symbol']} (Gap: {gap:.2f})")
                                    time.sleep(10)
            
        except Exception as e:
            print(f"🚨 SYSTEM ERROR: {e}", flush=True)
            
        time.sleep(30)

if __name__ == "__main__":
    main()
