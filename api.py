"""API HTTP de solicitudes de viáticos: otra entrada a la misma aplicación que agente.py.

Las rutas solo llaman a logica/; las reglas y el acceso a datos viven allí.
Arranque:  python -m uvicorn api:app
"""

from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from bd import basedatos
from logica import solicitudes as logica

RUTA_BD = basedatos.RUTA_BD


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
