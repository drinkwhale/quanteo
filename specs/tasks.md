# quanteo 구현 작업 목록 (tasks.md)

- **설계 근거:** [specs/2026-06-18-quanteo-architecture.md](2026-06-18-quanteo-architecture.md)
- **브랜치 전략:** Feature Branch Workflow (phase 브랜치 → task 브랜치)
- **진행 규칙:** "T{번호}까지 진행해줘" / "Phase {번호} 진행해줘" 요청 시 `~/.claude/prompts/task-implementation-agent.md` 절차에 따라 자동 진행.
- **안전 원칙:** 모든 주문 경로는 기본 `vps`(모의투자). `prod`는 명시 플래그로만.

> 체크박스 규칙: 미완료 `[ ]` → 완료 `[x]`. 각 Task 완료 시 갱신.

---

## Phase 1 — 부트스트랩 & 인증

- [x] **T001** `pyproject.toml` 생성, uv 환경 구성, 기본 디렉토리 스캐폴드(`core/`, `tests/`)
- [x] **T002** `core/config/` — 환경(prod/vps)·시장(domestic/overseas) 설정 로딩, `kis_devlp.yaml` 읽기 (기본값 `vps`)
- [x] **T003** `core/adapters/kis/auth.py` — 앱키/시크릿으로 access token 발급·캐싱·재발급
- [x] **T004** `core/adapters/kis/auth.py` — WebSocket 접속키 발급(`auth_ws` 패턴)
- [x] **T005** TR_ID·REST/WS 도메인 매핑 테이블(환경×시장) 정의

## Phase 2 — 시세 & 상태저장

- [x] **T006** `core/store/` — SQLite 스키마(positions/orders/fills/signals/settings/events_log) + 마이그레이션
- [x] **T007** `core/adapters/kis/rest.py` — 현재가/잔고 조회 REST 호출
- [x] **T008** `core/adapters/kis/ws.py` — 실시간 시세/체결 WebSocket 구독
- [x] **T009** `core/marketdata/` — 수신 데이터를 내부 표준(Tick/Quote/Candle)으로 정규화·공급
- [x] **T010** `core/events/` — Event Bus(발행/구독) 구현

## Phase 2.5 — 알림 (Telegram)

- [x] **T033** `core/notifier/base.py` — `Notifier` Protocol 정의 + `NotifyEvent`·`NotifyLevel` 타입
- [x] **T034** `core/notifier/telegram.py` — `TelegramNotifier` 구현 (aiogram v3, asyncio.Queue 기반 Rate limit)
- [x] **T035** `core/notifier/mock.py` — `MockNotifier` 구현 (테스트용, `sent_events` 리스트 누적)
- [x] **T036** `core/notifier/templates.py` — 이벤트별 메시지 템플릿 (Signal/Order/Fill/Risk/Error/Status)
- [x] **T037** Event Bus 구독 연결 + `app.py` 통합 (`notifier.run()` asyncio.gather 추가)
- [x] **T038** `kis_devlp.yaml` 에 telegram 섹션 추가 + `enabled: false` 시 MockNotifier 자동 교체

## Phase 3 — 전략 엔진

- [x] **T011** `core/strategy/base.py` — Strategy 플러그인 인터페이스(Protocol) 정의
- [x] **T012** `core/strategy/engine.py` — 플러그인 로드·지표 갱신·시그널 생성 루프
- [x] **T013** `core/strategy/plugins/` — 첫 규칙 기반 지표 전략(예: 이동평균 교차) 구현
- [x] **T014** 전략 경량 검증 하니스(과거 캔들로 시그널 확인)

## Phase 4 — 리스크 & 주문 실행

- [x] **T015** `core/risk/` — Risk Manager: 한도(종목당 금액·일일 주문수·총 노출) 가드
- [x] **T016** `core/risk/` — 손절/익절 `check_exit` 로직
- [x] **T017** `core/risk/` — 킬스위치/일시정지 상태 관리
- [x] **T018** `core/execution/` — Order Executor: 주문 전송·멱등성(client_order_id)·체결 추적
- [x] **T019** `core/adapters/kis/rest.py` — 매수/매도 주문 REST 호출(환경별 TR_ID)
- [x] **T020** vps(모의투자) 통합 테스트: 시그널 → 리스크 → 주문 라운드트립

## Phase 5 — 제어 API

