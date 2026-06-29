# quanteo 아키텍처 설계서

- **작성일:** 2026-06-18
- **최종 갱신:** 2026-06-29 (Phase 8 — Toss증권 어댑터 마이그레이션 반영)
- **상태:** 승인됨 (브레인스토밍 → 설계 확정 → Phase 8 Toss 어댑터 추가)
- **대상:** KIS / Toss증권 교체 가능 브로커 어댑터 기반 완전 자동매매 봇
- **접근 방식:** 접근 B — 모듈형 Python 코어 + 얇은 제어 API + TypeScript 대시보드

> 이 문서는 새 세션에서도 참조되는 **단일 진실 공급원(single source of truth)** 이다.
> 구현이 진행되면서 실제와 달라지면 이 문서를 갱신할 것.

---

## 1. 확정된 요구사항

| 항목            | 결정                                                                         |
| --------------- | ---------------------------------------------------------------------------- |
| **핵심 목표**   | 완전 자동매매 봇 (사람 개입 없이 시그널 → 주문까지 실행)                     |
| **대상 시장**   | 국내 주식 + 해외 주식 (시장 추상화 필수)                                     |
| **스택**        | Python 매매 코어 + TypeScript 웹 대시보드                                    |
| **전략 구성**   | 규칙 기반 지표 전략, 플러그인 교체형                                         |
| **리스크 관리** | 손절/익절(기본) + 최소 안전 가드(포지션·금액 한도, 킬스위치) 권장 베이스라인 |
| **운영**        | 로컬 상주 + 모의투자(vps)로 시작 → 추후 클라우드 확장 가능하도록 설계        |

### 비기능 요구사항

- **안전 기본값:** 환경 기본값은 항상 `vps`(모의투자). 실전(`prod`)은 명시적 설정 + 별도 플래그로만.
- **클라우드 진화:** 단일 프로세스로 시작하되 컨테이너화·멀티프로세스 분리가 쉬운 경계.
- **Rate limit 준수:** KIS 호출 빈도 제한을 고려한 폴링/주문 루프.
- **자격증명 격리:** 키/시크릿/토큰은 저장소 밖. 절대 커밋 금지.

---

## 2. 전체 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│  quanteo-core  (Python, 상주 프로세스)                        │
│                                                               │
│   ┌──────────┐   ┌───────────┐   ┌──────────┐                │
│   │ Market   │──▶│ Strategy  │──▶│ Risk     │                │
│   │ Data     │   │ Engine    │   │ Manager  │                │
│   │ (feed)   │   │ (plugins) │   │ (가드)   │                │
│   └──────────┘   └───────────┘   └────┬─────┘                │
│        ▲                                │                     │
│        │                                ▼                     │
│   ┌────┴────────────┐            ┌──────────┐                │
│   │ BrokerAdapter   │◀───────────│ Order    │                │
│   │ (Protocol)      │  주문 실행  │ Executor │                │
│   ├─────────────────┤            └──────────┘                │
│   │ KisRestClient   │  (KIS — REST/WS)                       │
│   │ TossRestClient  │  (Toss — REST 폴링)                    │
│   └─────────────────┘                                        │
│        │                                                  │
│   ┌────┴───────────────────────────────────┐             │
│   │  State Store (SQLite + DuckDB)          │             │
│   │  + Event Bus (asyncio.Queue)            │             │
│   └──────┬──────────────────────────┬──────┘             │
│          ▲                          │ events              │
│   ┌──────┴───────────┐   ┌──────────▼──────┐             │
│   │  Control API     │   │    Notifier     │             │
│   │  (FastAPI        │   │  (Telegram Bot) │             │
│   │   REST + WS)     │   └──────────┬──────┘             │
│   └──────┬───────────┘              │ Telegram API       │
└──────────┼───────────────────────────┼───────────────────┘
           │  HTTP/WebSocket            │
  ┌────────┴─────────┐       ┌─────────┴──────┐
  │  quanteo-dashboard │     │  Telegram 앱   │
  │  상태조회·실시간·제어 │     │  (알림 수신)   │
  └───────────────────┘      └────────────────┘
