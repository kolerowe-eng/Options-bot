import os
import time
import requests
from datetime import datetime
import pytz

# 🩺 SYSTEM CHECK: Initializing the "Bad Boy"
print("🩺 SYSTEM CHECK: High-Frequency Auto-Discovery Bot is loading...", flush=True)

# --- 1. CONFIGURATION ---
TRADIER_TOKEN = os.getenv("TRADIER_TOKEN")
TRADIER_ACCOUNT_ID = os.getenv("TRADIER_ACCOUNT_ID")
KALSHI_API_KEY = os.getenv("KALSHI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

PROB_EDGE_THRESHOLD = 0.03 # 3% Edge required to fire
MAX_RISK_PER_TRADE = 200   # Max dollars to spend per trade
EST = pytz.timezone('US/Eastern')

# --- 2. CORE FUNCTIONS ---

def send_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message})
    except Exception as e:
        print(f"Telegram Error: {e}", flush=True)

def get_current_spy_price():
    """Asks Tradier for current SPY price to find the right Kalshi bracket."""
    url = "https://sandbox.tradier.com/v1/markets/quotes"
    params = {'symbols': 'SPY'}
    headers = {'Authorization': f'Bearer {TRADIER_TOKEN}', 'Accept': 'application/json'}
    try:
        response = requests.get(url, params=params, headers=headers).json()
        quote = response.get('quotes', {}).get('quote', {})
        if isinstance(quote, list): quote = quote[0]
        return float(quote.get('last', 0))
    except Exception as e:
        print(f"Tradier Price Error: {e}", flush=True)
        return None

def get_automated_ticker():
    """Matches current SPY price to today's Kalshi KXINX brackets."""
    spy_price = get_current_spy_price()
    if not spy_price: return None
    
    spx_approx = spy_price * 10
    now = datetime.now(EST)
    date_str = now.strftime("%y%b%d").upper() # e.g., 26APR14
    event_ticker = f"KXINX-{date_str}H1600"
    
    url = f"https://api.elections.kalshi.com/trade-api/v2/events/{event_ticker}?with_nested_markets=true"
    try:
        res = requests.get(url).json()
        markets = res.get('markets', []) or res.get('event', {}).get('markets', [])
        for m in markets:
            floor = m.get('floor_strike', 0)
            cap = m.get('cap_strike', 99999)
            if floor <= spx_approx <= cap:
                return m['ticker']
    except Exception as e:
        print(f"Discovery Error: {e}", flush=True)
    return None

def get_live_kalshi_prob(ticker):
    """Direct hit on a specific market to get the real probability."""
    url = f"https://api.elections.kalshi.com/trade-api/v2/markets/{ticker}"
    try:
        res = requests.get(url).json()
        m = res.get('market', {})
        # SENSOR: V2 dollar fields first, then legacy integers
        raw = (m.get('last_price_dollars') or m.get('yes_bid_dollars') or 
               m.get('yes_ask_dollars') or m.get('last_price') or 0)
        
        prob = float(raw)
        return prob / 100.0 if prob > 1.0 else prob
    except: return 0.0

def get_tradier_lottos(symbol):
    """Finds today's 'Lotto' puts in the sweet spot range."""
    url = "https://sandbox.tradier.com/v1/markets/options/chains"
    params = {
        'symbol': symbol, 
        'expiration': datetime.now(EST).strftime("%Y-%m-%d"), 
        'greeks': 'true'
    }
    headers = {'Authorization': f'Bearer {TRADIER_TOKEN}', 'Accept': 'application/json'}
    try:
        res = requests.get(url, params=params, headers=headers).json()
        options = res.get('options', {}).get('option', [])
        # Expanded range: 0.01 to 0.20 to catch final-hour movement
        lottos = [o for o in options if o['option_type'] == 'put' and 0.01 <= o['ask'] <= 0.20]
        return sorted(lottos, key=lambda x: x['greeks']['delta'])[0] if lottos else None
    except: return None

# --- 3. MAIN EXECUTION LOOP ---

def main():
    send_alert("🤖 BOT ONLINE: High-Frequency Discovery Brain is active in Richmond.")
    
    while True:
        now = datetime.now(EST)
        current_time_val = now.hour * 100 + now.minute
        
        # 10:30 AM to 4:00 PM EST (9:30 AM to 3:00 PM CST)
        if 1030 <= current_time_val < 1600:
            ticker = get_automated_ticker()
            if ticker:
                k_prob = get_live_kalshi_prob(ticker)
                lotto = get_tradier_lottos("SPY")
                
                if k_prob > 0 and lotto:
                    opt_prob = abs(lotto['greeks']['delta'])
                    gap = k_prob - opt_prob
                    
                    # LOGGING VITAL SIGNS
                    print(f"🎯 {ticker[-5:]} | Kalshi: {k_prob:.2f} | Tradier: {opt_prob:.2f} | Gap: {gap:.2f}", flush=True)
                    
                    if gap > PROB_EDGE_THRESHOLD:
                        qty = int(MAX_RISK_PER_TRADE / (lotto['ask'] * 100))
                        if qty > 0:
                            order_url = f"https://sandbox.tradier.com/v1/accounts/{TRADIER_ACCOUNT_ID}/orders"
                            headers = {'Authorization': f'Bearer {TRADIER_TOKEN}', 'Accept': 'application/json'}
                            data = {
                                'class': 'option', 'symbol': 'SPY', 'option_symbol': lotto['symbol'],
                                'side': 'buy_to_open', 'quantity': qty, 'type': 'market', 'duration': 'day'
                            }
                            try:
                                res = requests.post(order_url, data=data, headers=headers)
                                print(f"✅ TRADE FIRED: Status {res.status_code}", flush=True)
                                send_alert(f"🚀 ORDER EXECUTED: Bought {qty} contracts of {lotto['symbol']} (Gap: {gap:.2f})")
                                
                                # 5-MINUTE COOLDOWN (Keeps Railway alive while pausing)
                                print("⏳ Trade Cooldown: Resuming hunt in 5 minutes...", flush=True)
                                time.sleep(300)
                            except Exception as e:
                                print(f"⚠️ Order Error: {e}", flush=True)
                else:
                    print(f"🔎 Scanning... (Kalshi: {k_prob:.2f} | Tradier: {'Ready' if lotto else 'No Lottos'})", flush=True)
            else:
                print("❌ Discovery: No active bracket found for today's price.", flush=True)
            
        elif current_time_val >= 1601:
            send_alert("🌙 Market is closed. Great work today!")
            return   
            
        # 30-SECOND HEARTBEAT
        time.sleep(30)

if __name__ == "__main__":
    main()
