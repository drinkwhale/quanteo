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

- [x] **T048** `specs/2026-06-18-quanteo-architecture.md` — Toss 어댑터 기준으로 아키텍처 문서 갱신
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

- [x] **T049** `TossRestClient` 확장 — 매수가능금액·판매가능수량·수수료 조회
  - `get_buying_power(currency: str = "KRW") -> BuyingPowerInfo`: `GET /api/v1/buying-power?currency={currency}` → `cashBuyingPower` 필드
  - `get_sellable_quantity(symbol: str) -> int`: `GET /api/v1/sellable-quantity?symbol={symbol}` → `sellableQuantity` 필드
  - `get_commissions() -> list[Commission]`: `GET /api/v1/commissions` → `commissionRate`, `startDate`, `endDate` 필드
  - **Risk Manager 연동:** 주문 전 `get_buying_power()` / `get_sellable_quantity()` 호출하여 주문 수량·금액 사전 검증 — `insufficient-buying-power` 에러보다 앞서 차단
  - `BuyingPowerInfo`, `Commission` 내부 타입 정의 (`core/adapters/toss/models.py`)

- [x] **T050** 주문 관리 완성 — 주문 목록·단건 조회·취소·정정
  - `list_orders(status: Literal["OPEN", "CLOSED"], symbol: str | None = None, cursor: str | None = None, limit: int = 100) -> tuple[list[Order], str | None]`: `GET /api/v1/orders` — `status` 필수, 페이지네이션은 `cursor` / `nextCursor` / `hasNext` 사용 (`nextPageToken` 없음)
  - `get_order(order_id: str) -> Order`: `GET /api/v1/orders/{orderId}` → `orderId`, `status`(enum: PENDING·PARTIAL_FILLED·FILLED·CANCELED 등), `execution` 전체 필드
  - `cancel_order(order_id: str) -> OrderOperationResponse`: `POST /api/v1/orders/{orderId}/cancel` → `{ orderId }` 반환, `409` 충돌 시 재조회 후 상태 반환
  - `modify_order(order_id: str, order_type: str, quantity: int | None = None, price: Decimal | None = None, confirm_high_value: bool = False) -> OrderOperationResponse`: `POST /api/v1/orders/{orderId}/modify` — `orderType`만 필수, `quantity`·`price`·`confirmHighValueOrder` 선택
  - State Store `orders` 테이블 동기화: 취소·정정 후 DB 레코드 상태 갱신
  - `OrderAck.cancel()` / `OrderAck.modify()` 헬퍼 메서드 추가 (Order Executor 레이어)
  - **Protocol 확장 여부 결정:** T039 `BrokerAdapter`에 `cancel_order` / `modify_order` / `list_orders` 추가할지, `TossRestClient` 전용 메서드로 둘지 T050 시작 시 확정

- [x] **T051** 체결 내역 조회 — `GET /api/v1/trades`
  - `get_trades(count: int = 100) -> list[Fill]`: `price`, `volume`, `timestamp`, `currency` 필드 매핑
  - `normalize_toss_trade(result: dict) -> Fill` 정규화 함수 추가 (`core/marketdata/normalizer.py`)
  - State Store `fills` 테이블 동기화: 봇 재시작 시 미동기화 체결 복원 (`recovery.py` 연동)
  - 체결 이벤트 → Event Bus 발행 → Telegram 알림 트리거 검증 (`FillEvent` 경로)

- [x] **T052** 마켓 정보 & 캘린더 API
  - `get_price_limits(symbol: str) -> PriceLimits`: `GET /api/v1/price-limits?symbol={symbol}` → `upperLimitPrice`, `lowerLimitPrice`, `timestamp`
  - **Risk Manager 연동:** 주문 가격이 상하한가 범위 초과 시 `RiskError` 발생 — `confirm-high-value-required` 에러 이전에 차단
  - `get_market_calendar_kr(date: str | None = None) -> KrMarketCalendar`: `GET /api/v1/market-calendar/KR` → `today`, `previousBusinessDay`, `nextBusinessDay`
  - `get_market_calendar_us(date: str | None = None) -> UsMarketCalendar`: `GET /api/v1/market-calendar/US`
  - `is_market_open(market: Literal["KR", "US"]) -> bool` 헬퍼: 캘린더 기반 개장 여부 → 폴링 루프·주문 루프 진입 가드로 활용

