import os
import io
import cv2
import numpy as np
import requests
import pytesseract
from fastapi import FastAPI, Request, Response, Query
from dotenv import load_dotenv
from PIL import Image
# --- IA médica conversacional (LLM) ---
import json
from openai import OpenAI

load_dotenv()

app = FastAPI()

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID", "")
GRAPH_API_VERSION = os.getenv("GRAPH_API_VERSION", "v22.0")
TESSERACT_CMD = os.getenv("TESSERACT_CMD", "")

if TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
MSG_URL = f"{GRAPH_BASE}/{PHONE_NUMBER_ID}/messages"
HEADERS = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}


# memoria de sesión ultra-simple (RAM) por número; para MVP basta
SESSIONS = {}  # { wa_id: {"age":..., "sex":..., "last_summary": "..."} }

def get_session(wa_id: str) -> dict:
    s = SESSIONS.get(wa_id, {})
    SESSIONS[wa_id] = s
    return s

def upsert_session(wa_id: str, **kwargs):
    s = get_session(wa_id)
    s.update({k:v for k,v in kwargs.items() if v is not None})
    SESSIONS[wa_id] = s

def normalize_yesno(text: str) -> str:
    t = text.strip().lower()
    return t

def need_demographics(sess: dict) -> list[str]:
    missing = []
    if not sess.get("age"):
        missing.append("edad")
    if not sess.get("sex"):
        missing.append("sexo (masculino/femenino)")
    return missing

def build_llm_prompt(parsed: dict, raw_text: str, sess: dict) -> str:
    profile = {
        "edad": sess.get("age"),
        "sexo": sess.get("sex"),
        "sintomas": sess.get("sx"),
    }

    payload = {
        "perfil_usuario": profile,
        "resultado_parseado": parsed,
        "texto_OCR": raw_text[:4000],
    }

    instruct = f"""
Eres un asistente médico especializado en interpretar exámenes de laboratorio (hemogramas, bioquímica, etc.) para pacientes no médicos.

### Objetivo
Redacta un informe interpretativo **completo y estructurado**, en español de Chile, con secciones y formato Markdown.

### Formato de salida
1. **🩸 Serie Roja**
   - Tabla con: Parámetro | Resultado | Rango de referencia | Interpretación breve
2. **🧫 Serie Plaquetar**
   - Igual formato
3. **⚪ Serie Blanca**
   - Igual formato
4. **⚖️ Resumen general**
   - Puntos con hallazgos clave
5. **💡 Recomendaciones**
   - Consejos clínicos prudentes, como repetir examen o consultar médico
6. **⚠️ Disclaimer**
   - "Esto no reemplaza la evaluación de un profesional de la salud."

### Estilo
- Tono claro, empático y educativo.
- No des diagnósticos definitivos.
- Si faltan edad o sexo, menciónalo.
- Usa unidades (g/dL, %, etc.) cuando existan.

Datos:
{json.dumps(payload, ensure_ascii=False, indent=2)}
"""
    return instruct


# Cliente del modelo
_openai_client = None
def get_openai_client():
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _openai_client

def analyze_with_llm(parsed: dict, raw_text: str, sess: dict) -> dict:
    try:
        prompt = build_llm_prompt(parsed, raw_text, sess)

        client = get_openai_client()

        messages = [
            {
                "role": "system",
                # ← ojo: aparece 'json' en minúscula
                "content": (
                    "Eres un asistente médico prudente. "
                    "Responde únicamente en json válido (json), sin texto extra ni explicaciones fuera del objeto."
                ),
            },
            {
                "role": "user",
                # ← repetimos la instrucción de 'json' por si acaso
                "content": (
                    prompt
                    + "\n\nDevuelve SOLO un objeto json con estas claves exactas: "
                    "resumen (string), preguntas_siguientes (array de strings), alertas (array de strings)."
                ),
            },
        ]

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.4,
            messages=messages,
            response_format={"type": "json_object"},
        )

        content = resp.choices[0].message.content
        data = json.loads(content)

        return {
            "resumen": data.get("resumen", "").strip(),
            "preguntas_siguientes": data.get("preguntas_siguientes", [])[:2],
            "alertas": data.get("alertas", [])[:3],
        }

    except Exception as e:
        print("LLM error:", e)
        # fallback seguro
        return {
            "resumen": (
                "Pude leer tu examen y vi algunos valores. "
                "Ten en cuenta que la interpretación cambia por edad/sexo y contexto clínico. "
                "Si tienes síntomas relevantes, consulta a un profesional."
            ),
            "preguntas_siguientes": ["¿Cuál es tu edad?", "¿Cuál es tu sexo?"],
            "alertas": ["Este resultado no reemplaza la evaluación médica."],
        }


