# =============================================================================
# [DEBUG-SECTION] Lemma Debug Logger Module
# =============================================================================
# PURPOSE:  Provides comprehensive internal operation logging for developers.
#           Captures API calls, inter-layer data exchanges, data formats,
#           section parsing results, topic profiles, and matcher decisions.
#
# REMOVAL:  To fully remove this debugging feature:
#           1. Delete this file (backend/app/debug_logger.py)
#           2. Remove LEMMA_DEBUG_MODE from config.py (search: [DEBUG-SECTION])
#           3. Remove the middleware line in main.py   (search: [DEBUG-SECTION])
#           4. Remove the import + hook calls in analysis.py (search: [DEBUG-SECTION])
#           5. Remove the import + hook calls in online_retriever.py (search: [DEBUG-SECTION])
#
# TOGGLE:   Set environment variable LEMMA_DEBUG_MODE=true  (or in .env)
#           Default is False — zero overhead when disabled.
# =============================================================================

import json
import time
import logging
import functools
from typing import Any
from datetime import datetime, timezone

from app.config import settings

# Dedicated logger — writes to its own handler so debug noise stays separate
_debug_logger = logging.getLogger("lemma.debug")

_INITIALISED = False

# ---------------------------------------------------------------------------
# Sensitive-field redaction
# ---------------------------------------------------------------------------
_REDACT_KEYS = frozenset({
    "password", "secret", "token", "api_key", "api-key",
    "authorization", "x-api-key", "credential",
    "POSTGRES_PASSWORD", "SEMANTIC_SCHOLAR_API_KEY", "CORE_API_KEY",
})


def _is_enabled() -> bool:
    """Return True only when the debug flag is on."""
    return getattr(settings, "DEBUG_MODE", False)


def _ensure_initialised():
    """Lazily attach a StreamHandler so output appears on stdout."""
    global _INITIALISED
    if _INITIALISED:
        return
    _INITIALISED = True
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "\n┌─[LEMMA-DEBUG] %(asctime)s\n│ %(message)s\n└─────────────────────────────────────"
    ))
    _debug_logger.addHandler(handler)
    _debug_logger.setLevel(logging.DEBUG)
    _debug_logger.propagate = False          # Don't duplicate into root logger


def _redact(data: Any, depth: int = 0) -> Any:
    """Recursively redact sensitive keys from dicts / lists."""
    if depth > 6:
        return "..."
    if isinstance(data, dict):
        out = {}
        for k, v in data.items():
            if isinstance(k, str) and k.lower() in _REDACT_KEYS:
                out[k] = "*** REDACTED ***"
            else:
                out[k] = _redact(v, depth + 1)
        return out
    if isinstance(data, (list, tuple)):
        return [_redact(item, depth + 1) for item in data[:20]]   # cap list length
    return data