- [x] **T021** `core/api/` — FastAPI 앱 + `/status`, `/positions`, `/orders` 조회 엔드포인트
- [x] **T022** `core/api/` — `/control/pause|resume|kill` 명령 엔드포인트
- [x] **T023** `core/api/` — `/stream` WebSocket(시세·시그널·체결·로그 실시간)
- [x] **T024** `core/app.py` — 코어 부팅·이벤트 루프 조립(모든 모듈 wiring)

## Phase 6 — 대시보드 (TypeScript)

- [x] **T025** `dashboard/` — 프로젝트 스캐폴드(패키지 매니저 확정, Control API 클라이언트)
- [x] **T026** 포지션·손익·주문내역 화면
- [x] **T027** 실시간 스트림(WS) 연동 + 로그 뷰
- [x] **T028** 일시정지/재개/킬스위치 제어 UI

## Phase 7 — 안전 & 운영

- [x] **T029** Rate limit 스로틀러(KIS Adapter 내장) + 백오프
- [x] **T030** 재시작 복구: State Store에서 포지션/미체결 주문 복원
- [x] **T031** `prod` 실전 게이트(이중 확인 플래그) + 안전 게이트 테스트
- [x] **T032** 컨테이너화(Dockerfile) — 클라우드 확장 대비

---

## Phase 8 — Toss증권 어댑터 마이그레이션

> **목표:** KIS 어댑터를 Toss증권 Open API로 교체한다.
> 전략·리스크·이벤트·State Store·대시보드는 무수정. 어댑터 레이어와 시세 피드만 교체.
>
> **핵심 제약:** Toss API는 WebSocket 미지원(추후 지원 예정) → REST 폴링 방식으로 전환.
> **모의투자 구분 없음:** Toss는 단일 URL. `Env` 개념은 유지하되 Toss 어댑터는 항상 동일 엔드포인트 사용.
> **인증:** OAuth2 Client Credentials (`application/x-www-form-urlencoded`), `client_id` + `client_secret`.
> **계좌:** 앱 시작 시 `GET /api/v1/accounts` 호출 → `accountSeq` 획득 → 이후 `X-Tossinvest-Account` 헤더에 사용.

- [x] **T039** `BrokerAdapter` Protocol 도입 — `core/adapters/base.py`에 브로커 교체 가능 추상화 레이어 정의
  - `BrokerAdapter(Protocol)`: `get_price()`, `get_balance()`, `place_order()` 3개 메서드 선언 (Phase 9 T050에서 `cancel_order()` / `modify_order()` / `list_orders()` 추가 예정 — Protocol 확장 vs. TossRestClient 단독 구현 여부는 T050 시작 시 결정)
  - `MarketPoller(Protocol)`: `start()`, `stop()`, `subscribe(symbol)` — 폴링/WS 피드 추상화
  - `KisRestClient`와 `TossRestClient` 모두 이 Protocol을 만족하도록 타입 어노테이션 추가
  - `OrderAck.kis_order_id` → `broker_order_id` 필드명 변경 (하위 호환 property alias 유지)

- [x] **T040** `TossCredentials` 설정 + `core/config/settings.py` 업데이트
  - `TossCredentials(BaseModel)`: `client_id: str`, `client_secret: SecretStr`
  - `AppSettings`에 `broker: Literal["kis", "toss"] = "kis"` 필드 추가
  - `kis_devlp.yaml.example`에 `toss:` 섹션 예시 추가 (`client_id`, `client_secret`)
  - 설정 로딩 시 `broker` 값 기반으로 KIS 또는 Toss 자격증명 선택

- [x] **T041** `core/adapters/toss/auth.py` — Toss OAuth2 인증
  - `POST /oauth2/token` (`application/x-www-form-urlencoded`, `grant_type=client_credentials`)
  - 토큰 캐시: `~/toss/cache/token.json` (기존 KIS 캐시 패턴 재사용, 경로만 분리)
  - 클라이언트당 유효 토큰 1개 원칙: 재발급 시 이전 토큰 즉시 무효화 → 캐시 갱신
  - **토큰 무효화 감지:** 캐시 로드 후 API 호출 시 `401 Unauthorized` 수신 → 캐시 삭제 후 즉시 재발급. 재시작·중복 인스턴스 실행으로 서버 측에서 이전 토큰이 무효화된 상황을 처리.
  - **선제적 갱신 옵션:** `OAuth2TokenResponse.expires_in`(초) 기반으로 만료 60초 전에 백그라운드 재발급 — `401` 감지 방식과 함께 선택 구현 가능
  - `get_account_seq()` 는 `auth.py`에 두지 않음 — `TossRestClient.__init__` 또는 팩토리에서 처리 (단일 책임 원칙)

