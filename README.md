# quanteo

Toss증권 Open API 기반 주식 자동매매 봇.

국내·해외 주식을 대상으로 시그널 생성 → 리스크 검증 → 주문 실행까지 완전 자동화.  
기본 환경은 **모의투자(`vps`)**이며, 실전(`prod`)은 명시 플래그로만 활성화된다.

---

## 아키텍처

```
┌─────────────────────────────────────────────────────────┐
│  quanteo-core  (Python, asyncio 상주 프로세스)           │
│                                                          │
│   Market Data ──▶ Strategy Engine ──▶ Risk Manager       │
│       ▲                                    │             │
│       │                                    ▼             │
│   Toss Adapter (REST 폴링) ◀────────── Order Executor     │
│       │                                                  │
│   State Store (SQLite) + Event Bus (asyncio.Queue)       │
│       ▲                          │ events                │
│   Control API (FastAPI)    Notifier (Telegram Bot)       │
└──────────┬────────────────────────┬─────────────────────┘
           │ HTTP/WebSocket          │ Telegram API
   quanteo-dashboard            Telegram 앱
```

**핵심 원칙:**

- **단방향 흐름**: 데이터 → 시그널 → 리스크 검증 → 주문. 모든 주문은 반드시 Risk Manager를 통과한다.
- **asyncio 단일 이벤트 루프**: 모든 I/O를 `asyncio.gather()`로 동시 실행 (스레드·락 없음).
- **BrokerAdapter Protocol**: `core/adapters/base.py` 추상화로 브로커 교체 시 상위 모듈 무수정.
- **REST 폴링**: Toss API WebSocket 미지원 → 2초 간격 `GET /api/v1/prices` 배치 조회.
- **실전 이중 게이트**: `--env prod`는 `--i-understand-real-money` 플래그 없이 진입 불가.

---

## 구현 현황 (Phase 1~14 완료)

> 상세 모듈·의존성·엔드포인트 현황은 [PROJECT_INDEX.md](PROJECT_INDEX.md) 참고.

| Phase     | 내용                             | Tasks     | 상태    |
| --------- | -------------------------------- | --------- | ------- |
| Phase 1   | 부트스트랩 & 인증                | T001~T005 | ✅ 완료 |
| Phase 2   | 시세 & 상태저장                  | T006~T010 | ✅ 완료 |
| Phase 2.5 | Telegram 알림 모듈               | T033~T038 | ✅ 완료 |
| Phase 3   | 전략 엔진 & 플러그인 시스템      | T011~T014 | ✅ 완료 |
| Phase 4   | Risk Manager & 주문 실행         | T015~T020 | ✅ 완료 |
| Phase 5   | Control API (FastAPI REST/WS)    | T021~T024 | ✅ 완료 |
| Phase 6   | TypeScript 대시보드 (React+Vite) | T025~T028 | ✅ 완료 |
| Phase 7   | 안전 & 운영 (Rate Limit·Docker)  | T029~T032 | ✅ 완료 |
| Phase 8   | Toss증권 어댑터 마이그레이션     | T039~T048 | ✅ 완료 |
| Phase 9   | Toss증권 어댑터 운영 완성        | T049~T056 | ✅ 완료 |
| Phase 10  | 정보 수집·알람 서브시스템        | T057~T068 | ✅ 완료 |
| Phase 11  | CCI 지표·멀티 타임프레임 판정    | T069~T072 | ✅ 완료 |
| Phase 12  | 박병창 매매기법 전략 플러그인    | T073~T076 | ✅ 완료 |
| Phase 13  | 백테스트 프레임워크              | T077~T083 | ✅ 완료 |
| Phase 14  | 프론트엔드 디자인 시스템 정비    | T084~T092 | ✅ 완료 |

---

## 디렉토리 구조

