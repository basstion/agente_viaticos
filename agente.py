import csv
import json
import re
import subprocess
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
SKILLS_DIR = BASE / ".claude" / "skills"
TIEMPO_MAXIMO_SCRIPT = 60  # segundos


def _leer_encabezado(texto):
    """Devuelve las claves de una línea del encabezado --- ... --- de un SKILL.md."""
    coincidencia = re.match(r"---\n(.*?)\n---(?:\n|$)", texto, re.DOTALL)
    datos = {}
    for linea in coincidencia.group(1).splitlines() if coincidencia else []:
        clave, separador, valor = linea.partition(":")
        valor = valor.strip()
        if valor.startswith('"'):
            try:
                valor = json.loads(valor)
            except ValueError:
                valor = valor.strip('"')
        else:
            valor = valor.strip("'")
        if separador:
            datos[clave.strip()] = valor
    return datos


def _cargar_skills():
    """Descubre las skills de .claude/skills/*/SKILL.md: {nombre: (carpeta, descripción)}."""
    skills = {}
    for archivo in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        datos = _leer_encabezado(archivo.read_text(encoding="utf-8"))
        if datos.get("name") and datos.get("description"):
            skills[datos["name"]] = (archivo.parent, datos["description"])
    return skills


SKILLS = _cargar_skills()


def _bloque_skills():
    """Lista de skills para el final de las instrucciones; vacío si no hay ninguna."""
    if not SKILLS:
        return ""
    lista = "\n".join(f"- {nombre}: {descripcion}" for nombre, (_, descripcion) in SKILLS.items())
    return (
        "\n\n<skills>\n"
        "Tienes estas skills: paquetes de instrucciones y scripts para tareas específicas.\n"
        f"{lista}\n\n"
        "Cómo usarlas:\n"
        "- Antes de usar una skill, cárgala con cargar_skill(nombre) y sigue sus instrucciones.\n"
        "- Cuando uses una skill, el formato de la skill reemplaza al de <formato>.\n"
        "- Para ejecutar un script de una skill usa ejecutar_script(skill, script, argumento): "
        "script es solo el nombre del archivo (por ejemplo validar.py) y argumento es la ruta del "
        "archivo que el script debe revisar. Lo que el script imprime es una fuente válida para "
        "responder; no cambies sus cifras.\n"
        "- Los veredictos de una skill son una revisión del cumplimiento de la política; no "
        "reemplazan la aprobación del jefe inmediato (regla 5).\n"
        "</skills>"
    )


INSTRUCCIONES = (
    (BASE / "prompts" / "sistema.md").read_text(encoding="utf-8") + "\n\n" + DOCUMENTOS + _bloque_skills()
)


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


def cargar_skill(nombre):
    """Devuelve el contenido del SKILL.md de la skill indicada."""
    if nombre not in SKILLS:
        raise ValueError(f"No existe la skill '{nombre}'. Skills disponibles: {', '.join(SKILLS) or 'ninguna'}.")
    print(f"[skill] cargando {nombre} ...")
    return (SKILLS[nombre][0] / "SKILL.md").read_text(encoding="utf-8")


def ejecutar_script(skill, script, argumento=None):
    """Ejecuta con Python un script de la carpeta scripts/ de una skill y devuelve lo que imprime."""
    if skill not in SKILLS:
        raise ValueError(f"No existe la skill '{skill}'. Skills disponibles: {', '.join(SKILLS) or 'ninguna'}.")
    carpeta_scripts = (SKILLS[skill][0] / "scripts").resolve()
    ruta = (carpeta_scripts / script).resolve()
    # Solo archivos .py que estén directamente en scripts/: sin rutas absolutas, "..", subcarpetas
    # ni enlaces que apunten fuera.
    if ruta.parent != carpeta_scripts or ruta.suffix != ".py" or not ruta.is_file():
        raise PermissionError(
            f"Me niego a ejecutar '{script}': solo ejecuto scripts .py ubicados directamente en la "
            f"carpeta scripts/ de la skill '{skill}'."
        )
    comando = [sys.executable, str(ruta)]
    if argumento:
        archivo = (BASE / argumento).resolve()
        if not archivo.is_relative_to(BASE.resolve()) or not archivo.is_file():
            raise PermissionError(f"Me niego a usar '{argumento}': debe ser un archivo existente dentro del proyecto.")
        comando.append(str(archivo))
    print(f"[script] ejecutando {skill}/{ruta.name} {argumento or ''}".rstrip() + " ...")
    proceso = subprocess.run(
        comando, cwd=BASE, capture_output=True, text=True, encoding="utf-8", timeout=TIEMPO_MAXIMO_SCRIPT
    )
    if proceso.returncode != 0:
        raise RuntimeError(f"El script terminó con código {proceso.returncode}: {proceso.stderr.strip()}")
    if proceso.stderr.strip():
        return f"{proceso.stdout}\n[advertencias del script]\n{proceso.stderr.strip()}"
    return proceso.stdout


FUNCIONES = {
    "sumar_gastos": sumar_gastos,
    "registrar_solicitud": registrar_solicitud,
    "cargar_skill": cargar_skill,
    "ejecutar_script": ejecutar_script,
}
# Herramientas que imprimen su propia traza ([skill] / [script]) cuando funcionan.
CON_TRAZA_PROPIA = {"cargar_skill", "ejecutar_script"}

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
    {
        "type": "function",
        "name": "cargar_skill",
        "description": (
            "Devuelve las instrucciones completas (SKILL.md) de una skill de la lista <skills>. "
            "Llámala antes de usar la skill y sigue lo que dice."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "nombre": {"type": "string", "description": "Nombre de la skill, tal como aparece en <skills>."},
            },
            "required": ["nombre"],
        },
    },
    {
        "type": "function",
        "name": "ejecutar_script",
        "description": (
            "Ejecuta con Python un script de la carpeta scripts/ de una skill y devuelve lo que imprime. "
            "Úsala solo para los scripts que las instrucciones de la skill indiquen, después de cargarla."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "skill": {"type": "string", "description": "Nombre de la skill, tal como aparece en <skills>."},
                "script": {
                    "type": "string",
                    "description": "Nombre del archivo del script, sin carpetas (por ejemplo validar.py).",
                },
                "argumento": {
                    "type": "string",
                    "description": "Ruta, relativa al proyecto, del archivo que el script debe revisar.",
                },
            },
            "required": ["skill", "script"],
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
    if con_error or llamada.name not in CON_TRAZA_PROPIA:
        print(f"[herramienta] {llamada.name}({json.dumps(llamada.arguments, ensure_ascii=False)}) -> "
              f"{json.dumps(resultado, ensure_ascii=False)}")
    # El texto de una skill o el informe de un script se envía tal cual, no como JSON escapado.
    texto = resultado if isinstance(resultado, str) else json.dumps(resultado, ensure_ascii=False)
    paso = {
        "type": "function_result",
        "name": llamada.name,
        "call_id": llamada.id,
        "result": [{"type": "text", "text": texto}],
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
