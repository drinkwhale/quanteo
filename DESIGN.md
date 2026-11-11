---
name: Quanteo Dashboard
description: 자동매매 봇 실시간 운용 대시보드
colors:
  canvas: "#0b0d11"
  panel: "#12151b"
  raised: "#1a1e26"
  line: "#242933"
  line-strong: "#3a4150"
  ink: "#edeff3"
  dim: "#a8afbc"
  muted: "#828a99"
  up: "#f55461"
  down: "#4f96ff"
  live: "#34d380"
  warn: "#f5a623"
  danger: "#ff6b35"
typography:
  hero-numeric:
    fontFamily: "Pretendard Variable, Pretendard, -apple-system, system-ui, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 700
    lineHeight: 1.33
    letterSpacing: "-0.025em"
  stat:
    fontFamily: "Pretendard Variable, Pretendard, -apple-system, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 600
    lineHeight: 1.5
  title:
    fontFamily: "Pretendard Variable, Pretendard, -apple-system, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 600
    lineHeight: 1.43
  data:
    fontFamily: "Pretendard Variable, Pretendard, -apple-system, system-ui, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 400
    lineHeight: 1.54
    note: "표 본문·내비게이션 전용 13px (Tailwind `text-data`)"
  label:
    fontFamily: "Pretendard Variable, Pretendard, -apple-system, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: 1.33
  micro:
    fontFamily: "Pretendard Variable, Pretendard, -apple-system, system-ui, sans-serif"
    fontSize: "0.6875rem"
    fontWeight: 400
    lineHeight: 1.45
    note: "종목코드·보조 태그 전용 11px (Tailwind `text-2xs`). 이보다 작은 글씨는 쓰지 않는다"
  mono:
    fontFamily: "ui-monospace, SFMono-Regular, JetBrains Mono, Menlo, Consolas, monospace"
    note: "종목코드·타임스탬프·이벤트 타입 전용. 사람이 읽는 문장에는 쓰지 않는다"
  numeric:
    fontFeatureSettings: "tabular-nums"
    note: "table과 .num 안의 숫자는 전역 고정폭"
rounded:
  sm: "4px"
  md: "6px"
  lg: "8px"
spacing:
  xs: "8px"
  sm: "12px"
  md: "16px"
  lg: "24px"
components:
  panel:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    note: "border 1px {colors.line}. 헤더(min-h 44px) + 내부 스크롤 본문 — Panel.tsx"
  btn:
    backgroundColor: "transparent"
    textColor: "{colors.dim}"
    rounded: "{rounded.md}"
    height: "32px"
    padding: "0 12px"
    note: "border 1px {colors.line-strong}. hover: bg {colors.raised}, text {colors.ink}"
  btn-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.canvas}"
    rounded: "{rounded.md}"
    height: "32px"
    padding: "0 12px"
  btn-live:
    backgroundColor: "rgba(52, 211, 128, 0.10)"
    textColor: "{colors.live}"
    rounded: "{rounded.md}"
    height: "32px"
    padding: "0 12px"
  btn-warn:
    backgroundColor: "rgba(245, 166, 35, 0.10)"
    textColor: "{colors.warn}"
    rounded: "{rounded.md}"
    height: "32px"
    padding: "0 12px"
  btn-danger:
    backgroundColor: "rgba(255, 107, 53, 0.10)"
    textColor: "{colors.danger}"
    rounded: "{rounded.md}"
    height: "32px"
    padding: "0 12px"
  segmented:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.muted}"
    rounded: "{rounded.md}"
    note: "선택된 칸: bg {colors.raised}, text {colors.ink} — Segmented.tsx"
  field:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    height: "32px"
    note: "border 1px {colors.line-strong}. focus: border {colors.ink}"
---

# Design System: Quanteo Dashboard

## 1. Overview

**Creative North Star: "The Trading Desk" — 색은 데이터다**

미국장이 열리는 밤 11시 반, 불 꺼진 방에서 IDE 옆 보조 모니터에 띄워 둔 화면을 흘끗 보고
"봇이 살아 있나, 지금 얼마 벌고 잃었나, 걸려 있는 주문이 있나"를 3초 안에 읽는다.
이 장면이 테마(다크)와 밀도, 위계를 전부 결정한다.

화면의 크롬(셸·버튼·탭·선택 상태·포커스 링)은 전부 무채색이다. 채도가 있는 픽셀은 예외 없이
둘 중 하나를 뜻한다 — **시세**(올랐나 내렸나, 샀나 팔았나) 아니면 **봇 상태**(돌고 있나 멈췄나).
브랜드 액센트 색은 없다. 그래서 화면에서 색이 보이면 그건 읽어야 할 정보다.

이전 시스템("The Instrumented Terminal")의 코너 브라켓, 배경 그리드 텍스처, emerald glow,
자유 드래그 패널은 걷어냈다. 계기판 분위기를 내는 장식이었지 정보가 아니었고, 고정 좌표
패널은 화면 폭이 달라지면 잘렸다.

**Key Characteristics:**

