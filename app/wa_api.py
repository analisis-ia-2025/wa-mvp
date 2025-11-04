import httpx
import logging
from .config import META_WA_ACCESS_TOKEN, META_WA_PHONE_NUMBER_ID

log = logging.getLogger("wa_api")
BASE_URL = f"https://graph.facebook.com/v19.0/{META_WA_PHONE_NUMBER_ID}/messages"
HEADERS = {
    "Authorization": f"Bearer {META_WA_ACCESS_TOKEN}",
    "Content-Type": "application/json"
}

async def send_text(to: str, body: str):
    payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": body}}
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(BASE_URL, headers=HEADERS, json=payload)
        if r.status_code != 200:
            log.error(f"WA send_text -> {r.status_code} {r.text}")
        else:
            log.info(f"WA send_text -> 200 {r.text}")

async def send_document_link(to: str, file_url: str, filename: str):
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "document",
        "document": {"link": file_url, "filename": filename}
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(BASE_URL, headers=HEADERS, json=payload)
        if r.status_code != 200:
            log.error(f"WA send_document_link -> {r.status_code} {r.text}")
        else:
            log.info(f"WA send_document_link -> 200 {r.text}")
