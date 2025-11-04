# app/pdf_utils.py
import os
import re
import unicodedata
from datetime import datetime
from typing import Optional

from fpdf import FPDF  # pip install fpdf2

# ========= Estilo =========
PAGE_MARGIN_L = 15
PAGE_MARGIN_R = 15
PAGE_MARGIN_T = 18
PAGE_MARGIN_B = 18

COLOR_PRIMARY = (33, 150, 243)
COLOR_ACCENT  = (76, 175, 80)
COLOR_WARN    = (244, 67, 54)
COLOR_TEXT    = (34, 34, 34)
COLOR_MUTED   = (120, 120, 120)
COLOR_CARD_BR = (220, 220, 220)
COLOR_RULE    = (220, 220, 220)

LINE_HEIGHT = 7.0
SECTION_SPACING = 4.0
PARAGRAPH_SPACING = 2.5

# Padding interno de tarjetas
CARD_PADDING_L = 3
CARD_PADDING_R = 3
CARD_PADDING_T = 3
CARD_PADDING_B = 3
CARD_MIN_HEIGHT = 14.0  # altura mínima visible

# ========= Fuentes (Unicode) =========
FONT_SEARCH_DIRS = [
    os.path.join("app", "assets", "fonts"),
    os.path.join("assets", "fonts"),
    os.path.join(os.getcwd(), "assets", "fonts"),
    os.path.join(os.getcwd(), "app", "assets", "fonts"),
    r"C:\Windows\Fonts",
]
FONT_CANDIDATE_SETS = [
    ("DejaVu", "DejaVuSans.ttf", "DejaVuSans-Bold.ttf"),
    ("ArialTTF", "arial.ttf", "arialbd.ttf"),
    ("SegoeUI", "segoeui.ttf", "segoeuib.ttf"),
]
UNICODE_FONT_FAMILY: Optional[str] = None

# ========= Utils =========
def sanitize_filename(name: str, max_length: int = 100, default: str = "file") -> str:
    if not name:
        return default
    safe = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    safe = safe.strip().replace(" ", "_")
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "", safe)
    safe = re.sub(r"\.+$", "", safe)
    if not safe:
        safe = default
    reserved = {
        "CON","PRN","AUX","NUL",
        "COM1","COM2","COM3","COM4","COM5","COM6","COM7","COM8","COM9",
        "LPT1","LPT2","LPT3","LPT4","LPT5","LPT6","LPT7","LPT8","LPT9"
    }
    if safe.upper() in reserved:
        safe = f"_{safe}_"
    return safe[:max_length]

def _safe_text(text: str, unicode_ready: bool) -> str:
    if unicode_ready:
        return text
    repl = {
        "—": "-", "–": "-",
        "•": "-", "·": "-",
        "✓": "+", "✔": "+",
        "⚠": "!", "❗": "!",
        "»": ">", "«": "<",
        "…": "...",
        "º": "o", "ª": "a",
        "“": '"', "”": '"', "‘": "'", "’": "'",
        "μ": "u", "°": " deg ",
        "\u00A0": " ", "\u200B": "", "\u200C": "", "\u200D": "",
    }
    for k, v in repl.items():
        text = text.replace(k, v)
    return text

def _find_font_files():
    for family, reg_name, bold_name in FONT_CANDIDATE_SETS:
        reg_path = None
        bold_path = None
        for base in FONT_SEARCH_DIRS:
            r = os.path.join(base, reg_name)
            if os.path.isfile(r) and not reg_path:
                reg_path = r
            b = os.path.join(base, bold_name)
            if os.path.isfile(b) and not bold_path:
                bold_path = b
            if reg_path and bold_path:
                break
        if reg_path:
            return family, reg_path, bold_path
    return None, None, None

