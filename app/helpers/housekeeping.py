# app/helpers/housekeeping.py
import os
import time
import logging
from typing import Iterable, Optional

logger = logging.getLogger("housekeeping")

def _purge_dir(dir_path: str, older_than_epoch: float, patterns: Optional[Iterable[str]] = None) -> dict:
    """
    Elimina archivos en dir_path con mtime < older_than_epoch.
    Si 'patterns' se entrega (e.g., [".pdf", ".jpg"]), solo borra si el nombre termina con alguno de esos sufijos.
    Retorna estadísticas {'scanned': int, 'deleted': int, 'errors': int}.
    """
    stats = {"scanned": 0, "deleted": 0, "errors": 0}
    if not dir_path or not os.path.isdir(dir_path):
        return stats

    pats = tuple(p.strip().lower() for p in (patterns or [])) or None

    for name in os.listdir(dir_path):
        path = os.path.join(dir_path, name)
        try:
            if not os.path.isfile(path):
                continue
            if pats and not name.lower().endswith(pats):
                continue

            stats["scanned"] += 1
            mtime = os.path.getmtime(path)
            if mtime < older_than_epoch:
                try:
                    os.remove(path)
                    stats["deleted"] += 1
                    logger.info(f"🧹 Eliminado por retención: {path}")
                except Exception as e:
                    stats["errors"] += 1
                    logger.warning(f"⚠️ No se pudo eliminar {path}: {e}")
        except Exception as e:
            stats["errors"] += 1
            logger.warning(f"⚠️ Error procesando {path}: {e}")
    return stats


def clean_old_files(pdf_dir: str, media_dir: Optional[str], retention_days: int) -> dict:
    """
    Limpia PDFs y media antiguos según 'retention_days'.
    - Elimina *.pdf en pdf_dir
    - Si media_dir existe, elimina imágenes/audio/video/documentos antiguos (extensiones comunes)
    Retorna dict con métricas.
    """
    now = time.time()
    older_than = now - float(retention_days) * 86400.0
    out = {"pdf": {}, "media": {}}

    # PDFs
    if pdf_dir and os.path.isdir(pdf_dir):
        out["pdf"] = _purge_dir(pdf_dir, older_than, patterns=[".pdf"])
    else:
        out["pdf"] = {"scanned": 0, "deleted": 0, "errors": 0}

    # Media (opcional)
    if media_dir and os.path.isdir(media_dir):
        media_exts = [".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp4", ".mov", ".m4v", ".avi",
                      ".mp3", ".ogg", ".wav", ".pdf", ".doc", ".docx", ".xls", ".xlsx"]
        out["media"] = _purge_dir(media_dir, older_than, patterns=media_exts)
    else:
        out["media"] = {"scanned": 0, "deleted": 0, "errors": 0}

    logger.info(f"✅ Housekeeping: {out}")
    return out
