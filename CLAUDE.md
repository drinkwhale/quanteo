# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## ⛔ 브랜치 규칙 (세션 시작 시 반드시 확인)

**코드를 수정하기 전에 항상 현재 브랜치를 확인한다.**

```bash
git branch --show-current
```

- `main` 브랜치라면 **즉시 작업 브랜치를 생성**한 후 수정을 시작한다.
- `main`에 직접 커밋하지 않는다. 예외 없음.
- 브랜치 명명 규칙: `fix/{slug}` / `task/T{NNN}-{slug}` / `phase/{N}-{slug}`

## Project

**quanteo** — 한국투자증권(KIS) Open Trading API를 이용한 주식 자동매매(트레이딩) 봇.

- 참고 API/샘플 저장소: https://github.com/koreainvestment/open-trading-api (Python 주력 + TypeScript 포팅 + MCP)
- 구현 전략: **Python + TypeScript 하이브리드**. 공식 `open-trading-api` 샘플 코드를 이 저장소로 **복사/적응(copy & adapt)** 하는 방식으로 개발.

## 📊 현재 구현 상태

**Phase 1~7 전체 완료 (T001~T038)**

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

**다음**: 신규 Phase 계획 필요 (specs/tasks.md 참고)

주요 구현 모듈: `core/config`, `core/adapters/kis/` (auth/rest/ws/tr_ids), `core/store/`, `core/marketdata/`, `core/events/`,
`core/strategy/`, `core/risk/`, `core/execution/`, `core/api/`, `core/notifier/`, `dashboard/` (React+Vite+Tailwind)

코드를 작성하기 전에 현재 디렉토리 구조를 먼저 확인하고, 이 문서와 실제 상태가 다르면 **이 문서를 갱신**할 것.

## 📐 설계 & 작업 문서 (새 세션에서 먼저 읽을 것)

아키텍처와 작업 계획이 확정되어 `specs/`에 문서화되어 있다. **작업 시작 전 반드시 확인.**

- **[specs/2026-06-18-quanteo-architecture.md](specs/2026-06-18-quanteo-architecture.md)** — 확정된 아키텍처 설계서(단일 진실 공급원). 구현이 달라지면 이 문서를 갱신.
- **[specs/tasks.md](specs/tasks.md)** — Phase·Task 단위 구현 작업 목록. "T{번호}/Phase 진행" 요청 시 이 파일 기준.

### 확정된 핵심 결정 (요약)

- **목표:** 완전 자동매매 봇 (시그널 → 주문까지 자동 실행)
- **시장:** 국내 + 해외 주식 (시장 추상화)
- **스택:** Python 매매 코어 + TypeScript 웹 대시보드
- **전략:** 규칙 기반 지표 전략, 플러그인 교체형 (전략은 **시그널만** 생성)
- **아키텍처(접근 B):** 모듈형 단일 Python 프로세스 + 얇은 Control API(FastAPI REST/WS) + TS 대시보드. 클라우드 확장 대비 모듈 경계 명확화.
- **모듈:** KIS Adapter → Market Data → Strategy Engine → Risk Manager → Order Executor / State Store(SQLite) / Event Bus / Notifier(Telegram) / Control API / Dashboard
- **안전 원칙:** 모든 주문은 **반드시 Risk Manager 통과**. 기본 환경 `vps`(모의투자), `prod`는 명시 플래그로만.

## KIS API 핵심 개념 (반드시 숙지)

자동매매의 정확성과 안전성이 직결되는 부분이라 가장 먼저 이해해야 한다.

- **인증 (`kis_auth.py` 패턴):** 앱키/시크릿으로 access token을 발급받아 REST 호출과 WebSocket 접속키를 관리. 토큰은 캐싱/재사용하며 만료 시 재발급.
- **환경 구분 (절대 혼동 금지):**
  - `prod` = **실전투자(실제 주문/실제 돈)**
  - `vps` = **모의투자(paper trading)**
  - REST 도메인과 WebSocket 도메인, 앱키/시크릿이 환경별로 **각각 다름**. 코드/설정에서 환경을 명시적으로 다루고, 기본값은 항상 모의투자(`vps`)로 둘 것.
- **설정 파일 `kis_devlp.yaml`:** 자격증명을 담으며 보통 `~/KIS/config/kis_devlp.yaml`에 위치(저장소 밖, 절대 커밋 금지). 실전/모의용 앱키·시크릿, HTS ID, 계좌번호(8자리 + 상품코드 2자리), User-Agent 포함.
- **계좌번호:** `CANO`(8자리) + `ACNT_PRDT_CD`(상품코드 2자리, 예: 종합계좌 `01`)로 분리되어 전달됨.
- **TR_ID:** 모든 REST 호출은 거래 ID(TR_ID)로 식별되며, **실전/모의에서 TR_ID가 다른 경우가 많다.** 주문/시세 함수 작성 시 환경에 맞는 TR_ID를 반드시 확인.
- **WebSocket:** 실시간 시세/체결 구독. 별도 접속키(`auth_ws` 패턴)로 연결 후 종목별로 `subscribe`.

## 공식 샘플 저장소 구조 (복사 출처)

`open-trading-api`에서 코드를 가져올 때 참고하는 두 가지 병렬 구조:

- `examples_llm/` — **함수 단위** 샘플. `inquire_price.py`(기능) + `chk_inquire_price.py`(테스트) 형태. 개별 API를 골라 적응할 때 출처.
- `examples_user/` — **카테고리 통합** 샘플. `domestic_stock_functions.py`(함수 모음) + `domestic_stock_examples.py`(실행 예제). 실전 흐름 참고용.
- 상품 카테고리: `domestic_stock/`, `overseas_stock/`, `domestic_futureoption/`, `domestic_bond/`, `etfetn/`, `elw/` 등.
- `auth/` — 토큰 발급(REST/WebSocket).

샘플을 복사할 때는 출처 경로를 커밋 메시지나 주석에 남겨, 이후 공식 저장소 업데이트와 대조할 수 있게 할 것.

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
- `chore: init uv project with Python 3.11`

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

- **자격증명 격리:** `kis_devlp.yaml`, `.env`, 앱키/시크릿/토큰은 절대 커밋하지 않는다. 토큰 캐시 파일도 마찬가지.
- **실전/모의 안전장치:** 주문(매수/매도) 로직은 환경(`prod`/`vps`)을 명시적 인자로 받고, 실전 주문은 의도적으로만 활성화되도록 설계. 테스트·개발 기본값은 모의투자.
- **하이브리드 경계:** Python과 TypeScript의 역할 분담이 정해지면 디렉토리/모듈 경계를 이 문서에 명시할 것.
- 한국투자증권 API는 호출 빈도 제한(rate limit)이 있으므로, 시세 폴링·주문 루프는 제한을 고려해 구현.
