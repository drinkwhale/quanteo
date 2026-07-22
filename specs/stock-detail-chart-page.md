# 종목 상세 차트 페이지 — 설계

이 문서는 "종목을 선택하면 현재가 차트를 볼 수 있는 화면"의 구현 가능성 조사와 아키텍처
설계다. [`specs/investor-flow-chart.md`](investor-flow-chart.md)(외국인/기관 수급 데이터
조사)의 §6을 대체·구체화하며, `specs/tasks.md` Phase 16의 프론트엔드 태스크(T104~)가 이
문서를 설계 근거로 참조한다.

---

## 0. 결론 요약

- **가격 차트 자체는 리스크가 낮다.** Toss Open API에 캔들(OHLCV) 엔드포인트
  (`GET /api/v1/candles`)가 이미 있고, `core/adapters/toss/rest.py:925`의
  `TossRestClient.get_candles()`로 이미 구현·연동까지 돼 있다(백테스트 등에서 사용 중).
  Control API에 얇은 프록시 라우트 하나만 추가하면 된다 — **신규 브로커 연동이나 데이터
  가공 로직이 필요 없다.**
- **심볼 코드 포맷도 확인됐다.** Toss `/api/v1/candles`·`/api/v1/stocks` 응답 예시가 국내
  종목에 `005930`(6자리) 코드를 쓴다 — `investor-flow-chart.md` §7에서 열린 질문으로
  남겼던 "Toss ↔ KIS 심볼 포맷 정합성"이 **해소됨**: 둘 다 동일한 6자리 코드를 쓴다.
- **부담은 프론트엔드 쪽에 있다.** 차트 라이브러리가 전혀 없고(§3), 대시보드에 라우터도
  없어(§2) 이번에 "화면을 하나 더 만드는" 문제와 "차트를 어떻게 그릴지"를 함께 풀어야 한다.
- **종목 자유 검색은 불가능하다.** Toss `/api/v1/stocks`는 정확한 심볼 목록만 받는다(이름
  기반 fuzzy search 아님) — §4에서 대안 UX 제시.

---

## 1. 데이터 소스 확정 (Toss `/api/v1/candles`)

```
GET /api/v1/candles?symbol=005930&interval=1d&count=100&before=...&adjusted=true
```

| 파라미터 | 값 | 비고 |
|---|---|---|
| `interval` | `1m` \| `1d` | Toss가 지원하는 두 봉 단위. 5분봉·주봉 등은 없음 |
| `count` | 최대 200 | 넘으면 `before`로 페이지네이션 |
| `before` | ISO 8601 | 이전 응답의 `nextBefore`를 그대로 전달 |
| `adjusted` | bool(기본 true) | 수정주가 적용 여부 |

- Rate Limits Group: **`MARKET_DATA_CHART`** — 기존 `MARKET_DATA`/`ORDER` 버킷과 별도로
  이미 분리돼 있음(스펙 명시). `core/adapters/throttler.py`에 이 그룹 전용 버킷을 하나
  추가하면 된다(신규 개념 아님, 기존 패턴 그대로 확장).
- `TossCandle` 모델이 이미 파싱까지 처리(`get_candles`가 `list[TossCandle]` 반환).
- **1m봉은 분 단위 실시간에 가깝지만, 외국인/기관 수급(Phase 16 KIS 데이터)은 일 단위다.**
  즉 1분봉 선택 시 하단 수급 패널은 "당일 데이터 없음/최근 일자 값만 참고 표시"로 처리해야
  한다 — 이 페이지 설계와 investor-flow-chart.md §1의 스코프 제약이 여기서 직접 만난다.

---

## 2. 네비게이션 방식 — 신규 라우터 도입 vs 기존 탭 패턴 재사용

현재 `dashboard/src/App.tsx`는 **라우터가 없는 단일 뷰**다. `StrategyPage`도 별도 경로가
아니라 App.tsx 안에 조건 없이 렌더링되는 섹션일 뿐이다(`package.json`에 react-router류
의존성 없음).

두 가지 선택지가 있다.

**옵션 A — react-router 도입, `/stocks/:symbol` 정식 라우트**
- 장점: URL로 특정 종목 차트를 딥링크·새로고침 가능. `PRODUCT.md`의 "향후: 멀티유저 SaaS
  전환" 방향과 장기적으로는 맞음.
- 단점: 신규 의존성, 레이아웃(StatusBar 등 공통 셸) 분리 리팩터링 필요. `PRODUCT.md`
  Design Principle 1·3("실행 중심", "화면 전환보다 현재 상태 파악이 우선")과는 다소
  긴장 관계 — 지금은 "운용 중 상태를 놓치지 않는 것"이 우선순위.

**옵션 B — `DESIGN.md` §5에 이미 정의돼 있는 "Tab Navigation" 컴포넌트를 실제로 도입**
(`DESIGN.md`:206-209, 지금까지 스펙만 있고 구현된 곳은 없음)
- App.tsx 최상단에 탭 2개: **"운용현황"**(현재 화면 전부) / **"종목상세"**(신규). 탭 전환은
  로컬 상태(`useState`)만으로 처리, 새 의존성 없음.
