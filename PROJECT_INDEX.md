# Project Index: quanteo

Generated: 2026-06-24

## 📋 Status

**Phase 1~6 완료** — Phase 7 (안전 & 운영) 진행 예정.

| Phase    | Tasks     | 상태    | 내용                                            |
| -------- | --------- | ------- | ----------------------------------------------- |
| **P1**   | T001–T005 | ✅ 완료 | 프로젝트 스캐폴드, 설정/환경 로딩, KIS 인증     |
| **P2**   | T006–T010 | ✅ 완료 | Market Data 수신·정규화, State Store, Event Bus |
| **P2.5** | T033–T038 | ✅ 완료 | Notifier 모듈 (Telegram + MockNotifier)         |
| **P3**   | T011–T014 | ✅ 완료 | Strategy Protocol, Engine, MA Cross, Harness    |
| **P4**   | T015–T020 | ✅ 완료 | Risk Manager + Order Executor (vps 주문)        |
| **P5**   | T021–T024 | ✅ 완료 | Control API REST/WS + 전체 모듈 wiring          |
| **P6**   | T025–T028 | ✅ 완료 | TypeScript 대시보드 (React+Vite+Tailwind)       |
| **P7**   | T029–T032 | ⬜ 미완 | 킬스위치·복구·rate limit·prod 게이트            |

**테스트:** 252 passed (Python) · TypeScript tsc clean (2026-06-24 기준)

---

## 📁 Project Structure (현재)

```
quanteo/
├── core/
│   ├── adapters/kis/         # KIS REST/WS Adapter + 인증 + TR_ID 매핑
│   │   ├── auth.py           # access token 발급·캐싱·재발급 + WebSocket 접속키
│   │   ├── rest.py           # 현재가·잔고 조회, 매수/매도 주문 REST
│   │   ├── ws.py             # 실시간 시세/체결 WebSocket 구독
│   │   └── tr_ids.py         # 환경(prod/vps)×시장(domestic/overseas) TR_ID 매핑
│   ├── api/                  # Control API (FastAPI)
│   │   ├── app.py            # create_app() 팩토리
│   │   ├── deps.py           # AppContainer 의존성 주입
│   │   ├── models.py         # BotStatus/PositionList/OrderList/StreamMessage
│   │   └── routes/
│   │       ├── status.py     # GET /status
│   │       ├── positions.py  # GET /positions
│   │       ├── orders.py     # GET /orders
│   │       ├── control.py    # POST /control/pause|resume|kill
│   │       └── stream.py     # WS /stream (Event Bus 브로드캐스트)
│   ├── config/settings.py    # AppSettings (Pydantic), kis_devlp.yaml 로딩
│   ├── events/
│   │   ├── bus.py            # EventBus (asyncio.Queue pub/sub)
│   │   └── types.py          # Event, EventType 정의
│   ├── execution/executor.py # OrderExecutor (주문전송·체결추적·멱등성)
│   ├── marketdata/
│   │   ├── feed.py           # MarketDataFeed (Tick/Quote/Candle 공급)
│   │   ├── models.py         # Tick, Quote, Candle 내부 표준 타입
│   │   └── normalizer.py     # KIS 원시 데이터 → 내부 표준 정규화
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
│   │   ├── db.py             # StateStore (aiosqlite CRUD)
│   │   └── schema.py         # DDL (positions/orders/fills/signals/events_log)
│   ├── strategy/
│   │   ├── base.py           # Strategy Protocol (warmup/on_tick/on_candle)
│   │   ├── engine.py         # StrategyEngine (플러그인 로드·시그널 루프)
│   │   ├── harness.py        # BacktestHarness (과거 캔들로 시그널 검증)
│   │   └── plugins/ma_cross.py  # 이동평균 교차 전략 플러그인
│   └── app.py                # 코어 부팅·asyncio.gather wiring (전체 진입점)
├── dashboard/                # TypeScript 웹 대시보드
│   ├── src/
│   │   ├── api/
│   │   │   ├── client.ts     # REST fetch 래퍼 + WebSocket 팩토리
│   │   │   └── types.ts      # BotStatus/PositionItem/OrderItem/StreamMessage 타입
│   │   ├── components/
│   │   │   ├── StatusBar.tsx     # 봇 상태 상단바 (halt_level·env·uptime)
│   │   │   ├── PositionsTable.tsx # 포지션 테이블
│   │   │   ├── OrdersTable.tsx    # 주문내역 테이블
│   │   │   ├── StreamLog.tsx      # 실시간 이벤트 로그 뷰
│   │   │   └── ControlPanel.tsx   # 일시정지/재개/킬스위치 UI
│   │   ├── hooks/
│   │   │   ├── useStatus.ts   # 3초 폴링
│   │   │   ├── usePositions.ts # 5초 폴링
│   │   │   ├── useOrders.ts   # 5초 폴링
│   │   │   └── useStream.ts   # WebSocket + 3초 재연결
│   │   ├── App.tsx           # 레이아웃 조립 (2/3 데이터 + 1/3 제어)
│   │   └── main.tsx          # React 18 진입점
│   ├── vite.config.ts        # /api → localhost:8000 proxy
│   ├── tailwind.config.js    # 다크 트레이딩 테마
│   └── package.json          # React 18, Vite 5, TailwindCSS 3
├── tests/                    # pytest (252 passed)
│   ├── adapters/kis/         # auth·rest·tr_ids·ws 단위 테스트
│   ├── api/                  # Control API 엔드포인트 테스트
│   ├── config/, events/, execution/, marketdata/
│   ├── notifier/             # Telegram·Mock·template·wiring 테스트
│   ├── risk/                 # RiskManager 한도·손절·킬스위치 테스트
│   ├── store/                # StateStore CRUD 테스트
│   ├── strategy/             # Engine·Harness·MA Cross 플러그인 테스트
│   ├── integration/          # signal→risk→order 라운드트립 테스트
│   └── conftest.py           # 공통 fixture (AppContainer mock, DB)
├── specs/
│   ├── tasks.md              # Phase·Task 체크박스 (구현 진척 관리)
│   └── 2026-06-18-quanteo-architecture.md  # 확정 아키텍처 설계서
├── pyproject.toml            # uv 프로젝트 설정, 의존성, ruff/pytest 설정
├── kis_devlp.yaml.example    # 자격증명 예시 (실제 파일은 저장소 밖)
└── CLAUDE.md                 # Claude Code 세션 지침
```

