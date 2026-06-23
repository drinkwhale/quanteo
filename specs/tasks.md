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

- [ ] **T021** `core/api/` — FastAPI 앱 + `/status`, `/positions`, `/orders` 조회 엔드포인트
- [ ] **T022** `core/api/` — `/control/pause|resume|kill` 명령 엔드포인트
- [ ] **T023** `core/api/` — `/stream` WebSocket(시세·시그널·체결·로그 실시간)
- [ ] **T024** `core/app.py` — 코어 부팅·이벤트 루프 조립(모든 모듈 wiring)

## Phase 6 — 대시보드 (TypeScript)

- [ ] **T025** `dashboard/` — 프로젝트 스캐폴드(패키지 매니저 확정, Control API 클라이언트)
- [ ] **T026** 포지션·손익·주문내역 화면
- [ ] **T027** 실시간 스트림(WS) 연동 + 로그 뷰
- [ ] **T028** 일시정지/재개/킬스위치 제어 UI

## Phase 7 — 안전 & 운영

- [ ] **T029** Rate limit 스로틀러(KIS Adapter 내장) + 백오프
- [ ] **T030** 재시작 복구: State Store에서 포지션/미체결 주문 복원
- [ ] **T031** `prod` 실전 게이트(이중 확인 플래그) + 안전 게이트 테스트
- [ ] **T032** 컨테이너화(Dockerfile) — 클라우드 확장 대비

---

## 다음 단계

구현을 시작하려면 "Phase 1 진행해줘" 또는 "T001까지 진행해줘"로 요청.
