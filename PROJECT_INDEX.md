# Project Index: quanteo

Generated: 2026-06-24

## 📋 Status

**Phase 1~5 완료** — Phase 6 (TypeScript 대시보드) 진행 예정.

| Phase    | Tasks     | 상태    | 내용                                            |
| -------- | --------- | ------- | ----------------------------------------------- |
| **P1**   | T001–T005 | ✅ 완료 | 프로젝트 스캐폴드, 설정/환경 로딩, KIS 인증     |
| **P2**   | T006–T010 | ✅ 완료 | Market Data 수신·정규화, State Store, Event Bus |
| **P2.5** | T033–T038 | ✅ 완료 | Notifier 모듈 (Telegram + MockNotifier)         |
| **P3**   | T011–T014 | ✅ 완료 | Strategy Protocol, Engine, MA Cross, Harness    |
| **P4**   | T015–T020 | ✅ 완료 | Risk Manager + Order Executor (vps 주문)        |
| **P5**   | T021–T024 | ✅ 완료 | Control API REST/WS + 전체 모듈 wiring          |
| **P6**   | T025–T028 | ⬜ 미완 | TypeScript 대시보드                             |
| **P7**   | T029–T032 | ⬜ 미완 | 킬스위치·복구·rate limit·prod 게이트            |

**테스트:** 252 passed (2026-06-24 기준)

---

## 📁 Project Structure (현재)

```
quanteo/
├── core/
│   ├── adapters/kis/         # KIS REST/WS Adapter + 인증 + TR_ID 매핑
│   │   ├── auth.py           # access token 발급·캐싱·재발급 + WebSocket 접속키
│   │   ├── rest.py           # 현재가/잔고 조회 + 매수/매도 주문 REST 호출
│   │   ├── ws.py             # 실시간 시세/체결 WebSocket 구독
│   │   └── tr_ids.py         # 환경×시장 TR_ID·도메인 매핑 테이블
│   ├── api/                  # Control API (FastAPI) — P5 완료
│   │   ├── app.py            # FastAPI 앱 팩토리 (lifespan 기반)
│   │   ├── deps.py           # AppContainer DI — StateStore/RiskManager/EventBus 공유
│   │   ├── models.py         # Pydantic 응답 스키마 (BotStatus/PositionList/OrderList)
│   │   └── routes/
│   │       ├── status.py     # GET /status — 봇 상태·halt_level·uptime
│   │       ├── positions.py  # GET /positions — 보유 포지션 목록
│   │       ├── orders.py     # GET /orders — 주문 내역 (status 필터, limit)
│   │       ├── control.py    # POST /control/pause|resume|kill
│   │       └── stream.py     # WebSocket /stream — EventBus 실시간 브로드캐스트
│   ├── config/
│   │   └── settings.py       # kis_devlp.yaml 로딩, env/market 분기
│   ├── events/
│   │   ├── bus.py            # asyncio.Queue 기반 pub/sub EventBus
│   │   └── types.py          # Event, EventType 정의
│   ├── execution/
│   │   └── executor.py       # 주문 전송·멱등성(client_order_id)·체결 추적
│   ├── marketdata/
│   │   ├── models.py         # Tick, Quote, Candle 데이터 모델
│   │   ├── feed.py           # KIS Adapter 연동 시세 공급
│   │   └── normalizer.py     # 수신 데이터 → 내부 표준 정규화
│   ├── notifier/
│   │   ├── base.py           # Notifier Protocol + NotifyEvent·NotifyLevel
│   │   ├── telegram.py       # TelegramNotifier (aiogram v3, Queue Rate limit)
│   │   ├── mock.py           # MockNotifier (테스트용, sent_events 누적)
│   │   ├── templates.py      # Signal/Order/Fill/Risk/Error/Status 템플릿
│   │   ├── factory.py        # enabled 플래그로 Telegram/Mock 교체
│   │   └── wiring.py         # Event Bus 구독 연결
│   ├── risk/
│   │   ├── manager.py        # RiskManager — 한도 가드·킬스위치·손절/익절
│   │   └── models.py         # Order, Position, Portfolio, HaltLevel, Rejection
│   ├── store/
│   │   ├── db.py             # SQLite 연결·마이그레이션 (aiosqlite)
│   │   └── schema.py         # positions/orders/fills/signals/events_log 스키마
│   ├── strategy/
│   │   ├── base.py           # Strategy Protocol (runtime_checkable), Signal, MarketContext
│   │   ├── engine.py         # 플러그인 관리, 캔들 버퍼, warmup 실패 격리
│   │   ├── harness.py        # 경량 백테스트 하니스 (research-to-live parity)
│   │   └── plugins/
│   │       └── ma_cross.py   # 이동평균 교차 전략 (MACrossStrategy)
│   └── app.py                # 전체 모듈 wiring + CLI 진입점 (asyncio.TaskGroup)
├── tests/
│   ├── adapters/kis/         # auth, rest, tr_ids, ws 단위 테스트
│   ├── api/                  # Control API 엔드포인트 테스트 (13개)
│   ├── config/               # settings 테스트
│   ├── events/               # EventBus 단위 테스트
│   ├── execution/            # OrderExecutor 단위 테스트
│   ├── integration/          # 시그널→리스크→주문 라운드트립 테스트
│   ├── marketdata/           # normalizer 테스트
│   ├── notifier/             # base, factory, mock, telegram, templates, wiring 테스트
│   ├── risk/                 # RiskManager (한도·킬스위치·손절/익절) 테스트
│   ├── store/                # db 테스트
│   └── strategy/
│       ├── test_base.py      # Signal·MarketContext·Strategy Protocol 테스트
│       ├── test_engine.py    # StrategyEngine 단위 테스트
│       ├── test_harness.py   # run_backtest 단위 테스트
│       └── plugins/
│           └── test_ma_cross.py  # MACrossStrategy 단위 테스트
├── specs/
│   ├── 2026-06-18-quanteo-architecture.md  # 확정 아키텍처 설계서 (단일 진실 공급원)
│   ├── tasks.md                             # T001~T038 구현 작업 목록
│   └── 2026-06-18-estimation.md            # Phase별 구현 견적
├── CLAUDE.md
├── pyproject.toml
└── README.md
```

