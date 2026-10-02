from __future__ import annotations

import httpx

from .config import get_settings


def _headers() -> dict[str, str]:
    s = get_settings()
    return {"x-internal-api-key": s.internal_api_key}


def get_enabled_llm_rules(owner_company_id: str | None = None) -> list[dict]:
    """Fetch enabled LLM rules from call-service internal API.

    Each returned dict contains:
      id, name, prompt,
      label_id, label_value, label_kind,
      allowed_labels: [{id, code, name, kind}]
    """
    s = get_settings()
    with httpx.Client(timeout=20.0) as client:
        params: dict[str, str] = {}
        normalized_company_id = str(owner_company_id or "").strip()
        if normalized_company_id:
            params["owner_company_id"] = normalized_company_id
        resp = client.get(
            f"{s.call_service_internal_url}/internal/v1/label-rules/llm-enabled",
            headers=_headers(),
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()
    return [x for x in list(data.get("items", [])) if isinstance(x, dict)]