- [x] **T042** `core/adapters/toss/rest.py` — 시세 & 잔고 조회
  - `__init__` 에서 `GET /api/v1/accounts` 호출 → 첫 번째 `accountSeq` 획득 후 인스턴스 변수 저장
  - `get_price(symbol: str) -> PriceInfo`: `GET /api/v1/prices?symbols={symbol}` → `result[0].lastPrice`
  - `get_balance(symbol: str | None = None) -> BalanceInfo`: `GET /api/v1/holdings` (`X-Tossinvest-Account: {accountSeq}` 헤더) — `symbol` 파라미터로 특정 종목만 필터 가능 (전체 잔고는 생략)
  - 응답 envelope: `{"result": {...}}` → `data["result"]` 추출 헬퍼
  - 에러 처리: `{"error": {"code": ..., "message": ...}}` → `RuntimeError` 변환
  - **Rate Limit 그룹별 스로틀러 분리:** `MARKET_DATA` 그룹(시세·잔고)과 `ORDER` 그룹(주문)은 별도 `FixedIntervalThrottler` 인스턴스 사용. 주문 전송이 시세 폴링 버킷을 소모하지 않도록 격리.

- [x] **T043** `core/adapters/toss/rest.py` — 주문 생성
  - `place_order(order: Order) -> OrderAck`: `POST /api/v1/orders`
  - 요청 바디: `{clientOrderId, symbol, side, orderType, quantity, price}` (TR_ID·시장 분기 불필요)
  - `clientOrderId` 네이티브 지원 → 멱등성 Toss 서버 보장 (`409 request-in-progress` 처리)
  - `1억원 이상 주문 확인` 에러(`confirm-high-value-required`) → Risk Manager 한도에서 사전 차단

- [x] **T044** `core/marketdata/feed.py` — WebSocket → REST 폴링 전환
  - `MarketDataFeed.__init__` 인자: `KisWsClient` 제거 → `rest_client: BrokerAdapter`, `poll_interval: float = 2.0`
  - 폴링 루프: `asyncio.sleep(poll_interval)` → `GET /api/v1/prices?symbols=A,B,C` 배치 조회 → 종목별 `Tick` 생성 → 핸들러 호출
  - `subscribe(symbol)` / `start()` / `stop()` 인터페이스 유지 (Strategy Engine 무수정)
  - 종목 목록 관리: `subscribe()` 호출 시 내부 집합에 추가 → 폴링 시 콤마 조인

- [x] **T045** `core/marketdata/normalizer.py` — Toss JSON 포맷 정규화
  - 기존 KIS 파이프(`^`) 구분 파서를 **반드시 `normalizer_kis.py`로 이동** (삭제 금지 — KIS 하위 호환 및 기존 테스트 유지)
  - `normalize_toss_price(symbol: str, result: dict) -> Tick`: `lastPrice`, `timestamp` 필드 매핑
  - `normalize_toss_holdings(result: dict) -> BalanceInfo`: `items[].quantity`, `averagePurchasePrice`, `marketValue` 매핑
  - 국내·해외 통합 처리 (`marketCountry: "KR"|"US"` + `currency: "KRW"|"USD"` 필드로 구분)

- [x] **T046** `core/app.py` — Toss 어댑터 wiring + KIS 어댑터 병존
  - `broker` 설정 값 기반 분기: `"toss"` 선택 시 Toss 어댑터 조립, `"kis"` 선택 시 기존 흐름 유지
  - Toss 선택 시: `TossAuth` → `accountSeq` 획득 → `TossRestClient` → `MarketDataFeed(폴링)` 조립
  - `core/adapters/kis/` 파일 전체 보존 (KIS 하위 호환 보장)

- [x] **T047** 통합 테스트 + Toss 어댑터 단위 테스트
  - `tests/adapters/toss/test_auth.py`: 토큰 발급·캐시 로드·재발급·`401` 감지 후 재발급 흐름 (httpx mock)
  - `tests/adapters/toss/test_rest.py`: 현재가·잔고·주문 요청 파라미터 및 응답 파싱 검증, Rate Limit 그룹 격리 검증
  - `tests/marketdata/test_feed_polling.py`: 폴링 루프에서 Tick 핸들러 호출 검증
  - `tests/integration/test_toss_roundtrip.py`: 시그널 → Risk Manager → Toss 주문 라운드트립 (MockRestClient)
  - 기존 KIS 테스트 전체 유지 (병존)

