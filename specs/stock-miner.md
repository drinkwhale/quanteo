# 일일 종목 추천 시스템 — 구현 스펙

> 이 문서는 Claude Code에게 그대로 전달해서 구현을 시작할 수 있도록 작성된 스펙입니다.
> 목표: 매일 장 마감 후 코스닥/코스피 유니버스를 스크리닝 → 스코어링 → 상위 종목을 텔레그램으로 발송.

---

## 1. 목표 (Goal)

장 마감 후(15:30 KST 이후) 자동으로 실행되어:
1. 전체 상장 종목을 정량 필터로 압축
2. 5축 스코어링으로 랭킹
3. 상위 N개 종목에 대해 LLM이 근거 요약(ProTip 스타일) 생성
4. 텔레그램으로 리포트 발송

기존 SK하이닉스 트레이딩 시스템의 **bounded autonomy 패턴**(에이전트는 제안만, 실행은 사람 승인)을 그대로 따른다. 이 시스템은 매매 자동 실행이 아니라 **발굴/알림**이 목적이므로 리스크가 낮지만, 워치리스트 등록 같은 상태 변경 액션은 사용자 승인을 거친다.

---

## 2. 아키텍처 개요

```
┌─────────────────┐     ┌──────────────┐     ┌──────────────┐     ┌────────────────┐
│  Screener Agent  │ --> │ Scorer Agent │ --> │ Analyst Agent │ --> │ Reporter Agent  │
│  (결정론적)        │     │  (결정론적)    │     │   (LLM)       │     │  (텔레그램 발송)  │
│  ~2000 → ~50     │     │  ~50 랭킹      │     │  Top 5~10 요약 │     │                 │
└─────────────────┘     └──────────────┘     └──────────────┘     └────────────────┘
```

- **Screener / Scorer는 LLM을 쓰지 않는다.** 순수 데이터 파이프라인(pandas)으로 구현해 재현성과 속도를 확보한다.
- **Analyst Agent만 Claude API를 호출**한다. 이미 스코어링으로 걸러진 상위 종목에 대해서만 호출하므로 비용이 통제된다.
- 전체 파이프라인은 **APScheduler 또는 cron**으로 매 거래일 15:40 KST에 트리거.

---

## 3. 모듈 구조 (제안 디렉토리)

```
stock-screener/
├── config/
│   ├── settings.yaml          # 임계값, 가중치, 유니버스 필터 조건
│   └── secrets.env            # KIS API key, DART API key, Telegram bot token
├── data/
│   ├── collectors/
│   │   ├── pykrx_client.py    # 시세, 시총, 수급, PER/PBR
│   │   ├── dart_client.py     # 재무제표, 공시
│   │   └── kis_client.py      # 기존 KIS 연동 재사용
│   └── cache/                 # 일별 원천 데이터 parquet 캐시
├── pipeline/
│   ├── screener.py            # 1차 필터 (결정론적)
│   ├── scorer.py               # 5축 스코어링 (결정론적)
│   └── ranker.py                # 섹터 percentile 랭킹
├── agents/
│   └── analyst_agent.py       # Claude API 호출, ProTip 요약 생성
├── notify/
│   └── telegram_reporter.py   # 메시지 포맷팅 + 발송
├── scheduler/
│   └── daily_job.py            # 전체 파이프라인 오케스트레이션 + cron 진입점
└── main.py
```

---

## 4. 데이터 수집 (Screener Agent)

### 4.1 유니버스
- 코스피 + 코스닥 전 종목에서 시작
- 1차 제외: 관리종목, 거래정지, 시가총액 500억 미만, 최근 20일 평균 거래대금 5억 미만 (유동성 필터)

### 4.2 수집 항목 (pykrx)
| 항목 | 소스 함수(예시) | 용도 |
|---|---|---|
| 종가/거래량/등락률 | `get_market_ohlcv` | 기술적 지표 |
| 시가총액 | `get_market_cap` | 유니버스 필터 |
| PER/PBR/배당수익률 | `get_market_fundamental` | 밸류에이션 |
| 투자자별 순매수 | `get_market_trading_value_by_investor` | 수급 |
| 공매도 잔고 | `get_shorting_balance_by_date` | 수급 보조 |

### 4.3 수집 항목 (DART OpenAPI)
- 최근 3개년 재무제표 (매출, 영업이익, 순이익, 부채, 유동자산/부채, 영업활동현금흐름)
- 최근 공시 목록 (자사주 취득/처분, 유상증자, 주요계약, 실적 정정)

### 4.4 캐싱 전략
- 재무제표는 분기 1회만 갱신되므로 로컬 parquet 캐시 + 갱신일 체크
- 시세/수급은 매일 갱신

---

## 5. 스코어링 (Scorer Agent)

5축 각각 1~5점(섹터 내 percentile 기반)으로 산출 후 가중합.

| 축 | 세부 지표 | 계산 방식 |
|---|---|---|
| 성장성 | 매출 YoY, 영업이익 YoY, EPS YoY | 최근 분기 vs 전년동기, 섹터 percentile |
| 수익성 | ROE, 영업이익률, 영업이익률 추세(3분기) | 절대값 + 추세 기울기 |
| 현금흐름 | 영업활동현금흐름/순이익 비율, FCF 전환율 | FCF = 영업CF - CapEx |
| 재무안정성 | 부채비율, 유동비율, 이자보상배율 | Altman Z-Score 보조 지표로 병기 |
| 상대가치 | PER/PBR/PSR/EV-EBITDA의 섹터 대비 + 자체 5년 밴드 위치 | 낮을수록 고득점 (역방향 정규화) |

