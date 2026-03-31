"""
core/capabilities.py
Registro ejecutable de skills y MCPs del bot.
"""

import json
import os
from typing import Callable


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(BASE_DIR, "data")

SKILLS_FILE = os.environ.get("SKILLS_FILE", os.path.join(DATA_DIR, "skills.json"))
MCPS_FILE = os.environ.get("MCPS_FILE", os.path.join(DATA_DIR, "mcps.json"))


DEFAULT_SKILLS = [
    {
        "id": "postal_consultas",
        "nombre": "Consultas postales",
        "descripcion": "Responde sobre envios, tarifas, rastreo, horarios y sucursales.",
        "modo": "rag+llm",
    },
    {
        "id": "multilenguaje",
        "nombre": "Traduccion conversacional",
        "descripcion": "Mantiene la conversacion en varios idiomas y traduce mensajes visibles.",
        "modo": "translation",
    },
    {
        "id": "orquestacion_capacidades",
        "nombre": "Orquestacion de capacidades",
        "descripcion": "Permite listar y ejecutar MCPs internos del bot desde la API o el chat.",
        "modo": "internal",
    },
]


DEFAULT_MCPS = [
    {
        "id": "rag_local",
        "nombre": "RAG local",
        "descripcion": "Inspecciona el estado de la base vectorial y el motor de embeddings.",
        "accion": "inspect_rag",
    },
    {
        "id": "system_status",
        "nombre": "Estado del sistema",
        "descripcion": "Reporta sesiones, modelo, Ollama y estado del actualizador.",
        "accion": "inspect_system",
    },
    {
        "id": "branches_summary",
        "nombre": "Resumen de sucursales",
        "descripcion": "Resume la cantidad de sucursales cargadas y cuantas tienen coordenadas.",
        "accion": "inspect_branches",
    },
]


def _load_catalog(path: str, fallback: list[dict]) -> list[dict]:
    if not os.path.exists(path):
        return fallback
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            return data
    except Exception as exc:
        print(f"   Error leyendo catalogo {path}: {exc}")
    return fallback


def listar_skills() -> list[dict]:
    return _load_catalog(SKILLS_FILE, DEFAULT_SKILLS)


def listar_mcps() -> list[dict]:
    return _load_catalog(MCPS_FILE, DEFAULT_MCPS)


def resumen_rag(chunks: int, embedding_model: str, chroma_path: str) -> dict:
    return {
        "activo": chunks > 0,
        "chunks": chunks,
        "embedding_model": embedding_model,
        "chroma_path": chroma_path,
    }


def get_runtime_capabilities(
    *,
    chunks: int,
    embedding_model: str,
    chroma_path: str,
    ollama_ok: bool,
    modelo: str,
    sesiones_activas: int,
    sucursales: list[dict],
    actualizacion: dict,
) -> dict:
    rag = resumen_rag(chunks=chunks, embedding_model=embedding_model, chroma_path=chroma_path)
    skills = []
    for skill in listar_skills():
        item = dict(skill)
        item["estado"] = "activa"
        skills.append(item)

    mcps = []
    for mcp in listar_mcps():
        item = dict(mcp)
        item["estado"] = "activo"
        item["disponible"] = True
        mcps.append(item)

    return {
        "skills": skills,
        "mcps": mcps,
        "rag": rag,
        "runtime": {
            "ollama": ollama_ok,
            "modelo": modelo,
            "sesiones_activas": sesiones_activas,
            "sucursales": len(sucursales),
            "sucursales_con_coords": sum(1 for s in sucursales if s.get("lat") and s.get("lng")),
            "actualizacion": actualizacion,
        },
    }


def detectar_consulta_especial(pregunta: str) -> str | None:
    texto = (pregunta or "").strip().lower()
    if not texto:
        return None

    if any(token in texto for token in ("mcp", "mcps", "model context protocol")):
        return "mcps"
    if any(token in texto for token in ("skill", "skills", "habilidad", "habilidades")):
        return "skills"
    if any(token in texto for token in ("rag", "chroma", "embeddings", "chunks", "base vectorial")):
        return "rag_local"
    if any(token in texto for token in ("estado del sistema", "status del sistema", "estado bot", "estado del bot")):
        return "system_status"
    if any(token in texto for token in ("sucursales cargadas", "resumen de sucursales", "estado de sucursales")):
        return "branches_summary"
    if any(token in texto for token in ("genera", "generar", "que puedes hacer", "capacidades del bot")):
        return "generar"
    return None