- [ ] **T048** `specs/2026-06-18-quanteo-architecture.md` — Toss 어댑터 기준으로 아키텍처 문서 갱신
  - KIS 전용 다이어그램·설명을 "브로커 어댑터 레이어" 추상화 기준으로 업데이트
  - Toss 어댑터 구조(REST only, 폴링 피드, Rate Limit 그룹) 반영
  - KIS 어댑터는 "기존 브로커 구현체" 섹션으로 병존 유지 명시
  - Toss API JSON 스펙은 `specs/tossinvest/` 폴더로 정리됨 (prefix 제거: `open-api.json`, `auth.json` 등)

---

## Phase 9 — Toss증권 어댑터 운영 완성

> **목표:** Phase 8에서 커버하지 못한 Toss OpenAPI 15개 엔드포인트를 구현해 실거래 운용에 필요한 안전망과 기능을 갖춘다.
>
> **커버리지 기준:** Phase 8은 인증·현재가·잔고·주문생성 5개 엔드포인트만 다룬다. Phase 9는 주문관리(취소·정정·조회), 매수가능금액, 판매가능수량, 상하한가, 캘린더, 체결내역, 종목정보, 환율, 과거 캔들 등 나머지 15개를 채운다.
>
> **우선순위:** `prod` 전환 전 필수(T049~~T053) → 선택 기능(T054~~T056).

- [ ] **T049** `TossRestClient` 확장 — 매수가능금액·판매가능수량·수수료 조회
  - `get_buying_power(currency: str = "KRW") -> BuyingPowerInfo`: `GET /api/v1/buying-power?currency={currency}` → `cashBuyingPower` 필드
  - `get_sellable_quantity(symbol: str) -> int`: `GET /api/v1/sellable-quantity?symbol={symbol}` → `sellableQuantity` 필드
  - `get_commissions() -> list[Commission]`: `GET /api/v1/commissions` → `commissionRate`, `startDate`, `endDate` 필드
  - **Risk Manager 연동:** 주문 전 `get_buying_power()` / `get_sellable_quantity()` 호출하여 주문 수량·금액 사전 검증 — `insufficient-buying-power` 에러보다 앞서 차단
  - `BuyingPowerInfo`, `Commission` 내부 타입 정의 (`core/adapters/toss/models.py`)

- [ ] **T050** 주문 관리 완성 — 주문 목록·단건 조회·취소·정정
  - `list_orders(status: Literal["OPEN", "CLOSED"], symbol: str | None = None, cursor: str | None = None, limit: int = 100) -> tuple[list[Order], str | None]`: `GET /api/v1/orders` — `status` 필수, 페이지네이션은 `cursor` / `nextCursor` / `hasNext` 사용 (`nextPageToken` 없음)
  - `get_order(order_id: str) -> Order`: `GET /api/v1/orders/{orderId}` → `orderId`, `status`(enum: PENDING·PARTIAL_FILLED·FILLED·CANCELED 등), `execution` 전체 필드
  - `cancel_order(order_id: str) -> OrderOperationResponse`: `POST /api/v1/orders/{orderId}/cancel` → `{ orderId }` 반환, `409` 충돌 시 재조회 후 상태 반환
  - `modify_order(order_id: str, order_type: str, quantity: int | None = None, price: Decimal | None = None, confirm_high_value: bool = False) -> OrderOperationResponse`: `POST /api/v1/orders/{orderId}/modify` — `orderType`만 필수, `quantity`·`price`·`confirmHighValueOrder` 선택
  - State Store `orders` 테이블 동기화: 취소·정정 후 DB 레코드 상태 갱신
  - `OrderAck.cancel()` / `OrderAck.modify()` 헬퍼 메서드 추가 (Order Executor 레이어)
  - **Protocol 확장 여부 결정:** T039 `BrokerAdapter`에 `cancel_order` / `modify_order` / `list_orders` 추가할지, `TossRestClient` 전용 메서드로 둘지 T050 시작 시 확정

- [ ] **T051** 체결 내역 조회 — `GET /api/v1/trades`
  - `get_trades(count: int = 100) -> list[Fill]`: `price`, `volume`, `timestamp`, `currency` 필드 매핑
  - `normalize_toss_trade(result: dict) -> Fill` 정규화 함수 추가 (`core/marketdata/normalizer.py`)
  - State Store `fills` 테이블 동기화: 봇 재시작 시 미동기화 체결 복원 (`recovery.py` 연동)
  - 체결 이벤트 → Event Bus 발행 → Telegram 알림 트리거 검증 (`FillEvent` 경로)

