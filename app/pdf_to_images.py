# app/pdf_to_images.py
import base64, fitz  # PyMuPDF
from typing import List

def pdf_bytes_to_dataurls(pdf_bytes: bytes, max_pages: int = 2, dpi: int = 180) -> List[str]:
    """
    Convierte las primeras max_pages de un PDF en data URLs (PNG) para análisis por visión.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    urls=[]
    for i, page in enumerate(doc):
        if i >= max_pages: break
        mat = fitz.Matrix(dpi/72, dpi/72)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        png_bytes = pix.tobytes("png")
        b64 = base64.b64encode(png_bytes).decode("ascii")
        urls.append(f"data:image/png;base64,{b64}")
    doc.close()
    return urls
