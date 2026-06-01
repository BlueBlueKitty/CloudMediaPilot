#!/usr/bin/env bash
set -euo pipefail

DOCKERHUB_USER="${DOCKERHUB_USER:-bluebluekitty}"
IMAGE_NAME="${IMAGE_NAME:-cloudmediapilot}"
DOCKERFILE="${DOCKERFILE:-backend/Dockerfile}"
CONTEXT="${CONTEXT:-.}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
VERSION_FILE="${REPO_ROOT}/backend/app/meta/version.json"
DEFAULT_VERSION=""

if [[ -f "${VERSION_FILE}" ]]; then
  DEFAULT_VERSION="$(VERSION_FILE="${VERSION_FILE}" python - <<'PY'
import json, pathlib
p = pathlib.Path(__import__("os").environ["VERSION_FILE"])
try:
    data = json.loads(p.read_text(encoding="utf-8"))
    print(str(data.get("current_version", "")).strip())
except Exception:
    print("")
PY
)"
fi

VERSION="${1:-${VERSION:-}}"

if [[ -z "${VERSION}" ]]; then
  if [[ -n "${DEFAULT_VERSION}" ]]; then
    read -r -p "请输入版本号 (直接回车使用默认: ${DEFAULT_VERSION}): " INPUT_VERSION
  else
    read -r -p "请输入版本号 (例如 0.1.1): " INPUT_VERSION
  fi
  if [[ -n "${INPUT_VERSION}" ]]; then
    VERSION="${INPUT_VERSION}"
  else
    VERSION="${DEFAULT_VERSION}"
  fi
fi

if [[ -z "$VERSION" ]]; then
  echo "版本号不能为空，且未能从 backend/app/meta/version.json 读取默认版本。" >&2
  exit 1
fi

# if [[ -z "${DOCKERHUB_TOKEN:-}" ]]; then
#   echo "请先设置 DOCKERHUB_TOKEN 环境变量，不建议在脚本中写死密码。" >&2
#   echo "示例: export DOCKERHUB_TOKEN=xxxx" >&2
#   exit 1
# fi

IMAGE="${DOCKERHUB_USER}/${IMAGE_NAME}"

# echo "[1/4] 登录 Docker Hub: ${DOCKERHUB_USER}"
# printf '%s' "$DOCKERHUB_TOKEN" | docker login -u "$DOCKERHUB_USER" --password-stdin

echo "[2/4] 构建镜像: ${IMAGE}:${VERSION}"
docker build \
  --build-arg APP_VERSION="${VERSION}" \
  -f "$DOCKERFILE" \
  -t "${IMAGE}:${VERSION}" \
  -t "${IMAGE}:latest" \
  "$CONTEXT"

echo "[3/4] 推送版本标签: ${IMAGE}:${VERSION}"
docker push "${IMAGE}:${VERSION}"

echo "[4/4] 推送 latest 标签: ${IMAGE}:latest"
docker push "${IMAGE}:latest"

echo "完成: ${IMAGE}:${VERSION} 和 ${IMAGE}:latest"