```

### 핵심 설계 원칙

1. **단방향 흐름:** 데이터 → 시그널 → 리스크 검증 → 주문. 주문은 **반드시** Risk Manager를 통과한다.
2. **시장·환경 캡슐화:** 국내/해외, prod/vps, TR_ID·도메인 차이를 KIS Adapter 안에 가두고 상위 모듈은 표준 인터페이스만 쓴다.
3. **단일 책임:** 각 모듈은 하나의 명확한 목적을 갖고 인터페이스로만 통신 → 독립 테스트 가능.
4. **asyncio 단일 이벤트 루프:** 모든 I/O(시세 수신, REST 호출, WS 브로드캐스트)는 `asyncio.gather()`로 동시 실행. 스레드 없음, 락 없음. (NautilusTrader 패턴 참조)

### asyncio 이벤트 루프 구조 (app.py)

```python
async def main():
    await asyncio.gather(
        adapter.run_ws_feed(),       # 실시간 시세 수신
        strategy_engine.run(),       # 시그널 생성 루프
        order_executor.run(),        # 주문/체결 처리 루프
        notifier.run(),              # Telegram 알림 전송 루프
        control_api.serve(),         # FastAPI REST+WS 서버
        health_monitor.run(),        # 연결 상태 감시 + 재접속
    )
