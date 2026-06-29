# 자동매매 시스템 — 정보 수집 & 알람 종합 기획서

> 작성 기준: 2026년 6월 기준 대화 내용 종합  
> 대상 종목: SK하이닉스(000660) 중심 / AI·반도체 섹터  
> 기술 스택: Python + KIS API + Telegram Bot + Google Calendar API

---

## 1. 시스템 전체 구조

```
[정보 수집층]
  ├── 국내 뉴스 (RSS / 네이버금융 / DART)
  ├── 해외 뉴스 (Finnhub / Yahoo RSS / TradingNews)
  ├── 경제지표 캘린더 (Investing.com / BLS / Fed 공식)
  ├── 실적발표 일정 (TipRanks / Investing.com)
  └── 환율 정보 (한국은행 API / ExchangeRate API)
        ↓
[처리층]
  ├── Claude Haiku — AI 중요도 필터 (HIGH / MEDIUM / LOW)
  ├── 키워드 필터 — 반도체 / HBM / FOMC / 환율 급변 등
  └── 중복 제거 / 한국시간 변환
        ↓
[출력층]
  ├── Telegram Bot — 즉시 알람 (HIGH 이벤트)
  └── Google Calendar — 예정 일정 자동 저장
```

---

## 2. 수집할 정보 목록

### 2-1. 국내 뉴스 (RSS — 무료)

| 소스 | RSS URL | 수집 내용 |
|------|---------|----------|
| 한국경제 | `https://www.hankyung.com/feed/economy` | 거시경제 속보 |
| 매일경제 | `https://www.mk.co.kr/rss/30000001/` | 반도체·기업 |
| 이데일리 | `https://www.edaily.co.kr/rss/edaily_news.xml` | 금리·환율·수급 |
| 네이버금융 | BeautifulSoup 스크래핑 | 종목별 공시·이슈 |
| DART (금감원) | `OpenDartReader` 라이브러리 | 유상증자·공시 |

### 2-2. 해외 뉴스 (API)

| 소스 | 방법 | 수집 내용 | 비용 |
|------|------|----------|------|
| Finnhub | REST API | 글로벌 기업 뉴스 | 무료 (60req/min) |
| Yahoo Finance | RSS feedparser | 글로벌 시황 | 무료 |
| TradingNews API | REST API | 브레이킹 뉴스 + 감성점수 | $20/월~ |

### 2-3. 매크로 경제지표 캘린더

#### 🇺🇸 미국 지표 (SK하이닉스 영향 大)

| 지표 | 발표 기관 | 한국시간 | 중요도 | 비고 |
|------|----------|---------|--------|------|
| **FOMC 금리결정** | 연준 (Fed) | 새벽 3:00 (서머타임) / 4:00 (겨울) | 🔴 최고 | 연 8회 |
| **CPI (소비자물가)** | BLS | 밤 9:30 (서머타임) / 10:30 (겨울) | 🔴 최고 | 매월 2번째 화요일경 |
| **NFP (비농업고용)** | BLS | 밤 9:30 | 🔴 최고 | 매월 첫 금요일 |
| PCE (개인소비지출) | BEA | 밤 9:30 | 🟡 높음 | 연준 선호 물가지표 |
| PPI (생산자물가) | BLS | 밤 9:30 | 🟡 높음 | CPI 선행지표 |
| GDP | BEA | 밤 9:30 | 🟡 높음 | 분기별 |
| 소매판매 | Census | 밤 9:30 | 🟡 중간 | 소비 선행지표 |
| ISM 제조업 PMI | ISM | 밤 11:00 | 🟡 중간 | 반도체 수요 선행 |

> **서머타임 기준**: 3월 둘째 일요일 ~ 11월 첫째 일요일 (EDT)  
> **겨울 기준**: 위 기간 이외 (EST, 1시간 늦음)

#### 🇰🇷 한국 지표

| 지표 | 발표 기관 | 중요도 | 비고 |
|------|----------|--------|------|
| 기준금리 결정 | 한국은행 | 🔴 높음 | 연 8회 |
| 수출입 동향 | 관세청 | 🔴 높음 | 반도체 수출 직결 |
| 소비자물가 | 통계청 | 🟡 중간 | 매월 초 |
| 경상수지 | 한국은행 | 🟡 중간 | |

#### 🇨🇳 중국 지표 (반도체 수요 선행)

| 지표 | 중요도 | 비고 |
|------|--------|------|
| 제조업 PMI | 🔴 높음 | 반도체 수요 선행지표 |
| 비제조업 PMI | 🟡 중간 | |
| GDP 성장률 | 🟡 중간 | 분기별 |

### 2-4. AI·반도체 실적발표 일정 (2026 하반기 확정)

