import pytest

from bd import basedatos
from logica import solicitudes
from logica.solicitudes import (
    APROBADA,
    LIMITE_TIQUETE,
    PENDIENTE_DIRECTOR,
    PENDIENTE_JEFE,
    POR_REVISAR,
    RECHAZADA,
    EmpleadoNoEncontrado,
    consultar_solicitudes,
    registrar_solicitud,
    validar_solicitud,
)

EMPLEADO = "Natalia Guzmán"

# (nombre, ciudad, noches, valor_noche, valor_tiquete, estado esperado)
# Topes de ciudades.csv: Bogotá/Medellín/Cartagena 320000; Barranquilla/Bucaramanga 240000.
CASOS = [
    # Hotel igual al tope cumple (no es "mayor que"); tiquete bajo el límite.
    ("C1", "Medellín", 2, 320000, 1360000, APROBADA),
    # Regla 2: 262000 > 240000. Se rechaza aunque el tiquete sea barato.
    ("C2", "Bucaramanga", 3, 262000, 390000, RECHAZADA),
    # Tiquete igual a $1.500.000 cumple (no es "más de"); hotel bajo el tope.
    ("C3", "Cartagena", 1, 300000, 1500000, APROBADA),
    # Hotel bien; regla 3: 1620000 > 1500000.
    ("C4", "Bogotá", 2, 250000, 1620000, PENDIENTE_DIRECTOR),
    # Regla 1: Miami no está en ciudades.csv. Decide antes que el tiquete de 2100000.
    ("C5", "Miami", 3, 280000, 2100000, POR_REVISAR),
    # Hotel igual al tope y tiquete bajo el límite, pero el costo (2.060.000) supera
    # 2.000.000 y sale el 2026-11-03: desde el 1 de nov. requiere al jefe inmediato.
    ("C6", "Barranquilla", 4, 240000, 1100000, PENDIENTE_JEFE),
]


@pytest.fixture
def bd(tmp_path):
    """Base temporal con los CSV cargados; no toca bd/altiplano.db."""
    ruta = tmp_path / "prueba.db"
    basedatos.crear_y_cargar(ruta)
    return ruta


@pytest.mark.parametrize(
    "caso, ciudad, noches, valor_noche, valor_tiquete, esperado",
    CASOS,
    ids=[c[0] for c in CASOS],
)
def test_registrar_solicitud_estado_segun_reglas(
    bd, caso, ciudad, noches, valor_noche, valor_tiquete, esperado
):
    resultado = registrar_solicitud(
        EMPLEADO, ciudad, "2026-11-03", noches, "Prueba",
        valor_noche, valor_tiquete, ruta=bd,
    )
    assert resultado["estado"] == esperado
    guardada = consultar_solicitudes(EMPLEADO, ruta=bd)[-1]
    assert guardada["estado"] == esperado
    assert guardada["radicado"] == resultado["radicado"]


def test_validar_no_necesita_base_de_datos():
    assert validar_solicitud(240000, 2, 240000, 1500000)[0] == APROBADA
    assert validar_solicitud(240000, 2, 240001, 0)[0] == RECHAZADA
    assert validar_solicitud(240000, 2, 240000, 1500001)[0] == PENDIENTE_DIRECTOR


def test_validar_ciudad_sin_tope_gana_a_las_demas_reglas():
    estado, motivo = validar_solicitud(None, 3, 999999, 9999999)
    assert estado == POR_REVISAR
    assert motivo


def test_validar_rechazo_gana_al_tiquete_alto():
    # Incumple la regla 2 y la 3: decide la primera.
    assert validar_solicitud(240000, 2, 300000, 2000000)[0] == RECHAZADA


def test_validar_viaje_de_un_dia_sin_noches():
    assert validar_solicitud(320000, 0, 0, 380000)[0] == APROBADA


def test_limite_del_tiquete_es_la_constante():
    assert LIMITE_TIQUETE == 1_500_000
    assert solicitudes.validar_solicitud(1, 0, 0, LIMITE_TIQUETE)[0] == APROBADA


def test_registrar_asigna_radicados_consecutivos(bd):
    primero = registrar_solicitud(EMPLEADO, "Bogotá", "2026-11-03", 1, "A", 300000, 0, ruta=bd)
    segundo = registrar_solicitud(EMPLEADO, "Bogotá", "2026-11-10", 1, "B", 300000, 0, ruta=bd)
    assert (primero["radicado"], segundo["radicado"]) == ("S-141", "S-142")


def test_registrar_ignora_mayusculas_y_tildes(bd):
    resultado = registrar_solicitud(
        "natalia guzman", "medellin", "2026-11-03", 1, "Prueba", 290000, 500000, ruta=bd
    )
    assert resultado["estado"] == APROBADA
    guardada = consultar_solicitudes("NATALIA GUZMÁN", ruta=bd)[-1]
    assert guardada["ciudad"] == "Medellín"


def test_registrar_devuelve_el_costo_estimado(bd):
    resultado = registrar_solicitud(
        EMPLEADO, "Cartagena", "2026-11-03", 2, "Feria comercial", 310000, 690000, ruta=bd
    )
    assert resultado["costo_estimado"] == 690000 + 2 * 310000


def test_empleado_inexistente_lanza_error_y_no_guarda(bd):
    antes = basedatos.siguiente_radicado(bd)
    with pytest.raises(EmpleadoNoEncontrado, match="Pedro Pérez"):
        registrar_solicitud("Pedro Pérez", "Bogotá", "2026-11-03", 1, "x", 300000, 0, ruta=bd)
    assert basedatos.siguiente_radicado(bd) == antes


