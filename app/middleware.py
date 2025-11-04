# app/middleware.py
# Fuerza dominio médico, construye prompt y renderiza respuestas.

from typing import Tuple, Dict
from .persona import MEDICAL_SYSTEM_PROMPT, REFUSAL_MESSAGE
from .formatters import format_whatsapp_message, parse_llm_json_prefix
from .confidence import estimate_confidence

CLINICAL = (
    "síntoma","sintoma","dolor","fiebre","tos","mareo","náusea","nausea","diarrea",
    "examen","hemograma","glucosa","colesterol","triglicéridos","trigliceridos","pcr","radiografía",
    "rx","tomografía","ecografía","saturación","presión","presion","oxígeno","oxigeno",
    "mg/dl","mmol/l","g/dl","u/l","mm hg"
)

def enforce_medical_domain(user_text: str) -> bool:
    lower = user_text.lower()
    return any(k in lower for k in CLINICAL)

def build_prompt(user_text: str) -> str:
    if not enforce_medical_domain(user_text):
        # Empuja al modelo a rechazar temas no médicos
        return MEDICAL_SYSTEM_PROMPT + "\n\nUsuario pide tema potencialmente no médico. Responde con rechazo elegante."
    return MEDICAL_SYSTEM_PROMPT

def render_response(llm_text: str) -> Tuple[str, Dict]:
    """
    Devuelve (mensaje_whatsapp, json_dict) y asegura confidence si falta.
    """
    try:
        data, _ = parse_llm_json_prefix(llm_text)
    except Exception:
        # No viene JSON al inicio, devolvemos mensaje formateado genérico
        msg = format_whatsapp_message(llm_text)
        return msg, {}

    # Autocompletar confidence si no llegó
    if "confidence" not in data:
        data["confidence"] = estimate_confidence(data)

    msg = format_whatsapp_message(llm_text)
    return msg, data
