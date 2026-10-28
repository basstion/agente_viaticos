"""Avisos por Telegram. Es la única parte del proyecto que habla con esa API.

El token va dentro de la URL de la API, así que nunca se imprime ni la URL ni
el mensaje de una excepción de `requests` (que la incluye).
"""

import os
from pathlib import Path

import requests
from dotenv import load_dotenv

RUTA_ENV = Path(__file__).resolve().parent.parent / ".env"
TIMEOUT_SEGUNDOS = 10
MAX_CARACTERES = 4096  # límite de Telegram por mensaje


def enviar_aviso(texto):
    """Envía `texto` al chat configurado. Devuelve True si Telegram lo aceptó.

    Nunca lanza errores: si algo falla imprime una línea corta y devuelve False.
    """
    try:
        load_dotenv(RUTA_ENV)
        token = os.getenv("TELEGRAM_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            print("Aviso no enviado: faltan TELEGRAM_TOKEN o TELEGRAM_CHAT_ID en el .env.")
            return False

        respuesta = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": str(texto)[:MAX_CARACTERES]},
            timeout=TIMEOUT_SEGUNDOS,
        )
        if respuesta.ok:
            return True

        try:
            detalle = respuesta.json().get("description", "sin detalle")
        except ValueError:
            detalle = "sin detalle"
        print(f"Aviso no enviado: Telegram respondió {respuesta.status_code} ({detalle}).")
        return False
    except Exception as error:  # noqa: BLE001 - esta función nunca debe lanzar
        print(f"Aviso no enviado: {type(error).__name__}.")
        return False