---

## 🚀 Entry Points

| 파일                        | 용도                                                 |
| --------------------------- | ---------------------------------------------------- |
| `core/app.py`               | 메인 봇 프로세스 진입점 (asyncio.TaskGroup)          |
| `core/api/app.py`           | FastAPI Control API 앱 팩토리                        |
| `uv run python -m core.app` | CLI 실행 (--env, --port, --with-trading 플래그 지원) |

---

## 📦 Core Modules

| 모듈              | 경로                                | 상태    | 책임                                                              |
| ----------------- | ----------------------------------- | ------- | ----------------------------------------------------------------- |
| Config            | `core/config/settings.py`           | ✅ 완료 | `kis_devlp.yaml` 로딩, env/market 분기                            |
| KIS Auth          | `core/adapters/kis/auth.py`         | ✅ 완료 | access token 발급·캐싱·재발급, WS 접속키                          |
| KIS REST          | `core/adapters/kis/rest.py`         | ✅ 완료 | 현재가/잔고 조회 + 매수/매도 주문 REST 호출                       |
| KIS WebSocket     | `core/adapters/kis/ws.py`           | ✅ 완료 | 실시간 시세/체결 WebSocket 구독                                   |
| TR_ID 매핑        | `core/adapters/kis/tr_ids.py`       | ✅ 완료 | 환경×시장 TR_ID·도메인 매핑 테이블                                |
| State Store       | `core/store/`                       | ✅ 완료 | SQLite OLTP (positions/orders/fills/signals/logs)                 |
| Market Data       | `core/marketdata/`                  | ✅ 완료 | Tick/Quote/Candle 정규화·공급                                     |
| Event Bus         | `core/events/bus.py`                | ✅ 완료 | asyncio.Queue pub/sub, sync/async 핸들러 지원                     |
| Notifier          | `core/notifier/`                    | ✅ 완료 | Telegram/Mock 알림, Event Bus 구독 연결                           |
| Strategy Protocol | `core/strategy/base.py`             | ✅ 완료 | Strategy Protocol, Signal(frozen), MarketContext                  |
| Strategy Engine   | `core/strategy/engine.py`           | ✅ 완료 | 플러그인 관리, 캔들 버퍼, warmup 실패 격리                        |
| Backtest Harness  | `core/strategy/harness.py`          | ✅ 완료 | 경량 백테스트 (research-to-live parity)                           |
| MA Cross Strategy | `core/strategy/plugins/ma_cross.py` | ✅ 완료 | 이동평균 교차 전략 플러그인                                       |
| Risk Manager      | `core/risk/manager.py`              | ✅ 완료 | 한도(종목/일일/총 노출)·킬스위치·손절/익절                        |
| Order Executor    | `core/execution/executor.py`        | ✅ 완료 | 주문 전송·체결 추적·멱등성(client_order_id)                       |
| Control API       | `core/api/`                         | ✅ 완료 | FastAPI REST (status/positions/orders/control) + WebSocket 스트림 |

---

## 🌐 Control API 엔드포인트 (Phase 5)

| 메서드      | 경로              | 설명                                          |
| ----------- | ----------------- | --------------------------------------------- |
| `GET`       | `/status`         | 봇 상태·halt_level·env·uptime 조회            |
| `GET`       | `/positions`      | 보유 포지션 목록 (qty > 0)                    |
| `GET`       | `/orders`         | 주문 내역 (status 필터, limit 파라미터)       |
| `POST`      | `/control/pause`  | 신규 포지션 진입 중단 (기존 포지션 유지)      |
| `POST`      | `/control/resume` | 일시정지 → 정상 운영 복귀                     |
| `POST`      | `/control/kill`   | 모든 신규 주문 차단 (재시작으로만 해제)       |
| `WebSocket` | `/stream`         | EventBus 실시간 브로드캐스트 + 30초 heartbeat |

