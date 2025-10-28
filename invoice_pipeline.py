"""
Replace the stub in run_invoice_pipeline() with your existing invoice-reading logic.

Contract:
- Input: list[str] file_paths -> absolute paths to PDFs/images extracted from uploads/ZIPs
- Output: pandas.DataFrame with your final records ready to write to Excel
"""

import os
import pandas as pd

def run_invoice_pipeline(file_paths:list) -> pd.DataFrame:
    # TODO: Replace this stub with your actual pipeline. Keep the same function name/signature.
    # Below is a placeholder so the app runs end-to-end.
    rows = []
    for p in file_paths:
        rows.append({
            "invoice_file": os.path.basename(p),
            "status": "processed",  # change to actual parse status
            "amount": None          # fill with your extracted fields
        })
    return pd.DataFrame(rows)
