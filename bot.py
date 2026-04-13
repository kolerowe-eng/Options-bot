import os
import time
import requests
from datetime import datetime
import pytz

# 🩺 SYSTEM CHECK: Final 5-minute push...
print("🩺 SYSTEM CHECK: Market-Direct Bot is loading for the Close...")

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
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message})
    except Exception as e:
        print(f"Telegram Error: {e}")

def get_current_spy_price():
    url = "https://sandbox.tradier.com/v1/markets/quotes"
    params = {'symbols': 'SPY'}
    headers = {'Authorization': f'Bearer {TRADIER_TOKEN}', 'Accept': 'application/json'}
    try:
        response = requests.get(url, params=params, headers=headers).json()
        quote = response.get('quotes', {}).get('quote', {})
        if isinstance(quote, list): quote = quote[0]
        return float(quote.get('last', 0))
    except: return None

def get_live_kalshi_prob(ticker):
    """Direct hit on the specific market to get the real price."""
    url = f"https://api.elections.kalshi.com/trade-api/v2/markets/{ticker}"
    try:
        res = requests.get(url).json()
        m = res.get('market', {})
        
        # SENSOR: Check V2 dollar strings first, then legacy cent integers
        raw = (m.get('last_price_dollars') or m.get('yes_bid_dollars') or 
               m.get('yes_ask_dollars') or m.get('last_price') or 
               m.get('yes_bid') or 0)
        
        # Convert to 0.XX format
        prob = float(raw)
        return prob / 100.0 if prob > 1.0 else prob
    except: return 0.0

def get_automated_ticker():
    spy_price = get_current_spy_price()
    if not spy_price: return None
    
    spx_approx = spy_price * 10
    date_str = datetime.now(EST).strftime("%y%b%d").upper()
    event_ticker = f"KXINX-{date_str}H1600"
    
    url = f"https://api.elections.kalshi.com/trade-api/v2/events/{event_ticker}?with_nested_markets=true"
    try:
        res = requests.get(url).json()
        markets = res.get('markets', []) or res.get('event', {}).get('markets', [])
        for m in markets:
            if m.get('floor_strike', 0) <= spx_approx <= m.get('cap_strike', 99999):
                return m['ticker']
    except: return None

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

# --- 3. MAIN EXECUTION LOOP ---

def main():
    send_alert("🤖 THE FINAL BELL: Bot is hunting the 3:00 PM close!")
    
    while True:
        now = datetime.now(EST)
        if 1030 <= (now.hour * 100 + now.minute) < 1600:
            ticker = get_automated_ticker()
            if ticker:
                k_prob = get_live_kalshi_prob(ticker)
                lotto = get_tradier_lottos("SPY")
                
                if k_prob > 0 and lotto:
                    opt_prob = abs(lotto['greeks']['delta'])
                    gap = k_prob - opt_prob
                    print(f"🎯 {ticker[-5:]} | Kalshi: {k_prob:.2f} | Tradier: {opt_prob:.2f} | Gap: {gap:.2f}")
                    
                    if gap > PROB_EDGE_THRESHOLD:
                        qty = int(MAX_RISK_PER_TRADE / (lotto['ask'] * 100))
                        if qty > 0:
                            # place_paper_order(lotto['symbol'], qty) logic here
                            url = f"https://sandbox.tradier.com/v1/accounts/{TRADIER_ACCOUNT_ID}/orders"
                            requests.post(url, data={'class':'option','symbol':'SPY','option_symbol':lotto['symbol'],'side':'buy_to_open','quantity':qty,'type':'market','duration':'day'}, headers={'Authorization':f'Bearer {TRADIER_TOKEN}'})
                            send_alert(f"🚀 TRADE FIRED: Bought {qty} contracts of {lotto['symbol']} (Gap: {gap:.2f})")
                            time.sleep(3600)
                else:
                    print(f"🔎 Scanning... (Kalshi: {k_prob:.2f} | Tradier: {'Ready' if lotto else 'No Lottos'})")
            
        elif (now.hour * 100 + now.minute) >= 1601:
            send_alert("🌙 Market is closed. Great work in Richmond today.")
            return   
            
        time.sleep(30)

if __name__ == "__main__":
    main()
