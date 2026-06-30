# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## ⛔ 브랜치 규칙 (세션 시작 시 반드시 확인)

**코드를 수정하기 전에 항상 현재 브랜치를 확인한다.**

```bash
git branch --show-current
```

- `main` 브랜치라면 **즉시 작업 브랜치를 생성**한 후 수정을 시작한다.
- `main`에 직접 커밋하지 않는다. 예외 없음.
- 브랜치 명명 규칙: `fix/{slug}` / `task/T{NNN}-{slug}` / `phase/{N}-{slug}` / `docs/{slug}`

## Project

**quanteo** — Toss증권 Open API를 이용한 주식 자동매매(트레이딩) 봇.

- **브로커:** Toss증권 단일 브로커 (KIS 완전 제거, Phase 8-9에서 마이그레이션 완료)
- 구현 전략: **Python + TypeScript 하이브리드**. Toss OpenAPI JSON 스펙(`specs/tossinvest/`) 기반으로 구현.

## 📊 현재 구현 상태

**Phase 1~~10 전체 완료 (T001~~T068)**

| Phase | 내용                          | Tasks     |
| ----- | ----------------------------- | --------- |
| 1     | 부트스트랩·인증               | T001~T005 |
| 2     | 시세·상태저장                 | T006~T010 |
| 2.5   | Telegram 알림                 | T033~T038 |
| 3     | 전략 엔진                     | T011~T014 |
| 4     | Risk Manager·주문 실행        | T015~T020 |
| 5     | Control API (FastAPI)         | T021~T024 |
| 6     | TypeScript 대시보드           | T025~T028 |
| 7     | 안전·운영 (Rate Limit·Docker) | T029~T032 |
| 8     | Toss증권 어댑터 마이그레이션  | T039~T048 |
| 9     | Toss증권 어댑터 운영 완성     | T049~T056 |
| 10    | 정보 수집·알람 서브시스템     | T057~T068 |

**다음:** 신규 Phase 계획 필요 (specs/tasks.md 참고)

주요 구현 모듈: `core/config`, `core/adapters/toss/` (auth/rest/models), `core/adapters/base.py` (BrokerAdapter Protocol), `core/store/`, `core/marketdata/`, `core/events/`,
`core/strategy/`, `core/risk/`, `core/execution/`, `core/api/`, `core/notifier/`, `dashboard/` (React+Vite+Tailwind),
`info/` (ai_filter·news·fx·calendar·telegram·scheduler·main)

코드를 작성하기 전에 현재 디렉토리 구조를 먼저 확인하고, 이 문서와 실제 상태가 다르면 **이 문서를 갱신**할 것.

## 📐 설계 & 작업 문서 (새 세션에서 먼저 읽을 것)

아키텍처와 작업 계획이 확정되어 `specs/`에 문서화되어 있다. **작업 시작 전 반드시 확인.**

- **[PROJECT_INDEX.md](PROJECT_INDEX.md)** — 프로젝트 전체 현황 요약 (구조·의존성·엔드포인트). 새 세션 첫 진입 시 읽을 것.
- **[specs/2026-06-18-quanteo-architecture.md](specs/2026-06-18-quanteo-architecture.md)** — 확정된 아키텍처 설계서(단일 진실 공급원). 구현이 달라지면 이 문서를 갱신.
- **[specs/tasks.md](specs/tasks.md)** — Phase·Task 단위 구현 작업 목록. "T{번호}/Phase 진행" 요청 시 이 파일 기준.
- **[specs/tossinvest/](specs/tossinvest/)** — Toss증권 Open API JSON 스펙 모음 (`open-api.json`, `auth.json`, `account.json`, `order.json`, `order-info.json`, `order-history.json`, `market-data.json`, `market-info.json`, `stock-info.json`, `asset.json`). Phase 8·9 구현 시 참고.

### 확정된 핵심 결정 (요약)

