#!/usr/bin/env bash
# core.app (Control API) 서버를 종료 후 동일 옵션으로 재시작한다.
#
# 사용법:
#   ./scripts/restart_server.sh                          # 기본: --market domestic --with-info
#   ./scripts/restart_server.sh --market overseas --with-trading
#
# 환경변수:
#   QUANTEO_PORT   - Control API 포트 (기본 8000, 프로세스 탐색에 사용)
#   QUANTEO_LOG    - 로그 파일 경로 (기본 /tmp/quanteo-core-app.log)

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

PORT="${QUANTEO_PORT:-8000}"
LOG_FILE="${QUANTEO_LOG:-/tmp/quanteo-core-app.log}"
DEFAULT_ARGS=(--market domestic --with-info)

# 기존 프로세스 종료 (포트 기준으로 탐색 - PID 파일에 의존하지 않아 항상 최신 상태를 반영)
EXISTING_PID="$(lsof -tiTCP:"${PORT}" -sTCP:LISTEN 2>/dev/null || true)"
if [[ -n "${EXISTING_PID}" ]]; then
  echo "[restart_server] 기존 core.app 프로세스 종료 (PID: ${EXISTING_PID}, port: ${PORT})"
  kill -TERM ${EXISTING_PID}

  for _ in $(seq 1 10); do
    if ! kill -0 ${EXISTING_PID} 2>/dev/null; then
      break
    fi
    sleep 1
  done

  if kill -0 ${EXISTING_PID} 2>/dev/null; then
    echo "[restart_server] 정상 종료 실패, SIGKILL 전송"
    kill -KILL ${EXISTING_PID} 2>/dev/null || true
  fi
else
  echo "[restart_server] 포트 ${PORT}에서 실행 중인 프로세스 없음"
fi

# 인자를 넘기지 않으면 기본값 사용
if [[ $# -eq 0 ]]; then
  set -- "${DEFAULT_ARGS[@]}"
fi

echo "[restart_server] 재시작: uv run python -m core.app $*"
nohup uv run python -m core.app "$@" > "${LOG_FILE}" 2>&1 &
disown

sleep 3

if lsof -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "[restart_server] 재시작 완료 (port ${PORT} 리스닝 중). 로그: ${LOG_FILE}"
else
  echo "[restart_server] 경고: 포트 ${PORT}가 아직 열리지 않았습니다. 로그를 확인하세요: ${LOG_FILE}"
  tail -n 30 "${LOG_FILE}" || true
  exit 1
fi
