# quanteo

한국투자증권(KIS) Open Trading API 기반 주식 자동매매 봇.

국내·해외 주식을 대상으로 시그널 생성 → 리스크 검증 → 주문 실행까지 완전 자동화를 목표로 한다.
기본 환경은 **모의투자(`vps`)**이며, 실전(`prod`)은 명시 플래그로만 활성화된다.

---

## 아키텍처 개요

```
┌─────────────────────────────────────────────────────────┐
│  quanteo-core  (Python, asyncio 상주 프로세스)            │
│                                                           │
│   Market Data ──▶ Strategy Engine ──▶ Risk Manager       │
│       ▲                                    │              │
│       │                                    ▼              │
│   KIS Adapter (REST/WS) ◀────────── Order Executor       │
│       │                                                   │
│   State Store (SQLite) + Event Bus (asyncio.Queue)        │
│       ▲                          │ events                 │
│   Control API (FastAPI)    Notifier (Telegram Bot)        │
└──────────┬────────────────────────┬──────────────────────┘
           │ HTTP/WebSocket          │ Telegram API
   quanteo-dashboard            Telegram 앱
```

**핵심 원칙:**

- 단방향 흐름: 데이터 → 시그널 → 리스크 검증 → 주문. 모든 주문은 반드시 Risk Manager를 통과한다.
- asyncio 단일 이벤트 루프: 모든 I/O를 `asyncio.gather()`로 동시 실행 (스레드·락 없음).
- 시장·환경 캡슐화: prod/vps 분기, TR_ID·도메인 차이는 KIS Adapter 안에 격리.

---

## 구현 현황

| Phase         | 설명                              | 상태 |
| ------------- | --------------------------------- | ---- |
| **Phase 1**   | 부트스트랩 & KIS 인증 (T001~T005) | 완료 |
| **Phase 2**   | 시세 & 상태저장 (T006~T010)       | 완료 |
| **Phase 2.5** | Telegram 알림 모듈 (T033~T038)    | 완료 |
| Phase 3       | 전략 엔진 (T011~T014)             | 예정 |
| Phase 4       | 리스크 & 주문 실행 (T015~T020)    | 예정 |
| Phase 5       | 제어 API (T021~T024)              | 예정 |
| Phase 6       | TypeScript 대시보드 (T025~T028)   | 예정 |
| Phase 7       | 안전 & 운영 (T029~T032)           | 예정 |

### 구현된 모듈

```
core/
├── config/          # 환경(prod/vps)·시장(domestic/overseas) 설정, kis_devlp.yaml 로딩
├── adapters/kis/
│   ├── auth.py      # Access Token 발급·캐싱·재발급, WebSocket 접속키
│   ├── rest.py      # 현재가·잔고 조회 REST 호출
│   ├── ws.py        # 실시간 시세/체결 WebSocket 구독
│   └── tr_ids.py    # TR_ID·REST/WS 도메인 매핑 (환경 × 시장)
├── store/
│   ├── schema.py    # SQLite 스키마 (positions/orders/fills/signals/settings/events_log)
│   └── db.py        # 마이그레이션 및 DB 접근
├── marketdata/
│   ├── models.py    # Tick / Quote / Candle 표준 모델
│   ├── normalizer.py# KIS 수신 데이터 → 내부 표준 변환
│   └── feed.py      # 시세 공급 루프
├── events/
│   ├── types.py     # 도메인 이벤트 타입 정의
│   └── bus.py       # Event Bus (asyncio.Queue 기반 발행/구독)
├── notifier/
│   ├── base.py      # Notifier Protocol + NotifyEvent/NotifyLevel 타입
│   ├── telegram.py  # TelegramNotifier (aiogram v3, Rate-limit 큐)
│   ├── mock.py      # MockNotifier (테스트용, sent_events 누적)
│   ├── templates.py # Signal/Order/Fill/Risk/Error/Status 메시지 템플릿
│   ├── factory.py   # 설정 기반 Notifier 생성 (enabled: false → MockNotifier)
│   └── wiring.py    # Event Bus 구독 연결
└── app.py           # 애플리케이션 진입점, asyncio.gather() 조립
```

---

## 요구사항

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) 패키지 매니저
- 한국투자증권 Open Trading API 앱키/시크릿 (모의투자 계정)

---

## 설치

```bash
# 의존성 설치
uv sync
```

---

## 설정

저장소 밖에 자격증명 파일을 생성한다. (`~/KIS/config/kis_devlp.yaml` 또는 커스텀 경로)

```bash
cp kis_devlp.yaml.example ~/KIS/config/kis_devlp.yaml
# 편집기로 앱키·시크릿·계좌번호 등을 채울 것
```

Telegram 알림을 사용하려면 `telegram` 섹션을 채우고 `enabled: true`로 변경한다.  
`enabled: false`(기본값)이면 자동으로 `MockNotifier`로 대체되어 알림 없이 동작한다.

---

## 실행

```bash
uv run python -m core.app
```

---

## 테스트

```bash
# 전체 테스트
uv run pytest

# 커버리지 포함
uv run pytest --cov=core --cov-report=term-missing

# 단일 모듈
uv run pytest tests/notifier/
```

---

## 린트 & 포맷

```bash
uv run ruff check .
uv run ruff format .
```

---

## 주요 의존성

| 패키지                | 용도                      |
| --------------------- | ------------------------- |
| `httpx`               | KIS REST API 비동기 호출  |
| `websockets`          | KIS WebSocket 실시간 시세 |
| `pydantic`            | 데이터 모델·검증          |
| `pyyaml`              | 설정 파일 파싱            |
| `fastapi` + `uvicorn` | 제어 API (Phase 5)        |
| `aiosqlite`           | 비동기 SQLite State Store |
| `duckdb`              | 분석 쿼리용 (Phase 5+)    |
| `aiogram`             | Telegram 봇 (aiogram v3)  |

---

## 보안 주의사항

- `kis_devlp.yaml`, `.env`, 앱키/시크릿/토큰 캐시 파일은 절대 커밋하지 않는다.
- 주문(매수/매도) 기본값은 항상 `vps`(모의투자). 실전 주문(`prod`)은 명시적 환경 플래그로만 활성화.
- KIS API 호출 빈도 제한(Rate Limit)을 초과하지 않도록 폴링·주문 루프에 스로틀을 적용한다.

---

## 설계 문서

- [`specs/2026-06-18-quanteo-architecture.md`](specs/2026-06-18-quanteo-architecture.md) — 아키텍처 설계서 (단일 진실 공급원)
- [`specs/tasks.md`](specs/tasks.md) — Phase·Task 단위 구현 작업 목록

---

## 라이선스

MIT
