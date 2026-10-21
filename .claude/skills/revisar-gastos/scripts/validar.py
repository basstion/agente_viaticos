#!/usr/bin/env python3
"""Revisa una legalización de gastos de viaje contra la política de viáticos.

Uso:
    python validar.py RUTA_CSV

Lee el CSV (UTF-8), decide el veredicto de cada gasto según la política
(referencia/politica_viaticos.md), calcula el total a reembolsar e imprime el
informe llenando plantilla_informe.md. Si el archivo trae varias legalizaciones,
imprime un informe por cada una.

Solo usa la biblioteca estándar.
"""

import csv
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
POLITICA = RAIZ / "referencia" / "politica_viaticos.md"
PLANTILLA = RAIZ / "plantilla_informe.md"
FIN_PLANTILLA = "<!-- fin de la plantilla -->"

# Reglas de la política, versión 2.0. Si la versión de referencia/ cambia,
# hay que revisar estas constantes.
VERSION_SOPORTADA = "2.0"
TOPE_ALIMENTACION = 95_000  # por día (sección 2)
TOPE_HOSPEDAJE = {"A": 320_000, "B": 240_000}  # por noche (sección 2)
TOPE_TRANSPORTE = 60_000  # por día (sección 2)
CIUDADES_GRUPO_A = {"bogota", "medellin", "cartagena"}  # sección 2
APROBACION_DIRECTOR_DESDE = 1_500_000  # gasto individual superior a (sección 3)
SIN_FACTURA_HASTA = 30_000  # sección 5
NOCHES_MINIMAS_LAVANDERIA = 5  # sección 6

COLUMNAS = [
    "legalizacion", "empleado", "ciudad", "salida", "regreso",
    "id", "fecha", "categoria", "descripcion", "factura", "valor_cop",
]

# Sección 6: (patrón sobre categoría + descripción sin tildes, motivo).
NO_REEMBOLSABLES = [
    (r"\b(alcohol\w*|cerveza\w*|vino|vinos|licor\w*|aguardiente|whisky|ron|tequila|coctel\w*|trago\w*)\b",
     "las bebidas alcohólicas no son reembolsables"),
    (r"\bpropina\w*\b", "las propinas no son reembolsables"),
    (r"\bmini ?bar\b", "los consumos de minibar no son reembolsables"),
    (r"\b(multa\w*|comparendo\w*)\b", "las multas de tránsito y comparendos no son reembolsables"),
    (r"\b(cine|concierto\w*|tour|tours|entretenimiento)\b",
     "el entretenimiento personal no es reembolsable"),
    (r"\bacompanante\w*\b", "los gastos de acompañantes no son reembolsables"),
]
LAVANDERIA = r"\blavander\w*"


class Gasto:
    def __init__(self, fila):
        self.id = fila["id"] or "(sin id)"
        self.fecha_texto = fila["fecha"]
        self.categoria = fila["categoria"]
        self.descripcion = fila["descripcion"]
        self.factura = fila["factura"]
        self.valor_texto = fila["valor_cop"]
        self.valor = None
        self.veredicto = ""
        self.motivo = ""


def normalizar(texto):
    """Minúsculas y sin tildes: 'Alimentación' -> 'alimentacion'."""
    base = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in base if not unicodedata.combining(c)).strip()


def pesos(valor):
    return "$" + f"{valor:,}".replace(",", ".") + " COP"


def a_entero(texto):
    """Devuelve el valor como entero positivo, o None si no es válido."""
    limpio = texto.replace("$", "").replace(" ", "")
    try:
        valor = int(limpio)
    except ValueError:
        try:
            decimal = float(limpio)
        except ValueError:
            return None
        if not decimal.is_integer():
            return None
        valor = int(decimal)
    return valor if valor > 0 else None


def a_fecha(texto):
    try:
        return date.fromisoformat(texto)
    except ValueError:
        return None


