import math
import heapq

from .lot import Lot
from typing import Dict, List

class Executor:
    """A Trade Simulator

    Simulates buy, sell, dividend and dividend tax transactions
    and keeps track of open and closed lots. Transactions such
    as sell, dividends and dividend taxes are recorded in each
    lot individually.

    Executor maintains two types of lots per ticker, ordered 
    by buy date. The open lot indicates the lots currently held
    while the closed lots indicates the lots that have been completely
    sold.
    """
    def __init__(self) -> None:
        self.lots: Dict[str, List[Lot]] = {}
        self.units: Dict[str, float] = {}
        self.closed_lots: Dict[str, List[Lot]] = {}
        self._lot_counter: Dict[str, int] = {}


    def execute(self, date: str, trx_type: str, ticker: str, price: float, units: float, commission: float, amount: float) -> None:
        trx_type = trx_type.lower()
        if trx_type == "buy":
            self._execute_buy(date, ticker, price, units, commission)
        elif trx_type == "sell":
            self._execute_sell(date, ticker, price, units, commission)
        elif trx_type == "dividend":
            self._execute_dividend(date, ticker, amount)
        elif trx_type == "dividend_tax":
            self._execute_dividend_tax(date, ticker, amount)
        else:
            raise ValueError(f"Transaction type {trx_type} not supported.")
        

    def new_lot(self, date: str, ticker: str, price: float, units: float, commission: float) -> Lot:
        lotid = self._get_lotid(ticker)
        return Lot(
            lotid=lotid,
            date=date,
            ticker=ticker,
            units=units,
            price=price,
            commission=commission
        )


    def _get_lotid(self, ticker: str) -> int:
        self._lot_counter[ticker] = self._lot_counter.get(ticker, 0) + 1
        return self._lot_counter[ticker]


    def _execute_buy(self, date: str, ticker: str, price: float, units: float, commission: float):
        lot = self.new_lot(date, ticker, price, units, commission)

        # Create a heap for each ticker
        # A heap is nothing but a list when using heapq
        if ticker not in self.lots:
            self.lots[ticker] = []

        ticker_lots = self.lots[ticker]
        heapq.heappush(ticker_lots, lot)

        self.units[ticker] = self.units.get(ticker, 0.0) + units


    def _execute_sell(self, date: str, ticker: str, price: float, units: float, commission: float):
        ticker_lots = self.lots[ticker]
        
        remaining_units = units
        while len(ticker_lots) > 0 and not math.isclose(remaining_units, 0.0, rel_tol=1e-9, abs_tol=1e-9):
            lot = heapq.heappop(ticker_lots)
            remaining_units = lot.sell(date=date, price=price, units=remaining_units, commission=commission)

            if not math.isclose(lot.units, 0.0, rel_tol=1e-9, abs_tol=1e-9):
                heapq.heappush(ticker_lots, lot)
            else:
                # If a lot is completely sold, move the lot to closed lots
                if ticker not in self.closed_lots:
                    self.closed_lots[ticker] = []
                heapq.heappush(self.closed_lots[ticker], lot)

            if remaining_units > 0:
                commission = 0  # commission only once

        self.units[ticker] -= units


    def _execute_dividend(self, date: str, ticker: str, amount: float):
        lots = self.lots[ticker]
        units = self.units[ticker]

        # Dividends are issued to every lot currently held.
        # Hence total dividends must be equal to units per lot * dividend per unit
        dividend_per_unit = amount / units
        for lot in lots:
            lot.dividend(date, dividend_per_unit)

        expected = sum(lot.units * dividend_per_unit for lot in lots)

        assert math.isclose(amount, expected, rel_tol=1e-6, abs_tol=1e-4), \
            f"Dividend Amount: {amount} does not match per lot dividend received ({expected})"


    def _execute_dividend_tax(self, date: str, ticker: str, amount: float):
        lots = self.lots[ticker]
        units = self.units[ticker]

        # Dividend tax is deducted from every lot currently held.
        # Hence total dividend tax must be equal to units per lot * dividend tax per unit
        dividend_tax_per_unit = amount / units
        for lot in lots:
            lot.dividend_tax(date, dividend_tax_per_unit)

        expected = sum(lot.units * dividend_tax_per_unit for lot in lots)

        assert math.isclose(amount, expected, rel_tol=1e-6, abs_tol=1e-4), \
            f"Dividend Tax Amount: {amount} does not match per lot dividend received ({expected})"
