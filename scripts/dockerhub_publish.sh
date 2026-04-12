#!/usr/bin/env bash
set -euo pipefail

DOCKERHUB_USER="${DOCKERHUB_USER:-bluebluekitty}"
IMAGE_NAME="${IMAGE_NAME:-cloudmediapilot}"
VERSION="${1:-${VERSION:-0.1.0}}"
DOCKERFILE="${DOCKERFILE:-backend/Dockerfile}"
CONTEXT="${CONTEXT:-.}"

if [[ -z "$VERSION" ]]; then
  echo "用法: $0 <version>" >&2
  echo "示例: $0 0.1.0" >&2
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
docker build -f "$DOCKERFILE" -t "${IMAGE}:${VERSION}" -t "${IMAGE}:latest" "$CONTEXT"

echo "[3/4] 推送版本标签: ${IMAGE}:${VERSION}"
docker push "${IMAGE}:${VERSION}"

echo "[4/4] 推送 latest 标签: ${IMAGE}:latest"
docker push "${IMAGE}:latest"

echo "完成: ${IMAGE}:${VERSION} 和 ${IMAGE}:latest"
