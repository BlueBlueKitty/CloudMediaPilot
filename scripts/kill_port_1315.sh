#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-1315}"
if ! [[ "${PORT}" =~ ^[0-9]+$ ]] || (( PORT < 1 || PORT > 65535 )); then
  echo "端口参数无效: ${PORT} (应为 1-65535)" >&2
  exit 1
fi

collect_pids() {
  if command -v lsof >/dev/null 2>&1; then
    lsof -ti tcp:"${PORT}" -sTCP:LISTEN 2>/dev/null || true
    return
  fi
  if command -v ss >/dev/null 2>&1; then
    ss -ltnp 2>/dev/null | awk -v p=":${PORT}" '$4 ~ p {print $NF}' | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' || true
    return
  fi
  if command -v netstat >/dev/null 2>&1; then
    netstat -ltnp 2>/dev/null | awk -v p=":${PORT}" '$4 ~ p {print $7}' | cut -d/ -f1 || true
    return
  fi
}

mapfile -t PIDS < <(collect_pids | awk 'NF' | sort -u)

if [[ "${#PIDS[@]}" -eq 0 ]]; then
  echo "端口 ${PORT} 当前没有监听进程。"
  exit 0
fi

for pid in "${PIDS[@]}"; do
  cmd="$(ps -p "${pid}" -o args= 2>/dev/null || true)"
  echo "发现占用端口 ${PORT} 的进程: PID=${pid}"
  [[ -n "${cmd}" ]] && echo "Command: ${cmd}"
  kill -9 "${pid}" 2>/dev/null || true
  if ps -p "${pid}" >/dev/null 2>&1; then
    echo "终止 PID=${pid} 失败，请检查权限。"
  else
    echo "已终止 PID=${pid}"
  fi
done

sleep 0.4
mapfile -t REMAIN < <(collect_pids | awk 'NF' | sort -u)
if [[ "${#REMAIN[@]}" -gt 0 ]]; then
  echo "端口 ${PORT} 仍被占用，剩余 PID: ${REMAIN[*]}" >&2
  exit 1
fi
echo "端口 ${PORT} 已释放。"
