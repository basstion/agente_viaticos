"""Configuración: lee el archivo .env de esta carpeta."""
import os
from pathlib import Path

CARPETA = Path(__file__).parent


def _cargar_env():
    """Carga las variables de clinica9/.env sin instalar nada."""
    archivo = CARPETA / ".env"
    if not archivo.exists():
        return
    for linea in archivo.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#") and "=" in linea:
            nombre, valor = linea.split("=", 1)
            os.environ.setdefault(nombre.strip(), valor.strip())


_cargar_env()


def clave_admin():
    """Clave que protege el reporte de reembolsos."""
    return os.getenv("CLAVE_ADMINISTRADOR")
