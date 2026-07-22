#!/usr/bin/env bash
# core.app (Control API) + dashboard를 종료 후 동일 옵션으로 재시작한다.
#
# 사용법:
#   ./scripts/restart_server.sh                          # 기본: --market domestic --with-info
#   ./scripts/restart_server.sh --market overseas --with-trading
#
# 환경변수:
#   QUANTEO_PORT      - Control API 포트 (기본 8000)
#   QUANTEO_LOG       - Control API 로그 파일 (기본 /tmp/quanteo-core-app.log)
#   DASHBOARD_PORT    - Dashboard 포트 (기본 5173)
#   DASHBOARD_LOG     - Dashboard 로그 파일 (기본 /tmp/quanteo-dashboard.log)

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

PORT="${QUANTEO_PORT:-8000}"
LOG_FILE="${QUANTEO_LOG:-/tmp/quanteo-core-app.log}"
DASHBOARD_PORT="${DASHBOARD_PORT:-5173}"
DASHBOARD_LOG="${DASHBOARD_LOG:-/tmp/quanteo-dashboard.log}"
DEFAULT_ARGS=(--market domestic --with-info)

# 기존 프로세스 종료 (포트 기준으로 탐색 - PID 파일에 의존하지 않아 항상 최신 상태를 반영)
# lsof가 PID를 여러 줄로 반환할 수 있어(포트 재사용 경합 등) 배열로 받아
# 각 PID를 개별적으로 종료·확인한다.

_terminate_port_process() {
  local port=$1
  local name=$2
  local pids=()
  while IFS= read -r pid; do
    [[ -n "${pid}" ]] && pids+=("${pid}")
  done < <(lsof -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true)

  if [[ ${#pids[@]} -gt 0 ]]; then
    echo "[restart_server] 기존 ${name} 프로세스 종료 (PID: ${pids[*]}, port: ${port})"
    for pid in "${pids[@]}"; do
      kill -TERM "${pid}" 2>/dev/null || true
    done

    for pid in "${pids[@]}"; do
      for _ in $(seq 1 10); do
        if ! kill -0 "${pid}" 2>/dev/null; then
          break
        fi
        sleep 1
      done

      if kill -0 "${pid}" 2>/dev/null; then
        echo "[restart_server] PID ${pid} 정상 종료 실패, SIGKILL 전송"
        kill -KILL "${pid}" 2>/dev/null || true
      fi
    done
  else
    echo "[restart_server] 포트 ${port}에서 실행 중인 ${name} 프로세스 없음"
  fi
}

_terminate_port_process "${PORT}" "core.app"
_terminate_port_process "${DASHBOARD_PORT}" "dashboard"

# 인자를 넘기지 않으면 기본값 사용
if [[ $# -eq 0 ]]; then
  set -- "${DEFAULT_ARGS[@]}"
fi

echo "[restart_server] Control API 재시작: uv run python -m core.app $*"
nohup uv run python -m core.app "$@" > "${LOG_FILE}" 2>&1 &
CORE_PID=$!
disown

# 백엔드 시작 확인
sleep 0.5
if ! kill -0 "${CORE_PID}" 2>/dev/null; then
  echo "[restart_server] 오류: core.app 프로세스가 시작 직후 종료됨. 로그:"
  tail -n 30 "${LOG_FILE}" || true
  exit 1
fi

# Dashboard 의존성 확인 및 시작
if [[ ! -d "dashboard/node_modules" ]]; then
  echo "[restart_server] Dashboard npm 의존성 설치 중..."
  cd dashboard && npm install && cd ..
fi

echo "[restart_server] Dashboard 재시작: npm run dev"
cd dashboard
nohup npm run dev > "${DASHBOARD_LOG}" 2>&1 &
DASHBOARD_PID=$!
disown
cd ..

# 대시보드 시작 확인
sleep 0.5
if ! kill -0 "${DASHBOARD_PID}" 2>/dev/null; then
  echo "[restart_server] 오류: dashboard 프로세스가 시작 직후 종료됨. 로그:"
  tail -n 30 "${DASHBOARD_LOG}" || true
  exit 1
fi

sleep 2.5

# 두 포트 모두 열림 확인
CORE_READY=false
DASHBOARD_READY=false

if lsof -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  CORE_READY=true
else
  echo "[restart_server] 경고: 포트 ${PORT}(Control API)가 아직 열리지 않았습니다. 로그:"
  tail -n 10 "${LOG_FILE}" || true
fi

if lsof -iTCP:"${DASHBOARD_PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  DASHBOARD_READY=true
else
  echo "[restart_server] 경고: 포트 ${DASHBOARD_PORT}(Dashboard)가 아직 열리지 않았습니다. 로그:"
  tail -n 10 "${DASHBOARD_LOG}" || true
fi

if [[ "${CORE_READY}" == "true" && "${DASHBOARD_READY}" == "true" ]]; then
  echo "[restart_server] 재시작 완료 ✓"
  echo "[restart_server] • Control API: http://127.0.0.1:${PORT}"
  echo "[restart_server] • Dashboard: http://127.0.0.1:${DASHBOARD_PORT}"
else
  echo "[restart_server] 오류: 일부 서비스 시작 실패. 로그를 확인하세요."
  exit 1
fi