def _register_unicode_fonts(pdf: FPDF) -> bool:
    global UNICODE_FONT_FAMILY
    family, reg, bold = _find_font_files()
    if not reg:
        UNICODE_FONT_FAMILY = None
        return False
    try:
        pdf.add_font(family, "", reg, uni=True)
        if bold:
            pdf.add_font(family, "B", bold, uni=True)
        UNICODE_FONT_FAMILY = family
        return True
    except Exception:
        UNICODE_FONT_FAMILY = None
        return False

def _set_font(pdf: FPDF, unicode_ready: bool, size: int = 12, bold: bool = False):
    style = "B" if bold else ""
    if unicode_ready and UNICODE_FONT_FAMILY:
        pdf.set_font(UNICODE_FONT_FAMILY, style, size=size)
    else:
        pdf.set_font("Helvetica", style, size=size)
    pdf.set_text_color(*COLOR_TEXT)

def _hr(pdf: FPDF, color=COLOR_RULE, y_offset=2):
    x1 = PAGE_MARGIN_L
    x2 = pdf.w - PAGE_MARGIN_R
    y  = pdf.get_y() + y_offset
    pdf.set_draw_color(*color)
    pdf.set_line_width(0.2)
    pdf.line(x1, y, x2, y)
    pdf.ln(y_offset + 1)

# ==== Layout interno de tarjeta ====
def _inner_left() -> float:
    return PAGE_MARGIN_L + CARD_PADDING_L
def _inner_right(pdf: FPDF) -> float:
    return pdf.w - PAGE_MARGIN_R - CARD_PADDING_R
def _inner_width(pdf: FPDF) -> float:
    return _inner_right(pdf) - _inner_left()

def _section_title(pdf: FPDF, text: str, unicode_ready: bool):
    pdf.ln(SECTION_SPACING)
    _set_font(pdf, unicode_ready, size=13, bold=True)
    pdf.set_text_color(*COLOR_PRIMARY)
    pdf.set_x(PAGE_MARGIN_L)
    pdf.cell(0, 8, _safe_text(text, unicode_ready), ln=True)
    pdf.set_text_color(*COLOR_TEXT)
    _hr(pdf, color=COLOR_RULE, y_offset=0.5)

def _card_begin(pdf: FPDF, padding=4, r=2.0):
    pdf.ln(1.5)
    x = PAGE_MARGIN_L
    y = pdf.get_y()
    pdf.set_xy(_inner_left(), y + CARD_PADDING_T)
    return x, y, padding, r

def _card_end(pdf: FPDF, x, y, padding=4, r=2.0, content_started: bool = True):
    """
    Importante: dibuja SOLO el borde al final (style='D') para NO tapar el texto.
    """
    y2 = pdf.get_y()
    if not content_started:
        return
    h = (y2 - y) + CARD_PADDING_B
    if h < CARD_MIN_HEIGHT:
        h = CARD_MIN_HEIGHT
    w = pdf.w - PAGE_MARGIN_L - PAGE_MARGIN_R
    pdf.set_draw_color(*COLOR_CARD_BR)
    try:
        pdf.rounded_rect(x, y, w, h, r, style="D")
    except Exception:
        pdf.rect(x, y, w, h, style="D")
    pdf.ln(2)

def _card_paragraph(pdf: FPDF, text: str, unicode_ready: bool):
    _set_font(pdf, unicode_ready, size=12, bold=False)
    pdf.set_x(_inner_left())
    pdf.multi_cell(_inner_width(pdf), LINE_HEIGHT, _safe_text(text, unicode_ready))
    pdf.ln(PARAGRAPH_SPACING)

def _card_bullet(pdf: FPDF, text: str, unicode_ready: bool):
    _set_font(pdf, unicode_ready, size=12, bold=False)
    bullet = "•" if unicode_ready else "-"
    left = _inner_left()
    w_inner = _inner_width(pdf)
    bullet_w = 5.0
    txt_w = max(w_inner - bullet_w, 5.0)
    pdf.set_x(left)
    pdf.cell(bullet_w, LINE_HEIGHT, _safe_text(bullet, unicode_ready), ln=0)
    pdf.set_x(left + bullet_w)
    pdf.multi_cell(txt_w, LINE_HEIGHT, _safe_text(text, unicode_ready))

