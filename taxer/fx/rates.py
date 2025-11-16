from typing import Any
import pandas as pd

from datetime import datetime
from .fetch import get_fetch_fn


class RateFetcher:
    """Fetches the conversion rates for INR to USD for the given time range."""
    def __init__(self, default_source: str = "sbi", fallback_source: str = "yahoo", use_business_days: bool = False) -> None:
        """
        Arguments:
            `fallback_source` (str): Source to use when default source (SBI) has no data. Default: `"yahoo"`
                When SBI does not provide conversion rates for certain time ranges, use the `fallback_source` to 
                obtain conversion rates.
            `use_business_days` (bool): If `True`, only working days are included in the returned results. Default: `False`
        """
        self.use_business_days = use_business_days
        self.default_source = default_source
        self.fallback_source = fallback_source

        self._source_fn = get_fetch_fn(default_source)
        self._fallback_source_fn = get_fetch_fn(fallback_source)

    def fetch(self, start: str, end: str):
        self._validate_date(start)
        self._validate_date(end)

        # shift the start by a month
        # this is needed to obtain the rate on the last working day of previous month
        prev_month_start = (pd.to_datetime(start) - pd.Timedelta(weeks=4)).strftime("%Y-%m-%d")
        
        source_df = self._source_fn(start, end, self.use_business_days)
        dates = pd.date_range(start=prev_month_start, end=end, freq='D' if not self.use_business_days else 'B')
        source_df = source_df.set_index("Date").reindex(dates).rename_axis("Date").reset_index()

        fallback_df = self._fallback_source_fn(prev_month_start, end, self.use_business_days)
        df = source_df.combine_first(fallback_df)

        # Create a dict for fast lookup: Date -> Rate
        rate_map = dict(zip(df["Date"], df["Rate"]))

        # Vectorized computation for last working day of previous month
        last_month_dates = pd.to_datetime(df["Date"]).map(lambda d: pd.to_datetime(self.last_working_day_prev_month(d.strftime("%Y-%m-%d"))))
        df["Rate_last_month_end"] = last_month_dates.map(rate_map)
        df = df[(df["Date"] >= start) & (df["Date"] <= end)]
        return df
    
    def last_working_day_prev_month(self, date: str) -> str:
        """
        Returns the last working day of the preceding month from the given date.
        
        Parameters:
            givendate (str): Input date in 'YYYY-MM-DD' format (or anything parsable by pandas).
        
        Returns:
            pd.Timestamp: The last business day of the previous month.
        """
        # Convert to pandas Timestamp
        d = pd.to_datetime(date)
        # Move to the first day of the current month
        first_day_cur_month = d.replace(day=1)
        # Step back one business day from that
        last_working_prev_month = pd.offsets.BMonthEnd(1).rollback(first_day_cur_month - pd.Timedelta(days=1))
        return last_working_prev_month.strftime("%Y-%m-%d")

    def _validate_date(self, date_str: str) -> None:
        """Validate if date_str is in YYYY-MM-DD format and is a real date.
        Raises ValueError if invalid.
        """
        try:
            datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError as e:
            raise ValueError(f"Expected date to be in YYYY-MM-DD format. Got '{date_str}'") from e
        
    def __call__(self, *args: Any, **kwargs: Any) -> pd.DataFrame:
        return self.fetch(**kwargs)

if __name__ == "__main__":
    rates = RateFetcher()
    df = rates(start="2015-01-01", end="2024-12-31")
    df.to_csv("fx_Rates.csv",index=False)
