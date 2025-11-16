# Indian Tax Calculator for US Stocks

A simple python program for computing capital gains on US Stocks for tax filing in India. 

_Note: Author of this program does not claim any responsibility on the accuracy of captial gains computation. Please consult your CA before filing taxes._ 

## Features

1. Capital Gains - Long Term and Short Term based on Financial Year (Apr - Mar).
2. Dividend Income - Divdends received and tax paid.
3. Schedule FA based on Calender Year (Jan-Dec).
4. Automatic USD to INR conversion using SBI TT Buying rates.
5. Works for ESPP and RSUs.

## Setup

### Project setup

Setup a python virtual environment:

```
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
```

Install python dependencies

```
pip install -r requirements.txt
```

### Preparing Data

There are a number of ways to invest in US Stocks like Vested finance, INR Money, Groww, etc. Each platform may report your trades data differently. This must be mapped to a common format the calculator can work with. Typically, this involves creating a CSV file (manually or using scripts) with the following format:

| **Field**       | **Description**                                                                                   | **Applies To**                                      | **Can Be Empty?**                                   |
|------------------|---------------------------------------------------------------------------------------------------|------------------------------------------------------|------------------------------------------------------|
| **Date**         | Date of equity purchased, sold, or dividend date in `YYYY-MM-DD` format. Must be sorted.         | All (`Buy`, `Sell`, `Dividend`, `Dividend_tax`)      | ❌ No                                                |
| **Name**         | Name of the company.                                                                              | All                                                  | ❌ No                                                |
| **Ticker**       | Ticker symbol of the company.                                                                     | All                                                  | ❌ No                                                |
| **Type**         | Type of trade — `Buy`, `Sell`, `Dividend`, `Dividend_tax`.                                        | All                                                  | ❌ No                                                |
| **Units**        | Number of units bought/sold.                                                                      | `Buy`, `Sell`                                        | ✔️ Yes — must be empty for `Dividend` / `Dividend_tax` |
| **Price**        | Price per share.                                                                                  | `Buy`, `Sell`                                        | ✔️ Yes — must be empty for `Dividend` / `Dividend_tax` |
| **Commission**   | Commission paid for buying or selling.                                                            | `Buy`, `Sell`                                        | ✔️ Yes — must be empty for `Dividend` / `Dividend_tax` |
| **Amount**       | Dividend received or dividend tax paid.                                                           | `Dividend`, `Dividend_tax`                           | ✔️ Yes — must be empty for `Buy` / `Sell`             |

**Example:**

```csv
Date,Name,Ticker,Type,Units,Price,Commission,Amount
2020-01-21,"Meta Platforms, Inc.",META,Buy,0.02247747,222.0,0.0,
2020-01-23,"Tesla, Inc.",TSLA,Buy,30.0,37.6,0.0,
2020-01-24,"Meta Platforms, Inc.",META,Buy,3.0,220.83,0.0,
2020-01-24,"Visa, Inc.",V,Buy,2.0,207.12,0.0,
2020-01-30,"Meta Platforms, Inc.",META,Buy,0.5,206.66,0.0,
...
2024-12-24,"Advanced Micro Devices, Inc.",AMD,Buy,3.0,125.79,0.56,
2024-12-30,"Meta Platforms, Inc.",META,Dividend_tax,,,,-3.15
2024-12-30,"Meta Platforms, Inc.",META,Dividend,,,,10.5
...
2025-02-18,"Palantir Technologies, Inc.",PLTR,Sell,10.0,124.2,1.86,
```

> [!IMPORTANT]
> You must handle stock splits if your data provider doesn't automatically adjust it for you.
> Take a look at [prepare.py](./platforms/vested_finance/prepare.py) to know how this was done for Vested Finance using yfinance.

## Computing Captial Gains

After preparing the data using the guidelines given above, the capital gains can be computed using:

```bash
python3 capital_gains.py -f <path/to/csv> -o CapitalGains.xlsx --financial-year=2025
```

<details>

<summary>Command Line options</summary>

```console
$ python3 captial_gains.py --help
usage: captial_gains.py [-h] -f FILE [-y FINANCIAL_YEAR] [-o OUTPUT]

options:
  -h, --help            show this help message and exit
  -f FILE, --file FILE  Path to CSV file containing trades (required)
  -y FINANCIAL_YEAR, --financial-year FINANCIAL_YEAR
                        Financial year to compute Captial Gains. Default: 2025
  -o OUTPUT, --output OUTPUT
                        Path to save the Captial Gains. Default: CapitalGains.xlsx
```

</details>

## Computing Schedule FA

The schedule FA can be calculated using the following:

```bash
python3 schedule_fa.py -f <path/to/csv> -o ScheduleFA.xlsx --calender-year=2025
```

<details>

<summary>Command Line options</summary>

```console
$ python3 schedule_fa.py --help
usage: schedule_fa.py [-h] -f FILE [-y CALENDER_YEAR] [-o OUTPUT]

options:
  -h, --help            show this help message and exit
  -f FILE, --file FILE  Path to CSV file containing trades (required)
  -y CALENDER_YEAR, --calender-year CALENDER_YEAR
                        Calender year to compute ScheduleFA. Default: 2025
  -o OUTPUT, --output OUTPUT
                        Path to save the ScheduleFA. Default: ScheduleFA.xlsx
```

</details>

## Note on Captial Gains periods on US Stocks

US Stocks in India are treated as unlisted equities. As a result, they are taxed as follows:

1. Short Term (holding period < 24 months): Income Tax Slab rates.
2. Long Term (holding period > 24 months): 12.5% LTCG tax rates.
3. Dividends are taxed in US at 25% tax rate which can be claimed as tax credit here in India.
4. Other Income (SLIPs, Interests, etc): Income Tax Slab rates.

## Note on FX Rates Data

The USD to INR conversion rates from SBI are fetched from https://github.com/sahilgupta/sbi-fx-ratekeeper (thanks!). This repository maintains SBI TT Buying rates from 2020. For conversion rates before 2020, the rates are fetched from Yahoo Finance (using `yfinance` library).

## Note on USD to INR Conversion Proceedure

**For Capital Gains**:

Uses SBI TT Buying Rate on the last working day of the previous month of the date of buy/sell/dividends received.
   
   Example:

    If you bought a share on 2025-04-15, and sold on 2025-05-15, then:
    a. Buy USD to INR Rate becomes the rate on 2025-03-31.
    b. Sell USD to INR Rate becomes the rate on 2025-04-30.
    c. If SBI / Yahoo finance does not have a rate for that day, the next published rate is used.

**For Schedule FA**:

All USD to INR conversions are done using the SBI TT Buying rate on the date of buy/sell/dividends of securities.

## Contributing Guidelines

You are free to support for add additional platforms like IND Money, Groww, etc into the [platforms](./platforms/) folder.

If you find any issue in the computation, please create an issue in the issues tab. PRs for fixing the issues are welcomed!

## License

MIT