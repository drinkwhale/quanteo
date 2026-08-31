# 관심종목 필터링 시스템 (Watchlist Filter)

재무 성장성 기반 다단계 필터링으로 관심종목을 선정합니다.

## 개요

코스피/코스닥 전체 종목에서 **3년간 자산·영업이익·매출 증가율**을 기준으로 순차 필터링하여 투자 가치가 높은 종목을 추출합니다.

```
2,000+ 종목
  ↓
[1단계] 자산 증가율 top 300
  ↓
[2단계] 영업이익 증가율 top 200
  ↓
[3단계] 매출 증가율 top 50
  ↓
[4단계] 시총 3천억 이상
  ↓
최종 관심종목 (보통 5~20개)
```

## 데이터 소스

- **시장 데이터:** pykrx (KRX 시세, 시총)
- **재무 데이터:** OpenDartReader (DART 공시, 자산·영업이익·매출)
- **시간 범위:** 최근 3년간 2개년 연간 비교 (연간 증가율 계산)

## 사용법

### 기본 실행

```bash
uv run python -m screener.scripts.build_watchlist --date 2026-08-28
```

**결과:**

- `screener/data/watchlist/watchlist_2026-08-28.csv` — CSV 형식
- `screener/data/watchlist/watchlist_2026-08-28.json` — JSON 형식

### 옵션

```bash
# 기준일 생략 시 어제 자동 설정
uv run python -m screener.scripts.build_watchlist

# 결과 저장 경로 지정
uv run python -m screener.scripts.build_watchlist \
  --date 2026-08-28 \
  --output-dir ./my_watchlists
```

### 출력 형식

**CSV:**

```
ticker,name,market_cap_billion,asset_growth_pct,oi_growth_pct,revenue_growth_pct
005930,SK하이닉스,50.0,15.5,12.3,8.7
247540,에코프로비엠,30.2,25.3,22.1,18.5
...
```

**JSON:**

```json
[
  {
    "ticker": "005930",
    "name": "SK하이닉스",
    "market_cap_billion": 50.0,
    "asset_growth_pct": 15.5,
    "oi_growth_pct": 12.3,
    "revenue_growth_pct": 8.7
  },
  ...
]
```

## 필터링 기준

### 1단계: 자산 증가율 top 300

최근 2개년 자산의 연간 증가율 기준 상위 300개 선정.

```python
자산 증가율 = (현재년도 자산 - 전년도 자산) / 전년도 자산 × 100
```

### 2단계: 영업이익 증가율 top 200

위 1단계 300개 중 영업이익 연간 증가율 기준 상위 200개 선정.

```python
영업이익 증가율 = (현재년도 영업이익 - 전년도 영업이익) / 전년도 영업이익 × 100
```

### 3단계: 매출 증가율 top 50

위 2단계 200개 중 매출 연간 증가율 기준 상위 50개 선정.

```python
매출 증가율 = (현재년도 매출 - 전년도 매출) / 전년도 매출 × 100
```

### 4단계: 시총 필터

위 3단계 50개 중 시가총액 3천억 이상만 최종 선정.

```python
시가총액 >= 300,000,000,000 (원)
```

## 코드 레벨 사용

### 기본 필터링

```python
import pandas as pd
from screener.data.collectors.pykrx_client import PykrxClient
from screener.data.collectors.dart_client import DartClient
from screener.pipeline.watchlist_filter import (
    calculate_yoy_growth,
    apply_watchlist_filters,
)

# 1. 시장 데이터 수집
pykrx = PykrxClient()
universe_df = pykrx.fetch_universe("2026-08-28")

# 2. 재무 데이터 수집
dart = DartClient()
financials_list = []
for ticker in universe_df["ticker"]:
    stmt = dart.fetch_financials(ticker, years=3)
    if len(stmt.years) >= 2:
        current, prior = stmt.years[-1], stmt.years[-2]
        financials_list.append({
            "ticker": ticker,
            "asset_current_year": current.total_equity,
            "asset_prior_year": prior.total_equity,
            "operating_income_current_year": current.operating_income,
            "operating_income_prior_year": prior.operating_income,
            "revenue_current_year": current.revenue,
            "revenue_prior_year": prior.revenue,
        })

financials_df = pd.DataFrame(financials_list).set_index("ticker")

# 3. 증가율 계산
financials_df["asset_growth"] = calculate_yoy_growth(
    financials_df.reset_index(), "asset"
).set_index(financials_df.index)
# ... 영업이익, 매출도 동일하게

# 4. 다단계 필터링 적용
candidates = apply_watchlist_filters(
    universe_df.set_index("ticker"),
    financials_df,
    top_n_asset=300,
    top_n_oi=200,
    top_n_revenue=50,
    min_market_cap=300e9,
)

for c in candidates:
    print(f"{c.ticker} {c.name}: 자산↑{c.asset_growth:.1f}%")
```

## 주의사항

### 데이터 결측 처리

- DART 공시 미제출 또는 수집 실패 시: 해당 종목은 스크리닝 제외
- 재무 데이터 부족(2개년 미만) 시: 증가율 계산 불가 → 제외

### 휴장일 처리

지정한 `date`가 휴장일인 경우:

1. pykrx가 빈 DataFrame 반환
2. 자동으로 직전 영업일 데이터 폴백 (로그에 경고 기록)

### 캐싱

- 시세/수급 데이터: 일별 parquet 캐시 (`screener/data/cache/`)
- 당일 캐시 존재 시 재호출 생략 → 속도 향상
- `.gitignore`에 `screener/data/cache/` 추가됨

## 성능

- 데이터 수집: ~~2~~3분 (DART API 의존)
- 필터링: ~1초
- 전체 실행: ~~3~~5분

## 테스트

```bash
# 단위 테스트
uv run pytest tests/screener/test_watchlist_filter.py -v

# 커버리지 확인
uv run pytest tests/screener/test_watchlist_filter.py --cov=screener.pipeline.watchlist_filter
```

## 확장

### 필터링 조건 커스터마이징

```python
candidates = apply_watchlist_filters(
    universe_df.set_index("ticker"),
    financials_df,
    top_n_asset=500,      # 자산 top 500
    top_n_oi=300,         # 영업이익 top 300
    top_n_revenue=100,    # 매출 top 100
    min_market_cap=200e9, # 시총 2천억 이상
)
```

### 추가 필터 레이어

현재 구현은 재무 성장성 중심입니다. 향후 다음을 추가할 수 있습니다:

- ROE / ROA 등 수익성 지표
- 부채비율 등 안정성 지표
- PER / PBR 등 상대가치
- 기관/외인 수급
- 기술적 모멘텀 (이동평균, RSI 등)

## 라이센스

quanteo 프로젝트 라이센스 준용
