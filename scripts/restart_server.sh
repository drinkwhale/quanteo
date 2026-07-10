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
# lsof가 PID를 여러 줄로 반환할 수 있어(포트 재사용 경합 등) 배열로 받아
# 각 PID를 개별적으로 종료·확인한다 — 문자열 그대로 kill에 넘기면 일부만
# 종료됐을 때 확인 루프가 어느 PID를 보고 있는지 꼬일 수 있다.
# macOS 기본 /bin/bash가 3.2라(라이선스 문제로 4+ 미탑재) mapfile을 못 쓴다 —
# while+read로 배열을 채우는 방식은 bash 3.2에서도 동작한다.
EXISTING_PIDS=()
while IFS= read -r pid; do
  [[ -n "${pid}" ]] && EXISTING_PIDS+=("${pid}")
done < <(lsof -tiTCP:"${PORT}" -sTCP:LISTEN 2>/dev/null || true)

if [[ ${#EXISTING_PIDS[@]} -gt 0 ]]; then
  echo "[restart_server] 기존 core.app 프로세스 종료 (PID: ${EXISTING_PIDS[*]}, port: ${PORT})"
  for pid in "${EXISTING_PIDS[@]}"; do
    kill -TERM "${pid}" 2>/dev/null || true
  done

  for pid in "${EXISTING_PIDS[@]}"; do
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
  echo "[restart_server] 포트 ${PORT}에서 실행 중인 프로세스 없음"
fi

# 인자를 넘기지 않으면 기본값 사용
if [[ $# -eq 0 ]]; then
  set -- "${DEFAULT_ARGS[@]}"
fi

echo "[restart_server] 재시작: uv run python -m core.app $*"
nohup uv run python -m core.app "$@" > "${LOG_FILE}" 2>&1 &
BG_PID=$!
disown

# set -e는 백그라운드(&) 명령의 실패를 잡지 못한다 — uv 미설치·모듈 경로 오류
# 등으로 프로세스가 즉시 죽어도 스크립트 자체는 성공한 것처럼 넘어간다.
# 그래서 3초를 통째로 기다리기 전에 짧게 먼저 살아있는지 확인해 "포트가 아직
# 안 열렸다"는 애매한 경고 대신 "시작 자체가 실패했다"를 바로 알린다.
sleep 0.5
if ! kill -0 "${BG_PID}" 2>/dev/null; then
  echo "[restart_server] 오류: core.app 프로세스가 시작 직후 종료됨. 로그:"
  tail -n 30 "${LOG_FILE}" || true
  exit 1
fi

sleep 2.5

if lsof -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "[restart_server] 재시작 완료 (port ${PORT} 리스닝 중). 로그: ${LOG_FILE}"
else
  echo "[restart_server] 경고: 포트 ${PORT}가 아직 열리지 않았습니다. 로그를 확인하세요: ${LOG_FILE}"
  tail -n 30 "${LOG_FILE}" || true
  exit 1
fi
