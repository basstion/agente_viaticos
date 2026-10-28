import pytest

from externos import notificaciones


class AvisoFalso:
    """Reemplaza a notificaciones.enviar_aviso: guarda los textos y no manda nada."""

    def __init__(self):
        self.enviados = []
        self.resultado = True  # lo que "devuelve" el aviso; False simula un fallo

    def __call__(self, texto):
        self.enviados.append(texto)
        return self.resultado


@pytest.fixture(autouse=True)
def aviso_falso(monkeypatch):
    """Todas las pruebas usan un aviso falso: nunca se manda un mensaje de verdad."""
    falso = AvisoFalso()
    monkeypatch.setattr(notificaciones, "enviar_aviso", falso)
    return falso