def clave_categoria(categoria):
    """Devuelve la clave de la categoría, o None si no se reconoce."""
    c = normalizar(categoria)
    if c.startswith("tiquete") or c.startswith("pasaje"):
        return "tiquete"
    if c.startswith("hospedaje"):
        return "hospedaje"
    if c.startswith("alimentacion"):
        return "alimentacion"
    if c.startswith("transporte"):
        return "transporte"
    if c in ("otros", "otro", "parqueadero", "parqueaderos", "peaje", "peajes", "papeleria"):
        return "otros"
    return None


def devolver(gasto, motivo):
    gasto.veredicto, gasto.motivo = "Devuelto", motivo


def rechazar(gasto, motivo):
    gasto.veredicto, gasto.motivo = "Rechazado", motivo


def revisar_tope(gasto, tope, nombre, unidad, acumulado, grupo=None):
    """Rechaza el gasto si, sumado a lo ya aprobado en la misma fecha, supera el tope."""
    total = acumulado + gasto.valor
    if total <= tope:  # un valor igual al tope está dentro del tope
        return False
    tope_texto = f"tope de {nombre} {unidad}" + (f" del Grupo {grupo}" if grupo else "")
    if acumulado:
        causa = (f"con lo ya aprobado ese día ({pesos(acumulado)}) suma {pesos(total)} "
                 f"y supera el {tope_texto} ({pesos(tope)}, sección 2)")
    else:
        causa = f"supera el {tope_texto} ({pesos(tope)}, sección 2)"
    rechazar(gasto, f"Sección 4: {causa} sin autorización escrita previa del director; "
                    "se rechaza completo.")
    return True


def evaluar(gastos, grupo, salida, regreso):
    noches = (regreso - salida).days
    aprobado_por_dia = {}  # (clave, fecha) -> valor ya aprobado ese día

    for g in gastos:
        # 1. Datos faltantes o inválidos -> Devuelto (sección 5, legalización).
        g.valor = a_entero(g.valor_texto)
        fecha = a_fecha(g.fecha_texto)
        clave = clave_categoria(g.categoria)
        if g.valor is None:
            devolver(g, "Sección 5: falta el valor o el valor no es válido.")
            continue
        if fecha is None:
            devolver(g, "Sección 5: falta la fecha o la fecha no es válida.")
            continue
        if not salida <= fecha <= regreso:
            devolver(g, "Sección 5: la fecha del gasto está fuera de las fechas del viaje.")
            continue
        if not g.categoria:
            devolver(g, "Sección 5: falta la categoría del gasto.")
            continue
        if clave is None:
            devolver(g, "Sección 2: la categoría no corresponde a un tipo de gasto de la política.")
            continue

        # 2. Gastos no reembolsables (sección 6).
        texto = normalizar(f"{g.categoria} {g.descripcion}")
        motivo_no_reembolsable = next(
            (m for patron, m in NO_REEMBOLSABLES if re.search(patron, texto)), None)
        if motivo_no_reembolsable is None and noches < NOCHES_MINIMAS_LAVANDERIA \
                and re.search(LAVANDERIA, texto):
            motivo_no_reembolsable = "la lavandería en viajes de menos de 5 noches no es reembolsable"
        if motivo_no_reembolsable:
            rechazar(g, f"Sección 6: {motivo_no_reembolsable}.")
            continue

        # 3. Topes por tipo de gasto (secciones 2 y 4).
        acumulado = aprobado_por_dia.get((clave, fecha), 0)
        if clave == "hospedaje" and revisar_tope(
                g, TOPE_HOSPEDAJE[grupo], "hospedaje", "por noche", acumulado, grupo):
            continue
        if clave == "alimentacion" and revisar_tope(
                g, TOPE_ALIMENTACION, "alimentación", "por día", acumulado):
            continue
        if clave == "transporte" and revisar_tope(
                g, TOPE_TRANSPORTE, "transporte terrestre urbano", "por día", acumulado):
            continue

        # 4. Aprobación del director para gastos individuales altos (sección 3).
        if g.valor > APROBACION_DIRECTOR_DESDE:
            devolver(g, f"Sección 3: supera {pesos(APROBACION_DIRECTOR_DESDE)} y falta la "
                        "aprobación del director del área.")
            continue

        # 5. Factura electrónica (sección 5).
        if g.valor > SIN_FACTURA_HASTA and not g.factura:
            devolver(g, f"Sección 5: falta la factura electrónica "
                        f"(valor mayor a {pesos(SIN_FACTURA_HASTA)}).")
            continue

        g.veredicto = "Aprobado"
        aprobado_por_dia[(clave, fecha)] = acumulado + g.valor