```

> **Research-to-Live Parity (NautilusTrader 패턴):** backtest와 live가 동일한 이벤트 모델을 쓰면 코드 변경 없이 연구에서 실전으로 배포 가능. Strategy 인터페이스를 tick 기반으로 설계해 이 속성을 보장.

---

## 3. 모듈 책임 & 디렉토리 구조

```
quanteo/
├── core/                       # Python 매매 코어
│   ├── adapters/
│   │   ├── base.py             # BrokerAdapter·MarketPoller Protocol 정의
│   │   ├── kis/                # KIS 구현체 (REST + WebSocket)
│   │   │   ├── auth.py         # access token 발급·캐싱·재발급
│   │   │   ├── rest.py         # REST 호출 (시세조회, 주문)
│   │   │   ├── ws.py           # WebSocket 구독 (실시간 시세/체결)
│   │   │   ├── throttler.py    # Rate limit 스로틀러 (FixedIntervalThrottler)
│   │   │   └── tr_ids.py       # 환경×시장 TR_ID·도메인 매핑 테이블
│   │   └── toss/               # Toss증권 구현체 (REST 폴링)
│   │       ├── auth.py         # OAuth2 Client Credentials (토큰 캐시 + 401 재발급)
│   │       └── rest.py         # REST 호출 (시세·잔고·주문, Rate Limit 그룹 분리)
│   ├── marketdata/             # 시세/체결 수신 → 내부 표준 형태로 정규화·공급
│   │   ├── feed.py             # MarketDataFeed (REST 폴링, Toss용)
│   │   ├── feed_kis.py         # MarketDataFeed (KIS WebSocket, 원본 보존)
│   │   ├── normalizer.py       # KIS 정규화 재수출 + Toss 정규화 함수
│   │   └── normalizer_kis.py   # KIS 전용 정규화 함수 (원본 보존)
│   ├── strategy/               # 전략 엔진 (지표 계산, 시그널 생성)
│   │   ├── base.py             # Strategy Protocol 정의
│   │   ├── engine.py           # 플러그인 로드·시그널 루프
│   │   └── plugins/            # 개별 전략 플러그인 (교체형)
│   ├── risk/                   # Risk Manager: 손절/익절·한도·킬스위치 가드
│   ├── execution/              # Order Executor: 주문 전송·체결추적·멱등성
│   ├── store/                  # State Store: SQLite(OLTP) + DuckDB(분석)
│   ├── events/                 # Event Bus: asyncio.Queue 기반 pub/sub
│   ├── notifier/               # 알림 모듈
│   │   ├── base.py             # Notifier Protocol (인터페이스)
│   │   ├── telegram.py         # TelegramNotifier (aiogram v3)
│   │   ├── mock.py             # MockNotifier (테스트용, 실제 전송 없음)
│   │   └── templates.py        # 이벤트별 메시지 템플릿
│   ├── api/                    # Control API: FastAPI REST + WebSocket
│   ├── config/                 # 설정 로딩 (환경/시장/전략 파라미터)
│   └── app.py                  # 코어 부팅·이벤트 루프 조립 (브로커별 분기)
├── dashboard/                  # TypeScript 웹 대시보드
├── specs/
│   ├── tossinvest/             # Toss증권 Open API JSON 스펙 모음
│   └── ...                     # 설계서·작업목록
├── tests/                      # pytest 테스트
├── pyproject.toml
└── CLAUDE.md
```

| 모듈                | 책임                                                                                                                   | 의존                              |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------- | --------------------------------- |
| **BrokerAdapter**   | 브로커 불가지론 인터페이스 (`get_price`, `get_balance`, `place_order`) — `core/adapters/base.py` Protocol 정의         | —                                 |
| **KIS 구현체**      | BrokerAdapter 구현: REST 호출, WebSocket 구독, 환경(prod/vps)·시장(국내/해외)별 TR_ID·도메인 분기, Rate limit 스로틀링 | KIS API                           |
| **Toss 구현체**     | BrokerAdapter 구현: OAuth2 인증, REST-only (폴링 기반), accountSeq 초기화, Rate Limit 그룹(MARKET\_DATA/ORDER) 분리    | Toss증권 Open API                 |
| **Market Data**     | 시세/체결을 내부 표준 형태로 정규화해 공급. KIS: WebSocket feed. Toss: REST 폴링 feed.                                 | BrokerAdapter 구현체              |
| **Strategy Engine** | 플러그인 로드, 지표 계산, 매수/매도 **시그널** 생성                                                                    | Market Data                       |
| **Risk Manager**    | 시그널 → 주문 전환 전 안전 가드 적용 (단계적 킬스위치, 변동성 기반 포지션 사이징)                                      | State Store                       |
| **Order Executor**  | 검증된 주문 전송, 체결 추적, 멱등성 보장                                                                               | BrokerAdapter 구현체, State Store |
| **State Store**     | 포지션·주문·체결 영속화 (SQLite OLTP) + 전략 성과·손익 분석 (DuckDB OLAP)                                              | —                                 |
| **Event Bus**       | asyncio.Queue 기반 모듈 간 느슨한 결합                                                                                 | —                                 |
| **Notifier**        | Event Bus 구독 → 이벤트별 Telegram 알림 전송. Rate limit 큐 내장. 테스트 시 MockNotifier로 교체.                       | Event Bus                         |
| **Control API**     | 대시보드용 조회/명령 REST + 실시간 WebSocket (snapshot-then-delta 패턴)                                                | State Store, Event Bus            |
| **Dashboard**       | 시각화 + 일시정지/킬스위치 제어                                                                                        | Control API                       |

---

## 4. 모듈별 인터페이스 (계약)

> 시그니처는 의도를 보이기 위한 의사코드. 구현 단계에서 타입을 확정한다.

### 4.1 브로커 어댑터 레이어 (BrokerAdapter Protocol)

`core/adapters/base.py`에 정의된 `typing.Protocol`로 브로커를 교체해도 상위 모듈(Strategy, Risk, Executor)은 변경 없음.

```python
@runtime_checkable
class BrokerAdapter(Protocol):
    async def get_price(self, symbol: str) -> PriceInfo: ...
    async def get_balance(self, symbol: str | None = None) -> BalanceInfo: ...
    async def place_order(self, order: Order) -> OrderAck: ...

@runtime_checkable
class MarketPoller(Protocol):
    def subscribe(self, symbol: str) -> None: ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
```

- `OrderAck.broker_order_id`: 브로커 불가지론 주문 ID 필드. KIS 하위호환용 `kis_order_id` property 유지.
- 브로커 선택은 `Settings.broker: Literal["kis", "toss"]`로 결정. `app.py`에서 분기.

#### 4.1.1 KIS 구현체 (`core/adapters/kis/`)

```python
class KisRestClient:  # BrokerAdapter 구현
    async def get_price(self, symbol: str) -> PriceInfo: ...   # TR_ID 자동 선택
    async def get_balance(self, symbol: str | None) -> BalanceInfo: ...
    async def place_order(self, order: Order) -> OrderAck: ...  # 환경별 TR_ID
