    
"""
worker.py: cola simple de tareas en background para:
- evitar que el webhook se bloquee
- reducir reintentos de Meta
- procesar visión/LLM y luego enviar la respuesta por WhatsApp
"""
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Any
from app.config import WORKER_MAX_THREADS

log = logging.getLogger("worker")

# Crea un pool de hilos
_pool = ThreadPoolExecutor(max_workers=max(1, WORKER_MAX_THREADS))

def submit(task: Callable[..., Any], *args, **kwargs):
    """
    Encola una tarea para ejecutarla en background.
    """
    log.info("Encolando tarea: %s", task.__name__)
    return _pool.submit(task, *args, **kwargs)
