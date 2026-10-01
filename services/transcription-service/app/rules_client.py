from __future__ import annotations

import httpx

from .config import get_settings


def _headers() -> dict[str, str]:
    s = get_settings()
    return {"x-internal-api-key": s.internal_api_key}


def get_enabled_llm_rules() -> list[dict]:
    """Fetch enabled LLM rules from call-service internal API.

    Each returned dict contains:
      id, name, prompt,
      label_id, label_value, label_kind,
      allowed_labels: [{id, code, name, kind}]
    """
    s = get_settings()
    with httpx.Client(timeout=20.0) as client:
        resp = client.get(
            f"{s.call_service_internal_url}/internal/v1/label-rules/llm-enabled",
            headers=_headers(),
        )
        resp.raise_for_status()
        data = resp.json()
    return [x for x in list(data.get("items", [])) if isinstance(x, dict)]
