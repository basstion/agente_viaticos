"""API HTTP de solicitudes de viáticos: otra entrada a la misma aplicación que agente.py.

Las rutas solo llaman a logica/; las reglas y el acceso a datos viven allí.
Arranque:  python -m uvicorn api:app
"""

from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from google.genai import errors as errores_gemini
from google.genai._gaos.lib import compat_errors  # excepciones de client.interactions (Interactions API)
from pydantic import BaseModel, ConfigDict, Field

import agente
from bd import basedatos
from logica import solicitudes as logica

RUTA_BD = basedatos.RUTA_BD
PAGINA_CHAT = Path(__file__).parent / "static" / "index.html"
# El SDK lanza una familia de excepciones u otra según la API; las dos traen el código HTTP.
ERRORES_GEMINI = (compat_errors.APIError, errores_gemini.APIError)


@asynccontextmanager
async def ciclo_de_vida(_app):
    basedatos.crear_y_cargar(RUTA_BD)  # crea bd/altiplano.db si falta; si ya tiene datos no los duplica
    yield


app = FastAPI(
    title="Viáticos Altiplano",
    description="Registro y consulta de solicitudes de viáticos. El estado lo decide la lógica de negocio.",
    lifespan=ciclo_de_vida,
)


class SolicitudNueva(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "nombre": "Natalia Guzmán",
                    "ciudad": "Medellín",
                    "fecha_salida": "2026-11-17",
                    "noches": 1,
                    "motivo": "Auditoría de bodega",
                    "valor_noche": 280000,
                    "valor_tiquete": 450000,
                }
            ]
        }
    )

    nombre: str = Field(description="Nombre completo del empleado que viaja.")
    ciudad: str = Field(description="Ciudad de destino.")
    fecha_salida: date = Field(description="Fecha de salida, AAAA-MM-DD.")
    noches: int = Field(ge=0, description="Número de noches. Un viaje de ida y vuelta el mismo día tiene 0.")
    motivo: str = Field(description="Motivo del viaje de trabajo.")
    valor_noche: int = Field(ge=0, description="Valor por noche del hotel cotizado, en pesos COP. 0 si no hay noches.")
    valor_tiquete: int = Field(ge=0, description="Valor del tiquete, en pesos COP.")


class SolicitudRegistrada(BaseModel):
    radicado: str
    estado: str
    motivo_estado: str = Field(description="Por qué la lógica asignó ese estado.")
    avisado: bool | None = Field(
        description="True si se envió el aviso por Telegram, False si falló, null si el estado no requiere aviso."
    )


class SolicitudGuardada(BaseModel):
    radicado: str
    fecha_radicado: str
    id_empleado: str
    ciudad: str
    fecha_salida: str
    noches: int
    motivo: str
    valor_noche: int
    valor_tiquete: int
    estado: str


@app.get("/solicitudes", response_model=list[SolicitudGuardada], summary="Solicitudes de un empleado")
def listar_solicitudes(empleado: str = Query(description="Nombre del empleado, sin importar mayúsculas ni tildes.")):
    try:
        return logica.consultar_solicitudes(empleado, ruta=RUTA_BD)
    except logica.EmpleadoNoEncontrado as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/solicitudes", response_model=SolicitudRegistrada, summary="Registrar una solicitud")
def crear_solicitud(solicitud: SolicitudNueva):
    try:
        resultado = logica.registrar_solicitud(
            solicitud.nombre,
            solicitud.ciudad,
            solicitud.fecha_salida.isoformat(),
            solicitud.noches,
            solicitud.motivo,
            solicitud.valor_noche,
            solicitud.valor_tiquete,
            ruta=RUTA_BD,
        )
    except logica.EmpleadoNoEncontrado as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return resultado


class MensajeChat(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"mensaje": "Hola, ¿qué puedes hacer?", "conversacion_id": None}]}
    )

    mensaje: str = Field(min_length=1, description="Mensaje del usuario para el agente.")
    conversacion_id: str | None = Field(
        default=None,
        description="Id devuelto en la respuesta anterior para continuar la conversación; null para empezar una nueva.",
    )


class RespuestaChat(BaseModel):
    respuesta: str = Field(description="Respuesta del agente.")
    conversacion_id: str = Field(description="Envíalo en el siguiente mensaje para que el agente recuerde lo hablado.")


@app.post("/chat", response_model=RespuestaChat, summary="Conversar con el agente de viáticos")
def chat(entrada: MensajeChat):
    # `def` (no `async def`): la llamada a Gemini es bloqueante y FastAPI la corre en un hilo aparte.
    try:
        interaccion = agente.responder(entrada.mensaje, entrada.conversacion_id)
    except ERRORES_GEMINI as error:
        # Un id que Gemini no reconoce llega como 400/404; el resto (429, 5xx, timeouts...) es un fallo del servicio.
        codigo = getattr(error, "status_code", None) or getattr(error, "code", None)
        if entrada.conversacion_id and codigo in (400, 404):
            raise HTTPException(status_code=404, detail="No encontré esa conversación. Empieza una nueva.") from error
        raise HTTPException(
            status_code=503,
            detail="El asistente no está disponible en este momento. Intenta de nuevo en unos minutos.",
        ) from error
    except httpx.HTTPError as error:
        raise HTTPException(
            status_code=503,
            detail="No pude comunicarme con el asistente. Intenta de nuevo en unos minutos.",
        ) from error
    except RuntimeError as error:  # el modelo no terminó de usar herramientas (MAX_VUELTAS)
        raise HTTPException(
            status_code=503,
            detail="El asistente no pudo completar la respuesta. Intenta reformular tu mensaje.",
        ) from error
    return {"respuesta": interaccion.output_text, "conversacion_id": interaccion.id}


@app.get("/", include_in_schema=False)
def pagina_chat():
    return FileResponse(PAGINA_CHAT)
