#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${SCRIPT_DIR}/../build"
CHAT_DIR="${BUILD_DIR}/chat_handler"
SOURCE_ROOT="${SCRIPT_DIR}/../.."

mkdir -p "${CHAT_DIR}"

pip install boto3 \
    -t "${CHAT_DIR}" \
    --platform manylinux2014_aarch64 \
    --only-binary=:all: \
    --quiet

cp "${SOURCE_ROOT}/lambda/chat_handler/lambda_function.py" "${CHAT_DIR}/"
cp -r "${SOURCE_ROOT}/services" "${CHAT_DIR}/"
cp -r "${SOURCE_ROOT}/utils" "${CHAT_DIR}/"
cp -r "${SOURCE_ROOT}/config" "${CHAT_DIR}/"

ZIP_PATH="${BUILD_DIR}/chat_handler.zip"
cd "${CHAT_DIR}"
zip -r "${ZIP_PATH}" . -q
cd "${SCRIPT_DIR}"

echo "Build complete: ${ZIP_PATH}"