- **목표:** 완전 자동매매 봇 (시그널 → 주문까지 자동 실행)
- **시장:** 국내 + 해외 주식 (시장 추상화)
- **스택:** Python 매매 코어 + TypeScript 웹 대시보드
- **전략:** 규칙 기반 지표 전략, 플러그인 교체형 (전략은 **시그널만** 생성)
- **아키텍처(접근 B):** 모듈형 단일 Python 프로세스 + 얇은 Control API(FastAPI REST/WS) + TS 대시보드. 클라우드 확장 대비 모듈 경계 명확화.
- **모듈:** Toss Adapter (REST 폴링, WS 미지원) → Market Data → Strategy Engine → Risk Manager → Order Executor / State Store(SQLite) / Event Bus / Notifier(Telegram) / Control API / Dashboard
- **안전 원칙:** 모든 주문은 **반드시 Risk Manager 통과**. 기본 환경 `vps`(모의투자), `prod`는 명시 플래그로만.

## Toss증권 API 핵심 개념 (반드시 숙지)

자동매매의 정확성과 안전성이 직결되는 부분이라 가장 먼저 이해해야 한다.

- **인증:** OAuth2 Client Credentials (`POST https://openapi.tossinvest.com/oauth2/token`, `application/x-www-form-urlencoded`). `client_id` + `client_secret` → access token 발급. 캐시: `~/toss/cache/token.json`. 401 수신 시 캐시 삭제 후 즉시 재발급.
- **모의투자 구분 없음:** Toss는 단일 URL(`https://openapi.tossinvest.com`). `prod`/`vps` 환경 구분이 코드에 남아 있으나 Toss 어댑터는 항상 동일 엔드포인트 사용.
- **계좌:** 앱 시작 시 `GET /api/v1/accounts` 호출 → `accountSeq` 획득 → 이후 `X-Tossinvest-Account` 헤더에 사용.
- **WebSocket 미지원:** 실시간 시세는 REST 폴링(`GET /api/v1/prices?symbols=...`, 기본 2초 간격)으로 대체. 추후 지원 예정.
- **설정 파일 `quanteo.yaml`:** 기본 경로 `~/quanteo/config/quanteo.yaml`(저장소 밖, 절대 커밋 금지). 경로 재지정: `export QUANTEO_CONFIG_PATH=/다른/경로/quanteo.yaml`. 앱키 발급: https://openapi.tossinvest.com → 앱 등록 후 `client_id`/`client_secret` 획득. 포맷 예시: `quanteo.yaml.example`.
- **스펙 참고:** `specs/tossinvest/` 디렉토리의 JSON 파일 (`open-api.json`, `auth.json`, `market-data.json`, `order.json` 등).

## 🌿 브랜치 전략 (Branch Strategy)

> **코드를 수정할 때는 반드시 아래 전략에 따라 브랜치를 만들고 작업한다.** `main`에 직접 커밋하지 않는다.

### 브랜치 구조

```
main
└── phase/{N}-{slug}          # Phase 단위 통합 브랜치
    └── task/T{NNN}-{slug}    # 개별 Task 작업 브랜치
```

### 브랜치 명명 규칙

| 유형         | 패턴                 | 예시                        |
| ------------ | -------------------- | --------------------------- |
| Phase 브랜치 | `phase/{N}-{slug}`   | `phase/1-bootstrap`         |
| Task 브랜치  | `task/T{NNN}-{slug}` | `task/T001-pyproject`       |
| 핫픽스       | `fix/{slug}`         | `fix/kis-auth-token-expiry` |
| 문서         | `docs/{slug}`        | `docs/update-architecture`  |

### 작업 절차 (Task 하나 = 브랜치 하나)