- Emerald Signal 하단 보더로 active 탭 표시 — 디자인 시스템에 이미 정의된 스타일 그대로
  쓰면 됨(`border-accent text-white` / `border-transparent text-muted`).
- `PRODUCT.md`의 "화면 전환보다 현재 상태 파악이 우선" 원칙과 자연스럽게 맞음: 운용현황
  탭을 벗어나도 상태바(StatusBar)는 공통으로 유지되므로 봇 상태 인지가 끊기지 않음.

**권장: 옵션 B.** 이유는 (1) 디자인 시스템에 이미 설계돼 있는 컴포넌트를 그대로 쓰는 것
(2) 신규 의존성 없음 (3) 현재 제품 원칙과의 정합성. 딥링크가 실제로 필요해지는 시점
(멀티유저 SaaS 전환)이 오면 그때 react-router로 이관해도 이번 작업이 낭비되지 않는다
(컴포넌트 자체는 라우팅 방식과 독립적으로 재사용 가능하게 설계 — §5).

---

## 3. 차트 라이브러리 — `lightweight-charts`

- **선택 근거**: TradingView가 만든 오픈소스(Apache-2.0) 캔들스틱 차트 라이브러리.
  캔들+거래량+보조지표를 **여러 pane으로 나눠 같은 시간축에 동기화**하는 것이 정확히 이번
  요구사항(가격 차트 + 하단 수급 지표)과 일치. 번들 크기가 작고(~45KB gzip 내외) React
  의존성이 없어 프레임워크 록인이 없다.
- **통합 패턴**: vanilla JS 라이브러리이므로 React에서는 `useRef` + `useEffect`로
  래핑한다 — `createChart(containerRef.current, options)` → 언마운트 시 `chart.remove()`.
  기존 코드베이스에 이미 이 패턴과 유사한 `useEffect` cleanup 관례가 있음(`useStream.ts`,
  `BacktestPanel`의 abort controller 등) — 새로운 패턴이 아니라 기존 관례의 연장.
- **DESIGN.md 색상 토큰 매핑**:
  | 차트 요소 | 색상 |
  |---|---|
  | 상승 캔들 | Live Green `#22c55e` |
  | 하락 캔들 | Alert Red `#ef4444` |
  | 배경 | 투명 (Panel의 Carbon Panel `#10141a` 그대로 비침) |
  | 그리드선 | Graphite Line `#1f2630` |
  | 크로스헤어/포커스 | Emerald Signal `#10b981` |
  | 거래량 바 | Ghost Gray `#6b7280` (저채도, 가격 캔들과 시각적 위계 구분) |
- **접근성 예외 — DESIGN.md "No-Ambiguity Rule"과의 긴장**: 캔들 상승/하락은 업계 표준
  관행상 색상만으로 구분한다(수백 개 캔들에 개별 레이블을 달 수 없음). 이는 기존
  positive/negative 텍스트 규칙의 의도된 예외로 다뤄야 한다. 완화책: 캔들 호버 시
  OHLC 수치를 텍스트 툴팁으로 노출(라이브러리 기본 기능인 crosshair + legend) —
  색상 없이도 정확한 값 확인 가능하게 한다. **이 예외는 `DESIGN.md`에 명시적으로
  기록해야 함**(§6 참고 — 이번 조사에서 함께 추가).

### 대안 검토 (기각)
- `recharts`/`visx`: 범용 차트 라이브러리라 캔들스틱 + 다중 pane 동기화를 직접 구현해야
  함 — 구현 비용이 훨씬 큼.
- `apexcharts`: 캔들스틱 지원은 하나 pane 동기화·성능이 lightweight-charts보다 약함
  (주식 차트 전용 설계가 아님).
- `d3` 직접 구현: 가장 유연하지만 확대/축소·크로스헤어·다중 pane 동기화를 전부 손으로
  만들어야 해 이번 스코프에는 과함.

---

## 4. 종목 선택 UX — 자유 검색 불가, 대안 설계

Toss `/api/v1/stocks?symbols=...`는 **정확한 심볼을 콤마로 나열**해야 하는 API다(이름으로
검색하는 fuzzy search가 아님). 종목명으로 검색하는 자유 검색 기능을 만들려면 별도의
"종목 마스터 리스트"(전 종목 코드+이름 DB)가 필요한데, 이런 목록을 제공하는 Toss 엔드포인트는
확인되지 않았다 — **이번 스코프에서는 자유 검색을 제외**하고 아래 두 경로로 MVP를 구성한다.

1. **최근/보유 종목 퀵픽** — 이미 포지션·주문·체결에 등장한 심볼은 `useStockNames`로 이름이
   캐시돼 있음(App.tsx:40-48). 이 목록을 그대로 "최근 종목" chip 리스트로 재사용.