```

- `Env` = `prod | vps`, `Market` = `domestic | overseas`
- TR_ID·도메인 매핑 테이블을 `tr_ids.py`에 분리 보유. 상위 모듈은 이를 알 필요 없음.
- WebSocket feed는 `feed_kis.py`에 별도 보존 (KIS 전용).
- **KIS Python 커뮤니티 래퍼(kisopenapi 등)는 v0.19.0 이후 개발 중단(Go 마이그레이션 진행 중).** 공식 `open-trading-api` 샘플을 직접 참조해 raw API 기반으로 구현.

#### 4.1.2 Toss증권 구현체 (`core/adapters/toss/`)

```python
class TossAuth:
    async def get_access_token(self) -> OAuth2Token: ...  # 캐시 → 파일 → 신규 발급
    async def refresh_on_401(self) -> OAuth2Token: ...    # 캐시 삭제 + 재발급
    # 만료 60초 전 proactive refresh 백그라운드 태스크 스케줄링

class TossRestClient:  # BrokerAdapter 구현
    async def initialize(self) -> None: ...               # GET /api/v1/accounts → accountSeq
    async def get_price(self, symbol: str) -> PriceInfo: ...
    async def get_balance(self, symbol: str | None) -> BalanceInfo: ...
    async def place_order(self, order: Order) -> OrderAck: ...
```

- **REST only** — WebSocket 없음. 시세는 `MarketDataFeed`(REST 폴링)로 대체.
- **Rate Limit 그룹 분리:** `MARKET_DATA` throttler(5 req/s)와 `ORDER` throttler(2 req/s)를 별도 `FixedIntervalThrottler` 인스턴스로 관리 → 시세 조회가 주문 쿼터를 소모하지 않음.
- **401 재발급:** 요청 실패 시 `auth.refresh_on_401()` 호출 후 1회 재시도. 409(중복 주문)는 `RuntimeError`.
- **토큰 캐시:** `~/toss/cache/token.json` (저장소 밖, 커밋 금지).
- **Toss API JSON 스펙:** `specs/tossinvest/` 폴더 (`open-api.json`, `auth.json`, `account.json`, `order.json` 등).

### 4.2 Strategy (플러그인 인터페이스)

```python
class Strategy(Protocol):
    name: str
    def warmup(self, history: list[Candle]) -> None: ...
    def on_tick(self, tick: Tick, ctx: MarketContext) -> Signal | None: ...
    # Signal = BUY/SELL + symbol + 수량/비중 + 근거(reason)
```

- 전략은 **시그널만** 낸다. 실제 주문 권한 없음 (단방향 흐름 강제).
- `warmup()`으로 과거 캔들을 로드해 초기 지표를 warm-up → backtest와 live가 동일한 경로를 따름 (**research-to-live parity**).
- `strategy/plugins/`에 파일을 추가하면 설정으로 활성화.

### 4.3 Risk Manager

```python
class RiskManager:
    def evaluate(self, signal: Signal, portfolio: Portfolio) -> Order | Rejection: ...
    def volatility_scale(self, signal: Signal, volatility: float) -> Signal: ...  # 변동성 기반 수량 조정
    def check_exit(self, position: Position, quote: Quote) -> Order | None: ...   # 손절/익절
    def halt_level(self) -> HaltLevel: ...             # NONE | REDUCE | PAUSE | KILL
    async def graduated_halt(self, level: HaltLevel) -> None: ...  # 단계적 킬스위치
