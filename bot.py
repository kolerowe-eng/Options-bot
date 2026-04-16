import os
import time
import requests
from datetime import datetime
import pytz

# 🩺 SYSTEM CHECK: Smart-Filter Bot is loading...
print("🩺 SYSTEM CHECK: Sovereign Bot (v2.1) is online.", flush=True)

# --- 1. CONFIGURATION ---
TRADIER_TOKEN = os.getenv("TRADIER_TOKEN")
TRADIER_ACCOUNT_ID = os.getenv("TRADIER_ACCOUNT_ID")
KALSHI_API_KEY = os.getenv("KALSHI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

PROB_EDGE_THRESHOLD = 0.03 
MAX_RISK_PER_TRADE = 200   
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
        
        if not markets:
            print(f"⚠️ Kalshi: No markets found for {date_str}. Check ticker format.", flush=True)
            return None, 0

        for m in markets:
            floor = m.get('floor_strike', 0)
            cap = m.get('cap_strike', 99999)
            if floor <= spx_approx <= cap:
                raw = (m.get('last_price_dollars') or m.get('yes_bid_dollars') or m.get('yes_ask_dollars') or m.get('last_price') or 0)
                prob = float(raw) / 100.0 if raw > 1 else float(raw)
                return m['ticker'], prob
        
        # If we reach here, we found markets but none match the price
        print(f"🔎 Price Alert: SPY at {spy_price}. No Kalshi bracket matches {spx_approx:.1f}", flush=True)
    except Exception as e:
        print(f"Discovery Error: {e}", flush=True)
    return None, 0

def get_today_active_positions():
    """ONLY counts positions that expire TODAY. Ignores yesterday's junk."""
    url = f"https://sandbox.tradier.com/v1/accounts/{TRADIER_ACCOUNT_ID}/positions"
    headers = {'Authorization': f'Bearer {TRADIER_TOKEN}', 'Accept': 'application/json'}
    today_str = datetime.now(EST).strftime("%Y-%m-%d")
    try:
        res = requests.get(url, headers=headers).json()
        all_pos = res.get('positions', {}).get('position', [])
        if not all_pos: return []
        if isinstance(all_pos, dict): all_pos = [all_pos]
        
        # Filter: Only keep positions where the symbol contains today's date
        # Tradier symbols look like: SPY260416P00695000
        short_date = datetime.now(EST).strftime("%y%m%d")
        active = [p for p in all_pos if short_date in p['symbol']]
        return active
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

# --- 3. MAIN LOOP ---

def main():
    send_alert("🤖 SMART-FILTER BOT ONLINE: Ignoring expired junk.")
    
    while True:
        now = datetime.now(EST)
        time_val = now.hour * 100 + now.minute
        
        if 930 <= time_val < 1550:
            # SENSOR: Only look at TODAY'S trades
            active_today = get_today_active_positions()
            
            if len(active_today) == 0:
                ticker, k_prob = get_automated_ticker_and_prob()
                
                if ticker and k_prob > 0:
                    print(f"🎯 Hunting: Found {ticker} at {k_prob:.2f}", flush=True)
                    # [Standard Entry Logic follows...]
                    url = "https://sandbox.tradier.com/v1/markets/options/chains"
                    params = {'symbol': 'SPY', 'expiration': now.strftime("%Y-%m-%d"), 'greeks': 'true'}
                    res = requests.get(url, params=params, headers={'Authorization': f'Bearer {TRADIER_TOKEN}', 'Accept': 'application/json'}).json()
                    options = res.get('options', {}).get('option', [])
                    lottos = [o for o in options if o['option_type'] == 'put' and 0.01 <= o['ask'] <= 0.20]
                    
                    if lottos:
                        lotto = sorted(lottos, key=lambda x: x['greeks']['delta'])[0]
                        opt_prob = abs(lotto['greeks']['delta'])
                        gap = k_prob - opt_prob
                        
                        if gap > PROB_EDGE_THRESHOLD:
                            qty = int(MAX_RISK_PER_TRADE / (lotto['ask'] * 100))
                            if qty > 0:
                                place_order(lotto['symbol'], qty)
                                send_alert(f"🚀 NEW TRADE: {qty} {lotto['symbol']}")
                                time.sleep(60)
                else:
                    # This tells you exactly why hunting isn't starting
                    if not ticker: print("🔎 Scanner: Still looking for a matching Kalshi bracket...", flush=True)
            else:
                print(f"✅ Active Position Detected ({active_today[0]['symbol']}). Monitoring exit...", flush=True)

        elif time_val >= 1601:
            send_alert("🌙 Day complete. Bot resting.")
            return   
            
        time.sleep(30)

if __name__ == "__main__":
    main()
