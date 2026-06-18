# quanteo 구현 워크플로 계획

- **생성일:** 2026-06-18
- **전략:** systematic / depth: deep
- **기준 문서:** [specs/2026-06-18-estimation.md](../specs/2026-06-18-estimation.md), [specs/tasks.md](../specs/tasks.md), [specs/2026-06-18-quanteo-architecture.md](../specs/2026-06-18-quanteo-architecture.md)
- **범위:** T001–T038 (8개 Phase, 38개 Task)

> **이 문서는 계획 전용이다. 구현 실행은 `/sc:implement` 또는 "T{번호}까지 진행해줘"로 별도 요청.**

---

## 1. 전체 의존성 맵

```
T001 (pyproject.toml)
  └─ T002 (config)
       ├─ T003 (auth REST token)
       │    └─ T004 (auth WS key)
       │         └─ T005 (TR_ID 매핑)
       │              ├─ T007 (REST 시세/잔고)
       │              ├─ T008 (WS 구독)
       │              └─ T019 (주문 REST 호출)
       └─ T005 (TR_ID 매핑) ──────────────────┐
                                               │
T001                                           │
  └─ T006 (SQLite 스키마)                      │
       └─ T018 (Order Executor)◄───────────────┤
                                               │
T008 → T009 (시세 정규화)                     │
T006 + T009 → T010 (Event Bus)                │
T010 + T009 → T011 (Strategy Protocol)        │
T011 → T012 (Strategy Engine)                 │
T012 → T013 (첫 플러그인)                     │
T013 → T014 (검증 하니스)                     │
                                               │
T010 → T033 (Notifier Protocol) ──P2.5         │
T033 → T034 (TelegramNotifier)                 │
T033 → T035 (MockNotifier)                     │
T033 → T036 (메시지 템플릿)                   │
T034 + T035 + T036 + T010 → T037              │
T037 → T038                                   │
                                               │
T014 → T015 (Risk 한도 가드)                  │
T015 → T016 (손절/익절)                       │
T016 → T017 (킬스위치)                        │
T017 + T018 + T005 → T019 ────────────────────┘
T019 → T020 (vps 통합 테스트)   ← MVP 완료 게이트

T020 → T021 (Control API /status 등)
T021 → T022 (/control endpoints)
T022 → T023 (/stream WS)
T023 → T024 (app.py 조립)

T024 → T025 (Dashboard 스캐폴드)
T025 → T026 (포지션/손익 화면)
T025 → T027 (WS 스트림 + 로그)
T026 + T027 → T028 (제어 UI)

T020 → T029 (Rate limit 스로틀러)   ─┐ P7 병렬 가능
T030 (재시작 복구) ──────────────────┤
T031 (prod 게이트) ──────────────────┤
T032 (Dockerfile) ───────────────────┘
```

---

## 2. 브랜치 전략

```
main
├── phase/1-bootstrap         T001–T005
│   ├── task/T001-scaffold
│   ├── task/T002-config
│   ├── task/T003-auth-rest
│   ├── task/T004-auth-ws
│   └── task/T005-trid-map
├── phase/2-marketdata         T006–T010
├── phase/2.5-telegram         T033–T038
├── phase/3-strategy           T011–T014
├── phase/4-risk-order         T015–T020
├── phase/5-control-api        T021–T024
├── phase/6-dashboard          T025–T028
└── phase/7-safety-ops         T029–T032
```

- phase 브랜치: `phase/{번호}-{slug}`
- task 브랜치: `task/T{번호}-{slug}` (phase 브랜치 기반 체크아웃)
- task → phase 브랜치로 merge (squash 권장)
- phase 완료 후 main으로 merge PR

---

## 3. TDD 원칙 (모든 Task 공통)

각 Task 구현 전 아래 순서를 지킨다:

```
1. RED   — 빈 구현에 대한 실패 테스트 작성 후 실행 확인
2. GREEN — 최소 구현으로 테스트 통과
3. CHECK — uv run pytest --cov 로 커버리지 80%+ 확인
4. REFACTOR — 코드 정리, 커버리지 유지
```