가중치는 `config/settings.yaml`에서 조정 가능하게 설계 (기본값: 균등 20%씩, 추후 백테스트로 조정).

**수급/기술적/모멘텀 지표는 별도 필터 레이어**로 취급 (스코어에 합산하지 않고, 동점자 우선순위 및 리포트 부가 정보로 사용):
- 외인+기관 동반 순매수 연속일수
- CCI, 52주 위치, 거래량 급증(20일 평균 대비 배수)
- 최근 실적 서프라이즈 여부, DART 주요 공시 발생 여부

> 설계 이유: 밸류에이션/재무 스코어는 "무엇을 살지"를 결정하고, 수급/기술은 "언제"에 가까운 정보라 성격이 다름. 섞으면 스코어 해석이 흐려짐.

### 출력
`ranker.py`가 5축 가중합 스코어 기준 상위 30~50개 종목 + 원본 지표값을 DataFrame으로 반환.

---

## 6. LLM 요약 (Analyst Agent)

- 입력: Scorer 출력 상위 N개(기본 10개)의 정량 데이터 + 최근 공시 텍스트
- Claude API에 구조화된 프롬프트로 전달, **출력은 JSON 강제**(파싱 안정성)
- 종목별 출력 스키마 예시:

```json
{
  "ticker": "005930",
  "name": "삼성전자",
  "one_line_thesis": "메모리 업턴 초입 + 재무 건전성 최상위",
  "protips": [
    "3분기 연속 영업이익률 개선",
    "부채비율 업종 평균 대비 현저히 낮음"
  ],
  "risk_flags": ["최근 유상증자 공시 있음"],
  "score_breakdown": {"growth": 4, "profitability": 5, "cashflow": 4, "stability": 5, "valuation": 3}
}
```

- **LLM은 사실 요약만** 하고 매수/매도 판단 문구는 생성하지 않도록 프롬프트에서 명시 (법적/신뢰성 리스크 관리)

---

## 7. 텔레그램 리포트 (Reporter Agent)

### 7.1 발송 트리거
- 매 거래일 15:40 KST, `daily_job.py`가 스케줄러로 실행
- 실패 시(API 장애 등) 재시도 3회 후 에러 알림 별도 발송

### 7.2 메시지 포맷 (예시)
```
📊 오늘의 발굴 종목 (2026-07-21)

1️⃣ 삼성전자 (005930) — 종합 4.2/5
   💡 메모리 업턴 초입 + 재무 건전성 최상위
   ✅ 3분기 연속 영업이익률 개선
   ✅ 부채비율 업종 평균 대비 현저히 낮음
   ⚠️ 최근 유상증자 공시 있음
   📈 외인 5일 연속 순매수 | PER 12.3(업종 대비 -20%)

[워치리스트 등록] [상세보기] [무시]
```

### 7.3 인터랙션 (bounded autonomy)
- 인라인 버튼으로 "워치리스트 등록" 선택 시에만 상태 변경 (DB/시트 기록)
- 자동 매매 연동 없음 — 정보 제공 + 사람 승인 하에 워치리스트 등록까지만

---

## 8. 구현 순서 (권장)

1. **Phase 1**: `pykrx_client.py` + `screener.py` — 유니버스 필터링까지 (LLM 없이 로컬 실행/검증)
2. **Phase 2**: `dart_client.py` + `scorer.py` — 5축 스코어 계산, CSV로 결과 출력해 수동 검증
3. **Phase 3**: `telegram_reporter.py` — 스코어 결과를 텔레그램으로 발송 (정량 데이터만, LLM 요약 없이)
4. **Phase 4**: `analyst_agent.py` 붙여서 LLM 요약 추가
5. **Phase 5**: `scheduler/daily_job.py`로 전체 자동화 + 크론 등록
6. **Phase 6**: 워치리스트 등록 인터랙션 (인라인 버튼 콜백 핸들링)

---

## 9. 설정 파일 예시 (`config/settings.yaml`)

```yaml
universe:
  min_market_cap: 50_000_000_000   # 500억
  min_avg_trading_value_20d: 500_000_000  # 5억
  exclude_administrative: true

scoring_weights:
  growth: 0.2
  profitability: 0.2
  cashflow: 0.2
  stability: 0.2
  valuation: 0.2

report:
  top_n: 10
  send_time_kst: "15:40"
  telegram_chat_id: "${TELEGRAM_CHAT_ID}"

llm:
  model: "claude-sonnet-4-6"
  max_tokens_per_stock: 400
```

---

## 10. 참고 — 기존 시스템과의 연계

- KIS API 클라이언트, Telegram Bot 연동 로직은 기존 SK하이닉스 트레이딩 시스템 코드 재사용 가능
- 수급(외인+기관 동반 순매수) 로직도 기존 구현 재사용
- 멀티 에이전트 오케스트레이션 프레임워크(LangGraph 등 조사했던 것)는 이 시스템에도 동일 적용 가능하나, Phase 1~3은 프레임워크 없이 순수 스크립트로 먼저 검증 후 도입 권장 (조기 추상화 방지)