# invoice_pipeline.py — web-app adapter built from your invoice_reader_v2
# Notes:
# - By default OCR is disabled (works on Streamlit Cloud). Set USE_OCR=True if your host has Tesseract+Poppler.
# - No files are written/moved; returns a pandas DataFrame to the Streamlit app.

import os, re, traceback
from pathlib import Path
from typing import List, Tuple
import pandas as pd

# ==== Toggle this to True ONLY if your host has Tesseract + Poppler installed ====
USE_OCR = False  # Streamlit Cloud-friendly default

# ---------- Utilities ----------
def safe_float(s, default=0.0):
    try:
        if s is None: return default
        s = str(s).strip().replace(",", "").replace(" ", "")
        return float(re.sub(r"[^\d\.\-]", "", s)) if s not in ["", "nan", "None"] else default
    except Exception:
        return default

def text_from_pdf(pdf_path: str) -> Tuple[str, bool]:
    """Try pdfplumber first; optionally fall back to OCR if USE_OCR=True."""
    import pdfplumber
    # 1) text layer
    try:
        with pdfplumber.open(pdf_path) as pdf:
            pages_text = [p.extract_text() or "" for p in pdf.pages]
        txt = "\n".join(t for t in pages_text if t).strip()
        if txt:
            return txt, False
    except Exception:
        pass

    if not USE_OCR:
        return "", False

    # 2) OCR fallback (requires Tesseract + Poppler on host)
    try:
        from pdf2image import convert_from_path
        import pytesseract
        from PIL import Image
        images = convert_from_path(pdf_path, dpi=300)
        ocr_text = []
        for img in images:
            if img.mode != "RGB":
                img = img.convert("RGB")
            ocr_text.append(pytesseract.image_to_string(img))
        return "\n".join(ocr_text).strip(), True
    except Exception:
        # best-effort final fallback: rasterize via pdfplumber
        try:
            with pdfplumber.open(pdf_path) as pdf:
                import pytesseract
                texts = []
                for p in pdf.pages:
                    img = p.to_image(resolution=150).original
                    if img.mode != "RGB":
                        img = img.convert("RGB")
                    texts.append(pytesseract.image_to_string(img))
            return "\n".join(texts).strip(), True
        except Exception:
            return "", True

def build_description(item_lines: List[str]) -> str:
    parts, hsn_seen = [], False
    for idx, raw in enumerate(item_lines):
        if raw is None: continue
        line = raw.strip()
        if idx == 0:
            line = re.sub(r"^\s*\d+\s+", "", line)
        m = re.search(r"\b\d{6,8}\b", line)
        if m and not hsn_seen:
            left = line[:m.start()].strip()
            if re.search(r"[A-Za-z]", left):
                parts.append(left)
            hsn_seen = True
            continue
        if re.search(r"[A-Za-z]", line) and not re.search(
            r"\b(Qty|Quantity|Unit|Price|Rate|Tax|Amount|Total|HSN|SGST|CGST|IGST|Disc|Discount|Round off)\b",
            line, re.I,
        ):
            digits = sum(ch.isdigit() for ch in line)
            letters = sum(ch.isalpha() for ch in line)
            if letters >= digits:
                parts.append(line)
    return " ".join(p for p in parts if p).replace("  ", " ").strip(" ~").strip()

