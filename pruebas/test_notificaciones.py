import requests

from externos import notificaciones

# Se importa aquí, antes de que el fixture automático (conftest) reemplace la función del módulo.
enviar_aviso_real = notificaciones.enviar_aviso

TOKEN = "123456:TOKEN-SECRETO-DE-PRUEBA"


class RespuestaFalsa:
    def __init__(self, status_code=200, cuerpo=None):
        self.status_code = status_code
        self.ok = status_code < 400
        self._cuerpo = cuerpo if cuerpo is not None else {}

    def json(self):
        return self._cuerpo


def _configurar(monkeypatch, post):
    monkeypatch.setattr(notificaciones, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("TELEGRAM_TOKEN", TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    monkeypatch.setattr(requests, "post", post)


def test_envia_con_timeout_de_10_segundos(monkeypatch):
    llamadas = []

    def post(url, **kwargs):
        llamadas.append((url, kwargs))
        return RespuestaFalsa()

    _configurar(monkeypatch, post)
    assert enviar_aviso_real("hola") is True
    url, kwargs = llamadas[0]
    assert url == f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    assert kwargs["timeout"] == 10
    assert kwargs["json"] == {"chat_id": "42", "text": "hola"}


def test_telegram_rechaza_devuelve_false_sin_mostrar_el_token(monkeypatch, capsys):
    _configurar(
        monkeypatch,
        lambda url, **kw: RespuestaFalsa(400, {"description": "Bad Request: chat not found"}),
    )
    assert enviar_aviso_real("hola") is False
    salida = capsys.readouterr().out
    assert "chat not found" in salida
    assert TOKEN not in salida and "api.telegram.org" not in salida


def test_error_de_red_devuelve_false_sin_mostrar_el_token(monkeypatch, capsys):
    def post(url, **kwargs):
        raise requests.ConnectionError(f"fallo conectando a {url}")  # el mensaje trae el token

    _configurar(monkeypatch, post)
    assert enviar_aviso_real("hola") is False
    salida = capsys.readouterr().out
    assert "ConnectionError" in salida
    assert TOKEN not in salida and "api.telegram.org" not in salida


def test_timeout_devuelve_false(monkeypatch):
    def post(url, **kwargs):
        raise requests.Timeout()

    _configurar(monkeypatch, post)
    assert enviar_aviso_real("hola") is False


def test_sin_configuracion_devuelve_false_sin_llamar_a_telegram(monkeypatch, capsys):
    def post(url, **kwargs):
        raise AssertionError("no debe llamar a Telegram")

    _configurar(monkeypatch, post)
    monkeypatch.delenv("TELEGRAM_CHAT_ID")
    assert enviar_aviso_real("hola") is False
    assert "TELEGRAM_CHAT_ID" in capsys.readouterr().out