- [x] **T053** 종목 정보 & 매수 유의사항
  - `get_stocks(symbols: list[str]) -> list[StockInfo]`: `GET /api/v1/stocks?symbols=A,B,C` → `symbol`, `name`, `market`, `status`, `currency` 등
  - `get_stock_warnings(symbol: str) -> list[StockWarning]`: `GET /api/v1/stocks/{symbol}/warnings` → `warningType`, `startDate`, `endDate`
  - **Risk Manager 연동:** `warningType` 있는 종목 주문 시 `RiskError` 발생 (매수 유의종목 차단)
  - 전략 엔진 `subscribe()` 시 종목 기본 정보 캐싱 → Strategy Plugin이 `StockInfo` 참조 가능
  - `tests/adapters/toss/test_stock_info.py`: warnings 차단 동작 검증

- [x] **T054** 환율 조회 & 해외 주식 KRW 환산
  - `get_exchange_rate(base_currency: str = "USD", quote_currency: str = "KRW") -> ExchangeRate`: `GET /api/v1/exchange-rate` → `rate`, `midRate`, `rateChangeType`, `validFrom`, `validUntil`
  - `BalanceInfo` 확장: `total_krw: Decimal` 필드 추가 — 해외 주식 보유분을 `midRate` 기준 KRW 환산합산
  - 환율 캐시: TTL 60초 인메모리 캐시 (`asyncio.Lock` 기반) — 폴링 루프마다 호출 방지
  - 대시보드 `/positions` 응답에 `krw_value` 필드 노출

- [x] **T055** 과거 캔들 데이터 & 백테스트 소스 연결
  - `get_candles(symbol: str, interval: str, count: int = 100, before: str | None = None, adjusted: bool = True) -> list[Candle]`: `GET /api/v1/candles`
  - `Candle` 내부 타입: `timestamp`, `openPrice`, `highPrice`, `lowPrice`, `closePrice`, `volume`, `currency`
  - `normalize_toss_candle(result: dict) -> Candle` 정규화 함수 추가 (`core/marketdata/normalizer.py`)
  - Strategy Engine 백테스트 하니스(T014) 에 Toss 캔들 데이터 소스 연결 — `BacktestFeed` 클래스 Toss 어댑터 지원
  - 지원 `interval` 값: 현재 스펙 enum `["1m", "1d"]` 두 가지만 확정. 추후 API 업데이트 시 확장 가능하도록 `Literal` 타입으로 정의

- [x] **T056** Control API 확장 & 대시보드 주문관리 UI
  - Control API `/market-status` 엔드포인트 추가: 국내·해외 개장 여부 + 캘린더 정보 (`KR`, `US`)
  - Control API `/risk-metrics` 확장 응답: `buyingPower`, `sellableQuantity`, `priceLimits` 포함
  - 대시보드 주문 내역 화면(T026)에 **취소** / **정정** 버튼 추가 → `cancel_order` / `modify_order` API 호출
  - 체결 내역(`/trades`) 전용 탭 추가: 체결가·수량·타임스탬프 표시
  - `tests/api/test_market_status.py`: 개장 여부 엔드포인트 응답 검증

---

## Phase 10 — 정보 수집 & 알람 시스템