def find_supplier_block(lines: List[str]) -> Tuple[str, str, str]:
    # (Same logic as your file—trimmed to fit)
    GSTIN_RE = re.compile(r'\b([0-9A-Z]{15})\b')
    SECTION_BREAK_RE = re.compile(
        r'(Despatch\s*From|Dispatch\s*From|Ship\s*To|Bill\s*To|Buyer|Consignee|Details\s*of\s*Goods)', re.I)
    ADDRESS_HINT_RE = re.compile(
        r'\b(road|rd\.?|street|st\.?|lane|nagar|post|p\.o\.|no\.?\s*\d|floor|block|phase|industrial|estate|area|sector|park|city|pin|pincode|zip|india|tel|phone|email)\b|\b\d{5,6}\b', re.I)
    NAME_HINT_RE = re.compile(r'\b(PVT|PRIVATE|LTD|LIMITED|LLP|INC|CO\.?|COMPANY|DEPARTMENT)\b', re.I)

    def clean_join(parts): 
        s = " ".join(p.strip(" ,;") for p in parts if p and p.strip()).strip(" ,;")
        return re.sub(r'\s{2,}', ' ', s)

    def split_name_addr(block):
        gst, name_lines, addr_lines = "", [], []
        for i, line in enumerate(block):
            m = GSTIN_RE.search(line)
            if m and not gst:
                gst = m.group(1); continue
            if NAME_HINT_RE.search(line) or (i <= 2 and re.search(r'[A-Za-z]', line) and not ADDRESS_HINT_RE.search(line)):
                name_lines.append(line)
            else:
                addr_lines.append(line)
        return gst, clean_join(name_lines), clean_join(addr_lines)

    # try “Supplier … Recipient” grid
    header_idx = None
    for i, ln in enumerate(lines):
        if re.search(r'\bSupplier\b', ln, re.I) and re.search(r'\bRecipient\b', ln, re.I):
            header_idx = i; break
    if header_idx is not None:
        # infer split based on two GSTINs on a row
        split_col = None
        for j in range(header_idx+1, min(header_idx+6, len(lines))):
            toks = list(GSTIN_RE.finditer(lines[j]))
            if len(toks) >= 2:
                left, right = toks[0], toks[1]
                split_col = (left.end() + right.start()) // 2
                break
        if split_col:
            block = []
            for k in range(j, min(header_idx+25, len(lines))):
                ln = lines[k]
                if SECTION_BREAK_RE.search(ln): break
                left = ln[:split_col].rstrip() if len(ln) >= split_col else ln
                if left.strip(): block.append(left.strip())
            gst, name, addr = split_name_addr(block)
            if gst or name or addr:
                return gst, name, addr

    # section slice
    sup_idx = next((i for i, ln in enumerate(lines) if re.search(r'^\s*Supplier\b', ln, re.I)), None)
    if sup_idx is not None:
        end_idx = next((j for j in range(sup_idx+1, len(lines))
                        if re.search(r'^\s*Recipient\b', lines[j], re.I) or SECTION_BREAK_RE.search(lines[j])), len(lines))
        block = [ln.strip() for ln in lines[sup_idx+1:end_idx] if ln and ln.strip()]
        if block:
            gst, name, addr = split_name_addr(block)
            if gst or name or addr:
                return gst, name, addr

    # generic fallback
    joined = "\n".join(lines)
    m = GSTIN_RE.search(joined)
    if m:
        gst = m.group(1)
        line_idx = next((i for i, ln in enumerate(lines) if gst in ln), None)
        window = [ln.strip() for ln in lines[max(0, (line_idx or 0)-2):(line_idx or 0)+10]]
        block = [ln for ln in window if ln]
        gst2, name, addr = split_name_addr(block)
        return (gst2 or gst), name, addr
    return "", "", ""

