import os
import time
import requests
from datetime import datetime
import pytz

# 🩺 SYSTEM CHECK: High-Frequency Scalper Loading...
print("🩺 SYSTEM CHECK: Relentless Scalper (v3.0) is active.", flush=True)

# --- 1. CONFIGURATION ---
TRADIER_TOKEN = os.getenv("TRADIER_TOKEN")
TRADIER_ACCOUNT_ID = os.getenv("TRADIER_ACCOUNT_ID")
KALSHI_API_KEY = os.getenv("KALSHI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

PROB_EDGE_THRESHOLD = 0.03 
MAX_RISK_PER_TRADE = 200   
TAKE_PROFIT_PCT = 0.20 # Sell at 20% gain
STOP_LOSS_PCT = 0.20   # Sell at 20% loss
EST = pytz.timezone('US/Eastern')

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
        res = requests.get(url).json()
        markets = res.get('markets', []) or res.get('event', {}).get('markets', [])
        for m in markets:
            if m.get('floor_strike', 0) <= spx_approx <= m.get('cap_strike', 99999):
                raw = (m.get('last_price_dollars') or m.get('yes_bid_dollars') or m.get('yes_ask_dollars') or 0)
                prob = float(raw) / 100.0 if raw > 1 else float(raw)
                return m['ticker'], prob
    except: return None, 0

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
    requests.post(url, data=data, headers=headers)

# --- 3. THE SCALPING ENGINE ---

def manage_active_trades():
    """Constantly checks current positions for TP/SL and the EOD Kill-Switch."""
    positions = get_live_positions()
    now = datetime.now(EST)
    time_val = now.hour * 100 + now.minute
    
    for p in positions:
        symbol = p['symbol']
        qty = int(p['quantity'])
        cost = float(p['cost_basis']) / qty
        
        # Get live bid
        q_url = f"https://sandbox.tradier.com/v1/markets/quotes?symbols={symbol}"
        q_res = requests.get(q_url, headers={'Authorization': f'Bearer {TRADIER_TOKEN}', 'Accept': 'application/json'}).json()
        current_bid = float(q_res['quotes']['quote'].get('bid', 0))
        
        # EXIT 1: KILL-SWITCH (2:50 PM CST)
        if time_val >= 1550:
            place_order(symbol, qty, 'sell_to_close')
            send_alert(f"💰 EOD KILL-SWITCH: Closed {symbol}")
            continue

        # EXIT 2: SCALPER PROFITS/LOSS
        if current_bid > 0:
            change = (current_bid - cost) / cost
            if change >= TAKE_PROFIT_PCT:
                place_order(symbol, qty, 'sell_to_close')
                send_alert(f"💎 SCALP WIN: Closed {symbol} at +{change*100:.1f}%")
            elif change <= -STOP_LOSS_PCT:
                place_order(symbol, qty, 'sell_to_close')
                send_alert(f"🛑 STOP LOSS: Closed {symbol} at {change*100:.1f}%")

def main():
    send_alert("🤖 SCALPER ONLINE: Constant Hunt & Sell mode active.")
    
    while True:
        now = datetime.now(EST)
        time_val = now.hour * 100 + now.minute
        
        # 1. ALWAYS MANAGE EXITS (Every 30 seconds)
        manage_active_trades()
        
        # 2. HUNTING PHASE (8:30 AM - 2:50 PM CST)
        if 930 <= time_val < 1550:
            ticker, k_prob = get_automated_ticker_and_prob()
            
            if ticker and k_prob > 0:
                # Get chain
                url = "https://sandbox.tradier.com/v1/markets/options/chains"
                params = {'symbol': 'SPY', 'expiration': now.strftime("%Y-%m-%d"), 'greeks': 'true'}
                res = requests.get(url, params=params, headers={'Authorization': f'Bearer {TRADIER_TOKEN}', 'Accept': 'application/json'}).json()
                options = res.get('options', {}).get('option', [])
                lottos = [o for o in options if o['option_type'] == 'put' and 0.01 <= o['ask'] <= 0.25]
                
                if lottos:
                    lotto = sorted(lottos, key=lambda x: x['greeks']['delta'])[0]
                    opt_prob = abs(lotto['greeks']['delta'])
                    gap = k_prob - opt_prob
                    
                    # LOGGING
                    print(f"🎯 {ticker[-5:]} | K: {k_prob:.2f} | T: {opt_prob:.2f} | Gap: {gap:.2f}", flush=True)
                    
                    if gap > PROB_EDGE_THRESHOLD:
                        # POSITION CHECK: Don't buy the EXACT same option if we already have it
                        current_symbols = [p['symbol'] for p in get_live_positions()]
                        if lotto['symbol'] not in current_symbols:
                            qty = int(MAX_RISK_PER_TRADE / (lotto['ask'] * 100))
                            if qty > 0:
                                place_order(lotto['symbol'], qty)
                                send_alert(f"🚀 SCALP ENTRY: Bought {qty} {lotto['symbol']} (Edge: {gap:.2f})")
            else:
                if time_val % 5 == 0: print("🔎 Scanning for market gaps...", flush=True)

        elif time_val >= 1601:
            send_alert("🌙 Market closed. Bot resting.")
            return   
            
        time.sleep(30)

if __name__ == "__main__":
    main()
