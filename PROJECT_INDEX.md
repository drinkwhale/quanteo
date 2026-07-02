# Project Index: quanteo

Generated: 2026-07-02 (Phase 14 완료)

---

## 📋 Status

**Phase 1~14 전체 완료** — T001~T092 모든 구현 Task 완료.

| Phase    | Tasks     | 상태    | 내용                                                                                              |
| -------- | --------- | ------- | ------------------------------------------------------------------------------------------------- |
| **P1**   | T001–T005 | ✅ 완료 | 프로젝트 스캐폴드, 설정/환경 로딩, Toss 인증 기반                                                 |
| **P2**   | T006–T010 | ✅ 완료 | Market Data 수신·정규화, State Store, Event Bus                                                   |
| **P2.5** | T033–T038 | ✅ 완료 | Notifier 모듈 (Telegram + MockNotifier)                                                           |
| **P3**   | T011–T014 | ✅ 완료 | Strategy Protocol, Engine, MA Cross, Harness                                                      |
| **P4**   | T015–T020 | ✅ 완료 | Risk Manager + Order Executor (vps 주문)                                                          |
| **P5**   | T021–T024 | ✅ 완료 | Control API REST/WS + 전체 모듈 wiring                                                            |
| **P6**   | T025–T028 | ✅ 완료 | TypeScript 대시보드 (React+Vite+Tailwind)                                                         |
| **P7**   | T029–T032 | ✅ 완료 | Rate Limit 스로틀러·재시작 복구·prod 게이트·Docker                                                |
| **P8**   | T039–T048 | ✅ 완료 | BrokerAdapter Protocol + Toss증권 REST 어댑터 + REST 폴링 MarketDataFeed·테스트                   |
| **P9**   | T049–T056 | ✅ 완료 | Toss 어댑터 운영 완성 (15개 엔드포인트) + Control API 확장 + 대시보드 3탭 UI                      |
| **P10**  | T057–T068 | ✅ 완료 | 정보 수집·알람 서브시스템 (뉴스·환율·실적·경제지표·AI필터·Google Calendar)                        |
| **P11**  | T069–T072 | ✅ 완료 | CCI 지표 + 멀티 타임프레임 방향 판정 엔진                                                         |
| **P12**  | T073–T076 | ✅ 완료 | 박병창 매매기법 전략 플러그인 (매수3원칙·매도2원칙·장중4유형·CCI+BBC 통합)                        |
| **P13**  | T077–T083 | ✅ 완료 | 백테스트 프레임워크 (엔진·메트릭·데이터소스·Walk-Forward·헤드앤숄더·API·대시보드UI)               |
| **P14**  | T084–T092 | ✅ 완료 | 프론트엔드 디자인 시스템 정비 (CSS 토큰 공식화·접근성 WCAG 2.1 AA·ConfirmDialog·shadcn/ui 초기화) |

**테스트:** 644 passed (Python) · TypeScript build clean (2026-07-02 기준, shadcn/ui `radix-nova` 프리셋 적용)

---

## 📁 Project Structure (현재)