---

## 🚀 Quick Start

```bash
# Python 코어
uv sync
uv run python -m core.app          # 봇 전체 실행
uv run pytest                       # 테스트 (252 cases)
uv run ruff check . && ruff format .  # 린트·포맷

# TypeScript 대시보드 (별도 터미널)
cd dashboard && npm install
npm run dev    # http://localhost:5173 (API 프록시 → :8000)
npm run build  # 프로덕션 빌드 (~154KB gzipped 49KB)
```

---

## 🔌 Control API 엔드포인트

| Method | Path              | 설명                            |
| ------ | ----------------- | ------------------------------- |
| GET    | `/status`         | 봇 상태 (halt_level·env·uptime) |
| GET    | `/positions`      | 보유 포지션 목록                |
| GET    | `/orders`         | 주문 내역                       |
| POST   | `/control/pause`  | 일시정지                        |
| POST   | `/control/resume` | 재개                            |
| POST   | `/control/kill`   | 킬스위치 활성화                 |
| WS     | `/stream`         | Event Bus 실시간 브로드캐스트   |

---

## 📦 핵심 의존성

### Python

| 패키지                | 용도                 |
| --------------------- | -------------------- |
| `fastapi` + `uvicorn` | Control API 서버     |
| `httpx`               | KIS REST 호출        |
| `websockets`          | KIS WebSocket 구독   |
| `pydantic v2`         | 설정·모델 검증       |
| `aiosqlite`           | State Store (SQLite) |
| `aiogram v3`          | Telegram 알림        |
| `duckdb`              | OLAP 분석 (예정)     |

### TypeScript (dashboard)

| 패키지                   | 용도                    |
| ------------------------ | ----------------------- |
| `react 18` + `react-dom` | UI 렌더링               |
| `vite 5`                 | 빌드·dev proxy          |
| `tailwindcss 3`          | 다크 트레이딩 UI 스타일 |
| `typescript 5`           | 타입 안전성             |

---

## 🔒 보안 원칙

- `kis_devlp.yaml` (앱키·시크릿·계좌번호) — 저장소 밖, 절대 커밋 금지
- 기본 환경 `vps` (모의투자). `prod` 실전은 명시 플래그만.
- 모든 주문 경로는 RiskManager 통과 필수.

---

## 📝 주요 설계 결정

- **asyncio 단일 이벤트 루프**: 스레드 없이 `asyncio.gather()`로 모든 I/O 병렬화
- **단방향 흐름**: MarketData → Strategy → RiskManager → OrderExecutor
- **플러그인 교체형 전략**: `strategy/plugins/`에 파일 추가 + 설정으로 활성화
- **Research-to-Live Parity**: Backtest·Live 동일 이벤트 모델 → 전략 코드 변경 없이 전환
- **단계적 킬스위치**: NONE → REDUCE → PAUSE → KILL 4단계
