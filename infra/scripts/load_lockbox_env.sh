#!/usr/bin/env bash

set -euo pipefail

# Requires:
# - YC_TOKEN or configured yc profile
# - jq
# - lockbox secret IDs passed via env

: "${LOCKBOX_SECRET_ID:?LOCKBOX_SECRET_ID is required}"

payload="$(yc lockbox payload get --id "${LOCKBOX_SECRET_ID}" --format json)"

extract() {
  local key="$1"
  echo "${payload}" | jq -r --arg k "$key" '.entries[] | select(.key == $k) | .textValue // empty'
}

cat <<EOF
export AUTH_DATABASE_URL='$(extract AUTH_DATABASE_URL)'
export CALLS_DATABASE_URL='$(extract CALLS_DATABASE_URL)'
export JWT_SECRET='$(extract JWT_SECRET)'
export AUTH_REGISTRATION_ENABLED='$(extract AUTH_REGISTRATION_ENABLED)'
export AUTH_BOOTSTRAP_ADMIN_LOGIN='$(extract AUTH_BOOTSTRAP_ADMIN_LOGIN)'
export AUTH_BOOTSTRAP_ADMIN_PASSWORD='$(extract AUTH_BOOTSTRAP_ADMIN_PASSWORD)'
export UPLOAD_SIGNING_SECRET='$(extract UPLOAD_SIGNING_SECRET)'
export YC_S3_ENDPOINT='$(extract YC_S3_ENDPOINT)'
export YC_S3_REGION='$(extract YC_S3_REGION)'
export YC_S3_BUCKET='$(extract YC_S3_BUCKET)'
export YC_ACCESS_KEY_ID='$(extract YC_ACCESS_KEY_ID)'
export YC_SECRET_ACCESS_KEY='$(extract YC_SECRET_ACCESS_KEY)'
export YMQ_ENDPOINT_URL='$(extract YMQ_ENDPOINT_URL)'
export YMQ_QUEUE_URL='$(extract YMQ_QUEUE_URL)'
export YMQ_REGION='$(extract YMQ_REGION)'
export YMQ_ACCESS_KEY_ID='$(extract YMQ_ACCESS_KEY_ID)'
export YMQ_SECRET_ACCESS_KEY='$(extract YMQ_SECRET_ACCESS_KEY)'
export CALL_SERVICE_INTERNAL_API_KEY='$(extract CALL_SERVICE_INTERNAL_API_KEY)'
export YC_IAM_TOKEN_SOURCE='$(extract YC_IAM_TOKEN_SOURCE)'
export YC_IAM_TOKEN='$(extract YC_IAM_TOKEN)'
export YC_METADATA_TOKEN_URL='$(extract YC_METADATA_TOKEN_URL)'
export YC_METADATA_TIMEOUT_SECONDS='$(extract YC_METADATA_TIMEOUT_SECONDS)'
export YC_METADATA_REFRESH_MARGIN_SECONDS='$(extract YC_METADATA_REFRESH_MARGIN_SECONDS)'
export SPEECHKIT_LONG_RUNNING_URL='$(extract SPEECHKIT_LONG_RUNNING_URL)'
export SPEECHKIT_OPERATION_URL='$(extract SPEECHKIT_OPERATION_URL)'
EOF