```
quanteo/
├── core/
│   ├── adapters/
│   │   ├── base.py           # BrokerAdapter·MarketPoller Protocol (typing.Protocol)
│   │   ├── models.py         # 공통 어댑터 모델 (OrderAck 등)
│   │   ├── throttler.py      # FixedIntervalThrottler + 지수 백오프 재시도
│   │   └── toss/             # Toss증권 구현체 (REST only, KIS 완전 제거)
│   │       ├── auth.py       # OAuth2 Client Credentials, 토큰 캐시, 401 재발급
│   │       ├── models.py     # 도메인 타입 (BuyingPowerInfo/TossOrder/Fill/PriceLimits/StockInfo/ExchangeRate/TossCandle 등)
│   │       └── rest.py       # 20개 엔드포인트: 시세·잔고·주문CRUD·체결·캘린더·종목정보·환율·캔들
│   ├── api/                  # Control API (FastAPI)
│   │   ├── app.py            # create_app() 팩토리
│   │   ├── deps.py           # AppContainer 의존성 주입 (broker: TossRestClient|None 포함)
│   │   ├── models.py         # BotStatus/PositionList/OrderList/FillList/MarketStatus/RiskMetrics
│   │   └── routes/
│   │       ├── status.py     # GET /status
│   │       ├── positions.py  # GET /positions
│   │       ├── orders.py     # GET /orders, POST /orders/{id}/cancel, POST /orders/{id}/modify
│   │       ├── control.py    # POST /control/pause|resume|kill
│   │       ├── stream.py     # WS /stream (Event Bus 브로드캐스트)
│   │       ├── market.py     # GET /market-status, GET /risk-metrics
│   │       ├── trades.py     # GET /trades (체결 내역)
│   │       └── backtest.py  # POST /backtest/run, GET /backtest/status|results (Phase 13)
│   ├── config/settings.py    # AppSettings (Pydantic), quanteo.yaml 로딩
│   ├── events/
│   │   ├── bus.py            # EventBus (asyncio.Queue pub/sub)
│   │   └── types.py          # Event, EventType 정의
│   ├── execution/executor.py # OrderExecutor (주문전송·체결추적·멱등성)
│   ├── marketdata/
│   │   ├── feed.py           # MarketDataFeed (REST 폴링, Toss용)
│   │   ├── models.py         # Tick, Quote, Candle 내부 표준 타입
│   │   └── normalizer.py     # Toss JSON → 내부 표준 정규화
│   ├── notifier/
│   │   ├── base.py           # Notifier Protocol, NotifyEvent, NotifyLevel
│   │   ├── telegram.py       # TelegramNotifier (aiogram v3, asyncio.Queue Rate limit)
│   │   ├── mock.py           # MockNotifier (테스트용)
│   │   ├── templates.py      # 이벤트별 메시지 템플릿
│   │   ├── factory.py        # enabled 여부로 Telegram/Mock 선택
│   │   └── wiring.py         # Event Bus → Notifier 구독 연결
│   ├── risk/
│   │   ├── manager.py        # RiskManager (한도가드·손절익절·킬스위치)
│   │   └── models.py         # HaltLevel, Order, Rejection 등
│   ├── store/
│   │   ├── db.py             # StateStore (aiosqlite CRUD + 재시작 복구 메서드)
│   │   └── schema.py         # DDL (positions/orders/fills/signals/events_log)
│   ├── strategy/
│   │   ├── base.py           # Strategy Protocol (warmup/on_tick/on_candle)
│   │   ├── engine.py         # StrategyEngine (플러그인 로드·시그널 루프)
│   │   ├── harness.py        # BacktestHarness (과거 캔들로 시그널 검증)
│   │   ├── timeframe_judge.py  # 멀티 타임프레임 방향 판정 (Phase 11)
│   │   ├── indicators/
│   │   │   ├── cci.py            # CCI 계산 + 골든/데드크로스 감지
│   │   │   ├── ma.py             # 이동평균, 캔들 분류, 대형캔들 판정
│   │   │   └── head_shoulders.py # 헤드앤숄더 패턴 감지 (하락전환·상승전환, Phase 13)
│   │   └── plugins/
│   │       ├── ma_cross.py         # 이동평균 교차 전략 플러그인
│   │       ├── bbc_buy.py          # 박병창 매수 3원칙 (T073)
│   │       ├── bbc_sell.py         # 박병창 매도 2원칙·45도 하락 (T074)
│   │       ├── intraday_signal.py  # 장중 시그널 4유형·Look-ahead bias 방지 (T075)
│   │       └── cci_bbc_strategy.py # CCI+BBC 통합 전략·신뢰도 스코어링·H&S override (T076+T081)
│   ├── backtest/             # 백테스트 프레임워크 (Phase 13)
│   │   ├── engine.py         # BacktestEngine (룩어헤드 방지, 수수료·세금 정확 반영)
│   │   ├── metrics.py        # PerformanceMetrics (MDD·Sharpe·승률·수익률 계산)
│   │   ├── toss_data_source.py # BacktestDataSource Protocol + SQLite 캐시(TTL 24h)
│   │   └── walk_forward.py   # WalkForwardValidator (슬라이딩 윈도우, 과적합 감지 30%)
│   └── app.py                # 코어 부팅·asyncio.gather wiring + prod 게이트 + --with-info
├── info/                     # Phase 10: 정보 수집·알람 서브시스템 (선택 통합)
│   ├── ai_filter/
│   │   └── claude_filter.py  # ClaudeFilter (Haiku, CRITICAL_KEYWORDS 2단 필터, FilterResult)
│   ├── news/
│   │   ├── rss_collector.py  # RssCollector (SQLite dedup, asyncio.gather 병렬 수집)
│   │   ├── dart_collector.py # DartCollector (opendartreader, 공시 수집)
│   │   └── finnhub_collector.py  # FinnhubCollector + YahooRssCollector (429 백오프)
│   ├── fx/
│   │   ├── rate_monitor.py   # FxRateMonitor (yfinance, 0.0 가드, 임계값 알람)
│   │   ├── daily_report.py   # FxDailyReporter (16:00 마감 리포트)
│   │   └── rate_rule.py      # interpret_fx() 해석 함수
│   ├── calendar/
│   │   ├── google_cal.py     # GoogleCalendarClient (gcsa, 중복방지, 401/429 재시도)
│   │   ├── earnings_data.py  # EarningsEvent + EARNINGS_SCHEDULE (2026 H2 8종목)
│   │   └── macro_events.py   # MacroEvent + MACRO_SCHEDULE (FOMC/CPI/NFP/BOK/PMI 30개)
│   ├── telegram/
│   │   └── info_notifier.py  # InfoNotifier (5개 포맷 함수, DLQ, 3회 재시도)
│   ├── scheduler.py          # InfoScheduler (AsyncIOScheduler KST, 7개 잡)
│   └── main.py               # InfoSystem (DI 조립, start/stop, DLQ 재시도 루프)
├── dashboard/                # TypeScript 웹 대시보드
│   ├── src/
│   │   ├── api/
│   │   │   ├── client.ts     # REST fetch 래퍼 + WebSocket 팩토리
│   │   │   ├── types.ts      # BotStatus/PositionItem/OrderItem/StreamMessage 타입
│   │   │   └── backtest.ts   # 백테스트 API 클라이언트 + pollUntilDone (Phase 13)
│   │   ├── components/
│   │   │   ├── StatusBar.tsx      # 봇 상태 상단바 (halt_level·env·uptime)
│   │   │   ├── PositionsTable.tsx # 포지션 테이블
│   │   │   ├── OrdersTable.tsx    # 주문내역 테이블 + 취소 버튼
│   │   │   ├── FillsTable.tsx     # 체결 내역 테이블
│   │   │   ├── StreamLog.tsx      # 실시간 이벤트 로그 뷰
│   │   │   └── ControlPanel.tsx   # 일시정지/재개/킬스위치 UI
│   │   ├── hooks/
│   │   │   ├── useStatus.ts    # 3초 폴링
│   │   │   ├── usePositions.ts # 5초 폴링
│   │   │   ├── useOrders.ts    # 5초 폴링
│   │   │   ├── useFills.ts     # 10초 폴링
│   │   │   └── useStream.ts    # WebSocket + 3초 재연결
│   │   ├── pages/
│   │   │   └── Strategy.tsx  # 전략 모니터링 (CCI·신뢰도 게이지·시그널 토스트·백테스트 UI·킬스위치)
│   │   ├── App.tsx           # 4탭 레이아웃: 포지션·주문·체결·전략
│   │   └── main.tsx          # React 18 진입점
│   ├── vite.config.ts        # /api → localhost:8000 proxy
│   ├── tailwind.config.js    # 다크 트레이딩 테마
│   └── package.json          # React 18, Vite 5, TailwindCSS 3
├── scripts/
│   └── send_balance.py       # 잔고 조회 후 Telegram 전송 일회성 스크립트
├── Dockerfile                # 멀티스테이지 빌드 (builder/runtime, 비루트 유저)
├── .dockerignore             # 자격증명·테스트·대시보드 제외
├── docker-compose.yml        # vps 기본 실행, 볼륨 마운트, healthcheck
├── tests/                    # pytest (577 cases)
│   ├── adapters/toss/        # TossAuth (8) + TossRestClient (9) + Phase9 (24) 단위 테스트
│   ├── api/                  # Control API 엔드포인트 테스트 (market-status·trades 포함)
│   ├── config/, events/, execution/, marketdata/
│   ├── marketdata/test_feed_polling.py  # REST 폴링 MarketDataFeed 테스트
│   ├── notifier/             # Telegram·Mock·template·wiring 테스트
│   ├── risk/                 # RiskManager 한도·손절·킬스위치 테스트
│   ├── store/                # StateStore CRUD + 재시작 복구 테스트
│   ├── test_prod_gate.py     # prod 이중 확인 게이트 안전 테스트
│   ├── strategy/
│   │   ├── test_engine.py, test_harness.py
│   │   ├── indicators/       # CCI·MA 지표 단위 테스트 (Phase 11)
│   │   └── plugins/          # MA Cross·bbc_buy·bbc_sell·intraday_signal·cci_bbc_strategy 테스트 (Phase 12)
│   ├── integration/          # signal→risk→order 라운드트립 + Toss 라운드트립 테스트
│   └── conftest.py           # 공통 fixture (AppContainer mock, DB)
├── specs/
│   ├── tasks.md              # Phase·Task 체크박스 (구현 진척 관리)
│   ├── 2026-06-18-quanteo-architecture.md  # 확정 아키텍처 설계서
│   └── tossinvest/           # Toss증권 Open API JSON 스펙 (구현 참고)
│       ├── open-api.json     # 전체 OpenAPI 3.1 스펙 (20개 엔드포인트)
│       ├── auth.json         # OAuth2 토큰 발급
│       ├── account.json      # 계좌·잔고·매수가능금액·판매가능수량
│       ├── order.json        # 주문 생성·취소·정정
│       ├── order-info.json   # 주문 단건·목록 조회
│       ├── order-history.json # 주문 이력 조회
│       ├── market-data.json  # 현재가·캔들·호가·체결내역·환율
│       ├── market-info.json  # 상하한가·수수료·마켓 캘린더(KR/US)
│       ├── stock-info.json   # 종목 기본 정보
│       └── asset.json        # 자산 포트폴리오
├── pyproject.toml            # uv 프로젝트 설정, 의존성, ruff/pytest 설정
├── quanteo.yaml.example      # 자격증명 예시 (실제 파일은 저장소 밖: ~/quanteo/config/quanteo.yaml)
└── CLAUDE.md                 # Claude Code 세션 지침
```