```
quanteo/
├── core/                        # Python 매매 코어
│   ├── app.py                   # 진입점 — asyncio.gather() 조립 + prod 게이트
│   ├── config/
│   │   └── settings.py          # 환경(prod/vps)·Toss 자격증명·Telegram 설정
│   ├── adapters/
│   │   ├── base.py              # BrokerAdapter·MarketPoller Protocol
│   │   ├── models.py            # 공통 어댑터 모델 (OrderAck 등)
│   │   ├── throttler.py         # Rate Limit 스로틀러 + 백오프
│   │   └── toss/
│   │       ├── auth.py          # OAuth2 Client Credentials, 토큰 캐시, 401 재발급
│   │       ├── models.py        # 도메인 타입 (BuyingPowerInfo/TossOrder/Fill/PriceLimits 등)
│   │       └── rest.py          # 20개 엔드포인트: 시세·잔고·주문CRUD·체결·캘린더·종목정보·환율·캔들
│   ├── store/
│   │   ├── schema.py            # SQLite 스키마 (positions/orders/fills/signals/events_log)
│   │   └── db.py                # 마이그레이션·State Store·재시작 복구 조회
│   ├── marketdata/
│   │   ├── models.py            # Tick / Quote / Candle 표준 모델
│   │   ├── normalizer.py        # Toss 수신 데이터 → 내부 표준 변환
│   │   └── feed.py              # REST 폴링 시세 공급 루프
│   ├── events/
│   │   ├── types.py             # 도메인 이벤트 타입 정의
│   │   └── bus.py               # Event Bus (asyncio.Queue 기반 발행/구독)
│   ├── strategy/
│   │   ├── base.py              # Strategy Protocol + Signal / MarketContext 타입
│   │   ├── engine.py            # 플러그인 로드·지표 갱신·시그널 생성 루프
│   │   ├── harness.py           # 전략 경량 검증 하니스 (과거 캔들 재현)
│   │   ├── timeframe_judge.py   # 멀티 타임프레임 방향 판정
│   │   ├── indicators/          # CCI·이동평균·헤드앤숄더 패턴 지표
│   │   └── plugins/             # 규칙 기반 전략 플러그인 (이동평균 교차·박병창 매매기법 등)
│   ├── backtest/                # 백테스트 엔진·메트릭·Walk-Forward 검증
│   ├── risk/
│   │   ├── models.py            # Order / Position / Rejection / HaltLevel 타입
│   │   └── manager.py           # 한도 가드·손절·익절·킬스위치 게이트키퍼
│   ├── execution/
│   │   └── executor.py          # 주문 전송·멱등성(clientOrderId)·체결 추적
│   ├── notifier/
│   │   ├── base.py              # Notifier Protocol + NotifyEvent / NotifyLevel 타입
│   │   ├── telegram.py          # TelegramNotifier (aiogram v3, Rate-limit 큐)
│   │   ├── mock.py              # MockNotifier (테스트용)
│   │   ├── templates.py         # Signal/Order/Fill/Risk/Error/Status 템플릿
│   │   ├── factory.py           # 설정 기반 Notifier 생성 (enabled: false → Mock)
│   │   └── wiring.py            # Event Bus 구독 연결
│   └── api/
│       ├── app.py               # FastAPI 앱 팩토리
│       ├── deps.py              # AppContainer 의존성 주입
│       ├── models.py            # 응답 모델 (Pydantic)
│       └── routes/
│           ├── status.py        # GET /status
│           ├── positions.py     # GET /positions
│           ├── orders.py        # GET /orders, POST /orders/{id}/cancel|modify
│           ├── control.py       # POST /control/pause|resume|kill
│           ├── stream.py        # WS /stream
│           ├── market.py        # GET /market-status, GET /risk-metrics
│           ├── trades.py        # GET /trades
│           └── backtest.py      # POST /backtest/run, GET /backtest/status|results
├── info/                        # 정보 수집·알람 서브시스템 (뉴스·환율·실적·경제지표·AI필터·Google Calendar)
├── dashboard/                   # TypeScript 대시보드 (React + Vite + Tailwind + shadcn/ui)
│   └── src/
│       ├── components/          # StatusBar / PositionsTable / OrdersTable / FillsTable / ControlPanel / StreamLog
│       ├── hooks/                # useStatus / usePositions / useOrders / useFills / useStream
│       ├── pages/                # Strategy.tsx — CCI·신뢰도 게이지·백테스트 UI
│       └── api/                  # Control API 클라이언트 + 타입
├── scripts/
│   └── send_balance.py          # 잔고 조회 후 Telegram 전송 일회성 스크립트
├── tests/                       # pytest (644 cases)
├── specs/                       # 아키텍처 설계서 + Task 목록 + Toss OpenAPI JSON 스펙
├── Dockerfile
├── docker-compose.yml
├── quanteo.yaml.example         # 자격증명 예시
└── pyproject.toml
```

