"""
logging_conf.py: Configuración estándar de logging.
"""
import logging
import sys

def setup_logging(level=logging.INFO):
    # Crea un formateador simple con hora, nivel y mensaje
    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%H:%M:%S"
    )

    # Handler a stdout
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(fmt)

    # Logger raíz
    root = logging.getLogger()
    root.setLevel(level)
    # Evita handlers duplicados si recargas con --reload
    root.handlers.clear()
    root.addHandler(h)
