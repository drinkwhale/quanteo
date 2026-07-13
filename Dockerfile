# ============================================================
# quanteo — Python 자동매매 코어 컨테이너
# 멀티스테이지 빌드: builder에서 의존성 설치 → runtime 이미지로 복사
# ============================================================

# ── Stage 1: builder ─────────────────────────────────────────
FROM python:3.12-slim AS builder

# uv 설치 (공식 standalone installer)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /build

# 의존성 파일만 먼저 복사 (레이어 캐시 활용)
COPY pyproject.toml uv.lock ./

# 프로덕션 의존성만 /build/.venv에 설치 (dev 그룹 제외)
RUN uv sync --frozen --no-dev --no-install-project

# 소스 복사 후 프로젝트 자체 설치 (core/ 트레이딩 코어 + info/ 정보수집·알람 서브시스템)
COPY core/ ./core/
COPY info/ ./info/
RUN uv sync --frozen --no-dev


# ── Stage 2: runtime ─────────────────────────────────────────
FROM python:3.12-slim AS runtime

# 보안: 루트가 아닌 전용 유저로 실행
RUN groupadd -r quanteo && useradd -r -g quanteo -m -d /home/quanteo quanteo

WORKDIR /app

# builder에서 가상 환경과 소스 복사
COPY --from=builder /build/.venv /app/.venv
COPY --from=builder /build/core/ ./core/
COPY --from=builder /build/info/ ./info/

# pyproject.toml은 패키지 메타데이터용으로 포함
COPY pyproject.toml ./

# 가상 환경 바이너리를 PATH에 추가
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Control API 기본 포트
EXPOSE 8000

# 설정·상태 마운트 포인트 (quanteo.yaml, sqlite DB는 절대 이미지에 포함 금지)
# Path.home()/quanteo 아래에서 config/quanteo.yaml, data/quanteo.db를 찾으므로
# 컨테이너 유저(quanteo)의 홈 하위 동일 경로에 그대로 마운트하면 별도 env 지정 불필요.
# 실행 시: -v ~/quanteo:/home/quanteo/quanteo
VOLUME ["/home/quanteo/quanteo"]

USER quanteo

# 기본 실행 명령 — 국내 시장, 정보수집·알람 서브시스템 포함 (트레이딩 미포함)
# 트레이딩 포함: --with-trading --i-understand-real-money 추가
ENTRYPOINT ["python", "-m", "core.app"]
CMD ["--market", "domestic", "--host", "0.0.0.0", "--port", "8000", "--with-info"]