---

## 🔧 Configuration

| 파일             | 위치            | 비고                                                |
| ---------------- | --------------- | --------------------------------------------------- |
| `kis_devlp.yaml` | `~/KIS/config/` | **저장소 밖, 커밋 금지.** 앱키/시크릿/계좌/Telegram |
| `pyproject.toml` | 프로젝트 루트   | uv 환경, Python 3.12+, 의존성 목록                  |

### 환경 구분 (절대 혼동 금지)

| 환경   | 의미                     | 기본값                       |
| ------ | ------------------------ | ---------------------------- |
| `vps`  | 모의투자 (paper trading) | 기본                         |
| `prod` | 실전투자 (실제 돈)       | 명시 플래그 + 이중 확인 필요 |

---

## 📚 Documentation

| 파일                                       | 내용                                           |
| ------------------------------------------ | ---------------------------------------------- |
| `specs/2026-06-18-quanteo-architecture.md` | 확정 아키텍처 설계서. 구현의 단일 진실 공급원. |
| `specs/tasks.md`                           | T001~T038 구현 작업 목록. Phase 단위 진행.     |
| `CLAUDE.md`                                | Claude Code 작업 지침 (KIS API 핵심 개념 포함) |

---

## 🧪 Test Coverage

| 대상 모듈        | 테스트 파일                                    |
| ---------------- | ---------------------------------------------- |
| KIS Adapter      | `tests/adapters/kis/` (auth/rest/tr_ids/ws)    |
| Config           | `tests/config/test_settings.py`                |
| Event Bus        | `tests/events/test_bus.py`                     |
| Market Data      | `tests/marketdata/test_normalizer.py`          |
| Notifier         | `tests/notifier/` (6개 파일)                   |
| State Store      | `tests/store/test_db.py`                       |
| Risk Manager     | `tests/risk/test_manager.py`                   |
| Order Executor   | `tests/execution/test_executor.py`             |
| Integration      | `tests/integration/test_signal_to_order.py`    |
| Control API      | `tests/api/` (status/positions/orders/control) |
| Strategy Base    | `tests/strategy/test_base.py`                  |
| Strategy Engine  | `tests/strategy/test_engine.py`                |
| Backtest Harness | `tests/strategy/test_harness.py`               |
| MA Cross         | `tests/strategy/plugins/test_ma_cross.py`      |

**총 252 tests passed** (2026-06-24)

---

## 🔗 Key Dependencies

| 라이브러리   | 용도                                   |
| ------------ | -------------------------------------- |
| Python 3.12+ | 매매 코어 런타임                       |
| uv           | Python 패키지 매니저                   |
| FastAPI      | Control API 서버                       |
| uvicorn      | ASGI 서버 (asyncio 루프에 직접 임베드) |
| aiosqlite    | 비동기 SQLite (State Store)            |
| websockets   | KIS WebSocket 클라이언트               |
| aiogram v3   | Telegram 봇 알림                       |
| pydantic v2  | 설정 및 API 스키마 검증                |
| pytest       | 테스트 프레임워크                      |

---

## 📝 Quick Start

```bash
# Python 환경 설정
uv sync

# 전체 테스트
uv run pytest

# 단일 모듈 테스트
uv run pytest tests/api/

# 봇 실행 (모의투자 — Control API만)
uv run python -m core.app --env vps --port 8000

# 봇 실행 (트레이딩 모듈 포함 — KIS 자격증명 필요)
uv run python -m core.app --env vps --with-trading

# API 문서
open http://localhost:8000/docs
```

자격증명 설정: `~/KIS/config/kis_devlp.yaml` 에 앱키/시크릿/계좌번호/Telegram 토큰 입력 후 실행.

---

## 🌿 Branch Strategy

```
main
└── phase/{N}-{slug}       # Phase 통합 브랜치
    └── task/T{NNN}-{slug} # Task 작업 브랜치
```

커밋 형식: `<type>[scope]: <description>` — types: `feat`, `fix`, `test`, `refactor`, `docs`, `chore`, `perf`

---

## Safety Rules

1. 기본 환경은 항상 `vps`(모의투자)
2. 모든 주문은 반드시 Risk Manager 통과
3. `prod` 실전 전환은 명시 플래그 이중 확인
4. 자격증명은 저장소 밖 — 절대 커밋 금지
5. KIS Rate limit 준수 (Adapter 내 스로틀러, T029)
6. Telegram `enabled: false` 시 MockNotifier 자동 교체 (테스트 안전)
7. `/control/kill` 이후 pause/resume 차단 — 재시작으로만 해제
