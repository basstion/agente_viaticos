import csv
import json
import sys
import unicodedata
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from google import genai

MODELO = "gemini-3.5-flash-lite"
MAX_VUELTAS = 5
BASE = Path(__file__).parent
GASTOS = BASE / "conocimiento" / "gastos.csv"
SOLICITUDES = BASE / "solicitudes.csv"
ESTADO_SOLICITUD = "Pendiente de aprobación del jefe inmediato"
DOCUMENTOS = "\n\n".join(
    f'<documento nombre="{archivo.name}">\n{archivo.read_text(encoding="utf-8")}\n</documento>'
    for archivo in sorted((BASE / "conocimiento").iterdir())
    if archivo.is_file() and archivo.suffix == ".md"
)
INSTRUCCIONES = (BASE / "prompts" / "sistema.md").read_text(encoding="utf-8") + "\n\n" + DOCUMENTOS


def _normalizar(texto):
    """Minúsculas y sin tildes, para comparar sin distinguir mayúsculas ni acentos."""
    sin_tildes = unicodedata.normalize("NFD", texto)
    return "".join(c for c in sin_tildes if unicodedata.category(c) != "Mn").casefold().strip()


def sumar_gastos(area=None, estado=None):
    """Cuenta y suma los gastos de gastos.csv, filtrando opcionalmente por área y/o estado."""
    area_buscada = _normalizar(area) if area else None
    estado_buscado = _normalizar(estado) if estado else None
    filas = 0
    total = 0
    with open(GASTOS, encoding="utf-8", newline="") as archivo:
        for fila in csv.DictReader(archivo):
            if area_buscada and _normalizar(fila["area"]) != area_buscada:
                continue
            if estado_buscado and _normalizar(fila["estado"]) != estado_buscado:
                continue
            filas += 1
            total += int(fila["valor_cop"])
    return {"filas": filas, "total_cop": total}


def registrar_solicitud(empleado, ciudad, fecha_salida, noches, motivo):
    """Agrega una solicitud de viaje a solicitudes.csv y devuelve su radicado consecutivo."""
    existe = SOLICITUDES.exists() and SOLICITUDES.stat().st_size > 0
    consecutivo = 1
    if existe:
        with open(SOLICITUDES, encoding="utf-8", newline="") as archivo:
            consecutivo = sum(1 for _ in csv.DictReader(archivo)) + 1
    radicado = f"S-{consecutivo:03d}"
    with open(SOLICITUDES, "a", encoding="utf-8", newline="") as archivo:
        escritor = csv.writer(archivo)
        if not existe:
            escritor.writerow(
                ["radicado", "fecha_registro", "empleado", "ciudad", "fecha_salida", "noches", "motivo", "estado"]
            )
        escritor.writerow(
            [radicado, date.today().isoformat(), empleado, ciudad, fecha_salida, noches, motivo, ESTADO_SOLICITUD]
        )
    return {"radicado": radicado}


FUNCIONES = {"sumar_gastos": sumar_gastos, "registrar_solicitud": registrar_solicitud}

HERRAMIENTAS = [
    {
        "type": "function",
        "name": "sumar_gastos",
        "description": (
            "Cuenta y suma los gastos registrados en el archivo de gastos (valores en COP). "
            "Úsala siempre que pregunten cuántos gastos hay o cuánto suman, en total o filtrados "
            "por área y/o por estado. No sirve para consultar reglas ni topes de la política."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "area": {
                    "type": "string",
                    "description": (
                        "Área a filtrar: Ventas, Operaciones, Tecnología, Mercadeo o Gestión Humana. "
                        "Omítelo para incluir todas las áreas."
                    ),
                },
                "estado": {
                    "type": "string",
                    "description": (
                        "Estado a filtrar: Aprobado, Pendiente o Rechazado. "
                        "Omítelo para incluir todos los estados."
                    ),
                },
            },
        },
    },
    {
        "type": "function",
        "name": "registrar_solicitud",
        "description": (
            "Registra una solicitud de viaje de trabajo y devuelve su número de radicado. "
            "Úsala solo cuando el empleado pida registrar o radicar una solicitud y ya tengas "
            "los cinco datos; no la uses para consultas."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "empleado": {"type": "string", "description": "Nombre completo del empleado que viaja."},
                "ciudad": {"type": "string", "description": "Ciudad de destino del viaje."},
                "fecha_salida": {"type": "string", "description": "Fecha de salida en formato AAAA-MM-DD."},
                "noches": {"type": "integer", "description": "Número de noches del viaje."},
                "motivo": {"type": "string", "description": "Motivo del viaje de trabajo."},
            },
            "required": ["empleado", "ciudad", "fecha_salida", "noches", "motivo"],
        },
    },
]

load_dotenv()  # carga GEMINI_API_KEY desde .env
client = genai.Client()  # toma GEMINI_API_KEY del entorno

if len(sys.argv) < 2:
    sys.exit('Uso: python agente.py "tu pregunta"')


def consultar(entrada, previa=None):
    """Una llamada al modelo; la instrucción y las herramientas se envían en cada vuelta."""
    argumentos = {"previous_interaction_id": previa} if previa else {}
    return client.interactions.create(
        model=MODELO,
        input=entrada,
        system_instruction=INSTRUCCIONES,
        tools=HERRAMIENTAS,
        **argumentos,
    )


def ejecutar(llamada):
    """Ejecuta la herramienta pedida por el modelo, imprime la traza y arma el function_result."""
    try:
        resultado = FUNCIONES[llamada.name](**llamada.arguments)
        con_error = False
    except Exception as error:  # el modelo recibe el error y puede corregir los argumentos
        resultado = {"error": f"{type(error).__name__}: {error}"}
        con_error = True
    print(f"[herramienta] {llamada.name}({json.dumps(llamada.arguments, ensure_ascii=False)}) -> "
          f"{json.dumps(resultado, ensure_ascii=False)}")
    paso = {
        "type": "function_result",
        "name": llamada.name,
        "call_id": llamada.id,
        "result": [{"type": "text", "text": json.dumps(resultado, ensure_ascii=False)}],
    }
    if con_error:
        paso["is_error"] = True
    return paso


interaction = consultar(" ".join(sys.argv[1:]))
for _ in range(MAX_VUELTAS):
    llamadas = [paso for paso in interaction.steps if paso.type == "function_call"]
    if not llamadas:
        break
    interaction = consultar([ejecutar(llamada) for llamada in llamadas], previa=interaction.id)

if any(paso.type == "function_call" for paso in interaction.steps):
    sys.exit(f"El modelo siguió pidiendo herramientas después de {MAX_VUELTAS} vueltas.")
print(interaction.output_text)