def test_valores_negativos_no_se_registran(bd):
    with pytest.raises(ValueError):
        registrar_solicitud(EMPLEADO, "Bogotá", "2026-11-03", -1, "x", 300000, 0, ruta=bd)


def test_consultar_solicitudes_de_un_empleado(bd):
    historicas = consultar_solicitudes("Natalia Guzmán", ruta=bd)
    assert [s["radicado"] for s in historicas] == ["S-102", "S-117", "S-133"]
    assert all(s["id_empleado"] == "E-05" for s in historicas)


def test_consultar_empleado_inexistente_lanza_error(bd):
    with pytest.raises(EmpleadoNoEncontrado):
        consultar_solicitudes("Pedro Pérez", ruta=bd)


def test_aviso_se_envia_con_los_datos_de_la_solicitud(bd, aviso_falso):
    # Tiquete de 1.620.000 > 1.500.000: queda pendiente de director.
    resultado = registrar_solicitud(
        EMPLEADO, "bogota", "2026-11-03", 2, "Feria comercial", 250000, 1620000, ruta=bd
    )
    assert resultado["estado"] == PENDIENTE_DIRECTOR
    assert resultado["avisado"] is True
    assert len(aviso_falso.enviados) == 1
    texto = aviso_falso.enviados[0]
    for dato in (
        resultado["radicado"], EMPLEADO, "Bogotá", PENDIENTE_DIRECTOR,
        "$2.120.000", "Feria comercial", resultado["motivo_estado"],
    ):
        assert dato in texto


@pytest.mark.parametrize(
    "ciudad, noches, valor_noche, valor_tiquete, fecha, estado",
    [
        ("Bogotá", 2, 250000, 1620000, "2026-11-03", PENDIENTE_DIRECTOR),
        ("Barranquilla", 4, 240000, 1100000, "2026-11-03", PENDIENTE_JEFE),
        ("Miami", 3, 280000, 2100000, "2026-11-03", POR_REVISAR),
    ],
)
def test_aviso_en_los_tres_estados_pendientes(
    bd, aviso_falso, ciudad, noches, valor_noche, valor_tiquete, fecha, estado
):
    resultado = registrar_solicitud(
        EMPLEADO, ciudad, fecha, noches, "Prueba", valor_noche, valor_tiquete, ruta=bd
    )
    assert resultado["estado"] == estado
    assert resultado["avisado"] is True
    assert len(aviso_falso.enviados) == 1


@pytest.mark.parametrize(
    "ciudad, noches, valor_noche, valor_tiquete, estado",
    [
        ("Medellín", 2, 320000, 1360000, APROBADA),
        ("Bucaramanga", 3, 262000, 390000, RECHAZADA),
    ],
)
def test_sin_aviso_si_el_estado_no_lo_requiere(
    bd, aviso_falso, ciudad, noches, valor_noche, valor_tiquete, estado
):
    resultado = registrar_solicitud(
        EMPLEADO, ciudad, "2026-11-03", noches, "Prueba", valor_noche, valor_tiquete, ruta=bd
    )
    assert resultado["estado"] == estado
    assert resultado["avisado"] is None
    assert aviso_falso.enviados == []


def test_si_el_aviso_falla_la_solicitud_queda_guardada(bd, aviso_falso):
    aviso_falso.resultado = False
    resultado = registrar_solicitud(
        EMPLEADO, "Bogotá", "2026-11-03", 2, "Prueba", 250000, 1620000, ruta=bd
    )
    assert resultado["avisado"] is False
    guardada = consultar_solicitudes(EMPLEADO, ruta=bd)[-1]
    assert guardada["radicado"] == resultado["radicado"]
    assert guardada["estado"] == PENDIENTE_DIRECTOR


# Regla nueva: desde 2026-11-01, costo estimado > 2.000.000 requiere al jefe inmediato.
# (nombre, tope, noches, valor_noche, valor_tiquete, fecha_salida, estado esperado)
CASOS_JEFE = [
    ("2.000.002 el 1 de nov", 320000, 2, 250001, 1500000, "2026-11-01", PENDIENTE_JEFE),
    ("2.000.000 exactos no pasa", 320000, 2, 250000, 1500000, "2026-11-01", APROBADA),
    ("2.060.000 antes de la fecha", 240000, 4, 240000, 1100000, "2026-10-31", APROBADA),
    ("sin fecha no aplica", 240000, 4, 240000, 1100000, None, APROBADA),
    ("con tiquete alto sigue el director", 320000, 2, 250000, 1620000, "2026-11-03", PENDIENTE_DIRECTOR),
    ("hotel sobre el tope sigue rechazada", 240000, 4, 300000, 1100000, "2026-11-03", RECHAZADA),
    ("ciudad sin tope sigue por revisar", None, 3, 280000, 1100000, "2026-11-03", POR_REVISAR),
]


@pytest.mark.parametrize(
    "tope, noches, valor_noche, valor_tiquete, fecha, esperado",
    [c[1:] for c in CASOS_JEFE],
    ids=[c[0] for c in CASOS_JEFE],
)
def test_regla_jefe_inmediato(tope, noches, valor_noche, valor_tiquete, fecha, esperado):
    estado, motivo = validar_solicitud(tope, noches, valor_noche, valor_tiquete, fecha)
    assert estado == esperado
    assert motivo
