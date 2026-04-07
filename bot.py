import os
import time
import requests
from datetime import datetime
import pytz

# --- 1. CONFIGURATION (Stored in Railway Environment Variables) ---
TRADIER_TOKEN = os.getenv("TRADIER_TOKEN")
TRADIER_ACCOUNT_ID = os.getenv("TRADIER_ACCOUNT_ID")
KALSHI_API_KEY = os.getenv("KALSHI_API_KEY") # Use Kalshi V2 Key
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Trading Parameters
SYMBOLS = ["SPY"]
MAX_RISK_PER_TRADE = 200  # Dollars to spend on "Lottos"
PROB_EDGE_THRESHOLD = 0.15 # 15% discrepancy between Kalshi and Options
EST = pytz.timezone('US/Eastern')

# --- 2. CORE FUNCTIONS ---

def send_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message})

def get_kalshi_signal():
    """
    Fetches the probability of a market crash from Kalshi.
    Example Ticker: 'KXSPY-26APR06-D125' (SPY down 1.25% today)
    """
    # Note: You will need to update the ticker daily or automate the ticker search
    today_str = datetime.now(EST).strftime("%y%b%d").upper()
    ticker = f"KXSPY-{today_str}-D150" # SPY Down 1.5% 
    
    url = f"https://api.elections.kalshi.com/trade-api/v2/markets_by_ticker/{ticker}"
    raw_response = requests.get(url)
print(f"DEBUG: Status {raw_response.status_code}, Body: {raw_response.text}") # The X-Ray
response = raw_response.json()
    
    # Probability = Yes Price / 100
    try:
        prob = response['market']['yes_price'] / 100
        return prob
    except KeyError:
        return None

def get_tradier_lottos(symbol):
    """
    Finds 0DTE Puts priced between $0.05 and $0.10.
    """
    url = f"https://sandbox.tradier.com/v1/markets/options/chains"
    today = datetime.now(EST).strftime("%Y-%m-%d")
    
    params = {'symbol': symbol, 'expiration': today, 'greeks': 'true'}
    headers = {'Authorization': f'Bearer {TRADIER_TOKEN}', 'Accept': 'application/json'}
    
    response = requests.get(url, params=params, headers=headers).json()
    options = response['options']['option']
    
    # Filter for OTM Puts with low premiums (The 'Cheap Options')
    lottos = [opt for opt in options if opt['option_type'] == 'put' and 0.05 <= opt['ask'] <= 0.12]
    
    if lottos:
        # Return the one with the highest Delta (highest prob of those cheap options)
        return sorted(lottos, key=lambda x: x['greeks']['delta'])[0]
    return None

def place_paper_order(option_symbol, qty):
    url = f"https://sandbox.tradier.com/v1/accounts/{TRADIER_ACCOUNT_ID}/orders"
    headers = {'Authorization': f'Bearer {TRADIER_TOKEN}', 'Accept': 'application/json'}
    
    data = {
        'class': 'option',
        'symbol': 'SPY',
        'option_symbol': option_symbol,
        'side': 'buy_to_open',
        'quantity': qty,
        'type': 'market',
        'duration': 'day'
    }
    
    requests.post(url, data=data, headers=headers)
    send_alert(f"🚀 ORDER PLACED: Bought {qty} contracts of {option_symbol}")

# --- 3. MAIN EXECUTION LOOP ---

def main():
    send_alert("🤖 Bot is online and hunting for Tail Risk in Richmond...")
    
    while True:
        now = datetime.now(EST)
        
        # Only run between 10:30 AM and 3:15 PM EST
        if now.hour >= 10 and now.minute >= 30 and now.hour < 15:
            
            k_prob = get_kalshi_signal()
            lotto = get_tradier_lottos("SPY")
            
            if k_prob and lotto:
                # Option Delta as a proxy for market-implied probability
                opt_prob = abs(lotto['greeks']['delta'])
                
                # THE ARBITRAGE TRIGGER:
                # If Kalshi probability > Option Probability + Edge
                if k_prob > (opt_prob + PROB_EDGE_THRESHOLD):
                    qty = int(MAX_RISK_PER_TRADE / (lotto['ask'] * 100))
                    if qty > 0:
                        place_paper_order(lotto['symbol'], qty)
                        time.sleep(3600) # Sleep for 1 hour after a trade to prevent over-trading
            
        elif now.hour == 15 and now.minute == 15:
            send_alert("Closing positions for the day to avoid pin risk.")
            # Add logic here to sell all open positions
            
        time.sleep(300) # Check every 5 minutes

if __name__ == "__main__":
    main()