> **목표:** SK하이닉스(000660) 매매 판단에 영향을 주는 국내외 뉴스·환율·실적발표·경제지표를 자동 수집하고, Claude Haiku로 중요도를 분류하여 Telegram 즉시 알람과 Google Calendar 일정 자동 저장까지 연결한다.
>
> **설계 근거:** [specs/info-alarm.md](info-alarm.md) 1~8절 전체.
> **신규 디렉토리:** `info/` — 독립 실행 가능한 정보 수집·알람 서브시스템. `core/app.py`에 선택적(`enabled` 플래그)으로 통합.
> **기존 재사용:** `core/notifier/TelegramNotifier` 주입·래핑. `core/config/settings.py` 확장. asyncio 기반 APScheduler.
>
> **단계 우선순위:** 즉시 가치(T057~~T062) → 환율 자동화(T063~~T064) → 캘린더 연동(T065~~T066) → 풀 통합(T067~~T068).

- [x] **T057** `info/` 스캐폴드 & 의존성 추가
  - `pyproject.toml`에 추가: `feedparser`, `beautifulsoup4`, `OpenDartReader`, `yfinance`, `pandas`, `gcsa`, `google-auth-oauthlib`, `icalendar`, `apscheduler` (**`schedule` 라이브러리는 추가하지 않는다** — apscheduler 단독 사용, cron 표현식 지원 필요)
  - `info/` 디렉토리 스캐폴드: `news/`, `fx/`, `calendar/`, `ai_filter/`, `telegram/` 서브패키지 생성 (`__init__.py` 포함)
  - `quanteo.yaml.example`에 `info:` 섹션 추가 — `dart.api_key`, `finnhub.api_key`, `google_calendar.credentials_path`, `anthropic.api_key`, `telegram.chat_id`
  - `core/config/settings.py`에 `InfoSettings(BaseModel)` 추가: 각 API 키·경로·알람 임계값(`fx_alert_threshold`) 로딩
  - **Google Calendar OAuth 최초 설정 절차** (`docs/setup/GOOGLE_CALENDAR_SETUP.md` 문서화):
    1. GCP 프로젝트 생성 → Calendar API 활성화
    2. OAuth2 클라이언트 자격증명 다운로드 → `~/.quanteo/google/credentials.json`
    3. 최초 실행 시 `gcsa`가 브라우저 OAuth 동의 화면 리다이렉트 → 토큰 캐시 자동 생성
    4. 이후 실행부터 캐시 토큰 자동 사용 (만료 시 자동 갱신)

- [x] **T058** AI 중요도 필터 (`info/ai_filter/claude_filter.py`)
  - `CRITICAL_KEYWORDS` 사전 필터 상수 정의 (스펙 5절 기준) — Claude 호출 전 키워드 매칭으로 LOW 사전 제거, API 비용 절감
  - `FilterResult` 데이터클래스: `score: Literal["HIGH", "MEDIUM", "LOW"]`, `reason: str`, `action: Literal["매수검토","매도검토","관망"]`
  - `ClaudeFilter.classify(title: str, body: str) -> FilterResult`: Claude Haiku(`claude-haiku-4-5-20251001`) 호출, 시스템 프롬프트는 스펙 5절 그대로 사용
  - **폴백 2단 정책 (무음 폐기 금지):**
    - 1단: Claude API 실패 → CRITICAL_KEYWORDS 매칭 수 기반 (2개↑ → MEDIUM, 미만 → LOW)
    - 2단: 키워드 매칭도 실패(예외 발생, 빈 키워드 리스트) → 운영자 긴급 알람 발송 후 LOW 반환. 뉴스를 조용히 버리지 않는다.
    - 두 단계 모두 `logger.error` 기록 + `FilterResult.reason`에 `[DEGRADED MODE]` 접두사
  - `tests/info/test_claude_filter.py`:
    - 키워드 사전 필터 경계 케이스 + Haiku JSON 응답 파싱 검증 (httpx mock)
    - **추가:** Claude API DOWN(`httpx.ConnectError`) 시 1단 폴백 동작 검증
    - **추가:** Haiku 응답 JSON 누락 필드(`score` 없음, 빈 문자열) 시 예외 처리 검증
    - **추가:** CRITICAL_KEYWORDS 빈 리스트일 때 2단 폴백 → 운영자 알람 발송 검증

