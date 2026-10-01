#!/usr/bin/env bash

set -euo pipefail

: "${LOCKBOX_SECRET_ID:?LOCKBOX_SECRET_ID is required}"

TARGET_ENV_FILE="${TARGET_ENV_FILE:-/home/evponomarev1985/transcription-platform/.env}"
METADATA_TOKEN_URL="${YC_METADATA_TOKEN_URL:-http://169.254.169.254/computeMetadata/v1/instance/service-accounts/default/token}"

token_json="$(curl -sS -H "Metadata-Flavor: Google" "${METADATA_TOKEN_URL}")"
access_token="$(printf '%s' "${token_json}" | jq -r '.access_token')"

if [[ -z "${access_token}" || "${access_token}" == "null" ]]; then
  echo "Failed to get metadata access token" >&2
  exit 1
fi

payload_json="$(curl -sS -H "Authorization: Bearer ${access_token}" "https://payload.lockbox.api.cloud.yandex.net/lockbox/v1/secrets/${LOCKBOX_SECRET_ID}/payload")"

tmp_env_file="$(mktemp)"

PAYLOAD_JSON="${payload_json}" python3 - "${tmp_env_file}" <<'PY'
import json
import os
import sys

target = sys.argv[1]
payload = json.loads(os.environ["PAYLOAD_JSON"])

with open(target, "w", encoding="utf-8") as f:
    for entry in payload.get("entries", []):
        key = entry.get("key")
        value = entry.get("textValue")
        if key and value is not None:
            f.write(f"{key}={value}\n")
PY

chmod 600 "${tmp_env_file}"
mv "${tmp_env_file}" "${TARGET_ENV_FILE}"

if id -u evponomarev1985 >/dev/null 2>&1; then
  chown evponomarev1985:evponomarev1985 "${TARGET_ENV_FILE}"
fi
