"""Reglas de negocio de las solicitudes de viáticos (kit7/reglas_solicitudes.md).

Este módulo decide el estado de una solicitud; guardar y consultar datos se
delega en bd/basedatos.py.
"""

from datetime import date

from bd import basedatos

# Política de viáticos, sección 3: un tiquete que cuesta más requiere al director.
LIMITE_TIQUETE = 1_500_000

# Política nueva: desde esa fecha, un costo estimado de más de este valor
# requiere al jefe inmediato (si ya requiere al director, sigue con el director).
LIMITE_COSTO_JEFE = 2_000_000
FECHA_INICIO_REGLA_JEFE = date(2026, 11, 1)

APROBADA = "Aprobada"
RECHAZADA = "Rechazada"
PENDIENTE_DIRECTOR = "Pendiente de director"
PENDIENTE_JEFE = "Pendiente de jefe inmediato"
POR_REVISAR = "Por revisar"


class EmpleadoNoEncontrado(ValueError):
    """El nombre no corresponde a ningún empleado de la base."""


def _pesos(valor):
    return "$" + f"{valor:,}".replace(",", ".")


def costo_estimado(noches, valor_noche, valor_tiquete):
    """Costo estimado = valor del tiquete + noches × valor por noche."""
    return valor_tiquete + noches * valor_noche


def _aplica_regla_jefe(fecha_salida):
    if fecha_salida is None:
        return False
    return date.fromisoformat(str(fecha_salida)[:10]) >= FECHA_INICIO_REGLA_JEFE


def validar_solicitud(
    tope_hospedaje, noches, valor_noche, valor_tiquete, fecha_salida=None
):
    """Aplica las reglas en orden y devuelve (estado, motivo).

    La primera regla que se cumple decide el estado. `tope_hospedaje` es None
    cuando la ciudad no está en ciudades.csv. "Más de" es estrictamente mayor:
    un valor igual al límite cumple.

    `fecha_salida` (date o 'AAAA-MM-DD') decide si rige la regla del jefe
    inmediato; sin fecha esa regla no se aplica.
    """
    if tope_hospedaje is None:
        return POR_REVISAR, "La ciudad de destino no está en la lista de ciudades con tope."
    if valor_noche > tope_hospedaje:
        return RECHAZADA, (
            f"El valor por noche ({_pesos(valor_noche)}) supera el tope de "
            f"hospedaje de la ciudad ({_pesos(tope_hospedaje)})."
        )
    if valor_tiquete > LIMITE_TIQUETE:
        return PENDIENTE_DIRECTOR, (
            f"El tiquete ({_pesos(valor_tiquete)}) supera el límite de "
            f"{_pesos(LIMITE_TIQUETE)}."
        )
    costo = costo_estimado(noches, valor_noche, valor_tiquete)
    if costo > LIMITE_COSTO_JEFE and _aplica_regla_jefe(fecha_salida):
        return PENDIENTE_JEFE, (
            f"El costo estimado ({_pesos(costo)}) supera {_pesos(LIMITE_COSTO_JEFE)} "
            "y requiere aprobación del jefe inmediato."
        )
    return APROBADA, "Cumple el tope de hospedaje y los límites de tiquete y costo."


def _buscar_empleado_o_error(nombre, ruta):
    empleado = basedatos.buscar_empleado(nombre, ruta)
    if empleado is None:
        raise EmpleadoNoEncontrado(
            f"No existe ningún empleado llamado '{nombre}'. "
            "No se registró la solicitud."
        )
    return empleado


def registrar_solicitud(
    empleado, ciudad, fecha_salida, noches, motivo, valor_noche, valor_tiquete,
    ruta=basedatos.RUTA_BD,
):
    """Valida y guarda una solicitud nueva. Devuelve un dict con el resultado.

    Lanza EmpleadoNoEncontrado, sin guardar nada, si el empleado no existe.
    """
    if min(noches, valor_noche, valor_tiquete) < 0:
        raise ValueError("Las noches y los valores no pueden ser negativos.")

    datos_empleado = _buscar_empleado_o_error(empleado, ruta)
    datos_ciudad = basedatos.buscar_ciudad(ciudad, ruta)
    tope = datos_ciudad["tope_hospedaje"] if datos_ciudad else None

    estado, motivo_estado = validar_solicitud(
        tope, noches, valor_noche, valor_tiquete, fecha_salida
    )

    # guardar_solicitud toma el siguiente radicado y lo inserta en una sola
    # transacción, así que dos registros simultáneos no repiten número.
    radicado = basedatos.guardar_solicitud(
        {
            "id_empleado": datos_empleado["id_empleado"],
            "ciudad": datos_ciudad["ciudad"] if datos_ciudad else ciudad.strip(),
            "fecha_salida": fecha_salida,
            "noches": noches,
            "motivo": motivo,
            "valor_noche": valor_noche,
            "valor_tiquete": valor_tiquete,
            "estado": estado,
        },
        ruta,
    )
    return {
        "radicado": radicado,
        "estado": estado,
        "motivo_estado": motivo_estado,
        "costo_estimado": costo_estimado(noches, valor_noche, valor_tiquete),
    }


def consultar_solicitudes(nombre, ruta=basedatos.RUTA_BD):
    """Solicitudes de un empleado, de la más antigua a la más reciente."""
    empleado = _buscar_empleado_o_error(nombre, ruta)
    return basedatos.listar_solicitudes(empleado["id_empleado"], ruta)
