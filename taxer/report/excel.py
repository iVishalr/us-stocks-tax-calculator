import os
import pandas as pd

from typing import Dict
from openpyxl.utils import get_column_letter

class ExcelWriter:
    def __init__(self, path: str):
        self.path = path
    
    def dump(self, dataframes: Dict[str, pd.DataFrame]) -> None:
        dirname = os.path.dirname(self.path)
        if dirname and not os.path.exists(dirname):
            os.makedirs(dirname)
        
        with pd.ExcelWriter(self.path, engine="openpyxl", mode="w") as writer:
            for sheet_name, df in dataframes.items():
                df.to_excel(writer, sheet_name=sheet_name, index=False)
            
            for sheet_name in dataframes:
                sheet = writer.sheets[sheet_name]
                for col in sheet.columns:
                    max_len = max(len(str(cell.value)) if cell.value is not None else 0 for cell in col)
                    col_letter = get_column_letter(col[0].column)
                    sheet.column_dimensions[col_letter].width = max_len + 2
