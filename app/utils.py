import re
from datetime import datetime
from babel.dates import format_datetime

def normalize_text(s: str) -> str:
    return (s or "").strip()

def is_yes(s: str) -> bool:
    return normalize_text(s).lower() in {"si", "sí", "yes", "y", "s", "ok", "claro", "vale"}

def now_cl() -> str:
    return format_datetime(datetime.now(), "EEEE d 'de' MMMM y, HH:mm", locale="es_CL")

def extract_age(text: str) -> int | None:
    m = re.search(r'(\d{1,3})\s*(años|año)?', text.lower())
    if m:
        try:
            age = int(m.group(1))
            if 0 < age < 120:
                return age
        except:
            return None
    return None

def extract_sex(text: str) -> str | None:
    t = text.lower()
    if any(x in t for x in ["masc", "hombre", "varón", "varon", "m"]):
        return "M"
    if any(x in t for x in ["fem", "mujer", "f", "fémina", "femenino"]):
        return "F"
    return None
