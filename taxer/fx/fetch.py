import pandas as pd
import numpy as np
import yfinance as yf

from typing import Callable

def get_fetch_fn(source: str) -> Callable[[str, str, bool], pd.DataFrame]:
    source = source.lower()
    if source == "sbi":
        return fetch_sbi_tt_buying_rates
    elif source == "yahoo":
        return fetch_yf_dollar_rates
    else:
        raise ValueError(f"Source {source} is not supported.")

def fetch_sbi_tt_buying_rates(start: str, end: str, business_days: bool = False) -> pd.DataFrame:
    """
    Fetches the SBI TT Buying Rates. The SBI Rates are fetched from
    sahilgupta/sbi-fx-ratekeeper github repository.

    Arguments:
        `business_days` (bool): Returns pandas.DataFrame with rates only for business days.

    Returns:
        Pandas DataFrame with SBI TT Buying rates.
    """
    df = pd.read_csv("https://raw.githubusercontent.com/sahilgupta/sbi-fx-ratekeeper/main/csv_files/SBI_REFERENCE_RATES_USD.csv")
    df["DATE"] = pd.to_datetime(df["DATE"]).dt.date
    df = df[["DATE", "TT BUY"]]

    # Take the last record per day based on datetime
    df = df.groupby("DATE").last().reset_index()
    df["DATE"] = pd.to_datetime(df["DATE"])
    df = df.sort_values(by=["DATE"]).reset_index(drop=True)
    df.rename(columns={"TT BUY": "Rate"}, inplace=True)
    
    dstart, dend = df["DATE"].iloc[0], df["DATE"].iloc[-1]
    dates = pd.date_range(start=f"{dstart.year}-01-01", end=f"{dend.year}-12-31", freq='D' if not business_days else 'B')
    df = df.set_index("DATE").reindex(dates).rename_axis("Date").reset_index()

    df["Rate"] = df["Rate"].replace(0, np.nan)
    df["Rate"] = df["Rate"].bfill()
    df["Rate"] = df["Rate"].round(2)
    return df


def fetch_yf_dollar_rates(start: str, end: str, business_days: bool = False) -> pd.DataFrame:
    """
    Fetches the INR to USD rates from Yahoo! Finance.

    Arguments:
        `start` (str): Start date in the format (YYYY-MM-DD)
        `end` (str): End date in the format (YYYY-MM-DD)
    
    Returns:
        Pandas DataFrame with Yahoo! Finance Rates
    """
    # yf does not include the end date in the results, hence increment by 1 day
    yf_end = (pd.to_datetime(end) + pd.Timedelta(days=1)).date().strftime("%Y-%m-%d")

    data = yf.Ticker("INR=X")
    df = data.history(start=start, end=yf_end)
    df = df.reset_index()
    df["Date"] = df["Date"].dt.date
    df = df[["Date", "Close"]]
    df = df.rename(columns={'Close': 'Rate'})

    dates = pd.date_range(start=start, end=end, freq='D' if not business_days else 'B')
    df = df.set_index("Date").reindex(dates).rename_axis("Date").reset_index()

    df["Rate"] = df["Rate"].bfill()
    df["Rate"] = df["Rate"].round(2)
    return df