2. **종목코드 직접 입력** — `Strategy.tsx`의 `BacktestPanel`(`pages/Strategy.tsx:299-317`)에
   이미 동일한 패턴(`<input type="text" value={symbol} ... placeholder="005930" />`)이
   있음 — 그대로 재사용.

자유 검색이 실제로 필요해지면 별도 작업으로 "종목 마스터 캐시"(KRX 상장종목 목록을 별도
배치로 가져와 SQLite에 저장) 구축이 선행돼야 한다 — 이번 Phase 16 스코프에는 포함하지 않음.

---

## 5. 컴포넌트 설계

```
dashboard/src/
  App.tsx                              # 최상단 Tab Navigation 추가 ("운용현황" | "종목상세")
  pages/
    StockDetail.tsx                    # 신규 — 종목상세 탭 컨텐츠
  components/
    TabNav.tsx                         # 신규 — DESIGN.md §5 Tab Navigation 컴포넌트 구현
    chart/
      PriceChart.tsx                   # 캔들+거래량 (lightweight-charts), symbol/interval prop
      InvestorFlowPanel.tsx            # 하단 수급 패널, PriceChart와 시간축 동기화
      IntervalToggle.tsx               # 1분봉/일봉 전환 (Toss interval 제약 그대로 노출)
      SymbolQuickPick.tsx              # 최근 종목 chip + 코드 직접 입력 (§4)
  api/
    candles.ts                         # GET /api/candles 클라이언트
    investorFlow.ts                    # GET /api/investor-flow 클라이언트 (Phase 16 T103)
  hooks/
    useCandles.ts                      # symbol/interval 변경 시 재조회, 폴링 없음(수동 새로고침)
```

- `PriceChart`/`InvestorFlowPanel`은 각각 독립 컴포넌트로 두되, 부모(`StockDetail.tsx`)가
  동일한 `IChartApi` 시간축을 props로 내려 두 pane을 동기화한다(lightweight-charts는
  `chart.addPane()`으로 한 `IChartApi` 인스턴스 안에 여러 pane을 만들 수 있어 별도의 수동
  동기화 코드 없이 자연스럽게 풀림 — 두 컴포넌트를 완전히 분리된 차트 인스턴스로 만들지
  않는 게 핵심 설계 포인트).
- 기존 `Panel` 컴포넌트로 전체를 감싸 코너 브라켓·헤어라인 등 기존 패널 프레이밍을 그대로
  적용(`Nested Cards Prohibited` 규칙 — 차트 자체는 Panel 안의 콘텐츠지 별도 패널이 아님).
- 폴링 주기: 기존 훅들(`useBalance(2000)` 등)과 달리 차트는 **수동 갱신 + interval 변경 시
  재조회**로 시작(장중 1분봉을 계속 폴링하려면 별도 설계 필요 — 이번 스코프는 "선택 시 조회"
  까지만).

---

## 6. `DESIGN.md` 갱신 필요 사항

이 기능 구현 시 `DESIGN.md`에 아래 두 가지를 추가해야 함(기존 문서에 없는 신규 컴포넌트
유형이므로):

1. **§5 Components에 "Price Chart (Candlestick)" 항목 추가** — §3에서 정한 색상 매핑
   (상승=Live Green, 하락=Alert Red, 그리드=Graphite Line, 크로스헤어=Emerald Signal),
   그리고 "No-Ambiguity Rule의 의도된 예외"임을 명시 + 호버 툴팁이 접근성 완화책이라는 근거.
2. **Tab Navigation을 실제 구현 예시로 승격** — 현재 §5에 스펙만 있고 "구현된 곳 없음" 상태.
   이번이 첫 구현이므로 실제 적용 후 필요 시 문법(클래스명 등) 미세조정을 반영.

---

## 7. 백엔드 API 설계

```
GET /api/candles?symbol=005930&interval=1d&count=100&before=&adjusted=true
  → core/adapters/toss/rest.py의 TossRestClient.get_candles() 그대로 프록시
  → MARKET_DATA_CHART 스로틀러 버킷 적용
```

Phase 16에 이미 있는 `GET /api/investor-flow`(T103)와 조합해 `StockDetail.tsx`가 두 API를
각각 호출한다 — 백엔드에서 합쳐서 내려줄 필요는 없음(두 데이터의 시간축·소스가 다르므로
프론트에서 조합하는 게 관심사 분리에 맞음).

---

## 8. Phase 16 태스크 반영

기존 `specs/tasks.md` Phase 16의 T102(캔들 API)·T104~T108(프론트)을 이 설계에 맞춰
구체화했다 — Phase 16 섹션 참고. 핵심 변경점:
- T102: "신규 캔들 조회 로직"이 아니라 **기존 `get_candles()` 프록시**로 범위 축소(효율 大↑).
- T104~: Tab Navigation(§2 옵션 B) 우선 구현 → PriceChart → SymbolQuickPick → StockDetail
  조합 순서로 재배열. InvestorFlowPanel은 Phase 16 백엔드 태스크(T098~T103) 완료 후 연결.
