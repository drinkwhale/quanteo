# quanteo

한국투자증권(KIS) Open Trading API 기반 주식 자동매매 봇.

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
│   KIS Adapter (REST/WS) ◀────────── Order Executor       │
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
- **asyncio 단일 이벤트 루프**: 모든 I/O를 `asyncio.TaskGroup`으로 동시 실행 (스레드·락 없음).
- **환경 격리**: prod/vps 분기, TR_ID·도메인 차이는 KIS Adapter 안에 캡슐화.
- **실전 이중 게이트**: `--env prod`는 `--i-understand-real-money` 플래그 없이 진입 불가.

---

## 구현 현황 (Phase 1~7 완료)

| Phase     | 내용                             | Tasks     | 상태    |
| --------- | -------------------------------- | --------- | ------- |
| Phase 1   | 부트스트랩 & KIS 인증            | T001~T005 | ✅ 완료 |
| Phase 2   | 시세 & 상태저장                  | T006~T010 | ✅ 완료 |
| Phase 2.5 | Telegram 알림 모듈               | T033~T038 | ✅ 완료 |
| Phase 3   | 전략 엔진 & 플러그인 시스템      | T011~T014 | ✅ 완료 |
| Phase 4   | Risk Manager & 주문 실행         | T015~T020 | ✅ 완료 |
| Phase 5   | Control API (FastAPI REST/WS)    | T021~T024 | ✅ 완료 |
| Phase 6   | TypeScript 대시보드 (React+Vite) | T025~T028 | ✅ 완료 |
| Phase 7   | 안전 & 운영 (Rate Limit·Docker)  | T029~T032 | ✅ 완료 |

---

## 디렉토리 구조

```
quanteo/
├── core/                        # Python 매매 코어
│   ├── app.py                   # 진입점 — asyncio.TaskGroup 조립
│   ├── config/
│   │   └── settings.py          # 환경(prod/vps)·시장·자격증명·Telegram 설정
│   ├── adapters/kis/
│   │   ├── auth.py              # Access Token 발급·캐싱·재발급, WS 접속키
│   │   ├── rest.py              # 시세/잔고/매수·매도 REST 호출
│   │   ├── ws.py                # 실시간 시세/체결 WebSocket 구독
│   │   ├── tr_ids.py            # TR_ID·REST/WS 도메인 매핑 (환경 × 시장)
│   │   └── throttler.py         # Rate Limit 스로틀러 + 백오프
│   ├── store/
│   │   ├── schema.py            # SQLite 스키마 (positions/orders/fills/signals/events_log)
│   │   └── db.py                # 마이그레이션·State Store·재시작 복구 조회
│   ├── marketdata/
│   │   ├── models.py            # Tick / Quote / Candle 표준 모델
│   │   ├── normalizer.py        # KIS 수신 데이터 → 내부 표준 변환
│   │   └── feed.py              # 시세 공급 루프
│   ├── events/
│   │   ├── types.py             # 도메인 이벤트 타입 정의
│   │   └── bus.py               # Event Bus (asyncio.Queue 기반 발행/구독)
│   ├── strategy/
│   │   ├── base.py              # Strategy Protocol + Signal / MarketContext 타입
│   │   ├── engine.py            # 플러그인 로드·지표 갱신·시그널 생성 루프
│   │   ├── harness.py           # 전략 경량 검증 하니스 (과거 캔들 재현)
│   │   └── plugins/             # 규칙 기반 전략 플러그인 (이동평균 교차 등)
│   ├── risk/
│   │   ├── models.py            # Order / Position / Rejection / HaltLevel 타입
│   │   └── manager.py           # 한도 가드·손절·익절·킬스위치 게이트키퍼
│   ├── execution/
│   │   └── executor.py          # 주문 전송·멱등성(client_order_id)·체결 추적
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
│           ├── orders.py        # GET /orders
│           ├── control.py       # POST /control/pause|resume|kill
│           └── stream.py        # WS /stream
├── dashboard/                   # TypeScript 대시보드 (React + Vite + Tailwind)
│   └── src/
│       ├── components/          # StatusBar / PositionsTable / OrdersTable / ControlPanel / StreamLog
│       ├── hooks/               # useStatus / usePositions / useOrders / useStream
│       └── api/                 # Control API 클라이언트 + 타입
├── tests/                       # pytest 테스트 스위트
├── specs/                       # 아키텍처 설계서 + Task 목록
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

---

## 요구사항

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) 패키지 매니저
- 한국투자증권 Open Trading API 앱키/시크릿 (모의투자 계정)
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
cp kis_devlp.yaml.example ~/KIS/config/kis_devlp.yaml
# 편집기로 앱키·시크릿·계좌번호·HTS ID를 채울 것
```

`QUANTEO_CONFIG_PATH` 환경 변수로 경로를 재지정할 수 있다. (기본: `~/KIS/config/kis_devlp.yaml`)

**Telegram 알림** 사용 시 `telegram` 섹션을 채우고 `enabled: true`로 변경.  
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

`KIS_CONFIG_DIR` 환경 변수로 KIS 설정 디렉토리를 지정한다. (기본: `~/KIS`)

---

## Control API

기동 후 `http://localhost:8000/docs` 에서 OpenAPI 문서를 확인할 수 있다.

| 메서드 | 엔드포인트        | 설명                                   |
| ------ | ----------------- | -------------------------------------- |
| `GET`  | `/status`         | 봇 상태 (환경·리스크 레벨·일일 주문수) |
| `GET`  | `/positions`      | 보유 포지션 목록                       |
| `GET`  | `/orders`         | 주문 내역                              |
| `POST` | `/control/pause`  | 신규 시그널 처리 일시정지              |
| `POST` | `/control/resume` | 일시정지 해제                          |
| `POST` | `/control/kill`   | 킬스위치 — 모든 신규 주문 차단         |
| `WS`   | `/stream`         | 시세·시그널·체결·로그 실시간 스트림    |

---

## 대시보드

```bash
# 개발 서버 (Control API가 8000포트에서 실행 중이어야 함)
cd dashboard && npm run dev

# 프로덕션 빌드
cd dashboard && npm run build
```

화면 구성: 봇 상태 표시줄 / 포지션 & 손익 테이블 / 주문 내역 / 실시간 로그 스트림 / 제어 버튼

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
| `httpx`               | KIS REST API 비동기 호출  |
| `websockets`          | KIS WebSocket 실시간 시세 |
| `pydantic`            | 데이터 모델·검증          |
| `pyyaml`              | 설정 파일 파싱            |
| `fastapi` + `uvicorn` | Control API               |
| `aiosqlite`           | 비동기 SQLite State Store |
| `duckdb`              | 분석 쿼리용               |
| `aiogram`             | Telegram 봇 (v3)          |

---

## 보안 주의사항

- `kis_devlp.yaml`, `.env`, 앱키/시크릿/토큰 캐시 파일은 절대 커밋하지 않는다.
- 주문 기본값은 항상 `vps`(모의투자). 실전(`prod`)은 명시적 이중 확인 플래그로만 활성화.
- KIS API Rate Limit을 초과하지 않도록 Throttler가 자동으로 요청을 조절한다.

---

## 설계 문서

- [`specs/2026-06-18-quanteo-architecture.md`](specs/2026-06-18-quanteo-architecture.md) — 아키텍처 설계서 (단일 진실 공급원)
- [`specs/tasks.md`](specs/tasks.md) — Phase·Task 단위 구현 작업 목록

---

## 라이선스

MIT
