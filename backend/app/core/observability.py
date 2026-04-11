"""
core/observability.py
Observabilidad básica: logs estructurados + métricas en memoria.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone

from flask import g, request


_logger = logging.getLogger("chatbotbo.observability")
if not _logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

_lock = threading.Lock()
_endpoint_state: dict[str, dict] = defaultdict(
    lambda: {
        "count": 0,
        "errors": 0,
        "status_2xx": 0,
        "status_4xx": 0,
        "status_5xx": 0,
        "latency_total_ms": 0.0,
        "latency_ms_window": deque(maxlen=300),
    }
)
_request_totals = {"count": 0, "errors": 0}
_extraction_metrics = {
    "total": 0,
    "success": 0,
    "failure": 0,
    "chars_total": 0,
    "by_kind": Counter(),
    "by_method": Counter(),
    "failure_reasons": Counter(),
}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def log_event(event: str, **fields) -> None:
    payload = {"ts": _iso_now(), "event": event}
    payload.update(fields)
    _logger.info(_safe_json(payload))


def _status_group(status_code: int) -> str:
    if 200 <= status_code < 300:
        return "status_2xx"
    if 400 <= status_code < 500:
        return "status_4xx"
    if status_code >= 500:
        return "status_5xx"
    return "status_2xx"


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int(round((len(ordered) - 1) * pct))
    return ordered[idx]


def record_http(endpoint: str, method: str, status_code: int, latency_ms: float) -> None:
    key = f"{method} {endpoint}"
    group = _status_group(status_code)
    with _lock:
        _request_totals["count"] += 1
        if status_code >= 500:
            _request_totals["errors"] += 1
        state = _endpoint_state[key]
        state["count"] += 1
        state[group] += 1
        if status_code >= 500:
            state["errors"] += 1
        state["latency_total_ms"] += latency_ms
        state["latency_ms_window"].append(latency_ms)

    log_event(
        "http.request",
        endpoint=endpoint,
        method=method,
        status=status_code,
        latency_ms=round(latency_ms, 2),
    )


def record_extraction(
    *,
    kind: str,
    success: bool,
    method: str | None = None,
    chars: int = 0,
    reason: str | None = None,
) -> None:
    with _lock:
        _extraction_metrics["total"] += 1
        _extraction_metrics["chars_total"] += max(chars, 0)
        _extraction_metrics["by_kind"][kind] += 1
        if method:
            _extraction_metrics["by_method"][method] += 1
        if success:
            _extraction_metrics["success"] += 1
        else:
            _extraction_metrics["failure"] += 1
            if reason:
                _extraction_metrics["failure_reasons"][reason] += 1

    log_event(
        "extraction.result",
        kind=kind,
        success=success,
        method=method or "",
        chars=chars,
        reason=reason or "",
    )


def get_observability_snapshot() -> dict:
    with _lock:
        endpoints = {}
        for key, state in _endpoint_state.items():
            count = state["count"] or 1
            latencies = list(state["latency_ms_window"])
            endpoints[key] = {
                "count": state["count"],
                "errors": state["errors"],
                "status_2xx": state["status_2xx"],
                "status_4xx": state["status_4xx"],
                "status_5xx": state["status_5xx"],
                "latency_avg_ms": round(state["latency_total_ms"] / count, 2),
                "latency_p95_ms": round(_percentile(latencies, 0.95), 2),
            }

        extraction = {
            "total": _extraction_metrics["total"],
            "success": _extraction_metrics["success"],
            "failure": _extraction_metrics["failure"],
            "success_rate": round(
                (
                    _extraction_metrics["success"] / _extraction_metrics["total"]
                    if _extraction_metrics["total"]
                    else 0.0
                )
                * 100,
                2,
            ),
            "chars_total": _extraction_metrics["chars_total"],
            "by_kind": dict(_extraction_metrics["by_kind"]),
            "by_method": dict(_extraction_metrics["by_method"]),
            "failure_reasons": dict(_extraction_metrics["failure_reasons"]),
        }

        totals = dict(_request_totals)

    return {
        "generated_at": _iso_now(),
        "requests": totals,
        "endpoints": endpoints,
        "extraction": extraction,
    }


def init_app(app) -> None:
    @app.before_request
    def _obs_before_request():
        g._obs_start_time = time.perf_counter()

    @app.after_request
    def _obs_after_request(response):
        start = getattr(g, "_obs_start_time", None)
        if start is None:
            return response
        latency_ms = (time.perf_counter() - start) * 1000.0
        endpoint = request.endpoint or request.path or "unknown"
        record_http(
            endpoint=endpoint,
            method=request.method,
            status_code=response.status_code,
            latency_ms=latency_ms,
        )
        return response
