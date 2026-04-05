import argparse
import numpy as np
import pandas as pd
import os

from tqdm import tqdm
from datetime import datetime
from typing import Dict, List, Any, Optional

from taxer.fx import RateFetcher
from taxer.trader import Executor
from taxer.trader.utils import fetch_ticker_information
from taxer.report.excel import ExcelWriter

class ScheduleFA:
    def __init__(self, df: pd.DataFrame, calender_year: str = ""):
        self.df = df
        self.rates = RateFetcher()
        self.trader = Executor()
        self.writer = ExcelWriter

        self.calender_year = int(calender_year) if calender_year else pd.to_datetime('today').year
        self._computation_results: Dict[str, pd.DataFrame] = {}

    def compute(self) -> pd.DataFrame:
        self._filter_upto_cy_end()
        self._execute_trades()

        trx_logs = self._get_trx_logs()
        computation_df = self._merge_trx_logs(trx_logs)

        min_lot_date = computation_df["lot_buy_date"].min()
        min_lot_date = str(min_lot_date.date())
        fx_rates_df = self.rates(start=min_lot_date, end=f"{self.calender_year}-12-31")
        fx_rates_df.reset_index(drop=True, inplace=True)

        computation_df = computation_df.merge(
            fx_rates_df.rename(columns={
                'Date': 'lot_buy_date',
                'Rate': 'fx_lot_buy_rate',
                'Rate_last_month_end': 'fx_lot_buy_rate_last_month_end'
            }), on="lot_buy_date",
            how="left"
        )
        computation_df["Lot Cost Basis (INR)"] = computation_df["lot_cost_basis"] * computation_df["fx_lot_buy_rate"]

        if 'sell_date' in computation_df.columns:
            computation_df = computation_df.merge(
                fx_rates_df.rename(columns={
                    'Date': 'sell_date',
                    'Rate': 'fx_sell_rate',
                    'Rate_last_month_end': 'fx_sell_rate_last_month_end'
                }), on="sell_date",
                how="left"
            )
            computation_df["Cost Basis (INR)"] = computation_df["sell_cost_basis"] * computation_df["fx_lot_buy_rate"]
            computation_df["Sell Proceeds (INR)"] = computation_df["sell_proceeds"] * computation_df["fx_sell_rate"]
            computation_df["Gains/Losses (INR)"] = computation_df["Sell Proceeds (INR)"] - computation_df["Cost Basis (INR)"]
        else:
            computation_df["sell_cost_basis"] = 0.0
            computation_df["sell_proceeds"] = 0.0
            computation_df["Cost Basis (INR)"] = 0.0
            computation_df["Sell Proceeds (INR)"] = 0.0
            computation_df["Gains/Losses (INR)"] = 0.0
            computation_df['sell_units'] = 0.0

        if 'dividend_date' in computation_df.columns:
            computation_df = computation_df.merge(
                fx_rates_df.rename(columns={
                    'Date': 'dividend_date',
                    'Rate': 'fx_dividend_rate',
                    'Rate_last_month_end': 'fx_dividend_rate_last_month_end'
                }), on="dividend_date",
                how="left"
            )
            computation_df["Dividend Received (INR)"] = computation_df["dividend_received"] * computation_df["fx_dividend_rate"]   
        else:
            computation_df["dividend_received"] = 0.0
            computation_df["Dividend Received (INR)"] = 0.0
        
        ticker_prices = {}
        for ticker in computation_df['ticker'].unique():
            ticker_prices[ticker] = fetch_ticker_information(ticker, self.calender_year)
        
        prices_df = self._get_price_history_for_tickers(computation_df, ticker_prices)

        merge_keys = ['ticker']
        if 'sell_date' in computation_df:
            merge_keys.append('sell_date')
        
        computation_df = computation_df.merge(prices_df, on=merge_keys, how="left")

        computation_df = computation_df.merge(
            fx_rates_df.rename(columns={
                'Date': 'Peak Date',
                'Rate': 'fx_peak_rate',
                'Rate_last_month_end': 'fx_peak_rate_last_month_end'
            }), on="Peak Date",
            how="left"
        )
        computation_df = computation_df.merge(
            fx_rates_df.rename(columns={
                'Date': 'Close Date',
                'Rate': 'fx_close_rate',
                'Rate_last_month_end': 'fx_close_rate_last_month_end'
            }), on="Close Date",
            how="left"
        )
        computation_df["Units for Valuation"] = np.where(
            computation_df['units_remaining'] > 0,
            computation_df['units_remaining'],
            computation_df['sell_units']
        )
        computation_df["Initial Value (USD)"] = computation_df["lot_cost_basis"]
        computation_df["Peak Value (USD)"] = computation_df["Peak (USD)"] * computation_df["Units for Valuation"]
        computation_df["Close Value (USD)"] = computation_df["Close (USD)"] * computation_df["units_remaining"]
        computation_df["Initial Value (INR)"] = computation_df["Initial Value (USD)"] * computation_df["fx_lot_buy_rate"]
        computation_df["Peak Value (INR)"] = computation_df["Peak Value (USD)"] * computation_df["fx_peak_rate"]
        computation_df["Close Value (INR)"] = computation_df["Close Value (USD)"] * computation_df["fx_close_rate"]
        computation_df.drop(columns=["Units for Valuation"], inplace=True)

        # Save intermediate computation
        computation_intermediate_df = computation_df.copy()

        aggregate_method = {
            # Lot info: keep first occurrence
            'lot_buy_date': 'first',
            'lot_buy_price': 'first',
            'lot_cost_basis': 'first',
            'lot_buy_commission': 'first',

            # Units
            'units_remaining': 'min',

            # Dividends
            'dividend_received': 'sum',
            'Dividend Received (INR)': 'sum',

            # Sells
            'sell_proceeds': 'sum',
            'Lot Cost Basis (INR)': 'sum',
            'Cost Basis (INR)': 'sum',
            'Sell Proceeds (INR)': 'sum',
            'Gains/Losses (INR)': 'sum',

            # Valuation Columns
            'Initial Value (USD)': 'max',
            'Peak Value (USD)': 'max',
            'Close Value (USD)': 'min',
            'Initial Value (INR)': 'max',
            'Peak Value (INR)': 'max',
            'Close Value (INR)': 'min',

            # Lot/Sell/Dividend/Peak/Close Fx rates
            'fx_lot_buy_rate': list,
            'fx_peak_rate': list,
            'fx_close_rate': list,

            # Dates: keep all as list
            'Peak Date': list,
            'Close Date': list
        }

        if 'sell_date' in computation_df:
            aggregate_method['fx_sell_rate'] = list
            aggregate_method['sell_date'] = list

        if 'dividend_date' in computation_df:
            aggregate_method['fx_dividend_rate'] = list
            aggregate_method['dividend_date'] = list

        computation_df = computation_df.groupby(['ticker', 'lot_id'], as_index=False).agg(aggregate_method)

        date_cols = ['sell_date', 'dividend_date', 'Peak Date', 'Close Date']
        for col in date_cols:
            if col not in computation_df:
                continue
            computation_df[col] = computation_df[col].apply(
                lambda x: ', '.join([pd.to_datetime(d).strftime('%Y-%m-%d') for d in x if pd.notnull(d)])
            )
        
        fx_cols = ['fx_lot_buy_rate', 'fx_sell_rate', 'fx_dividend_rate', 'fx_peak_rate', 'fx_close_rate']
        for col in fx_cols:
            if col not in computation_df:
                continue
            computation_df[col] = computation_df[col].apply(
                lambda x: ', '.join([str(d) for d in x if pd.notnull(d)])
            )
        
        ticker_info = {}
        ticker_prices_dict = {}
        for ticker, ticker_data in ticker_prices.items():
            ticker_prices_dict[ticker] = ticker_data.pop('prices')
            ticker_info[ticker] = ticker_data
        
        prices_list = []
        for ticker, df in ticker_prices_dict.items():
            df = df.copy()
            df['ticker'] = ticker
            prices_list.append(df)
        
        ticker_prices_df = pd.concat(prices_list).reset_index().rename(columns={'index': 'Date'})
        ticker_prices_df['Date'] = pd.to_datetime(ticker_prices_df['Date']).dt.tz_localize(None)
        for col in ticker_prices_df.select_dtypes(include=["datetime64[ns]"]).columns:
            ticker_prices_df[col] = ticker_prices_df[col].dt.tz_localize(None)

        ticker_info_df = pd.DataFrame.from_dict(ticker_info, orient='index').reset_index()
        ticker_info_df.rename(columns={'index': 'ticker'}, inplace=True)

        computation_df = computation_df.merge(
            ticker_info_df,
            on='ticker',
            how='left'
        )

        # Save aggregate df
        computation_aggregate_df = computation_df.copy()

        computation_df['Sr No'] = range(1, len(computation_df) + 1)
        computation_df['Nature of Entity'] = 'Company'
        summary_columns = ['Sr No', 'Country Name', 'Name', 'Address', 'Zip Code', 'Nature of Entity', 'lot_buy_date', 'Initial Value (INR)', 'Peak Value (INR)', 'Close Value (INR)', 'Dividend Received (INR)', 'Sell Proceeds (INR)']
        computation_df = computation_df[summary_columns]
        computation_df.rename(columns={
            'lot_buy_date': 'Date of acquiring the interest/stake',
            'Dividend Received (INR)': 'Total gross amount paid wrt the holding during the period',
            'Sell Proceeds (INR)': 'Total gross proceeds from sale or redemption of investment'
        }, inplace=True)

        for df in [computation_df, computation_aggregate_df, computation_intermediate_df, ticker_prices_df]:
            for col in df.select_dtypes(include=["datetime64[ns]", "datetime64", "datetime"]).columns:
                df[col] = df[col].dt.strftime('%d-%m-%Y')

        # Units at the end of CY
        units_df = pd.DataFrame(list(self.trader.units.copy().items()), columns=['Ticker', 'Units'])
        units_df = units_df[units_df['Units'] > 0]
        units_df.sort_values(by=['Ticker'],inplace=True)
        units_df.rename(columns={'Units': f"Units as of {self.calender_year}-12-31"}, inplace=True)

        self._computation_results["Summary"] = computation_df
        self._computation_results["Computation"] = computation_aggregate_df
        self._computation_results["Breakdown"] = computation_intermediate_df
        self._computation_results["Stock Price History"] = ticker_prices_df
        self._computation_results["Final Holdings"] = units_df

        return computation_aggregate_df

    def dump(self, save_path: str = "ScheduleFA.xlsx") -> None:
        writer = self.writer(save_path)
        writer.dump(self._computation_results)
        print(f"Saved computation results in {save_path}.")

    def _execute_trades(self):
        d = self.df.to_dict("list")
        zipped = zip(d['Date'], d['Ticker'], d['Type'], d['Price'], d['Units'], d['Commission'], d['Amount'])
        for date, ticker, trx_type, price, units, commission, amount in tqdm(zipped, total=len(d['Date'])):
            self.trader.execute(
                date=date, 
                ticker=ticker,
                trx_type=trx_type,
                price=price,
                units=units,
                commission=commission,
                amount=amount
            )

    @property
    def units(self) -> Dict[str, float]:
        return self.trader.units.copy()
    
    def _filter_upto_cy_end(self) -> None:
        self.df["Date"] = pd.to_datetime(self.df["Date"])
        cutoff = pd.Timestamp(f"{self.calender_year}-12-31")
        self.df = self.df[self.df["Date"] <= cutoff]
    
    def _to_dataframe(self, d: Dict[str, List[Dict[str, Any]]], schema: Optional[List[str]] = None) -> pd.DataFrame:
        rows = []
        for ticker, lots in d.items():
            for lot in lots:
                rows.append({"ticker": ticker, **lot})
        df = pd.DataFrame(rows)
        if df.empty:
            return pd.DataFrame(columns=schema)
        else:
            return df
    
    def _get_trx_logs(self) -> Dict[str, List[Dict[str, Any]]]:
        tickers = self._get_tickers_in_calender_year()
        trx_logs: Dict[str, List[Dict[str, Any]]] = {}

        def collect_logs(lots):
            for lot in lots:
                lot_trx_logs: List[Dict[str, Any]] = lot.trx_log.get(f"CY{self.calender_year}", [])
                for item in lot_trx_logs:
                    trx_logs.setdefault(item["type"], []).append(item)

        for _, lots in self.trader.lots.items():
            collect_logs(lots)

        for closed_ticker, lots in self.trader.closed_lots.items():
            if closed_ticker not in tickers:
                continue
            collect_logs(lots)
        
        return trx_logs
    
    def _merge_trx_logs(self, trx_logs: Dict[str, List[Dict[str, Any]]]) -> pd.DataFrame:
        data: Dict[str, List[Dict[str, Any]]] = {}
        sell_data: Dict[str, List[Dict[str, Any]]] = {}
        dividend_data: Dict[str, List[Dict[str, Any]]] = {}

        for ticker, lots in self.trader.lots.items():
            for lot in lots:
                d = {
                    'lot_id': lot.lotid,
                    'lot_buy_date': lot.date,
                    'lot_buy_units': lot.initial_units,
                    'lot_buy_price': lot.price,
                    'lot_buy_commission': lot.commission,
                    'lot_cost_basis': (lot.initial_units * lot.price) + lot.commission,
                    'units_remaining': lot.units
                }

                if ticker not in data:
                    data[ticker] = []
                data[ticker].append(d)

        lot_schema = self._get_lot_schema()
        for trx_type in ['SELL', 'DIVIDEND']:
            for trx in trx_logs.get(trx_type, []):
                ticker = trx['lot_ticker']
                if trx_type == 'SELL':
                    schema = {**lot_schema}
                    schema.update(self._get_sell_schema())
                elif trx_type == 'DIVIDEND':
                    schema = {**lot_schema}
                    schema.update(self._get_dividend_schema())
                
                d = {k: trx[v] for k, v in schema.items()}
                trx_data = sell_data if trx_type == "SELL" else dividend_data
                if ticker not in trx_data:
                    trx_data[ticker] = []
                trx_data[ticker].append(d)
        
        dfs: List[pd.DataFrame] = []
        for k, df_data in {'FA': data, 'SELL': sell_data, 'DIVIDEND': dividend_data}.items():
            schema = ["ticker"]
            schema.extend(list(lot_schema.keys()))
            if k == 'SELL':
                schema.extend(list(self._get_sell_schema().keys()))
            elif k == 'DIVIDEND':
                schema.extend(list(self._get_dividend_schema().keys()))
            df = self._to_dataframe(df_data, schema=schema)
            dfs.append(df)
        
        fa_df, sell_df, dividend_df = dfs
        merge_keys = ["ticker"] + list(lot_schema.keys())

        df = fa_df
        for _df in [sell_df, dividend_df]:
            if _df.empty:
                continue
            df = df.merge(
                _df,
                on=merge_keys,
                how="outer"
            )

        return df

    def _get_tickers_in_calender_year(self) -> List[str]:
        tickers = self.df[self.df["Date"] >= f'{self.calender_year}-01-01']['Ticker'].unique()
        tickers = tickers.tolist()
        return tickers
    
    def _get_price_history_for_tickers(self, df: pd.DataFrame, ticker_prices: Dict[str, Any]) -> pd.DataFrame:
        results = []

        # Pre-group by unique ticker/sell_date combos
        col_filters = ["ticker"]
        if 'sell_date' in df:
            col_filters.append("sell_date")

        unique_pairs = df[col_filters].drop_duplicates()

        for _, row in unique_pairs.iterrows():
            ticker = row["ticker"]
            sell_date = pd.to_datetime(row["sell_date"]) if 'sell_date' in row and pd.notna(row["sell_date"]) else None

            history = ticker_prices[ticker]['prices'].copy()
            history.index = pd.to_datetime(history.index).tz_localize(None)  # ensure clean index

            if sell_date is not None:
                # Case 1: Use only data up to sell_date
                filtered = history[history.index <= sell_date]

                if not filtered.empty:
                    peak_date = filtered["High"].idxmax()
                    max_high = filtered.loc[peak_date, "High"]

                    close_date = filtered.index[-1]
                    close = filtered.iloc[-1]["Close"]
                else:
                    peak_date, max_high, close_date, close = None, None, None, None

            else:
                # Case 2: Global peak + close
                peak_date = history["High"].idxmax()
                max_high = history.loc[peak_date, "High"]

                close_date = history.index[-1]
                close = history.iloc[-1]["Close"]

            entry = {
                "ticker": ticker,
                "sell_date": sell_date,
                "Peak (USD)": max_high,
                "Peak Date": peak_date,
                "Close (USD)": close,
                "Close Date": close_date,
            }

            if sell_date is None:
                entry.pop("sell_date")

            results.append(entry)

        return pd.DataFrame(results)
    
    def _get_lot_schema(self) -> Dict[str, str]:
        return {
            'lot_id': "lot_id", 
            'lot_buy_date': "lot_buy_date", 
            'lot_buy_units': "lot_buy_units", 
            'lot_buy_price': "lot_buy_price", 
            'lot_buy_commission': "lot_buy_commission", 
            'lot_cost_basis': "lot_cost_basis",
            'units_remaining': "units_remaining"
        }

    def _get_sell_schema(self) -> Dict[str, str]:
        return {
            'sell_date': "sell_date", 
            'sell_units': "sell_units", 
            'sell_cost_basis': "cost_basis",
            'sell_proceeds': "sell_proceeds", 
            'units_remaining': "units_remaining"
        }

    def _get_dividend_schema(self) -> Dict[str, str]:
        return {
            'dividend_date': "dividend_date", 
            'dividend_received': "dividend_received", 
            'units_remaining': "units"
        }

if __name__ == "__main__":
    current_year = datetime.now().year
    parser = argparse.ArgumentParser()
    parser.add_argument("-f", "--file", required=True, help="Path to CSV file containing trades (required)")
    parser.add_argument("-y", "--calender-year", type=int, default=current_year, help=f"Calender year to compute ScheduleFA. Default: {current_year}")
    parser.add_argument("-o", "--output", default="ScheduleFA.xlsx", help="Path to save the ScheduleFA. Default: ScheduleFA.xlsx")
    args = parser.parse_args()

    if not os.path.exists(args.file):
        raise FileNotFoundError(f"{args.file}: no such file or directory found")
    
    if args.calender_year > current_year:
        raise ValueError(f"expected calender year to be less than {current_year}, got {args.calender_year}")

    df = pd.read_csv(args.file)
    df["Date"] = pd.to_datetime(df["Date"])
    a = ScheduleFA(df=df, calender_year=str(args.calender_year))

    print("Computing ScheduleFA")

    a.compute()

    output_dir = os.path.dirname(args.output)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    a.dump(save_path=args.output)