- [x] **T059** 국내 뉴스 RSS 수집기 (`info/news/rss_collector.py`)
  - `NewsItem` 데이터클래스: `title`, `url`, `source`, `published_kst: datetime`, `raw_body: str`
  - `RssCollector.fetch() -> list[NewsItem]`: 한국경제·매일경제·이데일리 RSS `feedparser` 비동기 병렬 수집 (`asyncio.gather`)
  - UTC→KST 변환 (`pytz.timezone("Asia/Seoul")`)
  - **중복 제거: SQLite 영속 dedup** (`~/.quanteo/info_dedup.db`, `seen_urls` 테이블, TTL 24시간). 인메모리 set 사용 금지 — 재시작 후 중복 알람 방지
  - **부분 실패 처리:** 개별 피드 타임아웃(10초) 시 해당 피드만 스킵, 수집된 결과는 정상 반환. 전체 피드 실패 시 `logger.error` 후 빈 리스트 반환 (예외 전파 없음)
  - 수집 후 `ClaudeFilter.classify()` 호출 → HIGH만 `InfoNotifier.send_news_alert()` 발송
  - > **네이버금융 BeautifulSoup 스크래핑** (스펙 2-1절): Phase 10 범위 외. 크롤링 구조 변경 리스크를 고려해 Phase 11에서 구현 결정 예정.
  - `tests/info/test_rss_collector.py`:
    - feedparser mock으로 중복 제거·KST 변환·HIGH 필터 연동 검증
    - **추가:** 모든 RSS 피드 타임아웃 시 빈 리스트 반환·예외 미전파 검증
    - **추가:** 일부 피드 실패 + 일부 성공 시 성공 결과만 반환 검증
    - **추가:** SQLite dedup — 재시작 후 동일 URL 재수신 시 발송 차단 검증

- [ ] **T060** DART 공시 수집기 (`info/news/dart_collector.py`)
  - `DartCollector.fetch(corp_code: str = "00164779") -> list[NewsItem]`: `OpenDartReader` 기반 SK하이닉스 최신 공시 조회
  - 필터 대상: 유상증자·전환사채·주요사항보고서 (`report_tp` 코드 기반)
  - 공시 수신 시 중요도 강제 HIGH → `InfoNotifier.send_news_alert()` 즉시 발송 (Claude 필터 생략)
  - **API 장애 처리:** OpenDartReader 예외 발생 시 `logger.error` 기록 후 빈 리스트 반환 (매매 시스템 중단 방지)
  - `tests/info/test_dart_collector.py`:
    - OpenDartReader mock으로 공시 유형 필터링·HIGH 강제 로직 검증
    - **추가:** OpenDartReader 예외(네트워크 오류, 인증 실패) 시 빈 리스트 반환·logger.error 호출 검증
    - **추가:** 공시 없음(빈 결과) 시 Telegram 미발송 검증

- [ ] **T061** 해외 뉴스 수집기 (`info/news/finnhub_collector.py`)
  - `FinnhubCollector.fetch(symbols: list[str]) -> list[NewsItem]`: `GET https://finnhub.io/api/v1/company-news` — NVDA·MU·TSM·AMD·ASML 등 티커별 수집
  - **Rate limit + 429 처리:** `asyncio.Semaphore` + 1초 인터벌로 60 req/min 준수. 그래도 429 수신 시 지수 백오프(1s→2s→4s, 최대 3회) 재시도. 3회 소진 시 해당 심볼 스킵 + `logger.warning`
  - **5xx·빈 응답 처리:** 서버 오류나 `[]` 응답은 해당 심볼 스킵, 전체 수집 완료
  - `YahooRssCollector.fetch() -> list[NewsItem]`: Yahoo Finance RSS `feedparser` 수집 (무료, 글로벌 시황)
  - 두 소스 모두 `ClaudeFilter.classify()` 통과 후 HIGH만 Telegram 발송
  - `tests/info/test_finnhub_collector.py`:
    - httpx mock으로 응답 파싱·Rate limit Semaphore 동작 검증
    - **추가:** 429 응답 → 지수 백오프 3회 재시도 후 스킵 검증
    - **추가:** 500 오류 시 해당 심볼 스킵·빈 리스트 반환 검증
    - **추가:** 빈 배열(`[]`) 응답 시 Telegram 미발송 검증

