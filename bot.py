import os
import time
import requests
from datetime import datetime
import pytz

# 🩺 SYSTEM CHECK: Final push loading...
print("🩺 SYSTEM CHECK: High-Frequency Bot is loading...")

# --- 1. CONFIGURATION ---
TRADIER_TOKEN = os.getenv("TRADIER_TOKEN")
TRADIER_ACCOUNT_ID = os.getenv("TRADIER_ACCOUNT_ID")
KALSHI_API_KEY = os.getenv("KALSHI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SYMBOLS = ["SPY"]
MAX_RISK_PER_TRADE = 200 
PROB_EDGE_THRESHOLD = 0.03 
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
        quote_data = response.get('quotes', {}).get('quote', {})
        if isinstance(quote_data, list):
            quote_data = quote_data[0]
        return float(quote_data.get('last', 0))
    except Exception as e:
        print(f"Tradier Price Error: {e}")
        return None

def get_automated_ticker_and_prob():
    """Finds today's ticker AND its probability in one single move."""
    spy_price = get_current_spy_price()
    if not spy_price:
        return None, 0
    
    spx_approx = spy_price * 10
    now = datetime.now(EST)
    date_str = now.strftime("%y%b%d").upper()
    event_ticker = f"KXINX-{date_str}H1600"
    
    url = f"https://api.elections.kalshi.com/trade-api/v2/events/{event_ticker}?with_nested_markets=true"
    
    try:
        response = requests.get(url).json()
        markets = response.get('markets', []) or response.get('event', {}).get('markets', [])
        
        for m in markets:
            floor = m.get('floor_strike', 0)
            cap = m.get('cap_strike', 99999)
            if floor <= spx_approx <= cap:
                # Grab price directly from the discovery object
                price_raw = m.get('last_price') or m.get('yes_ask') or m.get('yes_bid') or 0
                prob = float(price_raw) / 100.0 if price_raw > 1 else float(price_raw)
                
                print(f"🎯 Match: {m['ticker']} | Kalshi Prob: {prob:.2f}")
                return m['ticker'], prob
    except Exception as e:
        print(f"Discovery Error: {e}")
    return None, 0

def get_tradier_lottos(symbol):
    url = "https://sandbox.tradier.com/v1/markets/options/chains"
    today = datetime.now(EST).strftime("%Y-%m-%d")
    params = {'symbol': symbol, 'expiration': today, 'greeks': 'true'}
    headers = {'Authorization': f'Bearer {TRADIER_TOKEN}', 'Accept': 'application/json'}
    try:
        response = requests.get(url, params=params, headers=headers).json()
        if 'options' not in response or response['options'] is None:
            return None
        options = response['options']['option']
        lottos = [opt for opt in options if opt['option_type'] == 'put' and 0.05 <= opt['ask'] <= 0.12]
        if lottos:
            return sorted(lottos, key=lambda x: x['greeks']['delta'])[0]
    except Exception as e:
        print(f"Tradier Lotto Error: {e}")
    return None

def place_paper_order(option_symbol, qty):
    url = f"https://sandbox.tradier.com/v1/accounts/{TRADIER_ACCOUNT_ID}/orders"
    headers = {'Authorization': f'Bearer {TRADIER_TOKEN}', 'Accept': 'application/json'}
    data = {
        'class': 'option', 'symbol': 'SPY', 'option_symbol': option_symbol,
        'side': 'buy_to_open', 'quantity': qty, 'type': 'market', 'duration': 'day'
    }
    requests.post(url, data=data, headers=headers)
    send_alert(f"🚀 ORDER PLACED: Bought {qty} contracts of {option_symbol}")

# --- 3. MAIN EXECUTION LOOP ---

def main():
    send_alert("🤖 Bot is active. Final 15 minutes of the hunt in Richmond!")
    
    while True:
        now = datetime.now(EST)
        current_time_val = now.hour * 100 + now.minute
        
        # Runs until 4:00 PM EST (3:00 PM CST)
        if 1030 <= current_time_val < 1600:
            ticker, k_prob = get_automated_ticker_and_prob()
            
            if ticker and k_prob > 0:
                lotto = get_tradier_lottos("SPY")
                
                if lotto:
                    opt_prob = abs(lotto['greeks']['delta'])
                    gap = abs(k_prob - opt_prob)
                    
                    print(f"📊 Kalshi Prob: {k_prob:.2f}")
                    print(f"📈 Tradier Prob: {opt_prob:.2f} (Strike: {lotto['strike']})")
                    print(f"⚖️ Current Gap: {gap:.2f}")
                    
                    if k_prob > (opt_prob + PROB_EDGE_THRESHOLD):
                        qty = int(MAX_RISK_PER_TRADE / (lotto['ask'] * 100))
                        if qty > 0:
                            place_paper_order(lotto['symbol'], qty)
                            time.sleep(3600) # Trade cooldown
                else:
                    print("❌ Tradier: No cheap puts found in range.")
            else:
                print("⚠️ No valid Kalshi price signal found yet.")
            
        elif current_time_val >= 1601:
            send_alert("🌙 Market is closed. Heading home.")
            return   
            
        print("⏳ Fast Scan: Waiting 30 seconds...")
        time.sleep(30)

if __name__ == "__main__":
    main()