def _truncate(text: str, max_len: int = 500) -> str:
    """Truncate long strings for readability."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + f"... [{len(text) - max_len} more chars]"


def _fmt(obj: Any) -> str:
    """Pretty-format an object for log output."""
    if obj is None:
        return "None"
    if isinstance(obj, str):
        return _truncate(obj)
    try:
        return _truncate(json.dumps(_redact(obj), indent=2, default=str))
    except (TypeError, ValueError):
        return _truncate(repr(obj))


# ============================================================================
# Public API — called from integration hooks
# ============================================================================

def log_http_request(method: str, path: str, query_params: str, body_preview: str | None = None):
    """Log an incoming HTTP request to the FastAPI application."""
    if not _is_enabled():
        return
    _ensure_initialised()
    msg = (
        f"HTTP REQUEST\n"
        f"│  Method : {method}\n"
        f"│  Path   : {path}\n"
        f"│  Query  : {query_params or '(none)'}"
    )
    if body_preview:
        msg += f"\n│  Body   : {_truncate(body_preview, 300)}"
    _debug_logger.debug(msg)


def log_http_response(method: str, path: str, status_code: int, elapsed_ms: float, body_preview: str | None = None):
    """Log an outgoing HTTP response from the FastAPI application."""
    if not _is_enabled():
        return
    _ensure_initialised()
    msg = (
        f"HTTP RESPONSE\n"
        f"│  {method} {path} → {status_code}  ({elapsed_ms:.1f}ms)"
    )
    if body_preview:
        msg += f"\n│  Body   : {_truncate(body_preview, 300)}"
    _debug_logger.debug(msg)


def log_pipeline_step(step_name: str, **kwargs):
    """
    Log a named step inside the analysis pipeline.

    Usage:
        log_pipeline_step("Section Parsing", sections_found=8, paper_type="empirical")
    """
    if not _is_enabled():
        return
    _ensure_initialised()
    details = "\n".join(f"│  {k:20s}: {_fmt(v)}" for k, v in kwargs.items())
    _debug_logger.debug(f"PIPELINE ▸ {step_name}\n{details}")


def log_api_call(api_name: str, url: str, params: dict | None = None,
                 response_status: int | None = None,
                 result_count: int | None = None,
                 elapsed_ms: float | None = None,
                 error: str | None = None):
    """Log an outbound API call to an external academic source."""
    if not _is_enabled():
        return
    _ensure_initialised()
    msg = (
        f"EXTERNAL API CALL\n"
        f"│  API    : {api_name}\n"
        f"│  URL    : {_truncate(url, 200)}"
    )
    if params:
        msg += f"\n│  Params : {_fmt(params)}"
    if response_status is not None:
        msg += f"\n│  Status : {response_status}"
    if result_count is not None:
        msg += f"\n│  Results: {result_count} candidates"
    if elapsed_ms is not None:
        msg += f"\n│  Time   : {elapsed_ms:.1f}ms"
    if error:
        msg += f"\n│  ERROR  : {error}"
    _debug_logger.debug(msg)


def log_data_exchange(source: str, destination: str, data_type: str,
                      record_count: int | None = None,
                      sample: Any = None):
    """Log data flowing between internal layers (services, DB, ES, etc.)."""
    if not _is_enabled():
        return
    _ensure_initialised()
    msg = (
        f"DATA EXCHANGE\n"
        f"│  {source}  →  {destination}\n"
        f"│  Type   : {data_type}"
    )
    if record_count is not None:
        msg += f"\n│  Count  : {record_count}"
    if sample is not None:
        msg += f"\n│  Sample : {_fmt(sample)}"
    _debug_logger.debug(msg)


def log_matcher_decision(query_text: str, match_type: str | None,
                         score: float | None, matched_text: str | None,
                         thresholds: dict | None = None):
    """Log an individual sentence-level matcher decision."""
    if not _is_enabled():
        return
    _ensure_initialised()
    verdict = "MATCH" if match_type else "NO MATCH"
    msg = (
        f"MATCHER ▸ {verdict}\n"
        f"│  Query   : {_truncate(query_text, 120)}"
    )
    if match_type:
        msg += f"\n│  Type    : {match_type}  (score={score:.4f})"
        msg += f"\n│  Matched : {_truncate(matched_text or '', 120)}"
    if thresholds:
        msg += f"\n│  Thresh  : {thresholds}"
    _debug_logger.debug(msg)


def log_section_result(section_name: str, analyzable: bool,
                       sentence_count: int = 0, plagiarized_count: int = 0,
                       score: float = 0.0):
    """Log per-section analysis outcome."""
    if not _is_enabled():
        return
    _ensure_initialised()
    status = "ANALYZED" if analyzable else "SKIPPED"
    msg = (
        f"SECTION RESULT ▸ {status}\n"
        f"│  Section : {section_name}\n"
        f"│  Sentences: {sentence_count}  |  Plagiarized: {plagiarized_count}  |  Score: {score:.2%}"
    )
    _debug_logger.debug(msg)


# ============================================================================
# FastAPI middleware — auto-logs every HTTP request/response
# ============================================================================

async def debug_middleware(request, call_next):
    """
    [DEBUG-SECTION] FastAPI middleware that logs request/response pairs.
    """
    if not _is_enabled():
        return await call_next(request)

    method = request.method
    path = str(request.url.path)
    query = str(request.url.query)

    # Read body preview (only for JSON content, and only first 500 bytes)
    body_preview = None
    content_type = request.headers.get("content-type", "")
    if "json" in content_type:
        try:
            body_bytes = await request.body()
            body_preview = body_bytes[:500].decode("utf-8", errors="replace")
        except Exception:
            pass

    log_http_request(method, path, query, body_preview)

    start = time.perf_counter()
    response = await call_next(request)
    elapsed = (time.perf_counter() - start) * 1000

    log_http_response(method, path, response.status_code, elapsed)
    return response
