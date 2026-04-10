import os
import time
import requests
from datetime import datetime
import pytz

# 🩺 SYSTEM CHECK: This will print as soon as the bot starts
print("🩺 SYSTEM CHECK: Bot script is loading...")

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

def get_kalshi_signal():
    ticker = "KXINX-26APR10H1600-B6812"
    url = f"https://api.elections.kalshi.com/trade-api/v2/markets/{ticker}"
    
    try:
        raw_response = requests.get(url)
        print(f"DEBUG: Kalshi Status {raw_response.status_code}")
        
        if raw_response.status_code != 200:
            return 0
            
        data = raw_response.json()
        prob = data.get('market', {}).get('yes_price', 0) / 100.0
        return prob
    except Exception as e:
        print(f"Kalshi Error: {e}")
        return 0

def get_tradier_lottos(symbol):
    url = "https://sandbox.tradier.com/v1/markets/options/chains"
    today = datetime.now(EST).strftime("%Y-%m-%d")
    params = {'symbol': symbol, 'expiration': today, 'greeks': 'true'}
    headers = {'Authorization': f'Bearer {TRADIER_TOKEN}', 'Accept': 'application/json'}
    
    try:
        response = requests.get(url, params=params, headers=headers).json()
        # Safety check: if no options are found, return None
        if 'options' not in response or response['options'] is None:
            return None
            
        options = response['options']['option']
        lottos = [opt for opt in options if opt['option_type'] == 'put' and 0.05 <= opt['ask'] <= 0.12]
        
        if lottos:
            return sorted(lottos, key=lambda x: x['greeks']['delta'])[0]
    except Exception as e:
        print(f"Tradier Error: {e}")
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
    send_alert("🤖 Bot is online and hunting for Tail Risk in Richmond...")
    
    while True:
        now = datetime.now(EST)
        current_time_val = now.hour * 100 + now.minute
        
        if 1030 <= current_time_val < 1600:
            k_prob = get_kalshi_signal()
            lotto = get_tradier_lottos("SPY")
            
            if k_prob:
                print(f"📊 Kalshi Prob: {k_prob:.2f}")
            
            if lotto:
                opt_prob = abs(lotto['greeks']['delta'])
                print(f"📈 Tradier Prob: {opt_prob:.2f} (Strike: {lotto['strike']})")
                print(f"⚖️ Current Gap: {abs(k_prob - opt_prob):.2f}")
                
                if k_prob > (opt_prob + PROB_EDGE_THRESHOLD):
                    qty = int(MAX_RISK_PER_TRADE / (lotto['ask'] * 100))
                    if qty > 0:
                        place_paper_order(lotto['symbol'], qty)
                        time.sleep(3600) 
            else:
                print("❌ Tradier: No cheap 'Lotto' puts found in the $0.05-$0.12 range.")
            
        elif now.hour == 15 and now.minute == 15:
            send_alert("💰 POSITIONS CLOSED: End of day safety check.")
            
        elif current_time_val >= 1601:
            send_alert("🌙 Market is closed. Heading home.")
            return   
            
        print("⏳ Waiting 5 minutes for next scan...")
        time.sleep(300)

# --- 4. THE ENTRY POINT (DO NOT DELETE THIS!) ---
if __name__ == "__main__":
    main()
