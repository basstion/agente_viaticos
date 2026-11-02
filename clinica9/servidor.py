"""Clínica de bugs · Altiplano S.A.S.

Mini-aplicación de reembolsos de viáticos de noviembre.
Para arrancarla, desde la raíz de tu proyecto:

    python clinica9/servidor.py

y abre http://127.0.0.1:8009 en el navegador.
"""
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse

from calculos import calcular_reembolsos
from config import clave_admin

CARPETA = Path(__file__).parent

app = FastAPI(title="Clínica de bugs · Altiplano")


@app.get("/")
def inicio():
    """Entrega la página del reporte."""
    return FileResponse(CARPETA / "static" / "index.html")


@app.get("/api/reembolsos")
def reembolsos(x_clave: str | None = Header(default=None)):
    """Devuelve los reembolsos de noviembre. Pide la clave de administrador."""
    if x_clave != clave_admin():
        raise HTTPException(status_code=401, detail="Clave incorrecta")
    return calcular_reembolsos()


if __name__ == "__main__":
    print("Clínica de bugs en http://127.0.0.1:8009  (Ctrl+C para detener)")
    uvicorn.run(app, host="127.0.0.1", port=8009)