KIS API 호출이 포함된 Task는 반드시 `MockKISAdapter`로 단위 테스트를 먼저 구성하고, 통합 테스트는 vps 장 운영 시간(주중 09:00–15:30 KST)에 별도 실행한다.

---

## 4. Phase별 상세 워크플로

---

### Phase 1 — 부트스트랩 & 인증 (T001–T005)

**예상 공수:** 14–20h | **브랜치:** `phase/1-bootstrap`

#### 진입 조건

- [ ] `~/KIS/config/kis_devlp.yaml` 에 vps 앱키/시크릿/계좌번호 준비됨
- [ ] Python 3.11+ 및 uv 설치 확인

#### 실행 순서

```
T001 → T002 → T003 → T004 → T005
  (순차 필수 — 각 단계가 다음 단계의 기반)
```

**T001 — pyproject.toml + 스캐폴드**

- 생성 파일: `pyproject.toml`, `core/__init__.py`, `tests/__init__.py`, `.env.example`, `Makefile`
- 의존성 초기 목록: `fastapi`, `uvicorn`, `aiohttp`, `websockets`, `pyyaml`, `pydantic`, `pytest`, `pytest-asyncio`, `pytest-cov`
- 테스트: `tests/test_scaffold.py` — import core 모듈 성공 확인
- 커밋: `feat: initialize project scaffold with uv and pyproject.toml`