| 날짜 (한국시간) | 티커 | 기업명 | 발표시간 | SK하이닉스 영향 | 핵심 포인트 |
|----------------|------|--------|---------|----------------|------------|
| **7월 15일** | ASML | ASML Holding | 장전 | 🟡 중간 | EUV 수주잔고 / Q2 €8.4~9.0B 가이던스 |
| **7월 16일** | TSM | TSMC | 장중 | 🔴 최고 | HBM 수요 / AI·HPC 2026 달러매출 +30% 가이던스 |
| **8월 4일** | AMD | AMD | 장후 | 🔴 높음 | MI400 GPU / Q2 $11.2B 가이던스 (+46% YoY) |
| **8월 26일** | NVDA | NVIDIA | 장후 | 🔴 최고 | Blackwell 수요 / HBM 최대 고객 / SK하이닉스 직결 |
| **9월 3일** | AVGO | Broadcom | 장후 | 🟡 중간 | AI ASIC / Q3 AI반도체 $16B (+200%+ YoY) |
| **9월 22일** | MU | Micron Technology | 장후 | 🔴 최고 | HBM/DRAM 직접 경쟁·동반 / 메모리 업황 바로미터 |

> **장후(AMC) → 한국시간**: 미국 동부시간 기준 오후 4~5시 발표 = 한국 다음날 새벽 5~6시 (서머타임) / 6~7시 (겨울)

#### 추가 관심 종목 (분기별 추적)

| 티커 | 기업 | 관련성 |
|------|------|--------|
| AMAT | Applied Materials | 반도체 장비 — DRAM 투자 선행 |
| LRCX | Lam Research | 반도체 장비 — 식각/증착 |
| KLAC | KLA Corporation | 반도체 장비 — 검사 |
| QCOM | Qualcomm | 모바일 수요 |
| MRVL | Marvell Technology | AI 커스텀칩 / 데이터센터 |
| INTC | Intel | DRAM 서버 수요 |
| META | Meta | AI 인프라 투자 (HBM 수요) |
| MSFT | Microsoft | AI 클라우드 (HBM 수요) |
| GOOGL | Alphabet | AI 인프라 (HBM 수요) |
| AMZN | Amazon | AI 클라우드 (HBM 수요) |

### 2-5. 환율 정보

#### 핵심 환율 — 모니터링 대상

| 환율 | 코드 | SK하이닉스 영향 | 알람 조건 |
|------|------|----------------|----------|
| **USD/KRW** | USDKRW | 🔴 직결 — 수출 매출 환산 | ±1% 이상 일중 변동 |
| **DXY (달러인덱스)** | DXY | 🔴 달러 강약 종합 | ±0.5% 이상 |
| **JPY/KRW** | JPYKRW | 🟡 경쟁사(일본) 가격경쟁력 | ±1.5% 이상 |
| **CNY/KRW** | CNYKRW | 🟡 중국 수요 / 경쟁사 | ±1% 이상 |
| **EUR/USD** | EURUSD | 🟡 글로벌 리스크 지표 | ±0.7% 이상 |

#### 환율 수집 API

