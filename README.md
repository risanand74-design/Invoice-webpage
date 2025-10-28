# Invoice → Excel (Streamlit Web App)

A minimal, permanent web page for your team to upload invoice files (PDFs/images or ZIP) and download a processed Excel — powered by your existing Python parsing logic.

## How it works
- Users visit the page, upload invoices, click **Process**.
- The app calls `invoice_pipeline.run_invoice_pipeline(file_paths)`.
- The function returns a `pandas.DataFrame`, which is streamed back to the user as an `.xlsx` download.

## Where to put your code
Edit `invoice_pipeline.py`:
```python
def run_invoice_pipeline(file_paths: list[str]) -> pd.DataFrame:
    # Implement your logic here and return a DataFrame
```
Keep the same function name and signature.

---

## Deploy (no local Python needed)

### Option A: Streamlit Cloud (recommended)
1. Create a **new GitHub repo** and upload these files.
2. Go to https://share.streamlit.io/ and connect your GitHub.
3. Select your repo and set **Main file path** to `app.py`.
4. (Optional) Add a password:
   - In Streamlit Cloud app → **Settings → Secrets**
   - Add: `STREAMLIT_PASSWORD = "your_password"`
5. Click **Deploy**. You’ll get a permanent URL to share.

### Option B: Hugging Face Spaces
1. Create a new **Space** with the **Streamlit** template.
2. Upload all files or link to your GitHub.
3. The app will build and run automatically.
4. Share the Space URL.

### Option C: Any server (Docker/VM)
- Install Python and run `streamlit run app.py`, or create a Docker image with system packages your pipeline needs (Tesseract/Poppler, etc.).

---

## File types
- PDFs and common images: `.pdf, .png, .jpg, .jpeg, .tif, .tiff, .bmp`
- ZIPs are auto-extracted; only supported file types inside will be processed.

## Simple access control (optional)
Set a password in Streamlit **secrets**:
```
STREAMLIT_PASSWORD = "ninedots123"    # example
```
The page will ask users for it before allowing processing.

---

## Notes
- If your pipeline needs system binaries (Tesseract/Poppler), prefer Docker or a host that supports them.
- For large batches, Streamlit Cloud works well for typical office use; for very heavy workloads, consider a queued backend (FastAPI + Redis) later.

---

© Your Organization
