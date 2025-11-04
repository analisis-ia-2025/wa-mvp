# 1) Ir al proyecto
cd C:\Franco\dr-ia-wa2

# 2) Crear y activar venv
python -m venv .venv
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\.venv\Scripts\Activate.ps1

# 3) Instalar dependencias
pip install -U pip
pip install -r requirements.txt

# 4) Copiar .env.example a .env y editar credenciales
Copy-Item .env.example .env

# 5) Iniciar servidor local
uvicorn app.webhook:app --host 0.0.0.0 --port 8000 --reload

# 6) Exponer con ngrok (otra consola)
ngrok http 8000

# 7) Configurar Webhook (Meta > WhatsApp > Configuración API)
#    - URL: https://TU-URL-NGROK/webhook
#    - Verify Token: el de tu .env
#    - Suscripciones: messages
#    - Añade tu número(s) en “destinatarios permitidos” si usas el número de prueba.

# 8) Probar flujo:
#    - "Hola" -> DR-IA se presenta y pide consentimiento.
#    - "Sí, autorizo" -> pide edad/sexo si faltan.
#    - Envía una imagen del examen -> responde con informe.
#    - Conversa en lenguaje natural -> mantiene coherencia (memoria).

# Credenciales de WhatsApp Cloud API
WA_ACCESS_TOKEN=<token_de_system_user>
WA_PHONE_NUMBER_ID=<phone_number_id>

