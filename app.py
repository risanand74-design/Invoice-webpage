import os
import io
import zipfile
import tempfile
import shutil
import datetime as dt
from typing import List

import streamlit as st
import pandas as pd

# ==== IMPORTANT ====
# Put your existing invoice parsing logic in invoice_pipeline.py -> run_invoice_pipeline()
from invoice_pipeline import run_invoice_pipeline

APP_TITLE = "Invoice → Excel (Upload & Download)"
ALLOWED_DOC_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".zip"}

st.set_page_config(page_title=APP_TITLE, page_icon="📄", layout="centered")

def _check_password():
    """Optional simple password gate. Set STREAMLIT_PASSWORD in Streamlit Secrets to enable."""
    expected = st.secrets.get("STREAMLIT_PASSWORD", None)
    if not expected:
        return True  # password not enabled
    key = "auth_ok"
    if key not in st.session_state:
        st.session_state[key] = False
    if st.session_state[key]:
        return True

    pwd = st.text_input("Enter access password", type="password")
    if st.button("Unlock"):
        if pwd == expected:
            st.session_state[key] = True
            st.success("Unlocked.")
            return True
        else:
            st.error("Wrong password")
            return False
    return False

def _save_uploads(files) -> str:
    work_dir = tempfile.mkdtemp(prefix="invoices_")
    for f in files:
        name = os.path.basename(f.name)
        dst = os.path.join(work_dir, name)
        with open(dst, "wb") as out:
            out.write(f.read())

        # if it's a zip, extract it
        lower = name.lower()
        if lower.endswith(".zip"):
            try:
                with zipfile.ZipFile(dst) as z:
                    z.extractall(work_dir)
                os.remove(dst)
            except zipfile.BadZipFile:
                pass
    return work_dir

def _collect_invoice_paths(root: str) -> List[str]:
    wanted = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
    out = []
    for r, _, files in os.walk(root):
        for n in files:
            if os.path.splitext(n)[1].lower() in wanted:
                out.append(os.path.join(r, n))
    return out

def main():
    st.markdown(f"## {APP_TITLE}")
    st.write("Upload your invoices (PDFs/images or a ZIP). Click **Process** to generate an Excel file.")

    if not _check_password():
        st.stop()

    uploads = st.file_uploader(
        "Upload PDFs / Images / ZIP",
        type=[e.strip(".") for e in ALLOWED_DOC_EXTS],
        accept_multiple_files=True
    )

    run = st.button("Process", type="primary", disabled=not uploads)

    if run:
        if not uploads:
            st.warning("Please upload at least one file.")
            st.stop()

        work_dir = _save_uploads(uploads)
        invoice_files = _collect_invoice_paths(work_dir)

        if not invoice_files:
            shutil.rmtree(work_dir, ignore_errors=True)
            st.error("No supported files found in your upload.")
            st.stop()

        with st.spinner(f"Processing {len(invoice_files)} file(s)..."):
            try:
                df = run_invoice_pipeline(invoice_files)

                # Ensure DataFrame
                if not isinstance(df, pd.DataFrame):
                    st.error("run_invoice_pipeline() did not return a pandas DataFrame.")
                    st.stop()

                stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
                fname = f"invoice_output_{stamp}.xlsx"
                bio = io.BytesIO()
                with pd.ExcelWriter(bio, engine="openpyxl") as xls:
                    df.to_excel(xls, index=False, sheet_name="Invoices")
                bio.seek(0)

                st.success(f"Done. Processed {len(invoice_files)} file(s).")
                st.download_button(
                    "Download Excel",
                    data=bio,
                    file_name=fname,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                st.info("Tip: To enable a password, set STREAMLIT_PASSWORD in your app secrets.")
            except Exception as e:
                st.error(f"Error while processing: {e}")
            finally:
                # Clean up temp dir
                shutil.rmtree(work_dir, ignore_errors=True)

    st.caption("© Your Organization")

if __name__ == "__main__":
    main()