- 색 축은 두 개뿐이고 서로 섞지 않는다 — 시세 축(up/down), 봇 상태 축(live/warn/danger)
- 봇 제어(일시정지·재개·킬스위치)는 헤더 한 곳에만 있고 어느 화면에서든 한 번에 닿는다
- 레이아웃은 고정이다. 1280px 이상에서 운용 화면은 한 뷰포트에 들어오고 패널 안에서만 스크롤한다
- 깊이는 3단 레이어(canvas → panel → raised)와 1px 선으로만 표현한다
- 숫자는 전부 고정폭(tabular-nums), 원화는 정수, 부호는 항상 표기

## 2. Colors

### 중립 — 크롬 전부

| 토큰          | 값        | 용도                                             |
| ------------- | --------- | ------------------------------------------------ |
| `canvas`      | `#0b0d11` | 페이지 바닥, 입력 필드·세그먼트 트랙             |
| `panel`       | `#12151b` | 패널, 헤더                                       |
| `raised`      | `#1a1e26` | hover, 선택된 탭·세그먼트, 다이얼로그·토스트     |
| `line`        | `#242933` | 패널 테두리, 구분선                              |
| `line-strong` | `#3a4150` | 버튼·필드 테두리, 스크롤바                       |
| `ink`         | `#edeff3` | 핵심 수치, 종목명, 선택 상태, 포커스 링          |
| `dim`         | `#a8afbc` | 보조 수치(수량·평단가), 버튼 기본 텍스트         |
| `muted`       | `#828a99` | 컬럼 헤더, 라벨, 코드, 타임스탬프 (대비 4.8:1 ↑) |

### 시세 축 — 국내 증시 관례

- **`up` `#f55461`**: 상승 · 매수 · 이익 · 양봉
- **`down` `#4f96ff`**: 하락 · 매도 · 손실 · 음봉
- 보합·방향 없음은 `muted`

등락·손익·매수/매도·캔들은 반드시 `lib/format.ts`의 `trendClass` / `sideClass`를 거친다.

### 봇 상태 축

- **`live` `#34d380`**: 가동 중, 스트림 연결됨, 체결 완료
- **`warn` `#f5a623`**: 축소 운용, 일시정지, 주문 대기
- **`danger` `#ff6b35`**: 킬스위치, 에러, 주문 거부, 실전 환경 표시

**The Two Axes Rule.** 시세 색으로 상태를 말하지 않고, 상태 색으로 시세를 말하지 않는다.
`danger`가 빨강이 아니라 주황인 이유가 이것이다 — 화면 가득한 "상승 빨강"과 킬스위치가
같은 색이면 좋은 소식과 비상 정지가 구분되지 않는다.

**The No-Ambiguity Rule.** 색만으로 뜻을 전달하지 않는다. 등락·손익에는 항상 부호(+/−)가,
매수/매도와 상태에는 항상 텍스트 라벨이 붙는다 (WCAG 1.4.1).

**The Colorless Chrome Rule.** 인터랙션 가능 여부·현재 선택·포커스는 `ink`/`raised`의 명도
차이로만 표현한다. 강조하고 싶다고 새 색을 들이지 않는다.

## 3. Typography

Pretendard 한 패밀리로 제목·본문·버튼·수치를 전부 처리하고, mono는 "기계가 찍은 값"
(종목코드·타임스탬프·이벤트 타입)에만 쓴다. 크기는 고정 rem 스케일이다.

| 단계         | 크기 | 굵기 | 쓰임                                         |
| ------------ | ---- | ---- | -------------------------------------------- |
| Hero Numeric | 24px | 700  | 총 평가금액 — 화면당 한 곳                   |
| Stat         | 16px | 600  | 평가손익·매입금액 등 요약 수치, 지표 값      |
| Title        | 14px | 600  | 패널 제목                                    |
| Data         | 13px | 400  | 표 본문, 내비게이션 (종목명·핵심 수치는 600) |
| Label        | 12px | 400  | 컬럼 헤더, 라벨, 버튼, 보조 문구             |
| Micro        | 11px | 400  | 종목코드, 수수료 내역 — 최소 크기            |

위계는 크기보다 **명도(ink → dim → muted)와 굵기**로 만든다. 표 한 행 안에서 눈이 가야 할
값(현재가·평가손익)만 `ink`/600이고 나머지는 `dim`이다.

## 4. Layout

- **셸**: 고정 헤더(48px) → 지수·환율 띠(36px) → 본문. 사이드바는 쓰지 않는다
- **운용**: 좌 `계좌`(위) + `주문·체결`(아래) / 우 `봇 활동`(위) + `시장 주도주`(아래).
  왼쪽은 "내 돈", 오른쪽은 "봇과 시장"
- **차트**: 좌 종목 바로가기(260px) / 우 차트
- **전략·봇**: 좌 운용 상태 / 중앙 전략 신호 + 봇 활동 / 우 백테스트
- **반응형**: 1280px 미만에서 세로로 쌓이고 페이지가 스크롤된다. 표는 줄바꿈하지 않고 패널
  안에서 가로 스크롤한다. 단일 열 그리드는 반드시 `grid-cols-1`(= `minmax(0,1fr)`)을 준다 —
  auto 트랙이면 넓은 표가 열을 밀어내 화면을 뚫는다