def extract_invoice_data(pdf_path: str) -> List[dict]:
    text, used_ocr = text_from_pdf(pdf_path)
    if not text:
        raise ValueError("No text extracted")

    lines = [ln for ln in text.splitlines() if ln and ln.strip()]

    # header fields
    irn = (re.search(r"IRN\s*[:\-]?\s*([A-Fa-f0-9]+)", text) or (None,)).group(1) if re.search(r"IRN", text) else ""
    invoice_number = ""
    for patt in [r"Document No\s*[:\-]?\s*(\S+)", r"Document\s*Number\s*[:\-]?\s*(\S+)",
                 r"Invoice\s*No\.?\s*[:\-]?\s*(\S+)", r"Bill\s*No\.?\s*[:\-]?\s*(\S+)"]:
        mm = re.search(patt, text, re.I)
        if mm: invoice_number = mm.group(1).strip(); break

    invoice_date = ""
    mm = re.search(r"Document Date\s*[:\-]?\s*(\d{2}[-/]\d{2}[-/]\d{4})", text, re.I) or \
         re.search(r"Date\s*[:\-]?\s*(\d{2}[-/]\d{2}[-/]\d{4})", text, re.I)
    if mm: invoice_date = mm.group(1).strip()

    supplier_gstin, supplier_name, supplier_address = find_supplier_block(lines)

    footer_total = None
    for patt in [r"Total\s+Inv\.?\.?\s*Amt\s*[:\s]*([\d,]+\.\d{1,2}|\d+)",
                 r"Total\s+Inv(?:oice)?\s*Amt\s*[:\s]*([\d,.,]+)",
                 r"Total\s+Inv(?:oice)?\.?\s*Amt[\s\(\)A-Za-z]*[:\s]*([\d,]+\.\d{1,2}|\d+)"]:
        m = re.search(patt, text, re.I)
        if m: footer_total = safe_float(m.group(1), None); break

    # collect item block
    item_lines_collected, capture = [], False
    for ln in lines:
        if re.search(r"Details of Goods(?: / Services)?", ln, re.I):
            capture = True; continue
        if capture:
            if re.search(r"Taxable\s+Amt|Total Inv", ln, re.I):
                item_lines_collected.append(ln); break
            item_lines_collected.append(ln)
    if not item_lines_collected:
        for idx, ln in enumerate(lines):
            if re.search(r"\bSr(\.| )?No\b", ln, re.I):
                item_lines_collected = lines[idx: idx+200]; break
    if not item_lines_collected:
        item_lines_collected = lines

    items, current = [], []
    for ln in item_lines_collected:
        if re.match(r"^\s*\d+\s+", ln):
            if current: items.append(current)
            current = [ln]
        else:
            if current: current.append(ln)
    if current: items.append(current)

    rows_out = []
    totals = {"total_taxable":0.0, "total_cgst":0.0, "total_sgst":0.0, "total_igst":0.0,
              "invoice_total": footer_total if footer_total is not None else 0.0}

    for it in items:
        desc = build_description(it)
        flat = " ".join(it).replace("\n", " ")
        parsed = {
            "Invoice number": invoice_number, "Invoice date": invoice_date,
            "Supplier GSTIN": supplier_gstin, "Supplier name": supplier_name, "Supplier address": supplier_address,
            "Item description": desc, "Item HSN code": "", "Quantity": None, "Unit": "", "Unit Price": None,
            "Taxable Amount": None, "CGST Rate": 0.0, "CGST Amount": 0.0,
            "SGST Rate": 0.0, "SGST Amount": 0.0, "IGST Rate": 0.0, "IGST Amount": 0.0,
            "Invoice Footer Total": footer_total, "IRN": irn, "Source file": os.path.basename(pdf_path),
        }

        m = re.search(
            r"(\d{4,8})\s+(\d+(?:\.\d+)?)\s+([A-Za-z]{1,4})\s+([\d,]+\.\d+|\d+)\s+([\d,.,]+\.\d+|\d+)\s*(\d{1,2}(?:\.\d+)?)\s+([\d,.,]+\.\d+|\d+)",
            flat)
        fb = re.search(
            r"(\d{4,8})\s+([\d,]+\.\d+|\d+)\s+([\d,.,]+\.\d+|\d+)\s+(\d{1,2}(?:\.\d+)?)\s+([\d,.,]+\.\d+|\d+)",
            flat)

        def apply_tax_split(taxable_amt, gst_rate):
            if isinstance(supplier_gstin, str) and supplier_gstin.startswith("29"):
                cgst_rate = sgst_rate = gst_rate/2.0
                cgst_amt = round(taxable_amt*cgst_rate/100.0, 2)
                sgst_amt = round(taxable_amt*sgst_rate/100.0, 2)
                igst_rate = igst_amt = 0.0
            else:
                igst_rate = gst_rate
                igst_amt = round(taxable_amt*igst_rate/100.0, 2)
                cgst_rate = sgst_rate = cgst_amt = sgst_amt = 0.0
            return cgst_rate, cgst_amt, sgst_rate, sgst_amt, igst_rate, igst_amt

        if m:
            hsn = m.group(1)
            qty = safe_float(m.group(2), 0.0)
            unit = m.group(3)
            unit_price = safe_float(m.group(4), 0.0)
            taxable_amt = safe_float(m.group(5), 0.0)
            gst_rate = safe_float(m.group(6), 0.0)
            parsed.update({"Item HSN code": str(hsn), "Quantity": qty, "Unit": unit,
                           "Unit Price": unit_price, "Taxable Amount": taxable_amt})
            cgst_r,cgst_a,sgst_r,sgst_a,igst_r,igst_a = apply_tax_split(taxable_amt, gst_rate)
            parsed.update({"CGST Rate": cgst_r,"CGST Amount": cgst_a,"SGST Rate": sgst_r,"SGST Amount": sgst_a,
                           "IGST Rate": igst_r,"IGST Amount": igst_a})
            totals["total_taxable"] += taxable_amt; totals["total_cgst"] += cgst_a; totals["total_sgst"] += sgst_a; totals["total_igst"] += igst_a
        elif fb:
            hsn = fb.group(1)
            unit_price = safe_float(fb.group(2), 0.0)
            taxable_amt = safe_float(fb.group(3), 0.0)
            gst_rate = safe_float(fb.group(4), 0.0)
            parsed.update({"Item HSN code": str(hsn), "Unit Price": unit_price, "Taxable Amount": taxable_amt})
            cgst_r,cgst_a,sgst_r,sgst_a,igst_r,igst_a = apply_tax_split(taxable_amt, gst_rate)
            parsed.update({"CGST Rate": cgst_r,"CGST Amount": cgst_a,"SGST Rate": sgst_r,"SGST Amount": sgst_a,
                           "IGST Rate": igst_r,"IGST Amount": igst_a})
            totals["total_taxable"] += taxable_amt; totals["total_cgst"] += cgst_a; totals["total_sgst"] += sgst_a; totals["total_igst"] += igst_a

        rows_out.append(parsed)

    if totals["invoice_total"] in (None, 0.0):
        totals["invoice_total"] = round(totals["total_taxable"] + totals["total_cgst"] + totals["total_sgst"] + totals["total_igst"], 2)

    for r in rows_out:
        r["Total Taxable"] = round(totals["total_taxable"], 2)
        r["Total CGST"] = round(totals["total_cgst"], 2)
        r["Total SGST"] = round(totals["total_sgst"], 2)
        r["Total IGST"] = round(totals["total_igst"], 2)
        r["Invoice Total"] = totals["invoice_total"]
    return rows_out