**T002 — core/config/**

- 파일: `core/config/__init__.py`, `core/config/loader.py`, `core/config/models.py`
- `AppConfig(BaseModel)`: env(vps|prod), market(domestic|overseas), kis_config_path
- `KISConfig`: app_key, app_secret, account_no, account_product_code, hts_id, user_agent
- 기본값: `env=vps` (절대 prod 기본값 금지)
- 테스트: 픽스처 yaml로 로딩 성공 + env=prod 시 명시 플래그 없으면 거부 확인
- 커밋: `feat: add config loader with vps-default and prod guard`

**T003 — auth.py REST 토큰**

- 파일: `core/adapters/kis/auth.py`
- `get_access_token(config: KISConfig) -> str`: POST 발급, 만료 전 재사용, 만료 시 재발급
- 토큰 캐시: 메모리(앱 수명 동안) + 선택적 파일캐시(저장소 밖 경로)
- 테스트: `MockHTTPSession` 으로 발급·캐시·재발급 3케이스
- 커밋: `feat: implement KIS REST access token issuance with caching`

**T004 — auth.py WS 접속키**

- T003과 같은 파일, `get_ws_approval_key(config, access_token) -> str` 추가
- 테스트: mock으로 WS key 발급 + 토큰 만료 시 재발급 체인 확인
- 커밋: `feat: add WebSocket approval key issuance to auth module`

**T005 — TR_ID + 도메인 매핑**

- 파일: `core/adapters/kis/trid.py`
- 구조: `Endpoint(domain: str, tr_id: str)` Dataclass
- 매핑 테이블: `{(env, market, operation) → Endpoint}` 딕셔너리
- 포함 항목: 현재가 조회, 잔고 조회, 매수 주문, 매도 주문, WS 실시간 시세 (domestic/overseas × prod/vps)
- 테스트: 전체 조합 키 존재 확인, 존재하지 않는 조합 → `KeyError` 명시
- 커밋: `feat: define TR_ID and domain mapping table for all env/market combinations`

#### 검증 게이트 (Phase 1 완료 기준)

- [ ] `uv run pytest tests/unit/phase1/ --cov=core/config --cov=core/adapters/kis --cov-fail-under=80`
- [ ] `uv run python -c "from core.config import load_config; print(load_config())"` — 에러 없이 실행
- [ ] KIS vps 토큰 발급 수동 검증 (24시간 가능, 장 외 시간도 OK)
- [ ] `.gitignore`에 `*.yaml`, `token_cache*`, `.env` 포함 확인

---

### Phase 2 — 시세 & 상태저장 (T006–T010)

**예상 공수:** 20–30h | **브랜치:** `phase/2-marketdata`

#### 진입 조건

- [ ] Phase 1 검증 게이트 통과
- [ ] KIS vps 토큰 발급 수동 확인 완료

#### 실행 순서

```
T006 ──────────┐
               ├─ (병렬 가능) → T009 → T010
T007 + T008 ──┘
```

**T006 — SQLite 스키마**

- 파일: `core/store/__init__.py`, `core/store/schema.py`, `core/store/migrate.py`
- 테이블: `positions`, `orders`, `fills`, `signals`, `settings`, `events_log`
- 마이그레이션: 버전 테이블 + up/down 함수
- 테스트: 인메모리 SQLite로 테이블 생성·삽입·조회 확인
- 커밋: `feat: define SQLite schema with migration support`

**T007 — REST 현재가/잔고 조회**

- 파일: `core/adapters/kis/rest.py`
- `get_price(ticker, config, env) -> PriceData`: TR_ID 분기 포함
- `get_balance(config, env) -> BalanceData`
- 테스트: MockHTTPSession 으로 응답 파싱·필드 매핑 확인
- 커밋: `feat: implement KIS REST price and balance query`

**T008 — WebSocket 구독**

- 파일: `core/adapters/kis/ws.py`
- `KISWebSocket`: `connect()`, `subscribe(ticker)`, `unsubscribe(ticker)`, `_recv_loop()`
- 재연결 로직: 지수 백오프 (1s, 2s, 4s, max 30s)
- 테스트: aiohttp mock으로 연결·구독·메시지 수신·재연결 시나리오
- 커밋: `feat: implement KIS WebSocket client with reconnect backoff`

**T009 — 시세 정규화**

- 파일: `core/marketdata/__init__.py`, `core/marketdata/models.py`, `core/marketdata/normalizer.py`
- 타입: `Tick(ticker, price, volume, timestamp)`, `Quote(...)`, `Candle(open, high, low, close, volume, ...)`
- `normalize_tick(raw_kis_msg) -> Tick`
- 테스트: KIS raw 메시지 샘플로 정규화 결과 검증 (domestic/overseas 각 1건 이상)
- 커밋: `feat: normalize KIS raw market data to Tick/Quote/Candle`

**T010 — Event Bus**

- 파일: `core/events/__init__.py`, `core/events/bus.py`
- `EventBus`: `publish(event_type, payload)`, `subscribe(event_type, handler)`
- asyncio 기반 (`asyncio.Queue` + Task per subscriber)
- 테스트: 복수 구독자 수신, 미구독 이벤트 무시, 핸들러 예외 격리
- 커밋: `feat: implement asyncio event bus with pub/sub`

#### 검증 게이트 (Phase 2 완료 기준)

- [ ] `uv run pytest tests/unit/phase2/ --cov-fail-under=80`
- [ ] KIS vps 현재가 조회 수동 확인 (주중 장 시간 내)
- [ ] KIS vps WS 시세 수신 10초 구독 수동 확인
- [ ] Event Bus publish → subscribe 수동 smoke 테스트

---

### Phase 2.5 — Telegram 알림 (T033–T038)

**예상 공수:** 11–18h | **브랜치:** `phase/2.5-telegram`

#### 진입 조건

- [ ] T010 (Event Bus) 완료

#### 실행 순서

```
T033 → (T034 ∥ T035 ∥ T036) → T037 → T038
         병렬 가능 (모두 T033 Protocol 구현체)
```

**T033 — Notifier Protocol**

- 파일: `core/notifier/base.py`
- `NotifyLevel(Enum)`: DEBUG, INFO, WARNING, ERROR, KILL
- `NotifyEvent(level, title, body, ticker?, pnl?)`: Dataclass
- `Notifier(Protocol)`: `async def send(event: NotifyEvent) -> None`
- 테스트: Protocol 준수 여부 타입 체크 (`typing.runtime_checkable` 활용)
- 커밋: `feat: define Notifier Protocol and NotifyEvent types`

**T034 — TelegramNotifier** _(T033 완료 후)_

- 파일: `core/notifier/telegram.py`
- aiogram v3 Bot 클라이언트 사용
- `asyncio.PriorityQueue`: KILL/ERROR 우선, 나머지 FIFO
- rate limit: 최소 1초 간격 (`asyncio.sleep(1)` after send)
- 반복 오류 30초 디바운스: 동일 오류 30초 내 재발송 억제
- 테스트: MockBot 으로 우선순위 순서 보장·rate limit 인터벌·디바운스 확인
- 커밋: `feat: implement TelegramNotifier with priority queue and rate limit`

**T035 — MockNotifier** _(T033 완료 후, T034와 병렬)_

- 파일: `core/notifier/mock.py`
- `MockNotifier`: `sent_events: list[NotifyEvent]` 누적, `async send()` 즉시 반환
- 테스트용 assertion helper: `assert_sent(level, title_contains)`
- 커밋: `feat: add MockNotifier for test and offline environments`

**T036 — 메시지 템플릿** _(T033 완료 후, T034와 병렬)_

- 파일: `core/notifier/templates.py`
- 이벤트별 포맷: Signal / Order / Fill / Risk / Error / Status
- `format_event(event: NotifyEvent) -> str` — 마크다운 포맷
- 테스트: 각 이벤트 타입별 최소 1개 스냅샷 테스트
- 커밋: `feat: add message templates for all notify event types`

**T037 — Event Bus 연결 + app.py 통합**

- `core/notifier/__init__.py`: `NotifierBridge(bus, notifier)` — 주요 이벤트 구독 → NotifyEvent 변환·발송
- `core/app.py` 최초 생성: `asyncio.gather(notifier.run(), ...)` 골격
- 테스트: MockNotifier + MockEventBus 로 이벤트 → 알림 변환 end-to-end 확인
- 커밋: `feat: wire notifier to event bus and create app.py skeleton`

**T038 — kis_devlp.yaml telegram 섹션 + MockNotifier 폴백**

- `kis_devlp.yaml` 스펙에 telegram 섹션 추가:
  ```yaml
  telegram:
    enabled: false
    bot_token: ""
    chat_id: ""
  ```
- `NotifierFactory.create(config) -> Notifier`: enabled=false → MockNotifier 자동 교체
- 테스트: enabled=false → MockNotifier 반환, enabled=true → TelegramNotifier 반환
- 커밋: `feat: add telegram config section and auto-fallback to MockNotifier`

#### 검증 게이트 (Phase 2.5 완료 기준)

- [ ] `uv run pytest tests/unit/phase2_5/ --cov-fail-under=80`
- [ ] `enabled: true` 상태로 실제 Telegram 채널에 STATUS 메시지 수신 수동 확인
- [ ] `enabled: false` 상태로 MockNotifier만 동작 확인
- [ ] KILL 이벤트가 INFO보다 먼저 전송됨을 priority queue 테스트로 확인

---

### Phase 3 — 전략 엔진 (T011–T014)

**예상 공수:** 15–23h | **브랜치:** `phase/3-strategy`

#### 진입 조건

- [ ] Phase 2 검증 게이트 통과

#### 실행 순서

```
T011 → T012 → T013 → T014
  (순차 필수 — Protocol → Engine → Plugin → Harness)
```

**T011 — Strategy Protocol**

- 파일: `core/strategy/base.py`
- `Signal(ticker, direction, confidence, strategy_name, timestamp)`: Dataclass
- `Strategy(Protocol)`: `name: str`, `async on_tick(tick: Tick) -> Signal | None`
- 커밋: `feat: define Strategy Protocol and Signal type`

**T012 — Strategy Engine**

- 파일: `core/strategy/engine.py`
- `StrategyEngine`: `register(strategy)`, `async run()` — 마켓 데이터 구독 → 플러그인 호출 → Signal 발행
- 플러그인 로드: `importlib` 동적 로드
- 테스트: 2개 MockStrategy 등록 후 Tick 공급 → Signal 발행 순서 확인
- 커밋: `feat: implement strategy engine with plugin dispatch loop`

**T013 — 첫 플러그인 (이동평균 교차)**

- 파일: `core/strategy/plugins/ma_crossover.py`
- 파라미터: `fast_period`, `slow_period` (설정 주입)
- `on_tick()`: 골든크로스 → BUY, 데드크로스 → SELL, 중립 → None
- 테스트: 단조 상승 시계열, 크로스 시점, 히스토리 부족 시 None
- 커밋: `feat: add moving average crossover strategy plugin`

**T014 — 검증 하니스**

- 파일: `core/strategy/harness.py` + `scripts/run_harness.py`
- 과거 캔들 CSV/JSON 로드 → Signal 목록 + 가상 손익 요약 출력
- KIS 실데이터 불필요 (오프라인 동작)
- 커밋: `feat: add strategy validation harness for offline backtesting`

#### 검증 게이트 (Phase 3 완료 기준)

- [ ] `uv run pytest tests/unit/phase3/ --cov-fail-under=80`
- [ ] `uv run python scripts/run_harness.py --data tests/fixtures/sample_candles.json` 에러 없이 실행
- [ ] 전략 시그널 → Telegram Signal 알림 수신 확인 (Phase 2.5 완료 전제)

---

### Phase 4 — 리스크 & 주문 실행 (T015–T020)

**예상 공수:** 25–37h | **브랜치:** `phase/4-risk-order`

> **가장 중요한 Phase.** 안전 로직 테스트 커버리지 목표 90%+.

#### 진입 조건

- [ ] Phase 3 검증 게이트 통과
- [ ] KIS vps 계좌 잔고 > 0

#### 실행 순서

```
T015 → T016 → T017 → T018 → T019 → T020
  (순차 필수 — 리스크 가드 없이 주문 코드 작성 금지)
```

**T015 — Risk Manager 한도 가드**

- 파일: `core/risk/manager.py`, `core/risk/limits.py`
- `RiskManager.check_order(signal, balance, positions) -> RiskResult`
- 테스트: 한도 이하 ALLOW, 한도 초과 DENY (종목당 금액·일일 주문수·총 노출 각각)
- 커밋: `feat: implement risk manager with position and order limits`

**T016 — 손절/익절 check_exit**

- 파일: `core/risk/exit.py`
- `check_exit(position, current_price, config) -> ExitSignal | None`
- 테스트: 손절 경계, 익절 경계, 중립 구간
- 커밋: `feat: add stop-loss and take-profit exit logic`

**T017 — 킬스위치/일시정지 상태 관리**

- 파일: `core/risk/state.py`
- `TradingState(Enum)`: RUNNING, PAUSED, KILLED
- `CircuitBreaker`: 졸업형 차단 REDUCE → PAUSE → KILL
- 테스트: 상태 전이 시퀀스, KILLED 상태에서 주문 시도 → DENY
- 커밋: `feat: implement graduated circuit breaker with kill switch`

**T018 — Order Executor**

- 파일: `core/execution/executor.py`
- `client_order_id`: `{ticker}-{timestamp}-{uuid4[:8]}` 포맷 (멱등성)
- 체결 추적: KIS Fill 수신 → `orders`, `fills` 테이블 갱신
- 테스트: 중복 제출 멱등성, 체결 수신 → DB 업데이트
- 커밋: `feat: implement order executor with idempotency and fill tracking`

**T019 — 매수/매도 주문 REST 호출**

- 파일: `core/adapters/kis/rest.py` (T007 확장)
- `place_order(ticker, side, qty, price, config, env) -> KISOrderResponse`
- TR_ID: domestic/overseas × prod/vps × buy/sell = 8개 조합 지원
- 커밋: `feat: implement buy/sell order REST calls with env-specific TR_IDs`

**T020 — vps 통합 테스트 (라운드트립)** ← **MVP 완료 게이트**

- 파일: `tests/integration/test_signal_to_order.py`
- 시나리오: MockStrategy 시그널 → RiskManager → OrderExecutor → KIS vps 주문 → Fill 수신
- 검증: `orders` 테이블 기록, `positions` 갱신, Telegram Fill 알림 수신
- 커밋: `test: add vps integration test for signal-to-order roundtrip (MVP gate)`

#### 검증 게이트 (Phase 4 완료 기준 = MVP 완료)

- [ ] `uv run pytest tests/unit/phase4/ --cov=core/risk --cov=core/execution --cov-fail-under=90`
- [ ] `uv run pytest tests/integration/test_signal_to_order.py` — KIS vps PASS
- [ ] KILLED 상태에서 주문 전송되지 않음 확인
- [ ] `prod` 실전 주문이 명시 플래그 없이 불가능함을 코드 레벨에서 확인

---

### Phase 5 — 제어 API (T021–T024)

**예상 공수:** 16–23h | **브랜치:** `phase/5-control-api`

#### 진입 조건

- [ ] Phase 4 MVP 게이트 통과

#### 실행 순서

```
T021 → T022 → T023 → T024
```

**T021 — 조회 엔드포인트**

- `GET /status`, `GET /positions`, `GET /orders`
- 테스트: TestClient로 응답 스키마 확인
- 커밋: `feat: add status, positions, orders query endpoints`

**T022 — 제어 엔드포인트**

- `POST /control/pause|resume|kill`
- 인증: Bearer `X-Control-Token` 헤더
- 테스트: 상태 전이 성공, 401, KILLED 후 resume 거부
- 커밋: `feat: add pause/resume/kill control endpoints with auth`

**T023 — WebSocket 스트림**

- `WS /stream`: 스냅샷 후 델타, `asyncio.Queue(maxsize=200)`, 30초 heartbeat
- 커밋: `feat: add WebSocket stream endpoint with snapshot-then-delta pattern`

**T024 — app.py 완성 (모듈 조립)**

- `asyncio.gather()`: KIS WS + Strategy Engine + Event Bus + Notifier + FastAPI
- graceful shutdown: SIGINT/SIGTERM → KILL → 포지션 저장 → 종료
- 커밋: `feat: wire all modules in app.py with graceful shutdown`

#### 검증 게이트 (Phase 5 완료 기준)

- [ ] `uv run pytest tests/unit/phase5/ --cov-fail-under=80`
- [ ] `uv run python core/app.py --env vps` 기동 후 `curl localhost:8000/status` PASS
- [ ] WS `/stream` 연결 후 시세 이벤트 수신 수동 확인

---

### Phase 6 — 대시보드 TypeScript (T025–T028)

**예상 공수:** 21–31h | **브랜치:** `phase/6-dashboard`

#### TS 스택 결정 (Phase 6 진입 전 확정)

| 옵션                                 | 권장 조건                        |
| ------------------------------------ | -------------------------------- |
| **Vite + React + TypeScript** (권장) | 내부 운영 도구, 번들 최소화 우선 |
| Next.js App Router                   | 외부 공개 UI, SEO 필요 시        |
| plain HTML + Alpine.js               | 빌드 회피, 초경량                |

#### 진입 조건

- [ ] Phase 5 검증 게이트 통과
- [ ] TS 스택 확정

#### 실행 순서

```
T025 → (T026 ∥ T027) → T028
```

**T025 — 대시보드 스캐폴드**

- `dashboard/` 디렉토리, Vite + React + TypeScript 초기화
- `dashboard/src/api/client.ts` Control API 클라이언트
- `useStream(url)` 훅: WS 연결·재연결·이벤트 파싱
- 커밋: `feat: scaffold TypeScript dashboard with Vite and API client`

**T026 — 포지션/손익/주문내역 화면**

- 컴포넌트: `PositionsTable`, `PnLSummary`, `OrdersHistory`
- 커밋: `feat: add positions, pnl summary, and orders history UI`

**T027 — WS 스트림 + 로그 뷰** _(T026과 병렬)_

- 컴포넌트: `StreamTicker`, `LogViewer`
- 커밋: `feat: add realtime stream ticker and log viewer`

**T028 — 제어 UI**

- 킬스위치 이중 확인 모달 포함
- 커밋: `feat: add pause/resume/kill control UI with confirmation modal`

#### 검증 게이트 (Phase 6 완료 기준)

- [ ] `pnpm build` 에러 없이 완료 (번들 < 150kb gzipped)
- [ ] 브라우저에서 포지션·주문·로그 화면 수동 확인
- [ ] PAUSE → RESUME → KILL 버튼 동작 수동 확인

---

### Phase 7 — 안전 & 운영 (T029–T032)

**예상 공수:** 16–23h | **브랜치:** `phase/7-safety-ops`

#### 진입 조건

- [ ] Phase 5 완료 (Phase 6과 병렬 진행 가능)

#### 실행 순서

```
T029 ∥ T030 ∥ T032   (병렬 가능)
T030 완료 후 → T031  (prod 게이트는 복구 후)
```

**T029 — Rate Limit 스로틀러**

- `core/adapters/kis/throttle.py`: KIS 호출 큐잉, 429 → 지수 백오프
- 커밋: `feat: add KIS rate limit throttler with exponential backoff`

**T030 — 재시작 복구**

- `core/store/recovery.py`: 기동 시 미체결 주문·포지션 복원
- 커밋: `feat: implement startup state recovery from State Store`

**T031 — prod 실전 게이트**

- `core/config/prod_gate.py`: env=prod 시 환경변수 + CLI 플래그 이중 확인
- 두 조건 모두 없으면 즉시 프로세스 종료
- 테스트: 조건 없이 → SystemExit, 두 조건 모두 → 통과
- 커밋: `feat: add prod confirmation gate with dual-flag requirement`

**T032 — Dockerfile**

- Python 3.11-slim, uv install, 비root 유저, `VOLUME /app/data`
- 커밋: `feat: add Dockerfile for containerized deployment`

#### 검증 게이트 (Phase 7 완료 기준 = 전체 완료)

- [ ] `uv run pytest tests/unit/phase7/ --cov-fail-under=80`
- [ ] prod 게이트 통합 테스트 PASS
- [ ] KIS vps 연속 10건 호출 → rate limit 에러 없이 완료
- [ ] 봇 재기동 후 이전 포지션 복원 수동 확인
- [ ] `docker build . && docker run --env QUANTEO_ENV=vps ...` 기동 확인

---

## 5. 크로스커팅 관심사

### 보안 체크리스트 (매 Phase 완료 시)

- [ ] `kis_devlp.yaml`, `token_cache*`, `.env` 커밋되지 않음
- [ ] `app_key`, `app_secret`, `bot_token` 소스코드 내 하드코딩 없음
- [ ] `git log -p | grep -i "app_key\|secret\|token"` 결과 없음

### KIS vps 테스트 스케줄

| Task                 | vps 장 시간 필요 여부   |
| -------------------- | ----------------------- |
| T003/T004 토큰 발급  | 불필요 (24시간)         |
| T007 REST 시세       | 필요                    |
| T008 WS 시세         | 필요 (장 중)            |
| T020 주문 라운드트립 | 필요 (장 중) — **핵심** |
| T029 Rate limit      | 불필요                  |

> 일정 계획 시 **월-금 오전 세션**을 통합 테스트 블록으로 예약할 것.

---

## 6. 마일스톤 체크포인트

| 마일스톤         | 기준 Task | 기대 시점    |
| ---------------- | --------- | ------------ |
| M1: 인증 동작    | T005      | Week 1       |
| M2: 시세 수신    | T010      | Week 2       |
| M3: 알림 동작    | T038      | Week 2–3     |
| M4: 전략 시그널  | T014      | Week 3       |
| **M5: MVP 완료** | **T020**  | **Week 3–5** |
| M6: 제어 API     | T024      | Week 5–6     |
| M7: 대시보드     | T028      | Week 6–8     |
| M8: prod 준비    | T032      | Week 8–10    |

---

## 7. 리스크 대응 절차

### R1: KIS WS 불안정 / TR_ID 오류

1. `open-trading-api` 공식 저장소 `examples_llm/`에서 최신 TR_ID 확인
2. `examples_user/domestic_stock_examples.py` 실행 흐름과 직접 대조
3. TR_ID 매핑 테이블(T005) 갱신 후 재테스트

### R2: asyncio + FastAPI WS 이벤트 루프 충돌

1. uvicorn `loop="asyncio"` 명시적 설정
2. `asyncio.run()` 대신 직접 `loop.run_until_complete(main())` 패턴
3. WS 핸들러를 별도 `asyncio.Task`로 격리

### R3: TS 스택 미확정으로 Phase 6 지연

- 즉시 결정: **Vite + React + TypeScript** (추가 검토 없이)

---

## 8. 다음 실행 단계

```
"Phase 1 진행해줘"   → T001–T005 자동 진행
"T001까지 진행해줘"  → T001 단일 Task 진행
```