| API | 무료 여부 | 업데이트 주기 | 비고 |
|-----|---------|------------|------|
| **한국은행 ECOS API** | 완전 무료 | 일 1회 (공식 고시) | [ecos.bok.or.kr](https://ecos.bok.or.kr) |
| **ExchangeRate-API** | 무료 (1,500req/월) | 일 1회 | 간편 REST |
| **Twelve Data API** | 무료 (800req/일) | 실시간 | Forex 포함 |
| **Yahoo Finance yfinance** | 완전 무료 | 실시간 | `yfinance` 라이브러리 |
| **Alpha Vantage** | 무료 (25req/일) | 실시간 | FX Intraday 지원 |

#### 환율 알람 로직

```
[매 30분 체크]
  USD/KRW 변동폭 계산 (현재가 vs 장초 기준가)
    ├── ±1.0% 이상 → 🔴 Telegram 즉시 알람
    ├── ±0.5~1.0%  → 🟡 Telegram 일반 알람
    └── ±0.5% 미만 → 무시

[일일 정리] (오후 4시, 장마감 후)
  → 당일 환율 변동 요약 Telegram 발송
  → USD/KRW, DXY, JPY/KRW 종합 리포트
```

#### 환율-주가 상관 해석 룰

| 상황 | 해석 | 대응 |
|------|------|------|
| USD/KRW 상승 (원화 약세) | SK하이닉스 달러 매출 → 원화 환산 이익 증가 | 긍정적 |
| USD/KRW 하락 (원화 강세) | 수출 이익 감소 | 부정적 |
| DXY 급등 + 원화 약세 | 글로벌 리스크오프 → 외국인 매도 가능성 | 주의 |
| 엔화 급약세 (JPY 약세) | 일본 메모리 경쟁사 가격경쟁력 저하 → 긍정 | 긍정적 |

---

## 3. Google Calendar 저장 정책

### 캘린더 색상 코딩

| 색상 | color_id | 용도 |
|------|----------|------|
| 🔴 빨강 (Tomato) | 11 | CRITICAL — NVDA/MU/TSM 실적, FOMC, CPI |
| 🟠 탠저린 (Tangerine) | 6 | HIGH — ASML/AMD/AVGO 실적, NFP, 한국은행 금리 |
| 🟡 바나나 (Banana) | 5 | MEDIUM — PCE, PPI, GDP, 중국 PMI |
| 🔵 피콕 (Peacock) | 7 | 환율 이벤트 — USD/KRW 급변 기록 |
| 💚 세이지 (Sage) | 2 | 한국 지표 — 수출입, 소비자물가 |

### 알람 설정 기준

| 이벤트 유형 | 사전 알람 |
|------------|----------|
| FOMC / NVDA / MU 실적 | 2시간 전 + 30분 전 (2중 알람) |
| CPI / NFP / TSM 실적 | 1시간 전 |
| 기타 실적발표 / 한국 지표 | 30분 전 |
| 환율 기록 이벤트 | 알람 없음 (기록용) |

---

## 4. Telegram 알람 포맷

### 뉴스 알람

```
🚨 [HIGH] 매크로 뉴스 알람

📰 {뉴스 제목}
🔗 {링크}

📋 분석: {Claude Haiku 한줄 요약}
🟢/🔴/🟡 대응: 매수검토 / 매도검토 / 관망

⏰ {HH:MM:SS KST}
```

### 실적발표 사전 알람 (1시간 전)

```
⏰ 실적발표 1시간 전 알람

🏢 {기업명} ({티커})
📅 {발표일시} ({장전/장후})
⚠️ 중요도: CRITICAL / HIGH

💡 SK하이닉스 연관:
{연관성 한줄 설명}

📊 컨센서스:
  EPS 예상: {값}
  매출 예상: {값}
```

### 환율 급변 알람

```
💱 환율 급변 알람

USD/KRW: {현재가} ({변동률}%)
DXY: {현재가} ({변동률}%)

📋 분석: {원화 강세/약세} — SK하이닉스 {긍정/부정}적
⏰ {HH:MM:SS KST}
```

### 일일 환율 마감 리포트 (오후 4시)

```
📊 환율 일일 마감 리포트

💵 USD/KRW: {종가} ({일중변동률}%)
📈 DXY:     {종가} ({일중변동률}%)
🇯🇵 JPY/KRW: {종가} ({일중변동률}%)
🇨🇳 CNY/KRW: {종가} ({일중변동률}%)

{전체 평가: 원화 강세/약세 — SK하이닉스 영향 한줄}
⏰ 기준: {YYYY-MM-DD} 종가
```

---

## 5. AI 중요도 필터 (Claude Haiku)

### 시스템 프롬프트

```
너는 한국 주식시장 전문 트레이더야.
다음 뉴스가 SK하이닉스(000660) 단기 주가에 
중요한 영향을 줄지 판단해줘.

중요도 기준:
- HIGH: FOMC 결정, 미중 반도체 규제, NVDA/MU/TSM 실적,
        SK하이닉스 직접 공시, 금리 서프라이즈, 환율 급변(±1%↑)
- MEDIUM: 메모리 업황, 반도체 수출입 통계, AMD/AVGO 실적,
          환율 중간 변동(±0.5~1%), 중국 PMI
- LOW: 일반 경제지표, 무관한 기업뉴스

JSON으로만 응답:
{"score": "HIGH/MEDIUM/LOW", "reason": "이유 한줄", "action": "매수검토/매도검토/관망"}
```

### 필터링 키워드 (사전 필터 — API 호출 절약)

```python
CRITICAL_KEYWORDS = [
    # 반도체 직접
    "HBM", "DRAM", "메모리", "반도체", "SK하이닉스", "하이닉스",
    "NVDA", "엔비디아", "Micron", "마이크론", "TSMC", "삼성전자",
    # 매크로
    "FOMC", "금리", "CPI", "소비자물가", "NFP", "고용",
    # 환율
    "원달러", "USD/KRW", "환율", "달러", "DXY",
    # 규제
    "반도체 수출규제", "대중 규제", "미중", "관세",
    # AI 수요
    "AI", "데이터센터", "HPC", "Blackwell", "GB200",
]
```

---

## 6. 기술 스택 & 패키지

```bash
# 뉴스 수집
pip install feedparser          # RSS 파싱
pip install beautifulsoup4      # 네이버금융 스크래핑
pip install OpenDartReader      # DART 공시
pip install requests            # HTTP 요청

# 환율
pip install yfinance            # Yahoo Finance (환율 실시간)
pip install pandas              # 데이터 처리

# AI 필터
pip install anthropic           # Claude Haiku

# 캘린더
pip install gcsa                # Google Calendar Simple API
pip install google-auth-oauthlib
pip install icalendar           # ICS 파일 생성 (아이폰 지원)
pip install pytz                # 한국시간 변환

# 스케줄러
pip install schedule            # 단순 스케줄링
# 또는
pip install apscheduler         # 고급 스케줄링 (cron 지원)

# Telegram
pip install python-telegram-bot
```

---

## 7. 실행 스케줄

| 시간 (KST) | 실행 내용 |
|------------|----------|
| 08:00 | 장전 뉴스 수집 / 당일 경제지표 일정 Telegram 발송 |
| 09:00~15:30 | **5분마다** 국내 뉴스 RSS 폴링 + HIGH 필터 알람 |
| 09:00~15:30 | **30분마다** USD/KRW 환율 체크 + 급변 알람 |
| 15:30 (장마감) | 실적발표 사전 확인 (당일 미국 장후 발표 예정 종목) |
| 16:00 | 일일 환율 마감 리포트 Telegram 발송 |
| 22:00~익일 06:00 | **10분마다** 미국 뉴스 RSS / Finnhub 폴링 |
| 22:30 (미장개장) | FOMC/CPI 등 미국 경제지표 발표 시간대 집중 모니터링 |
| 매월 1일 00:00 | 다음 달 경제지표 일정 + 실적발표일 Google Calendar 자동 저장 |

---

## 8. 정보 소스 우선순위 요약

```
🔴 CRITICAL (즉시 알람 필수)
  → FOMC 금리결정 / CPI 서프라이즈 / NVDA·MU·TSM 실적
  → SK하이닉스 직접 공시 (DART)
  → 미중 반도체 수출규제 뉴스
  → USD/KRW ±1% 이상 급변

🟠 HIGH (알람 권장)
  → NFP 비농업고용 / PCE / 한국은행 금리결정
  → AMD·AVGO·ASML 실적
  → 반도체 수출입 통계 (관세청)
  → 중국 제조업 PMI (반도체 수요 선행)

🟡 MEDIUM (일간 리포트 포함)
  → PPI / GDP / 소매판매
  → AMAT·LRCX·KLAC·MRVL 실적
  → USD/KRW ±0.5~1% 변동
  → 엔화·위안화 추세 변화

⬜ LOW (무시 또는 로그만)
  → 일반 경제지표 (관련성 낮음)
  → ±0.5% 미만 환율 변동
```

---

## 9. 구현 단계별 로드맵

| 단계 | 작업 | 예상 소요 |
|------|------|----------|
| **1단계** | RSS 뉴스 수집 + Telegram 그대로 전송 (필터 없음) | 1일 |
| **2단계** | 키워드 필터 추가 (CRITICAL_KEYWORDS 기반) | 0.5일 |
| **3단계** | Claude Haiku AI 중요도 분류 연동 | 1일 |
| **4단계** | USD/KRW 환율 수집 + 급변 알람 | 0.5일 |
| **5단계** | Google Calendar API 연동 + 실적발표일 자동 저장 | 1일 |
| **6단계** | 일일 환율 마감 리포트 + 경제지표 캘린더 자동화 | 1일 |
| **7단계** | CCI 매매 시그널 + HIGH 뉴스 동시 발생 시 우선매수 연계 | 2일 |

---

## 10. 파일 구조 (구현 시 참고)

```
auto_trading/
├── main.py                  # 메인 실행 파일
├── config.py                # API 키, 설정값
├── news/
│   ├── rss_collector.py     # RSS 뉴스 수집
│   ├── dart_collector.py    # DART 공시 수집
│   └── finnhub_collector.py # 해외 뉴스 수집
├── calendar/
│   ├── google_cal.py        # Google Calendar API
│   ├── earnings_data.py     # 실적발표일 데이터
│   └── macro_events.py      # 경제지표 일정 데이터
├── fx/
│   ├── rate_monitor.py      # 환율 수집 및 급변 감지
│   └── daily_report.py      # 일일 환율 리포트
├── ai_filter/
│   └── claude_filter.py     # Claude Haiku 중요도 분류
├── telegram/
│   └── bot.py               # Telegram 알람 발송
└── scheduler.py             # APScheduler 스케줄 관리
```

---

*마지막 업데이트: 2026-06-29 | SK하이닉스(000660) 자동매매 시스템 기획*