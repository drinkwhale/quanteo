# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**quanteo** — 한국투자증권(KIS) Open Trading API를 이용한 주식 자동매매(트레이딩) 봇.

- 참고 API/샘플 저장소: https://github.com/koreainvestment/open-trading-api (Python 주력 + TypeScript 포팅 + MCP)
- 구현 전략: **Python + TypeScript 하이브리드**. 공식 `open-trading-api` 샘플 코드를 이 저장소로 **복사/적응(copy & adapt)** 하는 방식으로 개발.

## ⚠️ 현재 상태 (Bootstrapping)

이 저장소는 아직 **코드가 거의 없는 초기 상태**다 (README, LICENSE, .gitignore + `specs/` 설계 문서만 존재). 아래 "아키텍처"와 "명령어"는 **참고 API 기준의 계획/규약**이며, 실제 파일·빌드 설정은 작업하면서 만들어진다. 코드를 작성하기 전에 항상 현재 디렉토리 구조를 먼저 확인하고, 이 문서와 실제 상태가 다르면 **이 문서를 갱신**할 것.

## 📐 설계 & 작업 문서 (새 세션에서 먼저 읽을 것)

아키텍처와 작업 계획이 확정되어 `specs/`에 문서화되어 있다. **작업 시작 전 반드시 확인.**

- **[specs/2026-06-18-quanteo-architecture.md](specs/2026-06-18-quanteo-architecture.md)** — 확정된 아키텍처 설계서(단일 진실 공급원). 구현이 달라지면 이 문서를 갱신.
- **[specs/tasks.md](specs/tasks.md)** — Phase·Task 단위 구현 작업 목록. "T{번호}/Phase 진행" 요청 시 이 파일 기준.

### 확정된 핵심 결정 (요약)

- **목표:** 완전 자동매매 봇 (시그널 → 주문까지 자동 실행)
- **시장:** 국내 + 해외 주식 (시장 추상화)
- **스택:** Python 매매 코어 + TypeScript 웹 대시보드
- **전략:** 규칙 기반 지표 전략, 플러그인 교체형 (전략은 **시그널만** 생성)
- **아키텍처(접근 B):** 모듈형 단일 Python 프로세스 + 얇은 Control API(FastAPI REST/WS) + TS 대시보드. 클라우드 확장 대비 모듈 경계 명확화.
- **모듈:** KIS Adapter → Market Data → Strategy Engine → Risk Manager → Order Executor / State Store(SQLite) / Event Bus / Control API / Dashboard
- **안전 원칙:** 모든 주문은 **반드시 Risk Manager 통과**. 기본 환경 `vps`(모의투자), `prod`는 명시 플래그로만.

## KIS API 핵심 개념 (반드시 숙지)

자동매매의 정확성과 안전성이 직결되는 부분이라 가장 먼저 이해해야 한다.

- **인증 (`kis_auth.py` 패턴):** 앱키/시크릿으로 access token을 발급받아 REST 호출과 WebSocket 접속키를 관리. 토큰은 캐싱/재사용하며 만료 시 재발급.
- **환경 구분 (절대 혼동 금지):**
  - `prod` = **실전투자(실제 주문/실제 돈)**
  - `vps` = **모의투자(paper trading)**
  - REST 도메인과 WebSocket 도메인, 앱키/시크릿이 환경별로 **각각 다름**. 코드/설정에서 환경을 명시적으로 다루고, 기본값은 항상 모의투자(`vps`)로 둘 것.
- **설정 파일 `kis_devlp.yaml`:** 자격증명을 담으며 보통 `~/KIS/config/kis_devlp.yaml`에 위치(저장소 밖, 절대 커밋 금지). 실전/모의용 앱키·시크릿, HTS ID, 계좌번호(8자리 + 상품코드 2자리), User-Agent 포함.
- **계좌번호:** `CANO`(8자리) + `ACNT_PRDT_CD`(상품코드 2자리, 예: 종합계좌 `01`)로 분리되어 전달됨.
- **TR_ID:** 모든 REST 호출은 거래 ID(TR_ID)로 식별되며, **실전/모의에서 TR_ID가 다른 경우가 많다.** 주문/시세 함수 작성 시 환경에 맞는 TR_ID를 반드시 확인.
- **WebSocket:** 실시간 시세/체결 구독. 별도 접속키(`auth_ws` 패턴)로 연결 후 종목별로 `subscribe`.

## 공식 샘플 저장소 구조 (복사 출처)

`open-trading-api`에서 코드를 가져올 때 참고하는 두 가지 병렬 구조:

- `examples_llm/` — **함수 단위** 샘플. `inquire_price.py`(기능) + `chk_inquire_price.py`(테스트) 형태. 개별 API를 골라 적응할 때 출처.
- `examples_user/` — **카테고리 통합** 샘플. `domestic_stock_functions.py`(함수 모음) + `domestic_stock_examples.py`(실행 예제). 실전 흐름 참고용.
- 상품 카테고리: `domestic_stock/`, `overseas_stock/`, `domestic_futureoption/`, `domestic_bond/`, `etfetn/`, `elw/` 등.
- `auth/` — 토큰 발급(REST/WebSocket).

샘플을 복사할 때는 출처 경로를 커밋 메시지나 주석에 남겨, 이후 공식 저장소 업데이트와 대조할 수 있게 할 것.

## 명령어 (참고 API 기준 — 프로젝트 부트스트랩 후 갱신 필요)

아직 이 저장소에는 빌드/테스트 설정이 없다. 참고 저장소 및 선택한 스택의 표준 명령:

**Python (uv, Python 3.11+):**

- 의존성: `uv sync`
- 실행: `uv run <script.py>`
- 단일 테스트: `uv run pytest <path>::<test_name>`

**TypeScript/Node.js (Node 18+):**

- 의존성: 패키지 매니저 확정 후 기재 (`.gitignore`는 npm/pnpm/yarn 모두 무시하도록 되어 있음)

> 실제 명령어는 `pyproject.toml`/`package.json`이 생성되는 시점에 이 섹션을 사실대로 갱신할 것. 존재하지 않는 명령을 추정해서 적지 말 것.

## 규칙 및 제약

- **자격증명 격리:** `kis_devlp.yaml`, `.env`, 앱키/시크릿/토큰은 절대 커밋하지 않는다. 토큰 캐시 파일도 마찬가지.
- **실전/모의 안전장치:** 주문(매수/매도) 로직은 환경(`prod`/`vps`)을 명시적 인자로 받고, 실전 주문은 의도적으로만 활성화되도록 설계. 테스트·개발 기본값은 모의투자.
- **하이브리드 경계:** Python과 TypeScript의 역할 분담이 정해지면 디렉토리/모듈 경계를 이 문서에 명시할 것.
- 한국투자증권 API는 호출 빈도 제한(rate limit)이 있으므로, 시세 폴링·주문 루프는 제한을 고려해 구현.