```bash
# 1. Phase 브랜치 생성 (Phase 시작 시 main 기반, 한 번만)
git checkout main && git pull
git checkout -b phase/1-bootstrap

# 2. Task 브랜치 생성 (Phase 브랜치 기반)
git checkout -b task/T001-pyproject

# 3. 구현 + 테스트

# 4. specs/tasks.md 체크박스 갱신 [ ] → [x]

# 5. 커밋 (Conventional Commits)
git add <files>
git commit -m "feat: scaffold pyproject.toml and core/ directory"

# 6. Task 브랜치 → Phase 브랜치로 Merge
git checkout phase/1-bootstrap
git merge --squash task/T001-pyproject
git commit -m "feat(T001): scaffold project with uv and core/ structure"

# 7. Phase 완료 시 — 반드시 아래 순서로 진행 (자동화 규칙)
#    a) PROJECT_INDEX.md 갱신: /sc:index-repo mode=update 실행
#    b) 변경사항 commit & push: git add -A && git commit && git push
#    c) PR 생성: gh pr create --base main --head phase/...
gh pr create --base main --head phase/1-bootstrap
```

> **⚡ Phase 완료 자동화 규칙 (Claude 필독)**
>
> Phase의 **마지막 Task까지 완료된 직후**, Claude는 반드시 아래 세 단계를 순서대로 실행한다.
> 사용자가 별도로 요청하지 않아도 자동 진행.
>
> 1. `/sc:index-repo mode=update` — PROJECT_INDEX.md 갱신
> 2. 변경사항 전체 commit & push (`phase/*` 브랜치)
> 3. `gh pr create --base main` — PR 생성 (이미 존재하면 skip)
>
> Stop hook (`settings.local.json`)이 미커밋 변경사항을 자동 commit+push하지만,
> **index 업데이트는 AI가 직접 실행해야 하므로** Claude가 세션 내에서 처리한다.

### 커밋 메시지 형식 (Conventional Commits)

```
<type>[scope]: <description>

<optional body>
```

| type       | 용도                    |
| ---------- | ----------------------- |
| `feat`     | 새 기능·모듈            |
| `fix`      | 버그 수정               |
| `test`     | 테스트 추가·수정        |
| `refactor` | 동작 변경 없는 리팩토링 |
| `docs`     | 문서만 변경             |
| `chore`    | 빌드·설정·의존성        |
| `perf`     | 성능 개선               |

예시:

- `feat(kis): add access token auth with file caching`
- `test(risk): add kill switch boundary case tests`
- `chore: init uv project with Python 3.12`

---

## 명령어

**Python (uv, Python 3.12+):**

- 의존성: `uv sync`
- 실행: `uv run <script.py>`
- 전체 테스트: `uv run pytest`
- 단일 테스트: `uv run pytest <path>::<test_name>`
- 린트: `uv run ruff check .`
- 포맷: `uv run ruff format .`

**TypeScript 대시보드:**

- 의존성: `cd dashboard && npm install`
- 개발 서버: `cd dashboard && npm run dev`
- 빌드: `cd dashboard && npm run build`

**Docker:**

- 전체 기동: `docker compose up -d`
- 로그 확인: `docker compose logs -f`

## 규칙 및 제약

- **자격증명 격리:** `quanteo.yaml`, `.env`, `client_id`/`client_secret`/토큰 캐시(`~/toss/cache/`)는 절대 커밋하지 않는다.
- **실전/모의 안전장치:** 주문(매수/매도) 로직은 환경(`prod`/`vps`)을 명시적 인자로 받고, 실전 주문은 의도적으로만 활성화되도록 설계. 테스트·개발 기본값은 모의투자.
- **하이브리드 경계:** `core/` (Python) — 매매 로직·Toss 연동·Control API(포트 8000). `dashboard/` (TypeScript) — 웹 UI 전용. 두 영역 간 통신은 Control API(REST/WS)만 사용.
- **Rate Limit:** `MARKET_DATA` 그룹(시세·잔고)과 `ORDER` 그룹(주문)은 **별도 스로틀러 버킷** 사용(`core/adapters/throttler.py`). 주문 버킷이 시세 버킷을 소모하지 않도록 격리.