def _card_check(pdf: FPDF, text: str, unicode_ready: bool):
    _set_font(pdf, unicode_ready, size=12, bold=True)
    pdf.set_text_color(*COLOR_ACCENT)
    check = "✓" if unicode_ready else "+"
    left = _inner_left()
    w_inner = _inner_width(pdf)
    icon_w = 5.0
    txt_w = max(w_inner - icon_w, 5.0)
    pdf.set_x(left)
    pdf.cell(icon_w, LINE_HEIGHT, _safe_text(check, unicode_ready), ln=0)
    pdf.set_text_color(*COLOR_TEXT)
    _set_font(pdf, unicode_ready, size=12, bold=False)
    pdf.set_x(left + icon_w)
    pdf.multi_cell(txt_w, LINE_HEIGHT, _safe_text(text, unicode_ready))

def _card_warn(pdf: FPDF, text: str, unicode_ready: bool):
    _set_font(pdf, unicode_ready, size=12, bold=True)
    pdf.set_text_color(*COLOR_WARN)
    warn = "⚠" if unicode_ready else "!"
    left = _inner_left()
    w_inner = _inner_width(pdf)
    icon_w = 5.0
    txt_w = max(w_inner - icon_w, 5.0)
    pdf.set_x(left)
    pdf.cell(icon_w, LINE_HEIGHT, _safe_text(warn, unicode_ready), ln=0)
    pdf.set_text_color(*COLOR_TEXT)
    _set_font(pdf, unicode_ready, size=12, bold=False)
    pdf.set_x(left + icon_w)
    pdf.multi_cell(txt_w, LINE_HEIGHT, _safe_text(text, unicode_ready))

def _write_link_line(pdf: FPDF, label: str, url: str, unicode_ready: bool):
    _set_font(pdf, unicode_ready, size=10, bold=False)
    pdf.set_text_color(*COLOR_MUTED)
    pdf.set_x(PAGE_MARGIN_L)
    pdf.write(LINE_HEIGHT, _safe_text(f"{label}: ", unicode_ready))
    pdf.set_text_color(*COLOR_PRIMARY)
    pdf.write(LINE_HEIGHT, _safe_text(url, unicode_ready), link=url)
    pdf.ln(5)
    pdf.set_text_color(*COLOR_TEXT)

# ====== Parsing ======
_SECTION_KEYWORDS = [
    r"^s[ií]ntomas[:\s]*$",
    r"^interpretaci[oó]n(\s+del\s+examen)?[:\s]*$",
    r"^recomendaci[oó]n(es)?(\s+m[eé]dica[s]?)?[:\s]*$",
    r"^3\s+preguntas\s+clave(\s+para\s+el\s+m[eé]dico)?[:\s]*$",
    r"^preguntas\s+clave[:\s]*$",
    r"^conclusi[oó]n(es)?[:\s]*$",
    r"^plan\s+de\s+seguimiento[:\s]*$",
]
_FALLBACK_SECTIONS = {
    "síntomas","sintomas",
    "interpretación del examen","interpretacion del examen",
    "3 preguntas clave para el médico","3 preguntas clave para el medico",
    "preguntas clave",
}

def _normalize_line(s: str) -> str:
    s = s.replace("\u00A0", " ").replace("\u200B", "").replace("\u200C", "").replace("\u200D", "")
    return s.rstrip()

def _is_section_heading(line: str) -> bool:
    t = line.strip()
    if t.startswith("# ") or t.startswith("## "):
        return True
    for pat in _SECTION_KEYWORDS:
        if re.match(pat, t, flags=re.I):
            return True
    if re.match(r"^\s*-{3,}\s*$", t):
        return True
    return False

def _as_clean_heading(line: str) -> str:
    t = line.strip()
    if t.startswith("# "):
        return t[2:].strip().rstrip(":").strip()
    if t.startswith("## "):
        return t[3:].strip().rstrip(":").strip()
    if re.match(r"^\s*-{3,}\s*$", t):
        return ""
    return t.rstrip(":").strip()

