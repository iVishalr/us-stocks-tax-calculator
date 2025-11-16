Data provided by different platforms like Vested Finance, IND Money must be transformed into a common format. Scripts to do this transformations go here.

Expected format

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