- [ ] **T062** Telegram 알람 메시지 포맷 확장 (`info/telegram/info_notifier.py`)
  - `InfoNotifier`: 기존 `core/notifier/TelegramNotifier`를 **생성자 주입**으로 받아 래핑 (중복 구현 금지)
  - **발송 실패 처리 (무음 소실 금지):** 발송 실패 시 지수 백오프(1s→2s→4s) 3회 재시도. 3회 소진 시 `logger.error` + 실패 항목을 `asyncio.Queue` 기반 dead-letter queue에 보존(최대 100건). 스케줄러 재시도 루프(5분 간격)가 큐를 소진
  - `send_news_alert(item: NewsItem, result: FilterResult)`: 스펙 4-1절 포맷 (`🚨 [HIGH]` 헤더, 분석·대응·타임스탬프)
  - `send_earnings_alert(event: EarningsEvent)`: 스펙 4-2절 포맷 (1시간 전 사전 알람, 컨센서스 EPS·매출 포함)
  - `send_fx_alert(snapshot: FxSnapshot)`: 스펙 4-3절 포맷 (`💱` 환율 급변, SK하이닉스 영향 한줄)
  - `send_fx_daily_report(report: FxDailyReport)`: 스펙 4-4절 포맷 (USD·DXY·JPY·CNY 4종 종가 리포트)
  - `send_morning_brief(events: list)`: 08:00 장전 당일 일정 브리핑
  - `tests/info/test_info_notifier.py`:
    - 각 포맷 함수 출력 문자열 스냅샷 검증 (MockTelegramNotifier)
    - **추가:** Telegram 발송 1~3회 실패 후 재시도 성공 검증
    - **추가:** 3회 모두 실패 시 dead-letter queue 적재 + logger.error 호출 검증

- [ ] **T063** 환율 수집 & 급변 감지 (`info/fx/rate_monitor.py`)
  - `FxSnapshot` 데이터클래스: `usdkrw`, `dxy`, `jpykrw`, `cnykrw`, `eurusd` — 각 현재가·전일종가·일중변동률
  - `FxRateMonitor.snapshot() -> FxSnapshot`: `yfinance` 티커 배치 조회 (`USDKRW=X`, `DX-Y.NYB`, `JPYKRW=X`, `CNYKRW=X`, `EURUSD=X`)
  - **기준가 초기화 (타이밍 버그 수정):**
    - 09:00 KST 이후 기동 시: `yfinance .history(period="1d", interval="1m")`로 당일 09:00 시가를 역산해 `base_snapshot` 설정
    - 09:00 이전 기동 시: 최초 `snapshot()` 결과를 잠정 base로 사용, `base_is_provisional = True` 플래그 설정
    - yfinance None/NaN 반환 시 `logger.warning` + 해당 환율 변동률 계산 생략 (알람 오발 방지)
  - 급변 감지 임계값 (스펙 2-5절): USD/KRW ±1%↑ → 🔴 즉시 / ±0.5~1% → 🟡 일반 / DXY ±0.5% / JPY/KRW ±1.5% / CNY/KRW ±1% / EUR/USD ±0.7%
  - `tests/info/test_rate_monitor.py`:
    - yfinance mock으로 임계값 경계 케이스(±0.999%, ±1.001%) 검증
    - **추가:** 09:00 이후 기동 시 `.history()` 호출로 시가 역산 검증
    - **추가:** yfinance None/NaN 반환 시 해당 쌍 알람 미발송 + logger.warning 검증
    - **추가:** 장 마감 시간대 stale 데이터 반환 시 알람 미발송 검증