- **화면 전환**: URL 해시(`#desk` `#chart` `#bot` `#watchlist`)가 단일 진실 공급원

간격은 패널 사이 12px, 패널 안쪽 16px, 표 셀 12×8px.

## 5. Elevation

그림자는 화면 위에 뜨는 것(다이얼로그·토스트·조작 결과 말풍선)에만 쓴다. 패널은 평평하고
`panel` 배경 + 1px `line` 테두리로만 구분한다. glow는 쓰지 않는다.

## 6. Components

### Panel (`Panel.tsx`)

화면의 유일한 컨테이너. `title` + `meta`(건수·기준 시각) + `actions`(필터·새로고침).
본문이 넘치면 패널 안에서 스크롤하고 표 헤더는 고정된다. **패널 안에 패널을 넣지 않는다** —
내부 구획은 구분선으로 나눈다.

### Buttons (`.btn` — index.css)

모양은 하나, 위험도만 색으로 구분한다.

- `.btn`: 기본(테두리만) — 새로고침, 취소, 조회
- `.btn-primary`: `ink` 채움 — 화면당 하나의 주 동작(백테스트 실행)
- `.btn-live` / `.btn-warn` / `.btn-danger`: 재개 / 일시정지 / 킬스위치. 틴트 10% → hover 20%
- 상태: hover, active, focus-visible(2px `ink` 링), disabled(opacity 40%), 처리 중("처리 중…")

### Bot Controls (`BotControls.tsx`)

상태 배지 + 토글 버튼(가동 중이면 일시정지, 멈춰 있으면 재개) + 구분선 + 킬스위치.
모든 조작은 확인 다이얼로그를 거치고, 실전 환경이면 다이얼로그에 경고 문장이 붙는다.
**이 컴포넌트를 다른 화면에 복제하지 않는다.**

### Segmented (`Segmented.tsx`)

같은 데이터를 다른 기준으로 볼 때 쓰는 유일한 토글 — 정렬, 주문 구분, 봉 주기.

### Data Table (`.tbl` — index.css)

컬럼 헤더 `muted` 12px 고정, 숫자 열은 `.r`(우측 정렬), 행 hover는 `raised/60`.
종목 셀은 종목명(600) 위, 코드(mono 11px) 아래.

### 상태 문구

- `.state-msg`: 빈 상태·로딩. "없음"으로 끝내지 말고 언제 채워지는지 알려준다
- `.state-err`: 에러 띠(`danger` 10% 배경). 조회가 실패했으면 "데이터 없음" 문구를 같이
  보여주지 않는다 — 실패와 0건은 다른 사실이다
- 결측 값은 `—`. 못 받은 값을 0으로 표시하지 않는다

### 실전 환경 표시

헤더의 `실전` 태그(`danger` 테두리)는 항상 보인다. 전략·봇 화면의 "환경" 항목과 모든 제어
확인 다이얼로그에서 문장으로 다시 알린다.

## 7. Motion

상태 전이에만 쓴다. hover·선택 150ms, 다이얼로그·토스트 등장 180–200ms `--ease-out`
(translateY + opacity). 가동 중 점만 `animate-pulse`. `prefers-reduced-motion`이면 전부 끈다.

## 8. Do's and Don'ts

### Do

- 등락·손익·매수/매도는 `trendClass`/`sideClass`로, 봇 상태는 `lib/halt.ts`의 `HALT_META`로 칠한다
- 색에는 항상 부호나 라벨을 붙인다
- 새 컨테이너는 `Panel`, 새 토글은 `Segmented`, 새 버튼은 `.btn` 계열을 쓴다
- 시각은 `fmtClock`/`fmtStamp`, 금액은 `fmtPrice`/`fmtPnl`로 포맷한다
- 실시간이 아닌 데이터는 기준 시각을 같이 보여준다

### Don't

- 브랜드 액센트 색을 들이지 않는다. 장식용 색·그라데이션·glow·배경 텍스처를 쓰지 않는다
- 시세 색으로 상태를, 상태 색으로 시세를 표현하지 않는다
- 봇 제어 버튼을 헤더 밖에 복제하지 않는다
- 패널을 중첩하거나, 같은 크기 카드 그리드로 화면을 채우지 않는다
- 드래그·리사이즈로 레이아웃을 사용자에게 떠넘기지 않는다
- 11px보다 작은 글씨, Pretendard·mono 외의 폰트를 쓰지 않는다
- `border-left` 컬러 스트라이프, `background-clip: text` 그라데이션 텍스트를 쓰지 않는다
- Trading212·Robinhood류 소비자 앱의 게임화 그래픽, 일반 SaaS 어드민의 사이드바 + 카드
  그리드, Bloomberg 터미널의 과밀을 따라가지 않는다
