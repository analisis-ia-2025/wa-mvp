import os
from dotenv import load_dotenv
load_dotenv()

APP_NAME = "DR MAX SALUD"

# FastAPI
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8080"))

# WhatsApp Cloud API (soporta tus nombres y los anteriores)
META_WA_PHONE_NUMBER_ID = (
    os.getenv("WA_PHONE_NUMBER_ID") 
    or os.getenv("META_WA_PHONE_NUMBER_ID") 
    or ""
)
META_WA_ACCESS_TOKEN = (
    os.getenv("WA_ACCESS_TOKEN") 
    or os.getenv("META_WA_ACCESS_TOKEN") 
    or ""
)
META_WA_VERIFY_TOKEN = (
    os.getenv("WEBHOOK_VERIFY_TOKEN") 
    or os.getenv("META_WA_VERIFY_TOKEN") 
    or "drmax-verify-token"
)

# Público (para enviar el PDF como link en WhatsApp)
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL")  # ej. https://drmax.midominio.cl

# Branding opcional
BOT_NAME = os.getenv("DRIA_BOT_NAME", "DR MAX SALUD")
BUSINESS_NAME = os.getenv("DRIA_BUSINESS_NAME", "DR MAX SALUD")
PRIVACY_URL = os.getenv("DRIA_PRIVACY_URL")
CONTACT_EMAIL = os.getenv("DRIA_CONTACT_EMAIL", "")
WELCOME_TTL_DAYS = int(os.getenv("DRIA_WELCOME_TTL_DAYS", "7"))
DATA_RETENTION_DAYS = int(os.getenv("DRIA_DATA_RETENTION_DAYS", "90"))
WELCOME_TEXT = os.getenv("DRIA_WELCOME_TEXT")

# Rutas de salida
BASE_DIR = os.path.dirname(os.path.dirname(__file__))  # raíz del proyecto
OUT_DIR = os.path.join(BASE_DIR, "out")
PDF_DIR = os.path.join(OUT_DIR, "reports")
os.makedirs(PDF_DIR, exist_ok=True)

# BD
DB_PATH = os.getenv("DB_PATH", os.path.join(BASE_DIR, "dria_memory.sqlite3"))

# LLM (opcional)
USE_LLM = os.getenv("USE_LLM", "false").lower() in ("1", "true", "yes")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

# Mensajería clínica
DISCLAIMER = (
    "Este servicio es informativo y NO reemplaza la atención médica presencial. "
    "Si presentas síntomas de urgencia, acude a un servicio de emergencia."
)
EMERGENCY_SIGNS = [
    "dolor fuerte en el pecho", "opresión torácica", "falta de aire severa",
    "dificultad para respirar", "debilidad de un lado del cuerpo",
    "confusión súbita", "desmayo", "convulsión", "sangrado abundante",
    "dolor abdominal intenso", "dolor de cabeza súbito y muy intenso",
]
import os

def _as_bool(v: str | None, default: bool = False) -> bool:
    if v is None:
        return default
    return str(v).strip().lower() in {"1", "true", "yes", "y", "on"}



# Nuevo: controlar si guardamos media a disco (fallback)
MEDIA_SAVE_TO_DISK = _as_bool(os.getenv("MEDIA_SAVE_TO_DISK"), default=False)
