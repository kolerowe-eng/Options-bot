import os
import time
import requests
from datetime import datetime
import pytz

# 🩺 SYSTEM CHECK: Final 10-minute push...
print("🩺 SYSTEM CHECK: Zero-Proof Bot is loading for the Close...")

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
        return None

def get_automated_ticker_and_prob():
    spy_price = get_current_spy_price()
    if not spy_price:
        return None, 0
    
    spx_approx = spy_price * 10
    now = datetime.now(EST)
    date_str = now.strftime("%y%b%d").upper()
    event_ticker = f"KXINX-{date_str}H1600"
    
    # We use the nested markets endpoint to get all brackets at once
    url = f"https://api.elections.kalshi.com/trade-api/v2/events/{event_ticker}?with_nested_markets=true"
    
    try:
        response = requests.get(url).json()
        markets = response.get('markets', []) or response.get('event', {}).get('markets', [])
        
        for m in markets:
            floor = m.get('floor_strike', 0)
            cap = m.get('cap_strike', 99999)
            if floor <= spx_approx <= cap:
                # --- THE NUCLEAR PRICE SENSOR ---
                # We check every possible V2 field for a price
                price_raw = (
                    m.get('yes_bid') or 
                    m.get('yes_ask') or 
                    m.get('last_price') or 
                    m.get('mid_price') or 
                    m.get('yes_price', 0)
                )
                
                # Convert to 0.XX format (Kalshi uses cents, e.g., 45)
                prob = float(price_raw) / 100.0 if price_raw > 1 else float(price_raw)
                
                print(f"🎯 Match: {m['ticker']} | Kalshi Price: {prob:.2f}")
                return m['ticker'], prob
    except Exception as e:
        print(f"Discovery Error: {e}")
    return None, 0

def get_tradier_lottos(symbol):
    url = "https://sandbox.tradier.com/v1/markets/options/chains"
    today = datetime.now(EST).strftime("%Y-%m-%d")
    # We expand the search for the final minutes
    params = {'symbol': symbol, 'expiration': today, 'greeks': 'true'}
    headers = {'Authorization': f'Bearer {TRADIER_TOKEN}', 'Accept': 'application/json'}
    try:
        response = requests.get(url, params=params, headers=headers).json()
        if 'options' not in response or response['options'] is None:
            return None
        options = response['options']['option']
        # FINAL MINUTE SETTINGS: Look for anything between $0.01 and $0.15
        lottos = [opt for opt in options if opt['option_type'] == 'put' and 0.01 <= opt['ask'] <= 0.15]
        if lottos:
            return sorted(lottos, key=lambda x: x['greeks']['delta'])[0]
    except Exception as e:
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
    send_alert("🤖 Final Countdown! Bot is hunting with 30-second scans...")
    
    while True:
        now = datetime.now(EST)
        current_time_val = now.hour * 100 + now.minute
        
        if 1030 <= current_time_val < 1600:
            ticker, k_prob = get_automated_ticker_and_prob()
            
            # Now we allow the loop to continue even if prob is very low
            if ticker and k_prob > 0:
                lotto = get_tradier_lottos("SPY")
                
                if lotto:
                    opt_prob = abs(lotto['greeks']['delta'])
                    gap = k_prob - opt_prob # We want Kalshi to be higher
                    
                    print(f"📊 Probabilities -> Kalshi: {k_prob:.2f} | Tradier: {opt_prob:.2f}")
                    print(f"⚖️ Edge: {gap:.2f}")
                    
                    if gap > PROB_EDGE_THRESHOLD:
                        qty = int(MAX_RISK_PER_TRADE / (lotto['ask'] * 100))
                        if qty > 0:
                            place_paper_order(lotto['symbol'], qty)
                            time.sleep(3600) 
                else:
                    print("❌ Tradier: No puts found in the $0.01-$0.15 range.")
            else:
                print("⚠️ Kalshi signal is still 0.00. Searching for liquidity...")
            
        elif current_time_val >= 1601:
            send_alert("🌙 Market is closed. Great hunt today!")
            return   
            
        time.sleep(30)

if __name__ == "__main__":
    main()
