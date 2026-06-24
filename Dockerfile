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

# 소스 복사 후 프로젝트 자체 설치
COPY core/ ./core/
RUN uv sync --frozen --no-dev


# ── Stage 2: runtime ─────────────────────────────────────────
FROM python:3.12-slim AS runtime

# 보안: 루트가 아닌 전용 유저로 실행
RUN groupadd -r quanteo && useradd -r -g quanteo quanteo

WORKDIR /app

# builder에서 가상 환경과 소스 복사
COPY --from=builder /build/.venv /app/.venv
COPY --from=builder /build/core/ ./core/

# pyproject.toml은 패키지 메타데이터용으로 포함
COPY pyproject.toml ./

# 가상 환경 바이너리를 PATH에 추가
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Control API 기본 포트
EXPOSE 8000

# 설정 파일 마운트 포인트 (kis_devlp.yaml은 절대 이미지에 포함 금지)
# 실행 시: -v ~/KIS:/home/quanteo/KIS:ro
VOLUME ["/home/quanteo/KIS"]

USER quanteo

# 기본 실행 명령 — vps(모의투자) 환경, Control API만
# 트레이딩 포함: --with-trading, 실전: --env prod --i-understand-real-money
ENTRYPOINT ["python", "-m", "core.app"]
CMD ["--env", "vps", "--host", "0.0.0.0", "--port", "8000"]