```

- 모든 시그널은 여기서 한도(종목당 최대 금액, 일일 주문 횟수, 총 노출)·중복주문·킬스위치 검사를 통과해야 주문이 된다.
- **변동성 기반 포지션 사이징:** 최근 실현 변동성에 반비례해 주문 수량 결정 → 변동성 확대 시 포지션 축소, 수렴 시 확대. 달러 리스크 일정 유지.
- **단계적 킬스위치 (Graduated Circuit Breaker):**
  1. `REDUCE` — 신규 포지션 크기 50% 축소 (변동성 급등 시)
  2. `PAUSE` — 신규 진입 중단, 기존 포지션 유지 (일일 손실 임박 시)
  3. `KILL` — 모든 신규 주문 차단, 손절은 허용 (한도 초과 시)
     > 단순 on/off 킬스위치보다 실제 손실을 줄이는 데 효과적.

### 4.4 Event Bus

```python
class EventBus:
    # asyncio.Queue 기반; 크로스 스레드 필요 시 asyncio.Queue(maxsize=1000)
    async def publish(self, event: Event) -> None: ...
    async def subscribe(self, event_type: type[Event], handler: Callable) -> None: ...
```

### 4.5 Control API (대시보드 계약)

| 메서드 | 경로                | 용도                                |
| ------ | ------------------- | ----------------------------------- |
| GET    | `/status`           | 봇 상태(실행/정지, 환경, 전략 목록) |
| GET    | `/positions`        | 현재 포지션·손익                    |
| GET    | `/orders?from=&to=` | 주문/체결 내역                      |
| POST   | `/control/pause`    | 신규 진입 일시정지                  |
| POST   | `/control/resume`   | 재개                                |
| POST   | `/control/kill`     | 킬스위치(모든 신규 주문 차단)       |
| WS     | `/stream`           | 시세·시그널·체결·로그 실시간        |

**WebSocket 구현 패턴 (FastAPI 모범 사례):**

- 연결 시 즉시 snapshot 전송 → 이후 delta(변경분)만 전송 (snapshot-then-delta)
- 클라이언트별 bounded queue (`asyncio.Queue(maxsize=200)`) — 느린 클라이언트가 전체를 막지 않도록
- 30초 heartbeat ping/pong — 역방향 프록시(nginx 등) timeout 방지
- JWT는 `Sec-WebSocket-Protocol` 헤더 또는 첫 메시지로 전달

### 4.6 Notifier (Telegram)

```python
class Notifier(Protocol):
    async def send(self, event: NotifyEvent) -> None: ...
    async def run(self) -> None: ...  # Event Bus 구독 루프

class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, level: NotifyLevel): ...
    async def send(self, event: NotifyEvent) -> None: ...
    async def run(self) -> None: ...

class MockNotifier:
    """테스트용 — 실제 전송 없이 sent_events 리스트에 누적."""
    sent_events: list[NotifyEvent]
    async def send(self, event: NotifyEvent) -> None: ...
    async def run(self) -> None: ...
```

**알림 이벤트 종류 및 메시지 포맷:**

| 이벤트                   | 레벨  | 메시지 예시                                         |
| ------------------------ | ----- | --------------------------------------------------- |
| `SignalEvent`            | INFO  | `🟢 [VPS] BUY 삼성전자(005930) × 10주 — MA교차`     |
| `OrderEvent` (접수)      | INFO  | `📋 [VPS] 매수 접수 005930 × 10 @ 75,400`           |
| `FillEvent` (체결)       | INFO  | `✅ [VPS] 체결 005930 × 10 @ 75,350`                |
| `RiskRejection`          | WARN  | `⚠️ [VPS] 리스크 거부 — 일일 주문 한도 초과`        |
| `HaltEvent` (PAUSE/KILL) | WARN  | `🛑 [VPS] 킬스위치 KILL 발동 — 일일 손실 한도 도달` |
| `StopLossEvent`          | WARN  | `🔴 [VPS] 손절 실행 005930 — -3.2%`                 |
| `ErrorEvent`             | ERROR | `🚨 [VPS] KIS WS 연결 끊김 — 재접속 중`             |
| 봇 시작/종료             | INFO  | `🤖 [VPS] quanteo 시작 — 전략: MA교차`              |

**설정 (외부 config, 커밋 금지):**

```yaml
# kis_devlp.yaml 또는 별도 notifier.yaml
telegram:
  bot_token: "..." # BotFather에서 발급
  chat_id: "..." # 수신할 채팅/채널 ID
  level: "INFO" # INFO | WARN | ERROR (하위 레벨 필터링)
  enabled: true # false 시 MockNotifier로 자동 대체
