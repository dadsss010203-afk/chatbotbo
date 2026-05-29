"""
services/tracking.py
Servicio de rastreo de envios postales via API externa.
"""

from __future__ import annotations

import os
import requests
from core import contacto, capabilities


TRACKING_API_URL = os.environ.get(
    "TRACKING_API_URL",
    contacto.tracking_api_url(),
)
TRACKING_API_TIMEOUT = int(os.environ.get("TRACKING_API_TIMEOUT", "20"))
TRACKING_API_VERIFY_SSL = os.environ.get("TRACKING_API_VERIFY_SSL", "false").strip().lower() in ("1", "true", "yes")


def _consultar_tracking_api(codigo: str) -> dict:
    try:
        response = requests.get(
            TRACKING_API_URL,
            params={"codigo": codigo},
            timeout=TRACKING_API_TIMEOUT,
            verify=TRACKING_API_VERIFY_SSL,
        )
        if response.status_code == 404:
            return {"existe_paquete": False, "resultado": [], "_not_found": True}
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("La API de rastreo no devolvio un JSON valido")
        return payload
    except requests.exceptions.Timeout:
        raise ValueError("El servicio de rastreo tardo demasiado. Intenta nuevamente en unos minutos.")
    except requests.exceptions.ConnectionError:
        raise ValueError("No se pudo conectar al servicio de rastreo. Intenta nuevamente en unos minutos.")
    except requests.RequestException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status == 404:
            return {"existe_paquete": False, "resultado": [], "_not_found": True}
        raise ValueError(f"El servicio de rastreo no esta disponible en este momento. Intenta mas tarde o llama al {contacto.telefono()}.") from exc
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("No se pudo interpretar la respuesta del servicio de rastreo.") from exc


def _format_tracking_response(codigo: str, payload: dict) -> tuple[str, dict]:
    existe_paquete = bool(payload.get("existe_paquete"))
    not_found = bool(payload.get("_not_found"))
    resultados = payload.get("resultado") if isinstance(payload.get("resultado"), list) else []
    paquete = resultados[0] if resultados else {}
    eventos = paquete.get("eventos") if isinstance(paquete.get("eventos"), list) else []
    total_eventos = int(paquete.get("total_eventos") or len(eventos) or 0)
    ultimo_evento = eventos[-1] if eventos else {}

    if not existe_paquete or not eventos:
        if not_found:
            msg = (
                f"El codigo {codigo} no fue encontrado en el sistema.\n"
                f"Verifica que el codigo este escrito correctamente.\n"
                f"Si el envio es reciente, puede que aun no este registrado — intenta nuevamente en unas horas.\n"
                f"Para mas ayuda llama al {contacto.telefono()} o visita {contacto.web()}."
            )
        else:
            msg = (
                f"No se encontraron eventos para el codigo {codigo}.\n"
                f"Verifica que el codigo este bien escrito o intenta nuevamente en unos minutos."
            )
        return (msg, {"ok": False, "pending": False, "codigo": codigo, "found": False,
                      "total_eventos": total_eventos, "raw": payload})

    lineas = [
        f"Estado del envio {codigo}:",
        f"  Ultimo evento: {ultimo_evento.get('nombre_evento') or 'Sin descripcion'}",
        f"  Fecha: {ultimo_evento.get('created_at') or 'Sin fecha'}",
        f"  Servicio: {ultimo_evento.get('servicio') or 'No especificado'}",
        f"  Total de eventos: {total_eventos}",
    ]
    if ultimo_evento.get("tabla_origen"):
        lineas.append(f"  Origen del registro: {ultimo_evento['tabla_origen']}")
    if ultimo_evento.get("office"):
        lineas.append(f"  Oficina: {ultimo_evento['office']}")
    if ultimo_evento.get("next_office"):
        lineas.append(f"  Siguiente oficina: {ultimo_evento['next_office']}")
    if ultimo_evento.get("ciudad_origen"):
        lineas.append(f"  Ciudad origen: {ultimo_evento['ciudad_origen']}")
    if ultimo_evento.get("ciudad_destino"):
        lineas.append(f"  Ciudad destino: {ultimo_evento['ciudad_destino']}")

    tracking_url = f"{contacto.tracking_url()}/?codigo={codigo}"

    return ("\n".join(lineas), {
        "ok": True, "pending": False, "codigo": codigo, "found": True,
        "total_eventos": total_eventos, "ultimo_evento": ultimo_evento,
        "tracking_url": tracking_url, "raw": payload,
    })


def _tracking_prompt_message(lang: str = "es") -> str:
    if lang == "en":
        return "Send me your complete tracking code, for example: C0028A03441BO"
    return "Enviame tu codigo de rastreo completo, por ejemplo: C0028A03441BO"


def _resolver_tracking_deterministico(pregunta: str) -> dict:
    codigo = capabilities.detectar_codigo_seguimiento(pregunta)
    if not codigo:
        return {
            "response": _tracking_prompt_message(),
            "tracking": {"ok": False, "pending": True, "requires_code": True},
            "quick_replies": [],
        }
    payload = _consultar_tracking_api(codigo)
    respuesta, tracking_data = _format_tracking_response(codigo, payload)
    return {"response": respuesta, "tracking": tracking_data, "quick_replies": []}