def render_medical_reply(llm: dict) -> str:
    lines = []
    if llm.get("resumen"):
        lines.append(llm["resumen"])
    if llm.get("alertas"):
        lines.append("")
        lines.append("⚠️ Alertas:")
        for a in llm["alertas"]:
            lines.append(f"- {a}")
    if llm.get("preguntas_siguientes"):
        lines.append("")
        lines.append("❓ Para personalizar mejor:")
        for q in llm["preguntas_siguientes"]:
            lines.append(f"- {q}")
    # Disclaimer final de seguridad, redundante
    lines.append("")
    lines.append("ℹ️ Esto no reemplaza la evaluación de un profesional de la salud.")
    return "\n".join(lines)


def send_text(to_number: str, body: str):
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "text": {"body": body},
    }
    r = requests.post(MSG_URL, headers={**HEADERS, "Content-Type":"application/json"}, json=payload, timeout=30)
    print("📤 Envío:", r.status_code, r.text)
    return r

def fetch_media_binary(media_id: str) -> bytes:
    # 1) Get media URL
    meta = requests.get(f"{GRAPH_BASE}/{media_id}", headers=HEADERS, timeout=30).json()
    url = meta.get("url")
    if not url:
        raise RuntimeError(f"No media url for id {media_id}: {meta}")
    # 2) Download with bearer
    rb = requests.get(url, headers=HEADERS, timeout=60)
    rb.raise_for_status()
    return rb.content

def ocr_image_bytes(img_bytes: bytes) -> str:
    # Convert to OpenCV image
    img = np.asarray(Image.open(io.BytesIO(img_bytes)).convert("RGB"))
    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    # Pre-proceso simple: escala de grises + binarización adaptativa
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    proc = cv2.adaptiveThreshold(gray, 255,
                                 cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                 cv2.THRESH_BINARY, 35, 10)

    # OCR (español + inglés)
    text = pytesseract.image_to_string(proc, lang="spa+eng")
    # Limpieza básica
    text = "\n".join([line.strip() for line in text.splitlines() if line.strip()])
    return text

import re

# Rangos de referencia para ADULTOS (pueden variar por laboratorio/sexo/edad)
RANGES = {
    "hemoglobina": (12.0, 17.5),   # g/dL
    "hematocrito": (36, 52),       # %
    "vcm": (80, 100),              # fL
    "hcm": (27, 33),               # pg
    "chcm": (32, 36),              # g/dL
    "rdw": (11.5, 15.5),           # %
    "leucocitos": (4.0, 11.0),     # 10^3/uL
    "plaquetas": (150, 450),       # 10^3/uL
    "vpm": (7, 12),                # fL
    # Diferencial en %
    "neutrofilos_%": (40, 75),
    "linfocitos_%": (20, 45),
    "monocitos_%": (2, 10),
    "eosinofilos_%": (0, 6),
    "basofilos_%": (0, 2),
}

def _clean(s: str) -> str:
    return re.sub(r"[^\w\s\.\,\-%/áéíóúÁÉÍÓÚñÑ]", " ", s.lower())

def _num(x: str):
    try:
        return float(x.replace(",", "."))
    except:
        return None