```

**Rate limit 처리:**

- Telegram API: 동일 chat에 초당 1메시지 제한 (공식 한도)
- 내부 `asyncio.Queue` + **최소 1초 전송 간격** — 0.05초 등 짧은 간격은 한도를 즉시 위반하므로 사용 금지
- 긴급 이벤트(KILL, ERROR)는 큐 앞에 삽입(priority queue)해 INFO 메시지에 묻히지 않도록 함
- 연속 동일 에러는 30초 내 첫 1건만 전송 후 나머지는 집계("에러 5건 추가 발생" 형태로 묶어 재전송)

---

## 5. 데이터 모델 (State Store)

### 5.1 SQLite — OLTP (트랜잭션, 현재 상태)

| 테이블       | 핵심 컬럼                                                                             |
| ------------ | ------------------------------------------------------------------------------------- |
| `positions`  | symbol, market, qty, avg_price, opened_at                                             |
| `orders`     | id, client_order_id(멱등키), symbol, side, qty, price, status, tr_id, env, created_at |
| `fills`      | order_id, qty, price, filled_at                                                       |
| `signals`    | strategy, symbol, side, reason, created_at                                            |
| `settings`   | key, value (전략 활성화·한도·환경 등)                                                 |
| `events_log` | level, source, message, created_at                                                    |

- **멱등성:** `orders.client_order_id`로 재시도 시 중복 주문 방지.

### 5.2 DuckDB — OLAP (분석, 성과 조회)

> 별도 `.duckdb` 파일 또는 SQLite에서 복사. 대량 집계(P&L 히스토리, 전략 성과, 드로다운 계산)에 사용.

| 뷰/테이블         | 용도                                           |
| ----------------- | ---------------------------------------------- |
| `pnl_history`     | 일별·전략별 손익 집계 (Control API 대시보드용) |
| `strategy_stats`  | 승률·샤프지수·최대 드로다운 집계               |
| `drawdown_series` | 포지션별 드로다운 시계열                       |

> **선택 가이드:** 현재 포지션/주문 관리 → SQLite. 성과 분석·리포트 → DuckDB. 초기 구현은 SQLite만으로 시작하고, 분석 요건이 생기면 DuckDB 레이어 추가.

---

## 6. 데이터 흐름 (정상 매수 경로)

> **KIS:** WS feed → tick 수신. **Toss:** REST 폴링 feed → tick 수신. 이후 흐름은 동일.

1. BrokerAdapter(feed) → tick 수신 → Market Data가 정규화 → Event Bus 발행
2. Strategy Engine가 tick 수신 → 지표 갱신 → `BUY` Signal 생성
3. Risk Manager `evaluate(signal)`:
   - `halt_level()` ≥ PAUSE? → Rejection
   - 한도 초과? → Rejection
   - 변동성 기반 수량 조정 (`volatility_scale`)
   - 통과 → Order 생성 (수량·가격 확정)
4. Order Executor → BrokerAdapter `place_order` → OrderAck (`broker_order_id`)
5. 체결 수신 → State Store 갱신(position/fill) → Event Bus:
   - Control API(WS) → Dashboard 반영
   - **Notifier → Telegram 체결 알림** (`✅ 체결 005930 × 10 @ 75,350`)
6. 보유 중 매 tick마다 Risk Manager `check_exit` → 손절/익절 조건 충족 시 매도 Order + **Telegram 손절 알림**
7. 리스크 거부/킬스위치 발동 시 → Event Bus → **Notifier → Telegram WARN/ERROR 알림** (즉시 전송)

---

## 7. 안전 설계 (완전 자동매매의 핵심)

- **환경 가드:** 기본 `vps`. `prod` 전환은 설정 파일 + 실행 시 명시 플래그(`--env prod --i-understand-real-money` 류) 이중 확인.
- **단계적 킬스위치:** REDUCE → PAUSE → KILL 3단계. Control API 수동 발동 또는 일일 손실 한도 자동 발동. 청산/손절은 KILL 상태에서도 허용.
- **한도(베이스라인):** 종목당 최대 투자금, 일일 최대 주문 횟수, 총 노출 한도. 설정으로 조정.
- **변동성 기반 포지션 사이징:** 변동성 확대 시 수량 자동 축소 → 달러 리스크 일정 유지.
- **손절/익절(필수):** 모든 포지션에 진입 시 손절/익절 기준 부여.
- **Rate limit:** KIS Adapter 내 토큰버킷 스로틀러. 초과 시 큐잉 → 지수 백오프.
- **장애 복구:** 재시작 시 State Store에서 포지션/미체결 주문 복구.
- **Telegram 알림:** 킬스위치·손절·에러 등 즉각 대응이 필요한 이벤트는 Telegram으로 실시간 알림. `enabled: false` 시 MockNotifier로 자동 대체돼 테스트에 영향 없음.

---

## 8. 테스트 전략

- **단위:** 각 모듈을 인터페이스 경계로 격리해 테스트. KIS Adapter는 mock 응답으로.
- **전략:** 과거 캔들 데이터로 시그널 검증(경량 백테스트 하니스 — research-to-live parity 보장).
- **리스크:** 한도·킬스위치·손절·변동성 스케일링 경계 케이스를 집중 테스트(안전 직결).
- **통합:** `vps`(모의투자) 환경에서 실제 주문 라운드트립 검증.
- **안전 게이트:** `prod` 경로는 명시 플래그 없이는 절대 실행되지 않음을 테스트로 보장.

---

## 9. 범위 밖 (YAGNI — 지금 하지 않음)

- 본격 백테스팅 플랫폼 / 전략 최적화 엔진
- 선물·옵션·채권·ELW 등 주식 외 상품
- 멀티프로세스/메시지버스 분산 (접근 C) — 경계만 열어두고 추후
- ML 기반 전략 / 외부 시그널 연동
- 멀티 유저 / 인증·권한 시스템
- DuckDB 분석 레이어 (초기 SQLite만으로 시작, 추후 추가)
- Telegram 봇 명령어 UI (양방향 제어 — `/pause`, `/kill` 등 Telegram에서 직접 명령) — Control API로 충분
- 멀티 채팅/채널 팬아웃, 알림 구독 관리

---

## 10. 구현 로드맵 (요약 — 상세는 `specs/tasks.md`)

| Phase              | 목표                                                                            |
| ------------------ | ------------------------------------------------------------------------------- |
| **P1 부트스트랩**  | 프로젝트 스캐폴드, 설정/환경 로딩, KIS Adapter 인증                             |
| **P2 시세**        | Market Data 수신·정규화, State Store                                            |
| **P2.5 알림**      | Notifier 모듈 (Telegram + MockNotifier)                                         |
| **P3 전략**        | Strategy 플러그인 인터페이스 + 첫 지표 전략                                     |
| **P4 리스크+주문** | Risk Manager 가드 + Order Executor (vps 주문)                                   |
| **P5 제어 API**    | Control API REST/WS                                                             |
| **P6 대시보드**    | TypeScript 대시보드                                                             |
| **P7 안전·운영**   | 킬스위치·복구·rate limit·prod 게이트                                            |
| **P8 Toss 어댑터** | BrokerAdapter Protocol 추상화 + Toss증권 REST 구현체 + REST 폴링 MarketDataFeed |

---

## 11. 외부 레퍼런스 패턴 (리서치 출처)

설계 결정에 참조한 오픈소스 시스템:

| 시스템                           | 차용한 패턴                                                               |
| -------------------------------- | ------------------------------------------------------------------------- |
| **NautilusTrader** (Rust+Python) | asyncio 단일 이벤트 루프, research-to-live parity, Strategy Protocol 설계 |
| **Freqtrade** (Python)           | 전략 플러그인 클래스 구조, 백테스트 하니스 패턴                           |
| **Jesse** (Python)               | 심플한 Strategy API, 내장 리스크 관리                                     |
| **AAT** (Python+C++)             | 모듈형 이벤트 드리븐 프레임워크, asyncio.gather 패턴                      |

> 직접 의존성으로 추가하지 않고 **패턴 참조**만. quanteo는 KIS API 특화 구현을 직접 유지.
