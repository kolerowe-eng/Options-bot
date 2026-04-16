import os
import time
import requests
from datetime import datetime
import pytz

# 🩺 SYSTEM CHECK: "Unlimited" Hunter is loading...
print("🩺 SYSTEM CHECK: Sovereign Multi-Trade Bot is online.", flush=True)

# --- 1. CONFIGURATION ---
TRADIER_TOKEN = os.getenv("TRADIER_TOKEN")
TRADIER_ACCOUNT_ID = os.getenv("TRADIER_ACCOUNT_ID")
KALSHI_API_KEY = os.getenv("KALSHI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

PROB_EDGE_THRESHOLD = 0.03 
MAX_RISK_PER_TRADE = 200   
EST = pytz.timezone('US/Eastern')

# Tracking for Split-Exit
sold_half_list = []

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
                raw = (m.get('last_price_dollars') or m.get('yes_bid_dollars') or m.get('last_price') or 0)
                prob = float(raw) / 100.0 if raw > 1 else float(raw)
                return m['ticker'], prob
    except: return None, 0

def get_tradier_positions():
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
    res = requests.post(url, data=data, headers=headers)
    return res.status_code

# --- 3. THE MANAGEMENT BRAIN ---

def manage_exits():
    global sold_half_list
    positions = get_tradier_positions()
    if not positions: 
        sold_half_list = [] # Reset tracking if we have no positions
        return
    
    now = datetime.now(EST)
    time_val = now.hour * 100 + now.minute
    
    for p in positions:
        symbol = p['symbol']
        qty = int(p['quantity'])
        cost_basis = float(p['cost_basis']) / qty
        
        # Check current Bid price
        quote_url = f"https://sandbox.tradier.com/v1/markets/quotes?symbols={symbol}"
        q_res = requests.get(quote_url, headers={'Authorization': f'Bearer {TRADIER_TOKEN}', 'Accept': 'application/json'}).json()
        current_bid = float(q_res['quotes']['quote'].get('bid', 0))
        
        # EXIT A: KILL-SWITCH (2:50 PM CST / 3:50 PM EST)
        if time_val >= 1550:
            print(f"⏰ KILL-SWITCH: Liquidating {qty} {symbol}", flush=True)
            place_order(symbol, qty, 'sell_to_close')
            send_alert(f"💰 EOD EXIT: Closed {symbol} at market.")
            continue

        # EXIT B: SPLIT-EXIT (100% GAIN)
        if current_bid >= (cost_basis * 2.0) and symbol not in sold_half_list:
            half_qty = max(1, qty // 2)
            place_order(symbol, half_qty, 'sell_to_close')
            sold_half_list.append(symbol)
            send_alert(f"💎 HOUSE MONEY: Sold half of {symbol} at 100% gain!")

# --- 4. MAIN EXECUTION LOOP ---

def main():
    send_alert("🤖 UNLIMITED BOT ONLINE: Hunting for multiple cycles today.")
    
    while True:
        now = datetime.now(EST)
        time_val = now.hour * 100 + now.minute
        
        # 1. Manage current trades
        manage_exits()
        
        # 2. Hunting Phase (8:30 AM - 2:50 PM CST)
        if 930 <= time_val < 1550:
            active_positions = get_tradier_positions()
            
            # POSITION GUARD: Only hunt if we don't currently have an open trade
            if len(active_positions) == 0:
                ticker, k_prob = get_automated_ticker_and_prob()
                
                if ticker and k_prob > 0:
                    # Find Lottos
                    url = "https://sandbox.tradier.com/v1/markets/options/chains"
                    params = {'symbol': 'SPY', 'expiration': now.strftime("%Y-%m-%d"), 'greeks': 'true'}
                    res = requests.get(url, params=params, headers={'Authorization': f'Bearer {TRADIER_TOKEN}', 'Accept': 'application/json'}).json()
                    options = res.get('options', {}).get('option', [])
                    lottos = [o for o in options if o['option_type'] == 'put' and 0.01 <= o['ask'] <= 0.20]
                    
                    if lottos:
                        lotto = sorted(lottos, key=lambda x: x['greeks']['delta'])[0]
                        opt_prob = abs(lotto['greeks']['delta'])
                        gap = k_prob - opt_prob
                        
                        print(f"🎯 {ticker[-5:]} | K: {k_prob:.2f} | T: {opt_prob:.2f} | Gap: {gap:.2f}", flush=True)
                        
                        if gap > PROB_EDGE_THRESHOLD:
                            qty = int(MAX_RISK_PER_TRADE / (lotto['ask'] * 100))
                            if qty > 0:
                                status = place_order(lotto['symbol'], qty)
                                send_alert(f"🚀 PURCHASE: Bought {qty} {lotto['symbol']} (Edge: {gap:.2f})")
                                print(f"✅ Trade fired. Status {status}. Now managing exit...", flush=True)
                                time.sleep(60) # Short wait to let Tradier update
            else:
                # Still print probability so you can watch the market
                _, k_prob = get_automated_ticker_and_prob()
                if time_val % 2 == 0: # Print every 1 min
                    print(f"🔎 Position open. Monitoring market... (K Prob: {k_prob:.2f})", flush=True)

        elif time_val >= 1601:
            send_alert("🌙 Market closed. Good night!")
            return   
            
        time.sleep(30)

if __name__ == "__main__":
    main()