def parse_hemogram_text(txt: str):
    """
    Extrae valores típicos de un hemograma desde texto OCR.
    Devuelve un dict normalizado con campos y unidades cuando es posible.
    """
    t = _clean(txt)

    # Mapeos de sinónimos frecuentes
    patterns = {
        "hemoglobina": r"\b(hemoglobina|hb)\b[:\s]*([0-9]+[.,]?[0-9]*)",
        "hematocrito": r"\b(hematocrito|hto?|hct)\b[:\s]*([0-9]+[.,]?[0-9]*)",
        "vcm": r"\b(v\.?c\.?m\.?|mcv)\b[:\s]*([0-9]+[.,]?[0-9]*)",
        "hcm": r"\b(h\.?c\.?m\.?|mch)\b[:\s]*([0-9]+[.,]?[0-9]*)",
        "chcm": r"\b(c\.?h\.?c\.?m\.?|mchc)\b[:\s]*([0-9]+[.,]?[0-9]*)",
        "rdw": r"\b(rdw|ade|ad\.?e\.?)\b[:\s]*([0-9]+[.,]?[0-9]*)",
        "plaquetas": r"\b(plaquetas|plt)\b[:\s]*([0-9]+[.,]?[0-9]*)",
        "vpm": r"\b(v\.?p\.?m\.?|mpv)\b[:\s]*([0-9]+[.,]?[0-9]*)",
        "leucocitos": r"\b(leucocitos|wbc)\b[:\s]*([0-9]+[.,]?[0-9]*)",
        # Diferencial (porcentaje). Acepta abreviaturas comunes
        "neutrofilos_%": r"\b(neu|neutro?f(?:ilos)?)\b[:\s]*([0-9]+[.,]?[0-9]*)\s*%?",
        "linfocitos_%": r"\b(lin|linfo?citos?)\b[:\s]*([0-9]+[.,]?[0-9]*)\s*%?",
        "monocitos_%": r"\b(mon|mono?citos?)\b[:\s]*([0-9]+[.,]?[0-9]*)\s*%?",
        "eosinofilos_%": r"\b(eos|eosino?f(?:ilos)?)\b[:\s]*([0-9]+[.,]?[0-9]*)\s*%?",
        "basofilos_%": r"\b(bas|baso?f(?:ilos)?)\b[:\s]*([0-9]+[.,]?[0-9]*)\s*%?",
    }

    data = {}
    for key, rx in patterns.items():
        m = re.search(rx, t, flags=re.I)
        if m:
            val = _num(m.group(2))
            if val is not None:
                data[key] = val

    # Heurísticas por columnas: a veces OCR deja los % difícil de vincular.
    # Si no detectó diferencial, prueba capturar secuencias "Neu 49.8", etc.
    if not any(k.endswith("_%") for k in data):
        for k, tag in [("neutrofilos_%", "neu"), ("linfocitos_%", "lin"), ("monocitos_%", "mon"),
                       ("eosinofilos_%", "eos"), ("basofilos_%", "bas")]:
            m = re.search(rf"\b{tag}\b[:\s]*([0-9]+[.,]?[0-9]*)", t)
            if m:
                v = _num(m.group(1))
                if v is not None:
                    data[k] = v

    return data

def flag_value(name: str, val: float):
    if name not in RANGES or val is None:
        return "?", ""
    lo, hi = RANGES[name]
    if val < lo:
        return "🔽", f"(bajo, ref {lo}-{hi})"
    if val > hi:
        return "🔼", f"(alto, ref {lo}-{hi})"
    return "✅", f"(normal {lo}-{hi})"

def build_summary(data: dict):
    lines = []
    # Orden sugerido
    order = [
        ("hemoglobina", "g/dL"),
        ("hematocrito", "%"),
        ("vcm", "fL"),
        ("hcm", "pg"),
        ("chcm", "g/dL"),
        ("rdw", "%"),
        ("leucocitos", "10^3/µL"),
        ("plaquetas", "10^3/µL"),
        ("vpm", "fL"),
        ("neutrofilos_%", "%"),
        ("linfocitos_%", "%"),
        ("monocitos_%", "%"),
        ("eosinofilos_%", "%"),
        ("basofilos_%", "%"),
    ]
    found = False
    for key, unit in order:
        if key in data:
            found = True
            icon, note = flag_value(key, data[key])
            label = key.replace("_%", "").capitalize().replace("vcm","VCM").replace("hcm","HCM").replace("chcm","CHCM").replace("rdw","RDW").replace("vpm","VPM")
            lines.append(f"{icon} {label}: {data[key]} {unit} {note}")
    if not found:
        return "No pude reconocer valores con confianza. ¿Puedes enviar una foto más nítida/recta o como documento PDF?"

    # Disclaimer breve
    lines.append("")
    lines.append("ℹ️ Rangos de referencia de adulto. Pueden variar por laboratorio, edad y sexo. Esto no sustituye evaluación médica.")
    return "\n".join(lines)



