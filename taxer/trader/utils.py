import yfinance as yf

from typing import Dict, Any

def fetch_ticker_information(ticker: str, year: int) -> Dict[str, Any]:
    data = yf.Ticker(ticker)

    info = data.info
    
    d = {
        'Address': f"{info['address1']}, {info['city']}, {info['state']}, {info['country']}, {info['zip']}",
        'Zip Code': info['zip'].split("-")[0],
        'Country Name': 'United States of America',
        'Name': f"{info['longName']} ({info['symbol']})"
    }

    history = data.history(start=f"{year}-01-01", end=f"{year+1}-01-01")
    d['prices'] = history
    return d