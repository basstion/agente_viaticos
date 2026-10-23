import csv
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

from dotenv import load_dotenv
from google import genai

from bd import basedatos
from logica import solicitudes as logica

MODELO = "gemini-3.5-flash-lite"
MAX_VUELTAS = 5  # vueltas de herramientas por mensaje del usuario
PALABRAS_SALIDA = ("salir", "exit", "quit")
BASE = Path(__file__).parent
GASTOS = BASE / "conocimiento" / "gastos.csv"
RUTA_BD = basedatos.RUTA_BD
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


def registrar_solicitud(nombre, ciudad, fecha_salida, noches, motivo, valor_noche, valor_tiquete):
    """Registra la solicitud con la lógica de negocio; el estado lo decide logica/, no el modelo.

    Si la lógica lanza un error (por ejemplo, empleado inexistente), se propaga a ejecutar(),
    que devuelve el mensaje al modelo sin romper el programa.
    """
    resultado = logica.registrar_solicitud(
        nombre, ciudad, fecha_salida, int(noches), motivo, int(valor_noche), int(valor_tiquete),
        ruta=RUTA_BD,
    )
    return {
        "radicado": resultado["radicado"],
        "estado": resultado["estado"],
        "motivo_estado": resultado["motivo_estado"],
    }


def consultar_mis_solicitudes(nombre):
    """Devuelve las solicitudes ya registradas del empleado, de la más antigua a la más reciente."""
    return {"solicitudes": logica.consultar_solicitudes(nombre, ruta=RUTA_BD)}


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
    "consultar_mis_solicitudes": consultar_mis_solicitudes,
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
            "Registra una solicitud de viaje de trabajo y devuelve su radicado, su estado y el "
            "motivo de ese estado, que decide el sistema. Úsala solo cuando el empleado pida "
            "registrar o radicar una solicitud y ya tengas los siete datos; no la uses para consultas."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "nombre": {"type": "string", "description": "Nombre completo del empleado que viaja."},
                "ciudad": {"type": "string", "description": "Ciudad de destino del viaje."},
                "fecha_salida": {"type": "string", "description": "Fecha de salida en formato AAAA-MM-DD."},
                "noches": {
                    "type": "integer",
                    "description": "Número de noches del viaje. Un viaje de ida y vuelta el mismo día tiene 0.",
                },
                "motivo": {"type": "string", "description": "Motivo del viaje de trabajo."},
                "valor_noche": {
                    "type": "integer",
                    "description": "Valor por noche del hotel cotizado, en pesos COP. Es 0 si no hay noches.",
                },
                "valor_tiquete": {"type": "integer", "description": "Valor del tiquete, en pesos COP."},
            },
            "required": [
                "nombre", "ciudad", "fecha_salida", "noches", "motivo", "valor_noche", "valor_tiquete",
            ],
        },
    },
    {
        "type": "function",
        "name": "consultar_mis_solicitudes",
        "description": (
            "Devuelve las solicitudes de viaje ya registradas de un empleado (radicado, fecha, ciudad, "
            "noches, valores y estado). Úsala cuando pregunten por sus solicitudes o por el estado de una."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "nombre": {"type": "string", "description": "Nombre completo del empleado."},
            },
            "required": ["nombre"],
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

basedatos.crear_y_cargar(RUTA_BD)  # crea bd/altiplano.db si falta; si ya tiene datos no los duplica

load_dotenv()  # carga GEMINI_API_KEY desde .env
client = genai.Client()  # toma GEMINI_API_KEY del entorno

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


def responder(mensaje, previa=None):
    """Un mensaje del usuario: atiende las herramientas que pida el modelo y devuelve la interacción final.

    `previa` es el id de la interacción anterior; así el modelo recuerda la conversación.
    """
    interaction = consultar(mensaje, previa)
    for _ in range(MAX_VUELTAS):
        llamadas = [paso for paso in interaction.steps if paso.type == "function_call"]
        if not llamadas:
            break
        interaction = consultar([ejecutar(llamada) for llamada in llamadas], previa=interaction.id)

    if any(paso.type == "function_call" for paso in interaction.steps):
        raise RuntimeError(f"El modelo siguió pidiendo herramientas después de {MAX_VUELTAS} vueltas.")
    return interaction


def principal():
    """Con terminal interactiva conversa hasta que el usuario salga; sin ella responde un mensaje y termina."""
    mensaje = " ".join(sys.argv[1:]).strip() or None
    interactivo = sys.stdin.isatty()
    if mensaje is None and not interactivo:
        sys.exit('Uso: python agente.py ["tu pregunta"]')

    if not interactivo:  # modo de un solo mensaje, como antes
        try:
            print(responder(mensaje).output_text)
        except RuntimeError as error:
            sys.exit(str(error))
        return

    print(f"Asistente de viáticos. Escribe tu mensaje; para terminar escribe {', '.join(PALABRAS_SALIDA)} o pulsa Ctrl+C.")
    previa = None
    while True:
        if mensaje is None:
            try:
                escrito = input("\nTú: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not escrito:
                continue
            if escrito.casefold() in PALABRAS_SALIDA:
                break
            mensaje = escrito
        try:
            interaction = responder(mensaje, previa)
        except Exception as error:  # un fallo en un turno no debe cerrar la conversación
            # `previa` no cambia: el turno fallido no queda en el historial del modelo.
            print(f"\n[error] {type(error).__name__}: {error}\nPuedes intentarlo de nuevo.")
        else:
            previa = interaction.id
            print(f"\nAgente: {interaction.output_text}")
        mensaje = None


if __name__ == "__main__":
    principal()
