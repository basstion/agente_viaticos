"""Muestra el nombre y el chat_id de quienes le han escrito al bot de Telegram."""
import os
import sys

import requests
from dotenv import load_dotenv


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv()
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        print("Falta TELEGRAM_TOKEN en el .env")
        return 1

    url = f"https://api.telegram.org/bot{token}/getUpdates"
    try:
        respuesta = requests.get(url, timeout=15)
    except requests.RequestException as e:
        # No se imprime el mensaje de la excepción: incluye la URL con el token.
        print(f"Error de conexión con Telegram ({type(e).__name__})")
        return 1

    datos = respuesta.json() if respuesta.content else {}
    if not respuesta.ok or not datos.get("ok"):
        print(f"Telegram respondió con error {respuesta.status_code}: "
              f"{datos.get('description', 'sin detalle')}")
        return 1

    actualizaciones = datos.get("result", [])
    if not actualizaciones:
        print("La lista de actualizaciones está vacía: nadie le ha escrito al bot todavía. "
              "Envíale un mensaje al bot y vuelve a ejecutar el script.")
        return 0

    vistos = {}
    for u in actualizaciones:
        mensaje = u.get("message") or u.get("edited_message") or u.get("channel_post")
        if not mensaje:
            continue
        chat = mensaje["chat"]
        nombre = " ".join(
            p for p in (chat.get("first_name"), chat.get("last_name")) if p
        ) or chat.get("title") or chat.get("username") or "(sin nombre)"
        vistos[chat["id"]] = nombre

    if not vistos:
        print("Hay actualizaciones, pero ninguna contiene un mensaje con chat.")
        return 0

    for chat_id, nombre in vistos.items():
        print(f"{nombre}: chat_id = {chat_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