@app.get("/webhook")
async def verify(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
):
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        return Response(content=hub_challenge or "", media_type="text/plain")
    return Response(status_code=403, content="Forbidden")

@app.post("/webhook")
async def incoming(request: Request):
    data = await request.json()
    print("📩 Payload recibido:", data)

    try:
        entry = data.get("entry", [])
        if not entry:
            return {"status": "ok"}
        changes = entry[0].get("changes", [])
        if not changes:
            return {"status": "ok"}
        value = changes[0].get("value", {})
        messages = value.get("messages", [])
        statuses = value.get("statuses", [])

        # Ignora callbacks de estado
        if statuses:
            return {"status": "ok"}
        if not messages:
            return {"status": "ok"}

        for msg in messages:
            from_number = msg.get("from")
            mtype = msg.get("type")

            if mtype == "text":
                text = msg.get("text", {}).get("body", "").strip()
                sess = get_session(from_number)

                # captura simple de edad/sexo si el usuario contesta
                if "edad" in text.lower():
                    # Ej: "edad 34" o "tengo 34"
                    m = re.search(r"(\d{1,3})", text)
                    if m:
                        upsert_session(from_number, age=int(m.group(1)))
                        send_text(from_number, "👌 Edad registrada. Cuando envíes tu examen, podré ajustar los rangos.")
                        return {"status":"ok"}

                if any(x in text.lower() for x in ["sexo", "genero", "género", "soy hombre", "soy mujer", "femenino", "masculino"]):
                    if "femenin" in text.lower() or "mujer" in text.lower():
                        upsert_session(from_number, sex="femenino")
                        send_text(from_number, "👌 Sexo registrado: femenino.")
                        return {"status":"ok"}
                    if "masculin" in text.lower() or "hombre" in text.lower():
                        upsert_session(from_number, sex="masculino")
                        send_text(from_number, "👌 Sexo registrado: masculino.")
                        return {"status":"ok"}

                # eco por defecto / ayuda
                send_text(from_number, "Puedo analizar tu examen (foto o PDF). También puedes decirme: 'edad 34' o 'sexo femenino' para afinar la interpretación.")

            elif mtype == "image":
                media_id = msg.get("image", {}).get("id")
                try:
                    bin_data = fetch_media_binary(media_id)
                    text = ocr_image_bytes(bin_data)
                    parsed = parse_hemogram_text(text)

                    sess = get_session(from_number)
                    # Guarda último resumen corto por si lo usas más adelante
                    upsert_session(from_number, last_raw=text)

                    # 1) Resumen objetivo (iconos/rangos) que ya tenías (opcional):
                    # summary = build_summary(parsed)
                    # send_text(from_number, summary)

                    # 2) Análisis conversacional con LLM:
                    llm = analyze_with_llm(parsed, text, sess)
                    reply = render_medical_reply(llm)
                    send_text(from_number, reply)

                except Exception as e:
                    print("❗ OCR/LLM error:", e)
                    send_text(from_number, "Tu imagen no se pudo analizar bien. Intenta enviarla como documento, con buena luz y sin sombras.")

            elif mtype == "document":
                # (Opcional) podrías hacer OCR de PDF/imágenes incrustadas.
                send_text(from_number, "📄 Recibí tu documento. Pronto habilitaré lectura de PDF.")

            else:
                send_text(from_number, f"Recibí un mensaje tipo '{mtype}'. Por ahora proceso texto e imágenes.")

    except Exception as e:
        print("❗ Error procesando webhook:", e)

    return {"status": "ok"}

@app.get("/health")
def health():
    return {"ok": True}
