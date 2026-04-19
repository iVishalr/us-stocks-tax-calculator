import argparse
import numpy as np
import os
import pandas as pd
import yfinance as yf

def main(file_path: str, save_path: str = "trades.csv"):
    dividends_df = pd.read_excel(file_path, sheet_name="All Transactions")
    trades_df = pd.read_excel(file_path, sheet_name="Trades")

    dividends_df = dividends_df[dividends_df["Type"].isin(["DIV", "DIVTAX"])].copy()
    dividends_df = dividends_df[dividends_df["Comment"] != "Dividend on Cash Balance"]
    dividends_df["Name"] = (
        dividends_df["Comment"]
        .str.replace(r"\s*,?\s*Inc\.?.*", ", Inc.", regex=True)
        .str.replace(r"\sDividend.*", "", regex=True)
        .str.strip()
    )
    dividends_df.reset_index(drop=True, inplace=True)

    trades_df["Name"] = trades_df["Name"].str.replace(r"\s*,?\s*Inc\.?.*", ", Inc.", regex=True).str.strip()
    name_to_ticker = trades_df.set_index("Name")["Ticker"].to_dict()

    # Add a new column "Ticker" in df_div
    dividends_df["Ticker"] = dividends_df["Name"].map(name_to_ticker)

    # Check if any names didn’t map (missing tickers)
    missing = dividends_df[dividends_df["Ticker"].isna()]["Name"].unique()
    if len(missing) > 0:
        print("Missing tickers for:", missing)

    # Copy to avoid modifying original
    df_div_expanded = dividends_df.copy()

    # Create trade-like columns in dividend df
    df_div_expanded["Activity"] = df_div_expanded["Type"]
    df_div_expanded["Order Type"] = ""
    df_div_expanded["Quantity"] = np.nan
    df_div_expanded["Price Per Share (in USD)"] = np.nan
    df_div_expanded["Cash Amount (in USD)"] = np.nan
    df_div_expanded["Commission Charges (in USD)"] = np.nan
    df_div_expanded["Amount"] = df_div_expanded["Amount (in USD)"].astype(float)

    # Reorder columns
    df_div_final = df_div_expanded[
        ["Date", "Time (in UTC)", "Name", "Ticker", "Activity", "Order Type",
        "Quantity", "Price Per Share (in USD)", "Cash Amount (in USD)",
        "Commission Charges (in USD)", "Amount"]
    ]

    # Align df_trades
    df_trades_aligned = trades_df.copy()
    df_trades_aligned["Amount"] = pd.Series([None] * len(df_trades_aligned), dtype="float64")
    df_trades_aligned = df_trades_aligned[
        ["Date", "Time (in UTC)", "Name", "Ticker", "Activity", "Order Type",
        "Quantity", "Price Per Share (in USD)", "Cash Amount (in USD)",
        "Commission Charges (in USD)", "Amount"]
    ]

    # Merge
    df_all = pd.concat([df_trades_aligned, df_div_final], ignore_index=True)
    df_all["Datetime"] = pd.to_datetime(df_all["Date"] + " " + df_all["Time (in UTC)"])
    df_all = df_all.sort_values("Datetime").reset_index(drop=True)
    df_all = df_all.drop(columns=["Datetime", "Time (in UTC)", "Cash Amount (in USD)", "Order Type"])
    df_all = df_all.rename(columns={'Activity': 'Type', 'Quantity': 'Units', 'Price Per Share (in USD)': 'Price', 'Commission Charges (in USD)': 'Commission'})

    # Adjust for stock splits
    tickers = df_all['Ticker'].unique()
    df_all["Date"] = pd.to_datetime(df_all["Date"], utc=True).dt.normalize()
    for ticker in tickers:
        data = yf.Ticker(ticker)
        splits = data.splits  # Series: Date -> ratio

        for split_date, ratio in splits.items():
            split_date = pd.to_datetime(split_date) # type: ignore

            if split_date.tzinfo is None:  # tz-naive → localize
                split_date = split_date.tz_localize("UTC")
            else:  # tz-aware → convert
                split_date = split_date.tz_convert("UTC")

            split_date = split_date.normalize()

            mask = (df_all["Ticker"] == ticker) & (df_all["Date"] < split_date)
            df_all.loc[mask, "Units"] *= ratio
            df_all.loc[mask, "Price"] /= ratio

    df_all["Date"] = df_all["Date"].dt.date
    df_all["Type"] = df_all["Type"].str.replace("^DIV$", "Dividend", regex=True)
    df_all["Type"] = df_all["Type"].str.replace("DIVTAX", "Dividend_tax")
    df_all.to_csv(save_path, index=False)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-f", "--file", required=True, help="Path to vested finance transactions excel sheet. (required)")
    parser.add_argument("-o", "--output", default="vested_finance_trades.csv", help="Path to store the processed data (CSV)")
    args = parser.parse_args()

    if not os.path.exists(args.file):
        raise FileNotFoundError(f"{args.file}: no such file or directory found")

    output_dir = os.path.dirname(args.output)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    main(args.file, args.output)