---

## 🚀 Quick Start

```bash
# Python 코어
uv sync
uv run python -m core.app                              # vps(모의투자), Control API만
uv run python -m core.app --with-trading               # 시장데이터·전략·주문 포함
uv run python -m core.app --with-info                  # 정보 수집·알람 서브시스템 포함
uv run python -m core.app --env prod --i-understand-real-money  # 실전 (이중 확인 필수)
uv run pytest                                          # 테스트 (393 cases)
uv run ruff check . && ruff format .                   # 린트·포맷

# Docker
docker compose up                                      # vps 환경 컨테이너 실행
docker compose up --build                              # 이미지 재빌드 후 실행

# TypeScript 대시보드 (별도 터미널)
cd dashboard && npm install
npm run dev    # http://localhost:5173 (API 프록시 → :8000)
npm run build  # 프로덕션 빌드
```

---

## 🔌 Control API 엔드포인트

| Method | Path                         | 설명                                       |
| ------ | ---------------------------- | ------------------------------------------ |
| GET    | `/status`                    | 봇 상태 (halt_level·env·uptime)            |
| GET    | `/positions`                 | 보유 포지션 목록                           |
| GET    | `/orders`                    | 주문 내역                                  |
| POST   | `/orders/{id}/cancel`        | 주문 취소                                  |
| POST   | `/orders/{id}/modify`        | 주문 정정                                  |
| GET    | `/trades`                    | 체결 내역 조회                             |
| GET    | `/market-status`             | 국내·해외 개장 여부 + 캘린더               |
| GET    | `/risk-metrics`              | 리스크 지표 (halt_level·buying_power)      |
| POST   | `/control/pause`             | 일시정지                                   |
| POST   | `/control/resume`            | 재개                                       |
| POST   | `/control/kill`              | 킬스위치 활성화                            |
| WS     | `/stream`                    | Event Bus 실시간 브로드캐스트              |
| POST   | `/backtest/run`              | 백테스트 비동기 실행 → run_id 반환 (202)   |
| GET    | `/backtest/status/{run_id}`  | 실행 상태 조회 (running/completed/failed)  |
| GET    | `/backtest/results/{run_id}` | 결과 조회 (PerformanceMetrics·에쿼티 커브) |

