import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chatbots.general.services.tracking import should_use_tracking_flow
from core import cache


def test_pregunta_general_no_entra_al_flujo_tracking():
    assert should_use_tracking_flow("¿Cuál es la dirección de la sucursal de La Paz?") is False


def test_codigo_tracking_si_entra_al_flujo_tracking():
    assert should_use_tracking_flow("Quiero rastrear mi paquete C0028A03441BO") is True


def test_pregunta_de_rastreo_si_entra_al_flujo_tracking():
    assert should_use_tracking_flow("Quiero consultar el seguimiento de mi envío") is True


def test_cache_no_retorna_respuestas_expiradas():
    key = cache._response_key("pregunta de prueba", "es", "", "", False)
    cache.set_json(key, {"response": "viejo", "expires_at": int(time.time()) - 1}, ttl=1)
    assert cache.get_response(pregunta="pregunta de prueba", lang="es") is None


def test_cache_age_seconds_empieza_en_cero_y_sube():
    payload = {"created_at": "2026-06-22T00:00:00+00:00", "ttl_seconds": 60}
    assert cache._cache_age_seconds(payload) >= 0
