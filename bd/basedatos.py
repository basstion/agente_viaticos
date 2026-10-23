"""Capa de datos de viáticos: SQLite + CSV de kit7/.

Solo guarda y consulta datos. No aplica reglas de negocio: los topes de
ciudades.csv se almacenan como datos y el estado de una solicitud lo trae
quien la guarda.
"""

import csv
import sqlite3
import unicodedata
from contextlib import closing
from datetime import date
from pathlib import Path

DIR_BD = Path(__file__).resolve().parent
RUTA_BD = DIR_BD / "altiplano.db"
DIR_CSV = DIR_BD.parent / "kit7"

ESQUEMA = """
CREATE TABLE IF NOT EXISTS empleados (
    id_empleado TEXT PRIMARY KEY,
    nombre      TEXT NOT NULL,
    area        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ciudades (
    ciudad         TEXT PRIMARY KEY,
    grupo          TEXT NOT NULL,
    tope_hospedaje INTEGER NOT NULL
);

-- ciudad no es llave foránea: se aceptan destinos que no están en ciudades
-- (p. ej. Lima), que otra capa marca como "Por revisar".
CREATE TABLE IF NOT EXISTS solicitudes (
    radicado       TEXT PRIMARY KEY,
    fecha_radicado TEXT NOT NULL,
    id_empleado    TEXT NOT NULL REFERENCES empleados (id_empleado),
    ciudad         TEXT NOT NULL,
    fecha_salida   TEXT NOT NULL,
    noches         INTEGER NOT NULL,
    motivo         TEXT NOT NULL,
    valor_noche    INTEGER NOT NULL,
    valor_tiquete  INTEGER NOT NULL,
    estado         TEXT NOT NULL
);
"""

# tabla -> (archivo CSV, columnas en orden, columnas enteras)
TABLAS = {
    "empleados": ("empleados.csv", ("id_empleado", "nombre", "area"), ()),
    "ciudades": (
        "ciudades.csv",
        ("ciudad", "grupo", "tope_hospedaje"),
        ("tope_hospedaje",),
    ),
    "solicitudes": (
        "solicitudes_historicas.csv",
        (
            "radicado", "fecha_radicado", "id_empleado", "ciudad",
            "fecha_salida", "noches", "motivo", "valor_noche",
            "valor_tiquete", "estado",
        ),
        ("noches", "valor_noche", "valor_tiquete"),
    ),
}

PREFIJO_RADICADO = "S-"
PRIMER_RADICADO = 101


def normalizar(texto):
    """Minúsculas, sin tildes y sin espacios sobrantes: 'Medellín ' -> 'medellin'."""
    if texto is None:
        return None
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", str(texto))
        if unicodedata.category(c) != "Mn"
    )
    return " ".join(sin_tildes.casefold().split())


def conectar(ruta=RUTA_BD):
    """Abre la base con llaves foráneas activas y la función SQL normalizar()."""
    conexion = sqlite3.connect(ruta)
    conexion.row_factory = sqlite3.Row
    conexion.execute("PRAGMA foreign_keys = ON")
    conexion.create_function("normalizar", 1, normalizar, deterministic=True)
    return conexion


def _leer_csv(archivo, columnas, enteras):
    with open(DIR_CSV / archivo, newline="", encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            yield tuple(
                int(fila[c]) if c in enteras else fila[c].strip() for c in columnas
            )


def crear_y_cargar(ruta=RUTA_BD):
    """Crea las tablas y carga los CSV en las que estén vacías.

    Es seguro llamarla varias veces: una tabla que ya tiene filas no se toca.
    Devuelve las filas que hay en cada tabla.
    """
    with closing(conectar(ruta)) as conexion, conexion:
        conexion.executescript(ESQUEMA)
        for tabla, (archivo, columnas, enteras) in TABLAS.items():
            hay = conexion.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
            if hay:
                continue
            marcas = ", ".join("?" for _ in columnas)
            conexion.executemany(
                f"INSERT INTO {tabla} ({', '.join(columnas)}) VALUES ({marcas})",
                _leer_csv(archivo, columnas, enteras),
            )
        return {
            t: conexion.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in TABLAS
        }


def buscar_empleado(nombre, ruta=RUTA_BD):
    """Empleado cuyo nombre coincide (sin mayúsculas ni tildes), o None."""
    with closing(conectar(ruta)) as conexion:
        fila = conexion.execute(
            "SELECT * FROM empleados WHERE normalizar(nombre) = normalizar(?)",
            (nombre,),
        ).fetchone()
    return dict(fila) if fila else None


def buscar_ciudad(ciudad, ruta=RUTA_BD):
    """Ciudad con su grupo y tope de hospedaje (sin mayúsculas ni tildes), o None."""
    with closing(conectar(ruta)) as conexion:
        fila = conexion.execute(
            "SELECT * FROM ciudades WHERE normalizar(ciudad) = normalizar(?)",
            (ciudad,),
        ).fetchone()
    return dict(fila) if fila else None


def _siguiente_radicado(conexion):
    mayor = conexion.execute(
        "SELECT MAX(CAST(SUBSTR(radicado, ?) AS INTEGER)) FROM solicitudes",
        (len(PREFIJO_RADICADO) + 1,),
    ).fetchone()[0]
    numero = PRIMER_RADICADO if mayor is None else mayor + 1
    return f"{PREFIJO_RADICADO}{numero}"


def siguiente_radicado(ruta=RUTA_BD):
    """Radicado que sigue al mayor existente (S-141 tras S-140)."""
    with closing(conectar(ruta)) as conexion:
        return _siguiente_radicado(conexion)


def guardar_solicitud(solicitud, ruta=RUTA_BD):
    """Inserta una solicitud y devuelve el radicado con que quedó.

    `solicitud` es un dict con id_empleado, ciudad, fecha_salida, noches,
    motivo, valor_noche, valor_tiquete y estado. Si no trae `radicado` se
    toma el siguiente, y si no trae `fecha_radicado` se usa la de hoy.
    Falla (sqlite3.IntegrityError) si el empleado no existe.
    """
    with closing(conectar(ruta)) as conexion, conexion:
        # El radicado se calcula y se inserta en la misma transacción.
        conexion.execute("BEGIN IMMEDIATE")
        radicado = solicitud.get("radicado") or _siguiente_radicado(conexion)
        conexion.execute(
            "INSERT INTO solicitudes (radicado, fecha_radicado, id_empleado, ciudad,"
            " fecha_salida, noches, motivo, valor_noche, valor_tiquete, estado)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                radicado,
                solicitud.get("fecha_radicado") or date.today().isoformat(),
                solicitud["id_empleado"],
                solicitud["ciudad"],
                solicitud["fecha_salida"],
                int(solicitud["noches"]),
                solicitud["motivo"],
                int(solicitud["valor_noche"]),
                int(solicitud["valor_tiquete"]),
                solicitud["estado"],
            ),
        )
    return radicado


def listar_solicitudes(id_empleado, ruta=RUTA_BD):
    """Solicitudes de un empleado, de la más antigua a la más reciente."""
    with closing(conectar(ruta)) as conexion:
        filas = conexion.execute(
            "SELECT * FROM solicitudes WHERE id_empleado = ?"
            " ORDER BY CAST(SUBSTR(radicado, ?) AS INTEGER)",
            (id_empleado, len(PREFIJO_RADICADO) + 1),
        ).fetchall()
    return [dict(f) for f in filas]


if __name__ == "__main__":
    for tabla, filas in crear_y_cargar().items():
        print(f"{tabla}: {filas} filas")
