#!/usr/bin/env bash
set -euo pipefail

get_next_patch_version() {
  local base_version="${1:-}"
  if [[ -z "${base_version}" ]]; then
    return 0
  fi

  if [[ "${base_version}" =~ ^([0-9]+)\.([0-9]+)\.([0-9]+)$ ]]; then
    echo "${BASH_REMATCH[1]}.${BASH_REMATCH[2]}.$((BASH_REMATCH[3] + 1))"
  else
    echo "${base_version}"
  fi
}

get_latest_dockerhub_version() {
  DOCKERHUB_USER="${1}" IMAGE_NAME="${2}" python - <<'PY'
import json
import os
import sys
import urllib.request

dockerhub_user = os.environ["DOCKERHUB_USER"]
image_name = os.environ["IMAGE_NAME"]
url = f"https://hub.docker.com/v2/repositories/{dockerhub_user}/{image_name}/tags/?page_size=100"
versions = []

try:
    while url:
        with urllib.request.urlopen(url, timeout=15) as response:
            payload = json.load(response)
        for item in payload.get("results", []):
            name = str(item.get("name") or "").strip()
            parts = name.split(".")
            if len(parts) == 3 and all(part.isdigit() for part in parts):
                versions.append(tuple(int(part) for part in parts))
        url = payload.get("next")
except Exception as exc:  # noqa: BLE001
    print(f"查询 Docker Hub 最新版本失败，将回退到本地 version.json。{exc}", file=sys.stderr)
    sys.exit(1)

if not versions:
    sys.exit(0)

latest = max(versions)
print(".".join(str(part) for part in latest))
PY
}

update_version_file() {
  VERSION_FILE="${1}" TARGET_VERSION="${2}" python - <<'PY'
import json
import os
import pathlib

version_file = pathlib.Path(os.environ["VERSION_FILE"])
version = os.environ["TARGET_VERSION"].strip()

data = json.loads(version_file.read_text(encoding="utf-8"))
if not isinstance(data, dict):
    raise SystemExit("version.json 格式不正确")

data["current_version"] = version
version_file.write_text(
    json.dumps(data, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PY
}

DOCKERHUB_USER="${DOCKERHUB_USER:-bluebluekitty}"
IMAGE_NAME="${IMAGE_NAME:-cloudmediapilot}"
DOCKERFILE="${DOCKERFILE:-backend/Dockerfile}"
CONTEXT="${CONTEXT:-.}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
VERSION_FILE="${REPO_ROOT}/backend/app/meta/version.json"
DOCKERHUB_LATEST_VERSION=""
LATEST_VERSION=""
DEFAULT_VERSION=""

if DOCKERHUB_LATEST_VERSION="$(get_latest_dockerhub_version "${DOCKERHUB_USER}" "${IMAGE_NAME}" 2> >(cat >&2))"; then
  :
else
  DOCKERHUB_LATEST_VERSION=""
fi

if [[ -f "${VERSION_FILE}" ]]; then
  LATEST_VERSION="$(VERSION_FILE="${VERSION_FILE}" python - <<'PY'
import json, os, pathlib
p = pathlib.Path(__import__("os").environ["VERSION_FILE"])
try:
    data = json.loads(p.read_text(encoding="utf-8"))
    print(str(data.get("current_version", "")).strip())
except Exception:
    print("")
PY
)"
fi

if [[ -n "${DOCKERHUB_LATEST_VERSION}" ]]; then
  LATEST_VERSION="${DOCKERHUB_LATEST_VERSION}"
  LATEST_VERSION_SOURCE="Docker Hub"
else
  LATEST_VERSION_SOURCE="本地 version.json"
fi

DEFAULT_VERSION="$(get_next_patch_version "${LATEST_VERSION}")"

if [[ -n "${LATEST_VERSION}" ]]; then
  echo "当前最新版本 (${LATEST_VERSION_SOURCE}): ${LATEST_VERSION}"
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
  echo "版本号不能为空，且未能从 backend/app/meta/version.json 读取当前最新版本。" >&2
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

update_version_file "${VERSION_FILE}" "${VERSION}"
echo "已更新版本文件: ${VERSION_FILE} -> ${VERSION}"

echo "完成: ${IMAGE}:${VERSION} 和 ${IMAGE}:latest"