def process_file(path: str):
    try:
        rows = extract_invoice_data(path)
        if not rows:
            raise ValueError("No rows extracted")
        return {"path": path, "rows": rows, "error": None}
    except Exception as e:
        return {"path": path, "rows": None, "error": str(e)}

# ---------- The function your Streamlit app calls ----------
def run_invoice_pipeline(file_paths: List[str]) -> pd.DataFrame:
    all_rows = []
    for p in file_paths:
        res = process_file(p)
        if not res["error"] and res["rows"]:
            all_rows.extend(res["rows"])
    df = pd.DataFrame(all_rows)
    if df.empty:
        return pd.DataFrame([{"Source file": os.path.basename(p), "status": "no data parsed"} for p in file_paths])
    preferred_cols = [
        "Invoice number","Invoice date","Supplier GSTIN","Supplier name","Supplier address",
        "Item description","Item HSN code","Quantity","Unit","Unit Price","Taxable Amount",
        "CGST Rate","CGST Amount","SGST Rate","SGST Amount","IGST Rate","IGST Amount",
        "Invoice Footer Total","Total Taxable","Total CGST","Total SGST","Total IGST",
        "Invoice Total","IRN","Source file"
    ]
    cols = [c for c in preferred_cols if c in df.columns] + [c for c in df.columns if c not in preferred_cols]
    return df[cols]