- [ ] **T052** 마켓 정보 & 캘린더 API
  - `get_price_limits(symbol: str) -> PriceLimits`: `GET /api/v1/price-limits?symbol={symbol}` → `upperLimitPrice`, `lowerLimitPrice`, `timestamp`
  - **Risk Manager 연동:** 주문 가격이 상하한가 범위 초과 시 `RiskError` 발생 — `confirm-high-value-required` 에러 이전에 차단
  - `get_market_calendar_kr(date: str | None = None) -> KrMarketCalendar`: `GET /api/v1/market-calendar/KR` → `today`, `previousBusinessDay`, `nextBusinessDay`
  - `get_market_calendar_us(date: str | None = None) -> UsMarketCalendar`: `GET /api/v1/market-calendar/US`
  - `is_market_open(market: Literal["KR", "US"]) -> bool` 헬퍼: 캘린더 기반 개장 여부 → 폴링 루프·주문 루프 진입 가드로 활용

- [ ] **T053** 종목 정보 & 매수 유의사항
  - `get_stocks(symbols: list[str]) -> list[StockInfo]`: `GET /api/v1/stocks?symbols=A,B,C` → `symbol`, `name`, `market`, `status`, `currency` 등
  - `get_stock_warnings(symbol: str) -> list[StockWarning]`: `GET /api/v1/stocks/{symbol}/warnings` → `warningType`, `startDate`, `endDate`
  - **Risk Manager 연동:** `warningType` 있는 종목 주문 시 `RiskError` 발생 (매수 유의종목 차단)
  - 전략 엔진 `subscribe()` 시 종목 기본 정보 캐싱 → Strategy Plugin이 `StockInfo` 참조 가능
  - `tests/adapters/toss/test_stock_info.py`: warnings 차단 동작 검증

- [ ] **T054** 환율 조회 & 해외 주식 KRW 환산
  - `get_exchange_rate(base_currency: str = "USD", quote_currency: str = "KRW") -> ExchangeRate`: `GET /api/v1/exchange-rate` → `rate`, `midRate`, `rateChangeType`, `validFrom`, `validUntil`
  - `BalanceInfo` 확장: `total_krw: Decimal` 필드 추가 — 해외 주식 보유분을 `midRate` 기준 KRW 환산합산
  - 환율 캐시: TTL 60초 인메모리 캐시 (`asyncio.Lock` 기반) — 폴링 루프마다 호출 방지
  - 대시보드 `/positions` 응답에 `krw_value` 필드 노출

- [ ] **T055** 과거 캔들 데이터 & 백테스트 소스 연결
  - `get_candles(symbol: str, interval: str, count: int = 100, before: str | None = None, adjusted: bool = True) -> list[Candle]`: `GET /api/v1/candles`
  - `Candle` 내부 타입: `timestamp`, `openPrice`, `highPrice`, `lowPrice`, `closePrice`, `volume`, `currency`
  - `normalize_toss_candle(result: dict) -> Candle` 정규화 함수 추가 (`core/marketdata/normalizer.py`)
  - Strategy Engine 백테스트 하니스(T014) 에 Toss 캔들 데이터 소스 연결 — `BacktestFeed` 클래스 Toss 어댑터 지원
  - 지원 `interval` 값: 현재 스펙 enum `["1m", "1d"]` 두 가지만 확정. 추후 API 업데이트 시 확장 가능하도록 `Literal` 타입으로 정의

- [ ] **T056** Control API 확장 & 대시보드 주문관리 UI
  - Control API `/market-status` 엔드포인트 추가: 국내·해외 개장 여부 + 캘린더 정보 (`KR`, `US`)
  - Control API `/risk-metrics` 확장 응답: `buyingPower`, `sellableQuantity`, `priceLimits` 포함
  - 대시보드 주문 내역 화면(T026)에 **취소** / **정정** 버튼 추가 → `cancel_order` / `modify_order` API 호출
  - 체결 내역(`/trades`) 전용 탭 추가: 체결가·수량·타임스탬프 표시
  - `tests/api/test_market_status.py`: 개장 여부 엔드포인트 응답 검증

---

## 다음 단계

구현을 시작하려면 "Phase 8 진행해줘" 또는 "T039까지 진행해줘"로 요청.
Phase 9는 Phase 8 완료 후 "Phase 9 진행해줘" 또는 "T049까지 진행해줘"로 시작.
