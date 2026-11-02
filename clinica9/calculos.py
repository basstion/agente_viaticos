"""Cálculo de reembolsos de viáticos. Las reglas están en politica_reembolsos.md."""
import csv
from datetime import date
from pathlib import Path

CARPETA = Path(__file__).parent
ARCHIVO = CARPETA / "datos" / "legalizaciones_noviembre.csv"

ALIMENTACION_POR_DIA = 80_000


def dias_de_viaje(salida: date, regreso: date) -> int:
    """Días de viaje que se reconocen para alimentación."""
    return (regreso - salida).days + 1


def calcular_reembolsos() -> list[dict]:
    """Lee las legalizaciones y calcula cuánto se le reembolsa a cada viaje."""
    resultado = []
    with open(ARCHIVO, encoding="utf-8", newline="") as archivo:
        for fila in csv.DictReader(archivo):
            salida = date.fromisoformat(fila["fecha_salida"])
            regreso = date.fromisoformat(fila["fecha_regreso"])
            dias = dias_de_viaje(salida, regreso)
            alimentacion = dias * ALIMENTACION_POR_DIA
            transporte = int(fila["transporte_cop"])
            resultado.append({
                "empleado": fila["empleado"],
                "ciudad": fila["ciudad"],
                "salida": fila["fecha_salida"],
                "regreso": fila["fecha_regreso"],
                "dias": dias,
                "alimentacion": alimentacion,
                "transporte": transporte,
                "total": alimentacion + transporte,
            })
    return resultado
