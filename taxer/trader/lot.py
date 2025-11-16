import pandas as pd

class Lot:
    """Holds the details of a trade lot"""
    def __init__(self, 
        lotid: int,
        date: str,
        ticker: str, 
        units: float,
        price: float,
        commission: float              
    ) -> None:
        self.lotid = lotid
        self.date = date
        self.ticker = ticker
        self.initial_units = units
        self.price = price
        self.commission = commission

        self.dividends_received = {}
        self.dividends_tax_paid = {}
        self.long_term_gains = {}
        self.short_term_gains = {}

        self.trx_log = {}
        self.units = units

    def _get_calendar_and_fiscal_year(self, date: str):
        d = pd.to_datetime(date)
        cal_year = str(d.year)

        # Fiscal year: Apr 1 – Mar 31
        if d.month >= 4:  # Apr to Dec → fiscal year starts current year
            fiscal_year = f"{d.year}-{d.year+1}"
        else:             # Jan to Mar → fiscal year starts previous year
            fiscal_year = f"{d.year-1}-{d.year}"
        return f"CY{cal_year}", f"FY{fiscal_year}"

    def sell(self, date: str, units: float, price: float, commission: float) -> float:
        """Executes a sell of the given units against this lot. Returns remaining units if any"""
                
        sell_cy_year, sell_fy_year = self._get_calendar_and_fiscal_year(date)
    
        units_sold = 0
        units_left_to_sell = 0
        if self.units - units < 0:
            units_sold = self.units
            units_left_to_sell = units - self.units
        else:
            units_sold = units

        cost_basis = units_sold * self.price
        sell_proceeds = (units_sold * price) + commission
        
        capital_gains_dict = self.short_term_gains
        if self.is_long_term(self.date, date):
            capital_gains_dict = self.long_term_gains

        capital_gains = sell_proceeds - cost_basis
        capital_gains_dict[sell_cy_year] = capital_gains_dict.get(sell_cy_year, 0) + capital_gains
        capital_gains_dict[sell_fy_year] = capital_gains_dict.get(sell_fy_year, 0) + capital_gains

        self.units -= units_sold

        d = {
            'type': 'SELL',
            'lot_id': self.lotid,
            'lot_ticker': self.ticker,
            'lot_buy_date': self.date,
            'lot_buy_price': self.price,
            'lot_buy_units': self.initial_units,
            'lot_buy_commission': self.commission,
            'lot_cost_basis': (self.initial_units * self.price) + self.commission,
            'cost_basis': cost_basis,
            'sell_date': date,
            'sell_price': price,
            'sell_units': units_sold,
            'sell_proceeds': sell_proceeds,
            'gains': capital_gains,
            'gains_type': 'long' if self.is_long_term(self.date, date) else 'short',
            'units_remaining': self.units
        }

        if sell_cy_year not in self.trx_log:
            self.trx_log[sell_cy_year] = []
        if sell_fy_year not in self.trx_log:
            self.trx_log[sell_fy_year] = []
        self.trx_log[sell_cy_year].append(d)
        self.trx_log[sell_fy_year].append(d)

        return units_left_to_sell
    

    def dividend(self, date: str, amount_per_unit: float):
        calender_year, fiscal_year = self._get_calendar_and_fiscal_year(date)
        dividend_amount = amount_per_unit * self.units

        if calender_year not in self.dividends_received:
            self.dividends_received[calender_year] = 0
        self.dividends_received[calender_year] += dividend_amount

        if fiscal_year not in self.dividends_received:
            self.dividends_received[fiscal_year] = 0
        self.dividends_received[fiscal_year] += dividend_amount

        d = {
            'type': 'DIVIDEND',
            'lot_id': self.lotid,
            'lot_ticker': self.ticker,
            'lot_buy_date': self.date,
            'lot_buy_price': self.price,
            'lot_buy_units': self.initial_units,
            'lot_buy_commission': self.commission,
            'lot_cost_basis': (self.initial_units * self.price) + self.commission,
            'dividend_date': date,
            'dividend_received': dividend_amount,
            'dividend_per_unit': amount_per_unit,
            'units': self.units,
        }

        if calender_year not in self.trx_log:
            self.trx_log[calender_year] = []
        if fiscal_year not in self.trx_log:
            self.trx_log[fiscal_year] = []

        self.trx_log[calender_year].append(d)
        self.trx_log[fiscal_year].append(d)


    def dividend_tax(self, date: str, amount_per_unit: float):
        calender_year, fiscal_year = self._get_calendar_and_fiscal_year(date)
        amount_per_unit = amount_per_unit * -1
        dividend_tax_amount = amount_per_unit * self.units * -1

        if calender_year not in self.dividends_tax_paid:
            self.dividends_tax_paid[calender_year] = 0
        self.dividends_tax_paid[calender_year] += dividend_tax_amount

        if fiscal_year not in self.dividends_tax_paid:
            self.dividends_tax_paid[fiscal_year] = 0
        self.dividends_tax_paid[fiscal_year] += dividend_tax_amount 

        d = {
            'type': 'DIVIDEND_TAX',
            'lot_id': self.lotid,
            'lot_ticker': self.ticker,
            'lot_buy_date': self.date,
            'lot_buy_price': self.price,
            'lot_buy_units': self.initial_units,
            'lot_buy_commission': self.commission,
            'lot_cost_basis': (self.initial_units * self.price) + self.commission,
            'dividend_tax_date': date,
            'dividend_tax_paid': dividend_tax_amount,
            'dividend_tax_per_unit': amount_per_unit,
            'units': self.units,
        }

        if calender_year not in self.trx_log:
            self.trx_log[calender_year] = []
        if fiscal_year not in self.trx_log:
            self.trx_log[fiscal_year] = []

        self.trx_log[calender_year].append(d)
        self.trx_log[fiscal_year].append(d)


    def is_long_term(self, buy_date: str, sell_date: str) -> bool:
        _buy_date = pd.to_datetime(buy_date)
        _sell_date = pd.to_datetime(sell_date)

        delta = _sell_date - _buy_date

        if delta.days >= 2 * 365:
            return True
        else:
            return False

    def get_units(self) -> float:
        return self.units
    
    def __lt__(self, other):
        return self.date < other.date