def _render_skills(skills: list[dict]) -> str:
    listado = "\n".join(
        f"- {item.get('nombre', 'Skill')} : {item.get('descripcion', 'Sin descripcion')}"
        for item in skills
    )
    return (
        f"Skills configuradas: {len(skills)}.\n"
        f"{listado}\n"
        "Las skills se aplican dentro del flujo del bot para conversar, traducir y orquestar capacidades."
    )


def _render_mcps(mcps: list[dict]) -> str:
    listado = "\n".join(
        f"- {item.get('nombre', 'MCP')} : {item.get('descripcion', 'Sin descripcion')}"
        for item in mcps
    )
    return (
        f"MCPs configurados: {len(mcps)}.\n"
        f"{listado}\n"
        "Estos MCPs pueden ejecutarse desde la API y tambien desde consultas especiales del chat."
    )


def render_generar(runtime_capabilities: dict) -> str:
    return (
        "Puedo generar respuestas con el modelo local, consultar el RAG institucional y ejecutar MCPs internos.\n"
        f"Skills: {len(runtime_capabilities['skills'])}. MCPs: {len(runtime_capabilities['mcps'])}. "
        f"Chunks RAG: {runtime_capabilities['rag']['chunks']}.\n"
        "Usa Generar, MCPs, Skills o Analizar RAG para inspeccionar cada capacidad."
    )


def execute_mcp(mcp_id: str, runtime_capabilities: dict) -> dict:
    handlers: dict[str, Callable[[dict], dict]] = {
        "rag_local": _mcp_rag_local,
        "system_status": _mcp_system_status,
        "branches_summary": _mcp_branches_summary,
    }
    handler = handlers.get(mcp_id)
    if handler is None:
        raise ValueError(f"MCP no soportado: {mcp_id}")
    return handler(runtime_capabilities)


def execute_special_query(tipo: str, runtime_capabilities: dict) -> dict:
    if tipo == "skills":
        return {
            "kind": "skills",
            "payload": runtime_capabilities["skills"],
            "response": _render_skills(runtime_capabilities["skills"]),
        }
    if tipo == "mcps":
        return {
            "kind": "mcps",
            "payload": runtime_capabilities["mcps"],
            "response": _render_mcps(runtime_capabilities["mcps"]),
        }
    if tipo == "generar":
        return {
            "kind": "summary",
            "payload": {
                "skills": len(runtime_capabilities["skills"]),
                "mcps": len(runtime_capabilities["mcps"]),
                "chunks": runtime_capabilities["rag"]["chunks"],
            },
            "response": render_generar(runtime_capabilities),
        }

    result = execute_mcp(tipo, runtime_capabilities)
    return {
        "kind": "mcp_execution",
        "payload": result,
        "response": result["text"],
    }


def _mcp_rag_local(runtime_capabilities: dict) -> dict:
    rag = runtime_capabilities["rag"]
    runtime = runtime_capabilities["runtime"]
    estado = "activo" if rag["activo"] else "sin indexacion"
    text = (
        f"Estado RAG: {estado}.\n"
        f"Chunks indexados: {rag['chunks']}.\n"
        f"Modelo de embeddings: {rag['embedding_model']}.\n"
        f"Base vectorial: {rag['chroma_path']}.\n"
        f"Modelo generativo: {runtime['modelo']}.\n"
        f"Ollama disponible: {'si' if runtime['ollama'] else 'no'}."
    )
    return {"mcp_id": "rag_local", "ok": True, "data": rag, "text": text}


def _mcp_system_status(runtime_capabilities: dict) -> dict:
    runtime = runtime_capabilities["runtime"]
    act = runtime["actualizacion"]
    text = (
        "Estado del sistema:\n"
        f"Modelo: {runtime['modelo']}.\n"
        f"Ollama: {'disponible' if runtime['ollama'] else 'no disponible'}.\n"
        f"Sesiones activas: {runtime['sesiones_activas']}.\n"
        f"Actualizacion en proceso: {'si' if act['en_proceso'] else 'no'}.\n"
        f"Ultimo resultado: {act['ultimo_resultado']}."
    )
    return {"mcp_id": "system_status", "ok": True, "data": runtime, "text": text}


def _mcp_branches_summary(runtime_capabilities: dict) -> dict:
    runtime = runtime_capabilities["runtime"]
    text = (
        "Resumen de sucursales:\n"
        f"Sucursales cargadas: {runtime['sucursales']}.\n"
        f"Con coordenadas: {runtime['sucursales_con_coords']}.\n"
        f"Sin coordenadas: {runtime['sucursales'] - runtime['sucursales_con_coords']}."
    )
    return {
        "mcp_id": "branches_summary",
        "ok": True,
        "data": {
            "sucursales": runtime["sucursales"],
            "sucursales_con_coords": runtime["sucursales_con_coords"],
        },
        "text": text,
    }
