# app/helpers/media_bytes.py
import io
import base64
import httpx
import logging
from typing import Optional, Tuple
from PIL import Image
from ..config import META_WA_ACCESS_TOKEN

logger = logging.getLogger("media_bytes")

# ====== CONFIGURACIÓN ======
MAX_IMAGE_SIZE_PX = 1600  # tamaño máximo del lado mayor (píxeles)
JPEG_QUALITY = 85          # calidad de salida si se convierte
# ============================


async def _wa_fetch_media_url(media_id: str) -> Optional[str]:
    """
    Devuelve la URL temporal de descarga para un media de WhatsApp.
    """
    try:
        url = f"https://graph.facebook.com/v19.0/{media_id}"
        headers = {"Authorization": f"Bearer {META_WA_ACCESS_TOKEN}"}
        async with httpx.AsyncClient(timeout=None) as client:
            r = await client.get(url, headers=headers)
            if r.status_code != 200:
                logger.error(f"❌ Error al obtener media_url -> {r.status_code}: {r.text}")
                return None
            return r.json().get("url")
    except Exception as e:
        logger.exception(f"⚠️ _wa_fetch_media_url falló: {e}")
        return None


async def _wa_download_bytes(url: str) -> Optional[bytes]:
    """
    Descarga los bytes crudos de un archivo de WhatsApp.
    """
    try:
        headers = {"Authorization": f"Bearer {META_WA_ACCESS_TOKEN}"}
        async with httpx.AsyncClient(timeout=None) as client:
            r = await client.get(url, headers=headers)
            if r.status_code != 200:
                logger.error(f"❌ Error descargando bytes -> {r.status_code}: {r.text}")
                return None
            return r.content
    except Exception as e:
        logger.exception(f"⚠️ _wa_download_bytes falló: {e}")
        return None


def _resize_image_if_needed(data: bytes, mime: str) -> Tuple[bytes, str]:
    """
    Si la imagen es grande, la redimensiona para que el lado mayor sea <= MAX_IMAGE_SIZE_PX.
    Devuelve (bytes_redimensionados, mime).
    """
    try:
        with Image.open(io.BytesIO(data)) as img:
            w, h = img.size
            if max(w, h) <= MAX_IMAGE_SIZE_PX:
                return data, mime  # no hace falta reducir

            scale = MAX_IMAGE_SIZE_PX / float(max(w, h))
            new_size = (int(w * scale), int(h * scale))
            img = img.resize(new_size, Image.LANCZOS)

            out = io.BytesIO()
            if img.mode in ("RGBA", "LA"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])
                img = background
            img.save(out, format="JPEG", quality=JPEG_QUALITY)
            return out.getvalue(), "image/jpeg"
    except Exception as e:
        logger.warning(f"⚠️ _resize_image_if_needed falló: {e}")
        return data, mime


def _to_base64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


async def get_media_bytes_and_mime(msg: dict) -> Tuple[Optional[bytes], Optional[str]]:
    """
    Retorna una tupla (bytes, mime) del media sin guardarlo en disco.
    - msg: el mensaje completo recibido desde el webhook de WhatsApp.
    - Devuelve (None, None) si falla.
    """
    try:
        t = msg.get("type")
        media = msg.get(t, {}) or {}
        media_id = media.get("id")
        mime = media.get("mime_type") or None

        if not media_id:
            return None, None

        meta_url = await _wa_fetch_media_url(media_id)
        if not meta_url:
            return None, None

        data = await _wa_download_bytes(meta_url)
        if not data:
            return None, None

        # Si es imagen, hacer resize preventivo
        if mime and mime.startswith("image/"):
            data, mime = _resize_image_if_needed(data, mime)

        return data, mime
    except Exception as e:
        logger.exception(f"⚠️ get_media_bytes_and_mime falló: {e}")
        return None, None


async def get_media_base64(msg: dict) -> Tuple[Optional[str], Optional[str]]:
    """
    Shortcut para obtener directamente (base64_str, mime).
    - Redimensiona si es imagen grande.
    """
    data, mime = await get_media_bytes_and_mime(msg)
    if not data:
        return None, None
    b64 = _to_base64(data)
    return b64, mime