def celda(texto):
    return texto.replace("|", "\\|").replace("\n", " ")


def informe(plantilla, version, filas):
    primera = filas[0]
    salida, regreso = a_fecha(primera["salida"]), a_fecha(primera["regreso"])
    if salida is None or regreso is None or regreso < salida:
        raise ValueError(f"La legalización {primera['legalizacion']} tiene fechas de salida "
                         "o regreso no válidas.")
    grupo = "A" if normalizar(primera["ciudad"]) in CIUDADES_GRUPO_A else "B"

    gastos = [Gasto(f) for f in filas]
    evaluar(gastos, grupo, salida, regreso)

    tabla = [
        "| " + " | ".join(celda(c) for c in (
            g.id, g.fecha_texto, g.categoria,
            pesos(g.valor) if g.valor else (g.valor_texto or "(sin valor)"),
            g.veredicto, g.motivo)) + " |"
        for g in gastos
    ]
    total = sum(g.valor for g in gastos if g.veredicto == "Aprobado")
    cuenta = lambda v: sum(1 for g in gastos if g.veredicto == v)

    valores = {
        "legalizacion": primera["legalizacion"],
        "empleado": primera["empleado"],
        "ciudad": primera["ciudad"],
        "grupo": grupo,
        "salida": primera["salida"],
        "regreso": primera["regreso"],
        "version": version,
        "filas": "\n".join(tabla),
        "presentados": str(len(gastos)),
        "aprobados": str(cuenta("Aprobado")),
        "rechazados": str(cuenta("Rechazado")),
        "devueltos": str(cuenta("Devuelto")),
        "total": pesos(total),
    }
    texto = plantilla
    for campo, valor in valores.items():
        texto = texto.replace("{{" + campo + "}}", valor)
    return texto


def leer_csv(ruta):
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        lector = csv.DictReader(f)
        faltan = [c for c in COLUMNAS if c not in (lector.fieldnames or [])]
        if faltan:
            raise ValueError("Al CSV le faltan estas columnas: " + ", ".join(faltan))
        filas = [{c: (r.get(c) or "").strip() for c in COLUMNAS} for r in lector]
    filas = [f for f in filas if any(f.values())]
    if not filas:
        raise ValueError("El CSV no tiene gastos.")
    return filas


def main(argv):
    if len(argv) != 2:
        print("Uso: python validar.py RUTA_CSV", file=sys.stderr)
        return 2
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        filas = leer_csv(argv[1])
        plantilla = PLANTILLA.read_text(encoding="utf-8").split(FIN_PLANTILLA)[0].strip() + "\n"
        coincidencia = re.search(r"\*\*Versión:\*\*\s*([\d.]+)", POLITICA.read_text(encoding="utf-8"))
        if not coincidencia:
            raise ValueError(f"No encontré la versión de la política en {POLITICA}.")
        version = coincidencia.group(1)
        if version != VERSION_SOPORTADA:
            print(f"Advertencia: la política es versión {version} y el script se escribió para "
                  f"la {VERSION_SOPORTADA}; revisa las reglas de validar.py.", file=sys.stderr)

        por_legalizacion = {}
        for fila in filas:
            por_legalizacion.setdefault(fila["legalizacion"], []).append(fila)
        informes = [informe(plantilla, version, grupo) for grupo in por_legalizacion.values()]
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    print("\n---\n\n".join(informes), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
