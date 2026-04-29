"""
core/escalation.py
Sistema de escalación a agentes humanos cuando el bot no puede resolver.
"""

import os
import json
import time
import uuid
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path

# Archivo de tickets (en producción usar base de datos)
ESCALATION_FILE = Path(__file__).parent.parent / "data" / "escalation_tickets.json"

# Estados de ticket
STATUS_PENDING = "pending"
STATUS_ASSIGNED = "assigned"
STATUS_RESOLVED = "resolved"
STATUS_CLOSED = "closed"


def _load_tickets() -> list:
    """Carga todos los tickets de escalación."""
    if not ESCALATION_FILE.exists():
        return []
    try:
        with open(ESCALATION_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []


def _save_tickets(tickets: list):
    """Guarda tickets en archivo."""
    ESCALATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(ESCALATION_FILE, 'w', encoding='utf-8') as f:
        json.dump(tickets, f, ensure_ascii=False, indent=2)


def create_ticket(
    session_id: str,
    user_message: str,
    bot_response: str = "",
    reason: str = "low_confidence",
    user_email: str = "",
    user_phone: str = "",
    priority: str = "medium"
) -> dict:
    """
    Crea un nuevo ticket de escalación.
    
    Args:
        session_id: ID de sesión del usuario
        user_message: Último mensaje del usuario
        bot_response: Respuesta que dio el bot (si hubo)
        reason: Razón de escalación (low_confidence, error, user_request, complex_query)
        user_email: Email del usuario (opcional)
        user_phone: Teléfono del usuario (opcional)
        priority: Prioridad (low, medium, high, urgent)
    
    Returns:
        Dict con información del ticket creado
    """
    tickets = _load_tickets()
    
    ticket = {
        "id": str(uuid.uuid4())[:8],
        "session_id": session_id,
        "user_message": user_message,
        "bot_response": bot_response,
        "reason": reason,
        "status": STATUS_PENDING,
        "priority": priority,
        "user_email": user_email,
        "user_phone": user_phone,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "assigned_to": None,
        "agent_notes": "",
        "resolution": "",
        "conversation_history": []
    }
    
    tickets.append(ticket)
    _save_tickets(tickets)
    
    # Notificar (aquí podrías integrar email, Slack, etc.)
    _notify_new_ticket(ticket)
    
    return ticket


def _notify_new_ticket(ticket: dict):
    """Notifica nuevo ticket (placeholder para integración real)."""
    print(f"\n🔔 NUEVO TICKET DE ESCALACIÓN #{ticket['id']}")
    print(f"   Razón: {ticket['reason']}")
    print(f"   Prioridad: {ticket['priority']}")
    print(f"   Mensaje: {ticket['user_message'][:80]}...")
    print(f"   Esperando asignación...\n")
    # Aquí podrías enviar email, notificación Slack, etc.


def get_pending_tickets() -> list:
    """Retorna tickets pendientes ordenados por prioridad."""
    tickets = _load_tickets()
    pending = [t for t in tickets if t['status'] == STATUS_PENDING]
    
    # Ordenar por prioridad y fecha
    priority_order = {'urgent': 0, 'high': 1, 'medium': 2, 'low': 3}
    pending.sort(key=lambda x: (priority_order.get(x['priority'], 2), x['created_at']))
    
    return pending


def assign_ticket(ticket_id: str, agent_name: str) -> Optional[dict]:
    """Asigna ticket a un agente."""
    tickets = _load_tickets()
    
    for ticket in tickets:
        if ticket['id'] == ticket_id:
            ticket['status'] = STATUS_ASSIGNED
            ticket['assigned_to'] = agent_name
            ticket['updated_at'] = datetime.now().isoformat()
            _save_tickets(tickets)
            return ticket
    
    return None


def resolve_ticket(ticket_id: str, resolution: str, agent_notes: str = "") -> Optional[dict]:
    """Marca ticket como resuelto."""
    tickets = _load_tickets()
    
    for ticket in tickets:
        if ticket['id'] == ticket_id:
            ticket['status'] = STATUS_RESOLVED
            ticket['resolution'] = resolution
            ticket['agent_notes'] = agent_notes
            ticket['updated_at'] = datetime.now().isoformat()
            _save_tickets(tickets)
            return ticket
    
    return None


def should_escalate(
    confidence_score: float = 0.0,
    response_text: str = "",
    error_occurred: bool = False,
    user_explicit_request: bool = False
) -> tuple[bool, str]:
    """
    Determina si se debe escalar a humano basado en varios factores.
    
    Returns:
        (should_escalate, reason)
    """
    if user_explicit_request:
        return True, "user_request"
    
    if error_occurred:
        return True, "error"
    
    if confidence_score < 0.3:
        return True, "low_confidence"
    
    # Detectar respuestas de "no sé" o evasivas
    uncertainty_phrases = [
        "no tengo esa información",
        "no lo sé",
        "no estoy seguro",
        "no puedo ayudar",
        "no entiendo",
        "consulta con un",
        "llama al",
    ]
    
    text_lower = response_text.lower()
    if any(phrase in text_lower for phrase in uncertainty_phrases):
        return True, "uncertain_response"
    
    return False, ""


def get_ticket_stats() -> dict:
    """Estadísticas de tickets."""
    tickets = _load_tickets()
    
    total = len(tickets)
    pending = len([t for t in tickets if t['status'] == STATUS_PENDING])
    assigned = len([t for t in tickets if t['status'] == STATUS_ASSIGNED])
    resolved = len([t for t in tickets if t['status'] == STATUS_RESOLVED])
    
    # Tiempo promedio de resolución
    resolved_tickets = [t for t in tickets if t['status'] == STATUS_RESOLVED]
    avg_time = 0
    if resolved_tickets:
        total_time = 0
        for t in resolved_tickets:
            created = datetime.fromisoformat(t['created_at'])
            updated = datetime.fromisoformat(t['updated_at'])
            total_time += (updated - created).total_seconds()
        avg_time = total_time / len(resolved_tickets) / 3600  # en horas
    
    return {
        "total": total,
        "pending": pending,
        "assigned": assigned,
        "resolved": resolved,
        "avg_resolution_hours": round(avg_time, 1)
    }