def _is_bullet(line: str) -> bool:
    # admite bullets con o SIN espacio tras el símbolo
    return bool(re.match(r"^\s*([\-*?\u2022\u00B7\u25E6\u2013\u2014])( |\t|$)", line))

def _strip_bullet_prefix(line: str) -> str:
    return re.sub(r"^\s*([\-*?\u2022\u00B7\u25E6\u2013\u2014])( |\t)?", "", line, count=1)

def _is_numbered(line: str) -> bool:
    return bool(re.match(r"^\s*\d+[\.\)\-\u2013\u2014]\s+", line))

# ========= Render principal =========
def save_markdown_as_pdf(
    markdown_text: str,
    out_dir: str = "./out",
    filename: Optional[str] = None,
    title: Optional[str] = None,
) -> str:
    class PDF(FPDF):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.unicode_ready = False

        def header(self):
            if self.page_no() == 1:
                return
            _set_font(self, self.unicode_ready, size=12, bold=True)
            self.set_text_color(*COLOR_PRIMARY)
            self.cell(0, 8, _safe_text(title or "Informe Médico", self.unicode_ready), ln=True, align="C")
            self.set_text_color(*COLOR_TEXT)
            _hr(self, y_offset=0.5)

        def footer(self):
            self.set_y(-15)
            _set_font(self, self.unicode_ready, size=8, bold=False)
            self.set_text_color(*COLOR_MUTED)
            self.cell(0, 10, _safe_text(f"Página {self.page_no()}", self.unicode_ready), 0, 0, "C")
            self.set_text_color(*COLOR_TEXT)

    os.makedirs(out_dir, exist_ok=True)

    fname = (filename if filename else "document.pdf")
    if not fname.lower().endswith(".pdf"):
        fname += ".pdf"
    safe_name = sanitize_filename(fname)
    output_path = os.path.abspath(os.path.join(out_dir, safe_name))

    pdf = PDF()
    pdf.set_auto_page_break(auto=True, margin=PAGE_MARGIN_B)
    pdf.set_margins(PAGE_MARGIN_L, PAGE_MARGIN_T, PAGE_MARGIN_R)

    unicode_ready = _register_unicode_fonts(pdf)
    pdf.unicode_ready = unicode_ready

    # Página 1: header
    pdf.add_page()
    _set_font(pdf, unicode_ready, size=16, bold=True)
    pdf.set_text_color(*COLOR_PRIMARY)
    pdf.set_x(PAGE_MARGIN_L)
    pdf.cell(0, 8, _safe_text(title or "Informe Médico", unicode_ready), ln=True, align="C")
    pdf.set_text_color(*COLOR_TEXT)
    _set_font(pdf, unicode_ready, size=10, bold=False)
    pdf.set_text_color(*COLOR_MUTED)
    pdf.set_x(PAGE_MARGIN_L)
    pdf.cell(0, 6, _safe_text(f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}", unicode_ready), ln=True, align="C")
    pdf.set_text_color(*COLOR_TEXT)
    _hr(pdf)

    md = (markdown_text or "").strip()
    # privacidad
    privacy_url = None
    m_priv = re.search(r"(https?://[^\s]+/privacy[^\s]*)", md, flags=re.I)
    if m_priv:
        privacy_url = m_priv.group(1)

    lines = [_normalize_line(x) for x in md.splitlines()]

    # Agrupación de secciones
    sections = []
    cur_title: Optional[str] = None
    cur_body = []

    def flush_section(force_placeholder: bool = True):
        nonlocal cur_title, cur_body, sections
        body_has_text = any(ln.strip() for ln in cur_body)
        if body_has_text:
            sections.append((cur_title, cur_body))
        else:
            if force_placeholder and cur_title and cur_title.lower() in _FALLBACK_SECTIONS:
                sections.append((cur_title, ["(sin datos proporcionados)"]))
        cur_title, cur_body = None, []

    for raw in lines:
        line = raw.rstrip()
        if _is_section_heading(line):
            flush_section(force_placeholder=True)
            title_txt = _as_clean_heading(line)
            cur_title = title_txt if title_txt else None
            continue
        cur_body.append(line)
    flush_section(force_placeholder=True)

    if not sections:
        sections = [(None, lines)]  # todo el documento como una tarjeta

    # Render secciones
    for sec_title, body_lines in sections:
        if sec_title:
            _section_title(pdf, sec_title, unicode_ready)

        x, y, pad, r = _card_begin(pdf, padding=5, r=2.0)
        wrote_any = False
        num_idx = 0

        for line in body_lines:
            if not line.strip():
                continue

            # Subtítulos ###
            if line.startswith("### "):
                _set_font(pdf, unicode_ready, size=12, bold=True)
                pdf.set_x(_inner_left())
                pdf.multi_cell(_inner_width(pdf), LINE_HEIGHT, _safe_text(line[4:].strip(), unicode_ready))
                pdf.ln(1)
                _set_font(pdf, unicode_ready, size=12, bold=False)
                wrote_any = True
                continue

            # Bullets (con o sin espacio tras el símbolo)
            if _is_bullet(line):
                txt = _strip_bullet_prefix(line).strip()
                if txt:
                    _card_bullet(pdf, txt, unicode_ready)
                    wrote_any = True
                continue

            # Numeradas
            if _is_numbered(line):
                mnum = re.match(r"^\s*(\d+)[\.\)\-\u2013\u2014]\s+(.*)$", line)
                if mnum:
                    try:
                        num_idx = int(mnum.group(1))
                    except Exception:
                        num_idx = (num_idx or 0) + 1
                    txt = mnum.group(2).strip()
                else:
                    num_idx = (num_idx or 0) + 1
                    txt = line.strip()
                if txt:
                    left = _inner_left()
                    w_inner = _inner_width(pdf)
                    num_w = 8.0
                    txt_w = max(w_inner - num_w, 5.0)
                    _set_font(pdf, unicode_ready, size=12, bold=False)
                    pdf.set_text_color(*COLOR_TEXT)
                    pdf.set_x(left)
                    pdf.cell(num_w, LINE_HEIGHT, _safe_text(f"{num_idx}.", unicode_ready), ln=0)
                    pdf.set_x(left + num_w)
                    pdf.multi_cell(txt_w, LINE_HEIGHT, _safe_text(txt, unicode_ready))
                    wrote_any = True
                continue

            # Checks / Warnings
            if re.match(r"^\s*(RECOMENDACI[ÓO]N|SUGERENCIA)[:\-]\s+", line, flags=re.I):
                txt = re.sub(r"^\s*(RECOMENDACI[ÓO]N|SUGERENCIA)[:\-]\s+", "", line, flags=re.I).strip()
                if txt:
                    _card_check(pdf, txt, unicode_ready)
                    wrote_any = True
                continue
            if re.match(r"^\s*(IMPORTANTE|ADVERTENCIA|URGENCIA)[:\-]\s+", line, flags=re.I):
                txt = re.sub(r"^\s*(IMPORTANTE|ADVERTENCIA|URGENCIA)[:\-]\s+", "", line, flags=re.I).strip()
                if txt:
                    _card_warn(pdf, txt, unicode_ready)
                    wrote_any = True
                continue

            # Párrafo normal
            _card_paragraph(pdf, line, unicode_ready)
            wrote_any = True

        if not wrote_any:
            _card_paragraph(pdf, "(sin datos proporcionados)", unicode_ready)
            wrote_any = True

        _card_end(pdf, x, y, padding=6, r=2.0, content_started=wrote_any)

    pdf.ln(2)
    if privacy_url:
        _write_link_line(pdf, "Privacidad", privacy_url, unicode_ready)

    pdf.output(output_path)
    return output_path