---

## 요구사항

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) 패키지 매니저
- Toss증권 Open API `client_id` / `client_secret` ([openapi.tossinvest.com](https://openapi.tossinvest.com) → 앱 등록)
- Node.js 18+ (대시보드 개발 시)

---

## 설치

```bash
# Python 의존성
uv sync

# 대시보드 의존성 (선택)
cd dashboard && npm install
```

---

## 설정

저장소 **밖**에 자격증명 파일을 생성한다. (절대 커밋 금지)

```bash
mkdir -p ~/quanteo/config
cp quanteo.yaml.example ~/quanteo/config/quanteo.yaml
# 편집기로 client_id, client_secret을 채울 것
```

`QUANTEO_CONFIG_PATH` 환경 변수로 경로를 재지정할 수 있다. (기본: `~/quanteo/config/quanteo.yaml`)

**Telegram 알림** 사용 시 `telegram` 섹션을 채우고 `enabled: true`로 변경.  
채널 chat_id는 `-100` 접두사가 필요하다 (예: `-100123456789`).  
`enabled: false`(기본값)이면 `MockNotifier`로 자동 대체되어 알림 없이 동작한다.

---

## 실행

### 로컬 실행

```bash
# Control API만 구동 (시세·주문 없음, 개발·검수용)
uv run python -m core.app --env vps

# 트레이딩 전체 활성화
uv run python -m core.app --env vps --with-trading

# 실전 환경 (이중 확인 필수)
uv run python -m core.app --env prod --with-trading --i-understand-real-money
```

**CLI 옵션:**

| 옵션                        | 기본값      | 설명                                       |
| --------------------------- | ----------- | ------------------------------------------ |
| `--env`                     | `vps`       | 투자 환경 (`vps` / `prod`)                 |
| `--market`                  | `domestic`  | 시장 (`domestic` / `overseas`)             |
| `--host`                    | `127.0.0.1` | Control API 바인드 호스트                  |
| `--port`                    | `8000`      | Control API 바인드 포트                    |
| `--with-trading`            | off         | MarketData / Strategy / Executor 포함 여부 |
| `--i-understand-real-money` | off         | prod 환경 이중 확인 플래그                 |

### Docker

```bash
# 기동 (vps, Control API만)
docker compose up -d

# 이미지 재빌드
docker compose up --build

# 로그 확인
docker compose logs -f quanteo-core
```

---

## Control API

기동 후 `http://localhost:8000/docs` 에서 OpenAPI 문서를 확인할 수 있다.

| 메서드 | 엔드포인트                   | 설명                                    |
| ------ | ---------------------------- | --------------------------------------- |
| `GET`  | `/status`                    | 봇 상태 (환경·리스크 레벨·일일 주문수)  |
| `GET`  | `/positions`                 | 보유 포지션 목록                        |
| `GET`  | `/orders`                    | 주문 내역                               |
| `POST` | `/orders/{id}/cancel`        | 주문 취소                               |
| `POST` | `/orders/{id}/modify`        | 주문 정정                               |
| `GET`  | `/trades`                    | 체결 내역 조회                          |
| `GET`  | `/market-status`             | 국내·해외 개장 여부 + 캘린더            |
| `GET`  | `/risk-metrics`              | 리스크 지표 (halt_level·buying_power)   |
| `POST` | `/control/pause`             | 신규 시그널 처리 일시정지               |
| `POST` | `/control/resume`            | 일시정지 해제                           |
| `POST` | `/control/kill`              | 킬스위치 — 모든 신규 주문 차단          |
| `WS`   | `/stream`                    | 시세·시그널·체결·로그 실시간 스트림     |
| `POST` | `/backtest/run`              | 백테스트 비동기 실행 → run_id 반환      |
| `GET`  | `/backtest/status/{run_id}`  | 백테스트 실행 상태 조회                 |
| `GET`  | `/backtest/results/{run_id}` | 백테스트 결과 조회 (메트릭·에쿼티 커브) |

---

## 대시보드

```bash
# 개발 서버 (Control API가 8000포트에서 실행 중이어야 함)
cd dashboard && npm run dev

# 프로덕션 빌드
cd dashboard && npm run build
```

화면 구성: 봇 상태 표시줄 / 포지션 & 손익 테이블 / 주문 내역 + 취소 버튼 / 체결 내역 / 실시간 로그 스트림 / 제어 버튼

---

## 테스트

```bash
# 전체 테스트
uv run pytest

# 커버리지 포함
uv run pytest --cov=core --cov-report=term-missing

# 모듈별
uv run pytest tests/risk/
uv run pytest tests/notifier/
uv run pytest tests/integration/
```

---

## 린트 & 포맷

```bash
uv run ruff check .
uv run ruff format .
```

---

## 전략 플러그인 개발

`core/strategy/base.py`의 `Strategy` Protocol을 구조적으로 충족하는 클래스를 작성한다.

```python
from core.strategy.base import Strategy, Signal, SignalSide, MarketContext
from core.marketdata.models import Candle, Tick

class MyStrategy:
    name = "my-strategy"

    def warmup(self, history: list[Candle]) -> None:
        # 과거 캔들로 지표 초기화
        ...

    def on_tick(self, tick: Tick, ctx: MarketContext) -> Signal | None:
        # 매매 조건 충족 시 Signal 반환, 아니면 None
        if ...:
            return Signal(strategy=self.name, symbol=tick.symbol,
                          side=SignalSide.BUY, qty=1, reason="조건 충족")
        return None
```

검증 하니스(`core/strategy/harness.py`)로 과거 캔들을 재현해 신호를 확인할 수 있다.

---

## 주요 의존성

| 패키지                | 용도                      |
| --------------------- | ------------------------- |
| `httpx`               | Toss REST API 비동기 호출 |
| `pydantic`            | 데이터 모델·검증          |
| `pyyaml`              | 설정 파일 파싱            |
| `fastapi` + `uvicorn` | Control API               |
| `aiosqlite`           | 비동기 SQLite State Store |
| `aiogram`             | Telegram 봇 (v3)          |

---

## 보안 주의사항

- `quanteo.yaml`, `~/toss/cache/token.json`(OAuth2 토큰 캐시)은 절대 커밋하지 않는다.
- 주문 기본값은 항상 `vps`(모의투자). 실전(`prod`)은 명시적 이중 확인 플래그로만 활성화.
- `MARKET_DATA`(시세·잔고)·`ORDER`(주문) 그룹별 별도 스로틀러 버킷으로 Rate Limit 격리.

---

## 설계 문서

- [`PROJECT_INDEX.md`](PROJECT_INDEX.md) — 프로젝트 전체 현황 요약 (구조·의존성·엔드포인트)
- [`specs/2026-06-18-quanteo-architecture.md`](specs/2026-06-18-quanteo-architecture.md) — 아키텍처 설계서 (단일 진실 공급원)
- [`specs/tasks.md`](specs/tasks.md) — Phase·Task 단위 구현 작업 목록
- [`specs/tossinvest/`](specs/tossinvest/) — Toss증권 Open API JSON 스펙

---

## 라이선스

MIT
