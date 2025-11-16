import argparse
import numpy as np
import pandas as pd
import os

from tqdm import tqdm
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple

from taxer.fx import RateFetcher
from taxer.trader import Executor
from taxer.report.excel import ExcelWriter

class CapitalGains:
    def __init__(self, df: pd.DataFrame, financial_year: str = "") -> None:
        self.df = df
        self.rates = RateFetcher()
        self.trader = Executor()
        self.writer = ExcelWriter

        self.financial_year = int(financial_year) if financial_year else pd.to_datetime('today').year
        self._computation_results: Dict[str, pd.DataFrame] = {}

    def compute(self) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        self._filter_upto_fy_end()
        self._execute_trades()

        trx_logs = self._get_trx_logs()
        computation_df = self._merge_trx_logs(trx_logs)

        min_lot_date = computation_df["lot_buy_date"].min()
        min_lot_date = str(min_lot_date.date())
        fx_rates_df = self.rates(start=min_lot_date, end=f"{self.financial_year + 1}-03-31")
        fx_rates_df.reset_index(drop=True, inplace=True)

        ltcg_df = computation_df[computation_df["gains_type"] == 'long']
        stcg_df = computation_df[computation_df["gains_type"] == 'short']
        dividends_df = computation_df[computation_df["dividend_date"].notna()]

        # -------------------
        # Calculate Dividend
        # -------------------
        dividends_df = dividends_df.merge(
            fx_rates_df.rename(columns={
                'Date': 'dividend_date',
                'Rate': 'fx_dividend_rate',
                'Rate_last_month_end': 'fx_dividend_rate_last_month_end'
            }), on="dividend_date",
            how="left"
        )
        dividends_df['dividend_tax_paid'] *= -1
        dividends_df['Dividend Received (INR)'] = dividends_df["dividend_received"] * dividends_df["fx_dividend_rate_last_month_end"]
        dividends_df['Dividend Tax Paid (INR)'] = dividends_df["dividend_tax_paid"] * dividends_df["fx_dividend_rate_last_month_end"]
        dividends_df['Net Dividend Received (INR)'] = dividends_df['Dividend Received (INR)'] - dividends_df['Dividend Tax Paid (INR)']
        dividends_df['Effective Tax Rate'] = round(100 * dividends_df['Dividend Tax Paid (INR)'] / dividends_df['Dividend Received (INR)'],2)
        dividends_df = dividends_df[["ticker", "dividend_date", "dividend_received", "dividend_tax_paid", "Dividend Received (INR)", "Dividend Tax Paid (INR)", "Net Dividend Received (INR)", "Effective Tax Rate", "fx_dividend_rate_last_month_end"]]
        dividends_df.sort_values(by=['dividend_date', 'ticker'], ascending=True, inplace=True)
        dividends_df.reset_index(drop=True, inplace=True)
        dividends_df.rename(columns={
            'ticker': 'Ticker',
            'dividend_date': 'Dividend Date',
            'dividend_received': 'Dividend Received (USD)',
            'dividend_tax_paid': 'Dividend Tax Paid (USD)',
            'fx_dividend_rate_last_month_end': 'USD/INR Conversion Rate'
        }, inplace=True)
        # ---------------
        # Calculate LTCG
        # ---------------
        ltcg_df = ltcg_df.merge(
            fx_rates_df.rename(columns={
                'Date': 'lot_buy_date',
                'Rate': 'fx_lot_buy_rate',
                'Rate_last_month_end': 'fx_lot_buy_rate_last_month_end'
            }), on="lot_buy_date",
            how="left"
        )
        ltcg_df = ltcg_df.merge(
            fx_rates_df.rename(columns={
                'Date': 'sell_date',
                'Rate': 'fx_sell_rate',
                'Rate_last_month_end': 'fx_sell_rate_last_month_end'
            }), on="sell_date",
            how="left"
        )
        ltcg_df['Gains/Losses (USD)'] = ltcg_df['sell_proceeds'] - ltcg_df['sell_cost_basis']
        ltcg_df['Cost Basis (INR)'] = ltcg_df['sell_cost_basis'] * ltcg_df['fx_lot_buy_rate_last_month_end']
        ltcg_df['Sell Proceeds (INR)'] = ltcg_df['sell_proceeds'] * ltcg_df['fx_sell_rate_last_month_end']
        ltcg_df['Gains/Losses (INR)'] = ltcg_df['Sell Proceeds (INR)'] - ltcg_df['Cost Basis (INR)']
        ltcg_df = ltcg_df[[
            "ticker", "lot_buy_date", "lot_buy_price", 
            "sell_date", "sell_units", "sell_cost_basis", "sell_proceeds", "Gains/Losses (USD)",
            'Cost Basis (INR)', 'Sell Proceeds (INR)', 'Gains/Losses (INR)', 
            'fx_lot_buy_rate_last_month_end', 'fx_sell_rate_last_month_end'
        ]]
        ltcg_df.sort_values(by=["sell_date"], inplace=True)
        ltcg_df.rename(columns={
            'ticker': 'Ticker',
            'lot_buy_date': 'Date Acquired',
            'lot_buy_price': 'Buy Price (USD)',
            'sell_date': 'Date Sold',
            'sell_units': 'Units Sold',
            'sell_cost_basis': 'Cost Basis (USD)',
            'sell_proceeds': 'Sell Proceeds (USD)',
            'fx_lot_buy_rate_last_month_end': 'USD/INR on Buy Date',
            'fx_sell_rate_last_month_end': 'USD/INR on Sell Date',
        }, inplace=True)
        # ---------------
        # Calculate STCG
        # ---------------
        stcg_df = stcg_df.merge(
            fx_rates_df.rename(columns={
                'Date': 'lot_buy_date',
                'Rate': 'fx_lot_buy_rate',
                'Rate_last_month_end': 'fx_lot_buy_rate_last_month_end'
            }), on="lot_buy_date",
            how="left"
        )
        stcg_df = stcg_df.merge(
            fx_rates_df.rename(columns={
                'Date': 'sell_date',
                'Rate': 'fx_sell_rate',
                'Rate_last_month_end': 'fx_sell_rate_last_month_end'
            }), on="sell_date",
            how="left"
        )
        stcg_df['Gains/Losses (USD)'] = stcg_df['sell_proceeds'] - stcg_df['sell_cost_basis']
        stcg_df['Cost Basis (INR)'] = stcg_df['sell_cost_basis'] * stcg_df['fx_lot_buy_rate_last_month_end']
        stcg_df['Sell Proceeds (INR)'] = stcg_df['sell_proceeds'] * stcg_df['fx_sell_rate_last_month_end']
        stcg_df['Gains/Losses (INR)'] = stcg_df['Sell Proceeds (INR)'] - stcg_df['Cost Basis (INR)']
        stcg_df = stcg_df[[
            "ticker", "lot_buy_date", "lot_buy_price", 
            "sell_date", "sell_units", "sell_cost_basis", "sell_proceeds", "Gains/Losses (USD)",
            'Cost Basis (INR)', 'Sell Proceeds (INR)', 'Gains/Losses (INR)', 
            'fx_lot_buy_rate_last_month_end', 'fx_sell_rate_last_month_end'
        ]]
        stcg_df.sort_values(by=["sell_date"], inplace=True)
        stcg_df.rename(columns={
            'ticker': 'Ticker',
            'lot_buy_date': 'Date Acquired',
            'lot_buy_price': 'Buy Price (USD)',
            'sell_date': 'Date Sold',
            'sell_units': 'Units Sold',
            'sell_cost_basis': 'Cost Basis (USD)',
            'sell_proceeds': 'Sell Proceeds (USD)',
            'fx_lot_buy_rate_last_month_end': 'USD/INR on Buy Date',
            'fx_sell_rate_last_month_end': 'USD/INR on Sell Date',
        }, inplace=True)

        # Format Date Acquired column in LTCG and STCG
        for df in [ltcg_df, stcg_df, dividends_df]:
            if df.empty:
                continue
            for col in ['Date Acquired', 'Date Sold', 'Dividend Date']:
                if col not in df.columns:
                    continue
                df[col] = pd.to_datetime(df[col]).dt.strftime('%d-%m-%Y')

        for df in [ltcg_df, stcg_df, dividends_df]:
            for col in df.select_dtypes(include=["datetime64[ns]"]).columns:
                df[col] = df[col].dt.tz_localize(None)

        summary_df = {}
        summary_df['Financial Year'] = f"FY{self.financial_year}-{self.financial_year+1}"
        # LTCG Summary
        summary_df['Long Term Capital Gains (USD)'] = str(round(ltcg_df[ltcg_df['Gains/Losses (USD)'] >= 0]['Gains/Losses (USD)'].sum(), 4))
        summary_df['Long Term Capital Losses (USD)'] = str(round(ltcg_df[ltcg_df['Gains/Losses (USD)'] < 0]['Gains/Losses (USD)'].sum() * -1, 4))
        _net_ltcg_usd = round(ltcg_df[ltcg_df['Gains/Losses (USD)'] >= 0]['Gains/Losses (USD)'].sum() - (ltcg_df[ltcg_df['Gains/Losses (USD)'] < 0]['Gains/Losses (USD)'].sum() * -1), 4)
        summary_df['Net Long Term Capital Gains (Losses) (USD)'] = str(_net_ltcg_usd) if _net_ltcg_usd >= 0 else f"({_net_ltcg_usd})"
        summary_df['Long Term Capital Gains (INR)'] = str(round(ltcg_df[ltcg_df['Gains/Losses (INR)'] >= 0]['Gains/Losses (INR)'].sum(), 4))
        summary_df['Long Term Capital Losses (INR)'] = str(round(ltcg_df[ltcg_df['Gains/Losses (INR)'] < 0]['Gains/Losses (INR)'].sum() * -1, 4))
        _net_ltcg_inr = round(ltcg_df[ltcg_df['Gains/Losses (INR)'] >= 0]['Gains/Losses (INR)'].sum() - (ltcg_df[ltcg_df['Gains/Losses (INR)'] < 0]['Gains/Losses (INR)'].sum() * -1), 4)
        summary_df['Net Long Term Capital Gains (Losses) (INR)'] = str(_net_ltcg_inr) if _net_ltcg_inr >= 0 else f"({_net_ltcg_inr})"
        
        # STCG Summary
        summary_df['Short Term Capital Gains (USD)'] = str(round(stcg_df[stcg_df['Gains/Losses (USD)'] >= 0]['Gains/Losses (USD)'].sum(), 4))
        summary_df['Short Term Capital Losses (USD)'] = str(round(stcg_df[stcg_df['Gains/Losses (USD)'] < 0]['Gains/Losses (USD)'].sum() * -1, 4))
        _net_stcg_usd = round(stcg_df[stcg_df['Gains/Losses (USD)'] >= 0]['Gains/Losses (USD)'].sum() - (stcg_df[stcg_df['Gains/Losses (USD)'] < 0]['Gains/Losses (USD)'].sum() * -1), 4)
        summary_df['Net Short Term Capital Gains (Losses) (USD)'] = str(_net_stcg_usd) if _net_stcg_usd >= 0 else f"({_net_stcg_usd})"
        summary_df['Short Term Capital Gains (INR)'] = str(round(stcg_df[stcg_df['Gains/Losses (INR)'] >= 0]['Gains/Losses (INR)'].sum(), 4))
        summary_df['Short Term Capital Losses (INR)'] = str(round(stcg_df[stcg_df['Gains/Losses (INR)'] < 0]['Gains/Losses (INR)'].sum() * -1, 4))
        _net_stcg_inr = round(stcg_df[stcg_df['Gains/Losses (INR)'] >= 0]['Gains/Losses (INR)'].sum() - (stcg_df[stcg_df['Gains/Losses (INR)'] < 0]['Gains/Losses (INR)'].sum() * -1), 4)
        summary_df['Net Short Term Capital Gains (Losses) (INR)'] = str(_net_stcg_inr) if _net_stcg_inr >= 0 else f"({_net_stcg_inr})"
        
        # Net Capital Gains
        _net_cg_usd = round(_net_stcg_usd + _net_ltcg_usd, 4)
        _net_cg_inr = round(_net_stcg_inr + _net_ltcg_inr, 4)
        summary_df[f'Net Captial Gains (Losses) (USD) [LTCG + STCG]'] = str(_net_cg_usd) if _net_cg_usd >= 0 else f'({_net_cg_usd})'
        summary_df[f'Net Captial Gains (Losses) (INR) [LTCG + STCG]'] = str(_net_cg_inr) if _net_cg_inr >= 0 else f'({_net_cg_inr})'

        # Dividends
        summary_df['Dividends Income (USD)'] = str(round(dividends_df['Dividend Received (USD)'].sum(), 4))
        summary_df['Dividends Income (INR)'] = str(round(dividends_df['Dividend Received (INR)'].sum(), 4))
        summary_df['Dividends Tax Paid (USD)'] = str(round(dividends_df['Dividend Tax Paid (USD)'].sum(), 4))
        summary_df['Dividends Tax Paid (INR)'] = str(round(dividends_df['Dividend Tax Paid (INR)'].sum(), 4))
        summary_df['Net Dividend Income (USD)'] = str(round(dividends_df['Dividend Received (USD)'].sum() - dividends_df['Dividend Tax Paid (USD)'].sum(), 4))
        summary_df['Net Dividend Income (INR)'] = str(round(dividends_df['Dividend Received (INR)'].sum() - dividends_df['Dividend Tax Paid (INR)'].sum(), 4))
        summary_df = pd.DataFrame(list(summary_df.items()), columns=["Field", "Value"])

        self._computation_results["Summary"] = summary_df
        self._computation_results["Long Term Capital Gains"] = ltcg_df
        self._computation_results["Short Term Capital Gains"] = stcg_df
        self._computation_results["Dividends"] = dividends_df

        return summary_df, ltcg_df, stcg_df, dividends_df

    def dump(self, save_path: str = "CapitalGains.xlsx") -> None:
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

    def _filter_upto_fy_end(self) -> None:
        self.df["Date"] = pd.to_datetime(self.df["Date"])
        cutoff = pd.Timestamp(f"{self.financial_year + 1}-03-31")
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
        tickers = self._get_tickers_in_financial_year()
        trx_logs: Dict[str, List[Dict[str, Any]]] = {}

        def collect_logs(lots):
            for lot in lots:
                lot_trx_logs: List[Dict[str, Any]] = lot.trx_log.get(f"FY{self.financial_year}-{self.financial_year+1}", [])
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
        dividend_tax_data: Dict[str, List[Dict[str, Any]]] = {}

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
        for trx_type in ['SELL', 'DIVIDEND', 'DIVIDEND_TAX']:
            for trx in trx_logs.get(trx_type, []):
                ticker = trx['lot_ticker']
                if trx_type == 'SELL':
                    trx_data = sell_data
                    schema = {**lot_schema}
                    schema.update(self._get_sell_schema())
                elif trx_type == 'DIVIDEND':
                    trx_data = dividend_data
                    schema = {**lot_schema}
                    schema.update(self._get_dividend_schema())
                elif trx_type == 'DIVIDEND_TAX':
                    trx_data = dividend_tax_data
                    schema = {**lot_schema}
                    schema.update(self._get_dividend_tax_schema())
                
                d = {k: trx[v] for k, v in schema.items()}
                if ticker not in trx_data:
                    trx_data[ticker] = []
                trx_data[ticker].append(d)
        
        dfs: List[pd.DataFrame] = []
        for k, df_data in {'CG': data, 'SELL': sell_data, 'DIVIDEND': dividend_data, 'DIVIDEND_TAX': dividend_tax_data}.items():
            schema = ["ticker"]
            schema.extend(list(lot_schema.keys()))
            if k == 'SELL':
                schema.extend(list(self._get_sell_schema().keys()))
            elif k == 'DIVIDEND':
                schema.extend(list(self._get_dividend_schema().keys()))
            elif k == 'DIVIDEND_TAX':
                schema.extend(list(self._get_dividend_tax_schema().keys()))
            df = self._to_dataframe(df_data, schema=schema)
            dfs.append(df)
        
        cg_df, sell_df, dividend_df, dividend_tax_df = dfs
        merged_dividend_df = dividend_df.merge(
            dividend_tax_df.rename(columns={
                'dividend_tax_date': 'dividend_date'
            }), on=["ticker", "dividend_date"] + list(lot_schema.keys()),
            how="inner"
        )
        df = (
            cg_df
            .merge(
                sell_df,
                on=["ticker"] + list(lot_schema.keys()),
                how="outer"
            )
            .merge(
                dividend_df,
                on=["ticker"] + list(lot_schema.keys()),
                how="outer"
            )
            .merge(
                merged_dividend_df,
                on=["ticker", "dividend_date", "dividend_received"] + list(lot_schema.keys()),
                how="outer"
            )
        )
        return df
    
    def _get_tickers_in_financial_year(self) -> List[str]:
        tickers = self.df[self.df["Date"] >= f'{self.financial_year}-04-01']['Ticker'].unique()
        tickers = tickers.tolist()
        return tickers

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
            'gains_type': "gains_type", 
            'units_remaining': "units_remaining"
        }

    def _get_dividend_schema(self) -> Dict[str, str]:
        return {
            'dividend_date': "dividend_date", 
            'dividend_received': "dividend_received", 
            'units_remaining': "units"
        }

    def _get_dividend_tax_schema(self) -> Dict[str, str]:
        return {
            'dividend_tax_date': "dividend_tax_date", 
            'dividend_tax_paid': "dividend_tax_paid", 
            'units_remaining': "units"
        }


if __name__ == "__main__":
    current_year = datetime.now().year
    parser = argparse.ArgumentParser()
    parser.add_argument("-f", "--file", required=True, help="Path to CSV file containing trades (required)")
    parser.add_argument("-y", "--financial-year", type=int, default=current_year, help=f"Financial year to compute Captial Gains. Default: {current_year}")
    parser.add_argument("-o", "--output", default="CaptialGains.xlsx", help="Path to save the Captial Gains. Default: CapitalGains.xlsx")
    args = parser.parse_args()

    if not os.path.exists(args.file):
        raise FileNotFoundError(f"{args.file}: no such file or directory found")
    
    if args.financial_year > current_year:
        raise ValueError(f"expected financial year to be less than {current_year}, got {args.calender_year}")

    df = pd.read_csv(args.file)
    df["Date"] = pd.to_datetime(df["Date"])
    a = CapitalGains(df=df, financial_year=str(args.financial_year))

    print("Computing Capital Gains")

    a.compute()

    output_dir = os.path.dirname(args.output)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    a.dump(save_path=args.output)
