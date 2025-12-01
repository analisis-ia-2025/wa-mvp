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


# ============================================================
# Branding / negocio / cumplimiento de políticas de negocio
# ============================================================

# Nombre "amigable" del bot (cara visible al usuario)
BOT_NAME = os.getenv("DRIA_BOT_NAME", APP_NAME if "APP_NAME" in globals() else "DR MAX SALUD")



BUSINESS_CONTACT_EMAIL = os.getenv("DRIA_CONTACT_EMAIL", "")
BUSINESS_CONTACT_PHONE = os.getenv("DRIA_CONTACT_PHONE", "")

# Aviso estándar que debe aparecer (o estar disponible) en las respuestas
DISCLAIMER = os.getenv(
    "DRIA_DISCLAIMER",
    "Aviso: Esta orientación es general y no reemplaza una consulta médica presencial con un profesional de la salud."
)

# Mensaje para casos de urgencia (Sensitive Use – D)
EMERGENCY_HINT = os.getenv(
    "DRIA_EMERGENCY_HINT",
    "Si presentas síntomas de gravedad (dolor en el pecho, dificultad para respirar, pérdida de conciencia, "
    "síntomas neurológicos agudos, sangrado abundante u otra situación de emergencia), acude de inmediato a un "
    "servicio de urgencias o llama al número de emergencias de tu país."
)