- [ ] **T064** 환율 일일 마감 리포트 (`info/fx/daily_report.py`)
  - `FxDailyReport` 데이터클래스: 4종 환율 종가·일중변동률·종합 평가 텍스트
  - `FxDailyReporter.generate() -> FxDailyReport`: 오후 4시 기준 yfinance 조회
  - 원화 강세/약세 종합 평가 룰 (`rate_rule.py`): 스펙 2-5절 "환율-주가 상관 해석 룰" 테이블 구현 (상황·해석·대응 매핑)
  - 생성 후 `InfoNotifier.send_fx_daily_report()` 호출
  - `tests/info/test_daily_report.py`: 룰 매핑 경계 케이스 + 리포트 텍스트 생성 검증

- [ ] **T065** Google Calendar API 연동 (`info/calendar/google_cal.py`)
  - `CalEvent` 데이터클래스: `summary`, `start: datetime`, `end: datetime`, `importance: Literal["CRITICAL","HIGH","MEDIUM","FX","KR"]`, `description: str`
  - `GoogleCalendarClient`: `gcsa` 라이브러리 OAuth2 인증 (`credentials.json` 경로는 `quanteo.yaml`)
  - **OAuth 토큰 만료 처리:** `add_event()` 중 401 수신 시 `gcsa` 자동 토큰 갱신 트리거. 갱신 실패 시 `logger.error` + 해당 이벤트 스킵 (매매 시스템 중단 없음)
  - `add_event(event: CalEvent)`: 색상 코딩 자동 적용 — CRITICAL→11(Tomato), HIGH→6(Tangerine), MEDIUM→5(Banana), FX→7(Peacock), KR→2(Sage)
  - 알람 설정 자동화: FOMC·NVDA·MU → 2중(120분+30분 전), CPI·NFP·TSM → 60분 전, 기타 → 30분 전
  - 중복 방지: 동일 `summary`+`start` 이벤트 검색 후 존재 시 스킵
  - **API 할당량 초과(429) 처리:** 지수 백오프 3회 재시도, 소진 시 `logger.error` + `bulk_add` 중단 없이 다음 이벤트 진행
  - `tests/info/test_google_cal.py`:
    - gcsa mock으로 색상·알람·중복 방지 로직 검증
    - **추가:** `add_event()` 중 401 발생 시 토큰 갱신 트리거 + 재시도 검증
    - **추가:** 429 할당량 초과 시 백오프 후 다음 이벤트 계속 처리 검증

- [ ] **T066** 실적발표 & 경제지표 캘린더 데이터 (`info/calendar/earnings_data.py`, `macro_events.py`)
  - **`EarningsEvent` 타입 정의** (`CalEvent` 서브클래스, T062 `send_earnings_alert` 연동):
    - `ticker: str`, `consensus_eps: str | None`, `consensus_sales: str | None`, `timing: Literal["장전","장중","장후"]`, `sk_impact: Literal["🔴 최고","🔴 높음","🟡 중간"]`
  - `EARNINGS_SCHEDULE: list[EarningsEvent]`: 스펙 2-4절 2026 하반기 실적 하드코딩 (ASML·TSM·AMD·NVDA·AVGO·MU + AMAT·LRCX·KLAC·MRVL·META·MSFT·GOOGL·AMZN), 컨센서스 값 포함
  - `MACRO_SCHEDULE`: 미국(FOMC·CPI·NFP·PCE·PPI·GDP·ISM)·한국(기준금리·수출입)·중국(PMI) 반복 스케줄 룰 정의. **범위: 2026년 하반기(2026-07~12)만.** 2027년 이후는 Phase 11에서 자동 갱신 연동 검토
  - `next_events(days: int = 7) -> list[CalEvent]`: 오늘 기준 N일 내 이벤트 필터링
  - `today_us_earnings() -> list[EarningsEvent]`: 오늘 미국 장후(22:30~익일 08:00 KST) 발표 예정 종목 필터링 — T067 15:30 잡에서 호출
  - `GoogleCalendarClient.bulk_add(events)`: 매월 1일 00:00 다음 달 전체 일정 일괄 저장
  - `tests/info/test_calendar_data.py`:
    - 날짜 필터링·중요도 매핑·bulk_add 중복 방지 검증
    - **추가:** `today_us_earnings()` — 오늘 날짜 기준 장후 실적만 필터 검증 (경계: 22:29 vs 22:30 KST)