---

## 📦 핵심 의존성

### Python

| 패키지                | 용도                         |
| --------------------- | ---------------------------- |
| `fastapi` + `uvicorn` | Control API 서버             |
| `httpx`               | Toss REST 호출 (OAuth2 포함) |
| `pydantic v2`         | 설정·모델 검증               |
| `aiosqlite`           | State Store (SQLite)         |
| `aiogram v3`          | Telegram 알림                |

### TypeScript (dashboard)

| 패키지                   | 용도                    |
| ------------------------ | ----------------------- |
| `react 18` + `react-dom` | UI 렌더링               |
| `vite 5`                 | 빌드·dev proxy          |
| `tailwindcss 3`          | 다크 트레이딩 UI 스타일 |
| `typescript 5`           | 타입 안전성             |

---

## 🔒 보안 원칙

- `quanteo.yaml` (`~/quanteo/config/quanteo.yaml`) 및 `~/toss/cache/token.json` — 저장소 밖, 절대 커밋 금지.
- 기본 환경 `vps` (모의투자). `prod` 실전은 `--i-understand-real-money` 이중 확인 필수.
- 모든 주문 경로는 RiskManager 통과 필수.
- Rate Limit: `MARKET_DATA`(시세·잔고)·`ORDER`(주문) 그룹별 별도 스로틀러 버킷 (`core/adapters/throttler.py`).
- 재시작 복구: `StateStore.get_open_positions()` / `get_pending_orders()` 로 직전 상태 로드.

---

## 📝 주요 설계 결정

- **asyncio 단일 이벤트 루프**: 스레드 없이 `asyncio.gather()`로 모든 I/O 병렬화
- **단방향 흐름**: MarketData → Strategy → RiskManager → OrderExecutor
- **BrokerAdapter Protocol**: `core/adapters/base.py` — 브로커 교체해도 상위 모듈 변경 없음
- **Toss 단일 브로커**: KIS 완전 제거. `core/adapters/toss/`만 유지.
- **WebSocket 대신 REST 폴링**: Toss API WS 미지원 → `feed.py`가 2초 간격으로 `GET /api/v1/prices` 배치 조회
- **플러그인 교체형 전략**: `strategy/plugins/`에 파일 추가 + 설정으로 활성화
- **단계적 킬스위치**: NONE → REDUCE → PAUSE → KILL 4단계
