# quanteo 대시보드 설계 시스템

이 문서는 quanteo 대시보드의 설계 원칙, 컴포넌트 시스템, 색상 토큰을 정의한다.

## 1. 디자인 원칙

- **현재 상태 우선**: 화면 전환보다 현재 봇 상태 인지가 우선순위. 공통 StatusBar는 모든 탭에서 유지.
- **Simple은 Beautiful**: 과도한 애니메이션이나 꾸미기보다 필요한 정보를 명확하게.
- **Dark Mode 기본**: 24시간 모니터링 환경에 맞춰 다크 모드 기반 설계.

## 2. 색상 토큰

```css
--color-space-black: #0f1117; /* 배경 */
--color-midnight-panel: #1a1d27; /* 패널 배경 */
--color-structural-line: #2a2d3a; /* 구분선, 비활성 버튼 배경 */
--color-signal-blue: #3b82f6; /* 활성 강조, 포커스 */
--color-signal-blue-deep: #2563eb; /* 호버 강조 */
--color-live-green: #22c55e; /* 상승, 성공 신호 */
--color-alert-red: #ef4444; /* 하락, 경고 신호 */
--color-caution-amber: #f59e0b; /* 주의 신호 */
--color-ghost-gray: #6b7280; /* 보조 텍스트, 시각적 위계 2순위 */
--color-ink-white: #f1f5f9; /* 주 텍스트, 밝은 전경 */
```

## 5. 컴포넌트 스타일

### Tab Navigation (T111 최초 구현)

탭 네비게이션은 App.tsx 최상단에 위치하며, 운용현황 / 종목상세 두 탭을 지원한다.

```
Active tab:    border-b-2 border-accent text-white
Inactive tab:  border-b-2 border-transparent text-muted hover:text-white
Hover state:   transition-colors
Focus state:   focus-visible:outline-signal-blue focus-visible:outline-offset-2
```

### Price Chart (Candlestick) — T112 최초 구현

lightweight-charts를 사용한 캔들 차트. DESIGN.md "No-Ambiguity Rule의 의도된 예외"를 적용한다.

**색상 매핑:**

| 요소       | 색상                     | 값      |
| ---------- | ------------------------ | ------- |
| 상승 캔들  | Live Green               | #22c55e |
| 하락 캔들  | Alert Red                | #ef4444 |
| 배경       | 투명 (Panel 배경 그대로) | —       |
| 그리드선   | Graphite Line            | #1f2630 |
| 크로스헤어 | Emerald Signal           | #10b981 |
| 거래량 바  | Ghost Gray               | #6b7280 |

**접근성 주석:**

캔들의 상승/하락을 색상으로만 구분하는 것은 `DESIGN.md "No-Ambiguity Rule"`의 의도된 예외다.
이유: 캔들스틱 차트는 금융 업계 표준 방식이며, 호버 시 OHLC 수치 툴팁으로 접근성을 완화한다.

### SymbolQuickPick 컴포넌트 (T113)

종목 선택 UI. 6자리 코드 입력 및 최근 종목 칩으로 구성.

- 입력창: `bg-midnight-panel border border-border`
- 칩 버튼: `bg-structural-line hover:bg-signal-blue transition-colors`
- Enter 키: 6자리 코드 완성 시 자동 검색

### IntervalToggle 컴포넌트 (T113)

1분봉 / 일봉 토글.

```
Active:   bg-signal-blue text-white
Inactive: bg-structural-line text-muted hover:text-white
```

---

## 6. StockDetail 페이지 (T114)

종목 상세 정보 및 차트 표시 페이지.

- 레이아웃: Panel 컨테이너 내 SymbolQuickPick + IntervalToggle + PriceChart 수직 배열
- 종목 미선택 시: 안내 텍스트만 표시
- 데이터 로딩 중: 로딩 스피너 표시
- 차트 로드 실패: 오류 메시지 표시

---

## 문서 버전

- **T111**: TabNav 컴포넌트 최초 구현
- **T112**: PriceChart 컴포넌트 최초 구현, 색상 토큰 정의
- **T113**: SymbolQuickPick, IntervalToggle 최초 구현
- **T114**: StockDetail 페이지 조립
- **T115**: 이 문서 생성
