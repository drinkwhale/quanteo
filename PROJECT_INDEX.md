# Project Index: quanteo

Generated: 2026-06-18

## 📋 Status

**Bootstrapping** — 설계 완료, 코드 없음. `specs/` 문서만 존재. Phase 1(T001)부터 구현 시작 예정.

---

## 📁 Project Structure (현재)

```
quanteo/
├── specs/
│   ├── 2026-06-18-quanteo-architecture.md  # 확정 아키텍처 설계서 (단일 진실 공급원)
│   └── tasks.md                             # Phase/Task 구현 목록 (T001~T032)
├── CLAUDE.md                                # 프로젝트 Claude 가이드
├── .gitignore
├── LICENSE
└── README.md
```

### 계획된 구조 (부트스트랩 후)

```
quanteo/
├── core/                        # Python 매매 코어 (uv, Python 3.11+)
│   ├── adapters/kis/            # KIS REST/WS Adapter + 인증 + TR_ID 매핑
│   ├── marketdata/              # 시세 정규화 (Tick/Quote/Candle)
│   ├── strategy/
│   │   ├── base.py              # Strategy Protocol 정의
│   │   ├── engine.py            # 플러그인 로드·시그널 루프
│   │   └── plugins/             # 교체형 전략 플러그인
│   ├── risk/                    # Risk Manager + 킬스위치
│   ├── execution/               # Order Executor (멱등성)
│   ├── store/                   # SQLite State Store
│   ├── events/                  # Event Bus
│   ├── api/                     # Control API (FastAPI REST + WS)
│   ├── config/                  # 환경/시장 설정 로딩
│   └── app.py                   # 코어 부팅·이벤트 루프 조립
├── dashboard/                   # TypeScript 웹 대시보드 (Phase 6)
├── tests/                       # pytest
└── pyproject.toml               # uv 환경 (T001에서 생성)
```

---

## 🚀 Entry Points (계획)

| 파일          | 용도                                       |
| ------------- | ------------------------------------------ |
| `core/app.py` | 메인 봇 프로세스 진입점                    |
| `core/api/`   | FastAPI Control API 서버                   |
| `dashboard/`  | TypeScript 대시보드 (패키지 매니저 미확정) |

---

## 📦 Core Modules (계획 — 아직 미구현)

| 모듈            | 경로                 | 의존                     | 책임                                           |
| --------------- | -------------------- | ------------------------ | ---------------------------------------------- |
| KIS Adapter     | `core/adapters/kis/` | KIS API                  | 인증, REST/WS, TR_ID 매핑, 환경·시장 분기      |
| Market Data     | `core/marketdata/`   | KIS Adapter              | Tick/Quote/Candle 정규화·공급                  |
| Strategy Engine | `core/strategy/`     | Market Data              | 플러그인 로드, 지표 계산, 시그널 생성          |
| Risk Manager    | `core/risk/`         | State Store              | 한도·킬스위치·손절·익절 가드                   |
| Order Executor  | `core/execution/`    | KIS Adapter, State Store | 주문 전송·체결 추적·멱등성                     |
| State Store     | `core/store/`        | —                        | SQLite 영속화 (positions/orders/fills/signals) |
| Event Bus       | `core/events/`       | —                        | 모듈 간 pub/sub                                |
| Control API     | `core/api/`          | State Store, Event Bus   | FastAPI REST + WS                              |
| Config          | `core/config/`       | —                        | `kis_devlp.yaml` 로딩, env/market 분기         |

---

## 🔧 Configuration

| 파일             | 위치                          | 비고                                                  |
| ---------------- | ----------------------------- | ----------------------------------------------------- |
| `kis_devlp.yaml` | `~/KIS/config/kis_devlp.yaml` | **저장소 밖, 커밋 금지.** 앱키/시크릿/HTS ID/계좌번호 |
| `.env`           | 프로젝트 루트                 | **커밋 금지.** gitignore 처리됨                       |
| `pyproject.toml` | 프로젝트 루트                 | T001에서 생성 (uv, Python 3.11+)                      |

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
| `specs/tasks.md`                           | T001~T032 구현 작업 목록. Phase 단위 진행.     |
| `CLAUDE.md`                                | Claude Code 작업 지침 (KIS API 핵심 개념 포함) |

---

## 🧪 Test Strategy (계획)

| 유형   | 대상                                                     |
| ------ | -------------------------------------------------------- |
| 단위   | 각 모듈을 인터페이스로 격리, KIS Adapter는 mock          |
| 전략   | 과거 캔들로 시그널 검증 (경량 하니스, T014)              |
| 리스크 | 한도·킬스위치·손절 경계 케이스 집중 (T015~T017)          |
| 통합   | `vps` 환경에서 시그널→리스크→주문 라운드트립 (T020)      |
| 안전   | `prod` 경로가 명시 플래그 없이 실행 불가임을 보장 (T031) |

---

## 🔗 Key Dependencies (계획)

| 라이브러리           | 용도                     |
| -------------------- | ------------------------ |
| Python 3.11+         | 매매 코어 런타임         |
| uv                   | Python 패키지 매니저     |
| FastAPI              | Control API 서버         |
| SQLite               | State Store              |
| websockets / aiohttp | KIS WebSocket 클라이언트 |
| pytest               | 테스트 프레임워크        |

---

## 🗺️ Implementation Roadmap

| Phase  | Tasks     | 목표                                            |
| ------ | --------- | ----------------------------------------------- |
| **P1** | T001–T005 | 프로젝트 스캐폴드, 설정/환경 로딩, KIS 인증     |
| **P2** | T006–T010 | Market Data 수신·정규화, State Store, Event Bus |
| **P3** | T011–T014 | Strategy 플러그인 인터페이스 + 첫 지표 전략     |
| **P4** | T015–T020 | Risk Manager + Order Executor (vps 주문)        |
| **P5** | T021–T024 | Control API REST/WS                             |
| **P6** | T025–T028 | TypeScript 대시보드                             |
| **P7** | T029–T032 | 킬스위치·복구·rate limit·prod 게이트            |

---

## 📝 Quick Start (부트스트랩 후)

```bash
# Python 환경 (T001 이후)
uv sync
uv run python core/app.py --env vps

# 테스트
uv run pytest tests/

# 단일 테스트
uv run pytest tests/test_risk.py::test_kill_switch
```

자격증명 설정: ~/KIS/config/kis_devlp.yaml 에 앱키/시크릿/계좌번호 입력 후 실행.

---

## Safety Rules

1. 기본 환경은 항상 vps(모의투자)
2. 모든 주문은 반드시 Risk Manager 통과
3. prod 실전 전환은 명시 플래그 이중 확인
4. 자격증명은 저장소 밖 — 절대 커밋 금지
5. KIS Rate limit 준수 (Adapter 내 스로틀러)
