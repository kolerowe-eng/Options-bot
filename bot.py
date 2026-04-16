import os
import time
import requests
from datetime import datetime
import pytz

# 🩺 SYSTEM CHECK: Memory-Locked Bot is loading...
print("🩺 SYSTEM CHECK: Ironclad Memory Bot is online.", flush=True)

# --- 1. CONFIGURATION ---
TRADIER_TOKEN = os.getenv("TRADIER_TOKEN")
TRADIER_ACCOUNT_ID = os.getenv("TRADIER_ACCOUNT_ID")
KALSHI_API_KEY = os.getenv("KALSHI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

PROB_EDGE_THRESHOLD = 0.03 
MAX_RISK_PER_TRADE = 200   
EST = pytz.timezone('US/Eastern')
LOG_FILE = "last_trade_date.txt"

# --- 2. PERMANENT MEMORY FUNCTIONS ---

def has_traded_today():
    """Checks the text file to see if we already fired a trade today."""
    if not os.path.exists(LOG_FILE): return False
    with open(LOG_FILE, "r") as f:
        last_date = f.read().strip()
    return last_date == datetime.now(EST).strftime("%Y-%m-%d")

def mark_as_traded():
    """Writes today's date to the file so we don't trade again after restart."""
    with open(LOG_FILE, "w") as f:
        f.write(datetime.now(EST).strftime("%Y-%m-%d"))

# --- 3. CORE LOGIC ---

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

def get_automated_ticker():
    spy_price = get_current_spy_price()
    if not spy_price: return None
    spx_approx = spy_price * 10
    date_str = datetime.now(EST).strftime("%y%b%d").upper()
    url = f"https://api.elections.kalshi.com/trade-api/v2/events/KXINX-{date_str}H1600?with_nested_markets=true"
    try:
        res = requests.get(url).json()
        markets = res.get('markets', []) or res.get('event', {}).get('markets', [])
        for m in markets:
            if m.get('floor_strike', 0) <= spx_approx <= m.get('cap_strike', 99999):
                return m['ticker']
    except: return None

def get_live_kalshi_prob(ticker):
    url = f"https://api.elections.kalshi.com/trade-api/v2/markets/{ticker}"
    try:
        res = requests.get(url).json()
        m = res.get('market', {})
        raw = m.get('last_price_dollars') or m.get('yes_bid_dollars') or m.get('last_price') or 0
        prob = float(raw)
        return prob / 100.0 if prob > 1.0 else prob
    except: return 0.0

def get_tradier_lottos(symbol):
    url = "https://sandbox.tradier.com/v1/markets/options/chains"
    params = {'symbol': symbol, 'expiration': datetime.now(EST).strftime("%Y-%m-%d"), 'greeks': 'true'}
    headers = {'Authorization': f'Bearer {TRADIER_TOKEN}', 'Accept': 'application/json'}
    try:
        res = requests.get(url, params=params, headers=headers).json()
        options = res.get('options', {}).get('option', [])
        lottos = [o for o in options if o['option_type'] == 'put' and 0.01 <= o['ask'] <= 0.20]
        return sorted(lottos, key=lambda x: x['greeks']['delta'])[0] if lottos else None
    except: return None

# --- 4. MAIN EXECUTION LOOP ---

def main():
    send_alert("🤖 IRONCLAD BOT: Permanent Memory Lock Engaged.")
    
    while True:
        now = datetime.now(EST)
        time_val = now.hour * 100 + now.minute
        
        # --- PHASE 1: THE 2:50 PM CST KILL-SWITCH (1450 CST = 1550 EST) ---
        if 1550 <= time_val < 1600:
            url = f"https://sandbox.tradier.com/v1/accounts/{TRADIER_ACCOUNT_ID}/positions"
            res = requests.get(url, headers={'Authorization': f'Bearer {TRADIER_TOKEN}', 'Accept': 'application/json'}).json()
            positions = res.get('positions', {}).get('position', [])
            if isinstance(positions, dict): positions = [positions]
            
            if positions:
                for p in positions:
                    symbol = p['symbol']
                    qty = p['quantity']
                    order_url = f"https://sandbox.tradier.com/v1/accounts/{TRADIER_ACCOUNT_ID}/orders"
                    requests.post(order_url, data={'class':'option','symbol':'SPY','option_symbol':symbol,'side':'sell_to_close','quantity':qty,'type':'market','duration':'day'}, headers={'Authorization':f'Bearer {TRADIER_TOKEN}'})
                    print(f"⏰ KILL-SWITCH: Liquidating {symbol}", flush=True)
                send_alert(f"💰 EOD EXIT: Closed {len(positions)} positions.")
                time.sleep(600) # Sleep through the rest of the close
            
        # --- PHASE 2: THE HUNTING PHASE (8:30 AM - 2:50 PM CST) ---
        if 930 <= time_val < 1550:
            if not has_traded_today():
                ticker = get_automated_ticker()
                if ticker:
                    k_prob = get_live_kalshi_prob(ticker)
                    lotto = get_tradier_lottos("SPY")
                    
                    if k_prob > 0 and lotto:
                        opt_prob = abs(lotto['greeks']['delta'])
                        gap = k_prob - opt_prob
                        print(f"🎯 {ticker[-5:]} | K: {k_prob:.2f} | T: {opt_prob:.2f} | Gap: {gap:.2f}", flush=True)
                        
                        if gap > PROB_EDGE_THRESHOLD:
                            qty = int(MAX_RISK_PER_TRADE / (lotto['ask'] * 100))
                            if qty > 0:
                                order_url = f"https://sandbox.tradier.com/v1/accounts/{TRADIER_ACCOUNT_ID}/orders"
                                requests.post(order_url, data={'class':'option','symbol':'SPY','option_symbol':lotto['symbol'],'side':'buy_to_open','quantity':qty,'type':'market','duration':'day'}, headers={'Authorization':f'Bearer {TRADIER_TOKEN}'})
                                mark_as_traded() # LOCK THE MEMORY
                                send_alert(f"🚀 TRADE FIRED: {qty} {lotto['symbol']} (Gap: {gap:.2f})")
                                print("🔒 MEMORY LOCKED: No more trades for today.", flush=True)
            else:
                if time_val % 5 == 0: # Print status every 5 mins
                    print("✅ Daily trade limit met. Monitoring market...", flush=True)

        elif time_val >= 1601:
            send_alert("🌙 Market closed. Good night Richmond.")
            return   
            
        time.sleep(30)

if __name__ == "__main__":
    main()
