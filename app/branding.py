# app/branding.py
# Constantes de marca y disclaimer reutilizables.

import os

APP_NAME = "DR MAX SALUD"
PRIMARY = (52, 120, 246)   # azul (RGB)
ACCENT  = (0, 174, 114)    # verde (RGB)
TEXT    = (33, 37, 41)
MUTED   = (108, 117, 125)

# Configurable por variable de entorno
LOGO_PATH = os.getenv("DRMAX_LOGO_PATH", "assets/logo_drmax.png")

DISCLAIMER = (
    "Este análisis es informativo y no reemplaza una consulta con un profesional de la salud. "
    "Ante síntomas graves o persistentes, acude a urgencias o a tu médico de confianza."
)