- [ ] **T067** APScheduler 스케줄러 통합 (`info/scheduler.py`, `info/main.py`)
  - **⚠️ 타임존 필수:** `AsyncIOScheduler(timezone="Asia/Seoul")` + 각 `CronTrigger(timezone="Asia/Seoul")`. 미설정 시 UTC 기준으로 모든 잡이 KST보다 9시간 늦게 실행됨
  - `InfoScheduler`: `AsyncIOScheduler` 기반 — 아래 크론 잡 전체 등록 (스펙 7절 기준):
    - `CronTrigger(hour=8, minute=0)` KST — 장전 뉴스 수집 + 당일 일정 브리핑
    - `IntervalTrigger(minutes=5)` 09:00~15:30 — 국내 RSS 폴링 + HIGH 알람
    - `IntervalTrigger(minutes=30)` 09:00~15:30 — USD/KRW 환율 체크 + 급변 알람
    - `CronTrigger(hour=15, minute=30)` — `today_us_earnings()` 호출 → 오늘 미국 장후 실적 예정 종목만 필터링 후 Telegram 발송 (전체 스케줄 아닌 당일 건만)
    - `CronTrigger(hour=16, minute=0)` — 환율 일일 마감 리포트
    - `IntervalTrigger(minutes=10)` 22:00~06:00 — 미국 뉴스 폴링 (Finnhub·Yahoo)
    - `CronTrigger(day=1, hour=0, minute=0)` — 다음 달 캘린더 자동 저장
  - **잡 예외 처리:** `misfire_grace_time=60`, `coalesce=True` 설정. 잡 내부 예외는 `try/except`로 잡아 `logger.error` 후 다음 실행 정상 유지 (스케줄러 중단 방지)
  - `InfoSystem`: 모든 컴포넌트 wiring + `start()` / `stop()` 라이프사이클 (의존성 주입 패턴)
  - `core/app.py` 통합: `info.enabled: true` 플래그 시 `InfoSystem.start()`를 `asyncio.gather`에 추가
  - `tests/info/test_scheduler.py`:
    - APScheduler mock으로 잡 등록 수·크론 표현식·타임존(`Asia/Seoul`) 검증
    - **추가:** 잡 내부 예외 발생 시 스케줄러 계속 실행 검증 (다음 interval 정상 트리거)
    - **추가:** `today_us_earnings()` 빈 결과 시 15:30 잡이 Telegram 미발송 검증

- [ ] **T068** 통합 테스트 & 문서 갱신
  - `tests/info/test_integration_news.py`: RSS 수집 → AI 필터 → Telegram 전송 엔드투엔드 (MockTelegramNotifier 사용)
  - `tests/info/test_integration_fx.py`: FxRateMonitor 급변 감지 → Telegram 알람 라운드트립
  - `tests/info/test_integration_calendar.py`: 실적발표 데이터 → Google Calendar 저장 → 중복 방지 라운드트립
  - **추가:** `tests/info/test_integration_degraded.py`: Claude API + Telegram 동시 장애 시 시스템 계속 동작 검증 (dead-letter queue 적재, 스케줄러 지속)
  - `specs/2026-06-18-quanteo-architecture.md` 갱신: Phase 10 정보 수집·알람 서브시스템 섹션 추가
  - `quanteo.yaml.example` 최종 정비: `info:` 전체 섹션 완성
  - `CLAUDE.md` 구현 상태표에 Phase 10 행 추가

---

## 다음 단계

구현을 시작하려면 "Phase 10 진행해줘" 또는 "T057까지 진행해줘"로 요청.
