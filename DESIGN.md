---
name: Quanteo Dashboard
description: 자동매매 봇 실시간 운용 대시보드
colors:
  void-black: "#05070a"
  carbon-panel: "#10141a"
  graphite-line: "#1f2630"
  emerald-signal: "#10b981"
  emerald-deep: "#059669"
  live-green: "#22c55e"
  alert-red: "#ef4444"
  caution-amber: "#f59e0b"
  ghost-gray: "#6b7280"
  ink-white: "#f1f5f9"
typography:
  display:
    fontFamily: "Pretendard, -apple-system, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 600
    lineHeight: 1.5
    letterSpacing: "-0.01em"
  body:
    fontFamily: "Pretendard, -apple-system, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "normal"
  label:
    fontFamily: "Pretendard, -apple-system, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "normal"
  mono:
    fontFamily: "ui-monospace, SFMono-Regular, JetBrains Mono, Menlo, Consolas, monospace"
    note: "시스템 라벨(ENV·MARKET·UPTIME), 타임스탬프, 종목코드, 로그 이벤트 타입 전용. 본문·헤더는 Pretendard 유지"
  numeric:
    fontFeatureSettings: "tabular-nums"
    note: "가격·수량·시각 등 정렬이 필요한 숫자는 폰트 교체 대신 tabular-nums로 정렬한다"
rounded:
  sm: "4px"
  md: "8px"
spacing:
  xs: "8px"
  sm: "12px"
  md: "16px"
  lg: "24px"
components:
  btn-pause:
    backgroundColor: "rgba(245, 158, 11, 0.10)"
    textColor: "{colors.caution-amber}"
    rounded: "{rounded.sm}"
    padding: "8px 16px"
  btn-pause-hover:
    backgroundColor: "rgba(245, 158, 11, 0.20)"
    textColor: "{colors.caution-amber}"
    rounded: "{rounded.sm}"
    padding: "8px 16px"
  btn-resume:
    backgroundColor: "rgba(34, 197, 94, 0.10)"
    textColor: "{colors.live-green}"
    rounded: "{rounded.sm}"
    padding: "8px 16px"
  btn-resume-hover:
    backgroundColor: "rgba(34, 197, 94, 0.20)"
    textColor: "{colors.live-green}"
    rounded: "{rounded.sm}"
    padding: "8px 16px"
  btn-kill:
    backgroundColor: "rgba(239, 68, 68, 0.10)"
    textColor: "{colors.alert-red}"
    rounded: "{rounded.sm}"
    padding: "8px 16px"
  btn-kill-hover:
    backgroundColor: "rgba(239, 68, 68, 0.20)"
    textColor: "{colors.alert-red}"
    rounded: "{rounded.sm}"
    padding: "8px 16px"
  section-panel:
    backgroundColor: "{colors.carbon-panel}"
    textColor: "{colors.ink-white}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
    note: "코너 브라켓(accent/40, 2px×2px) + 상단 1px emerald 그라데이션 라인 포함 — Panel.tsx 공용 셸"
---

# Design System: Quanteo Dashboard

## 1. Overview

**Creative North Star: "The Instrumented Terminal"**

Quanteo 대시보드는 봇이 운용되는 동안 운용자가 계기판 앞에 앉아 있는 감각을 준다. 포지션, 주문, 체결, 전략 실행 흐름이 어둠 위에 부상하고, 패널 모서리의 브라켓과 헤어라인이 이 화면이 "계측되고 있다"는 신호를 조용히 보낸다. 화면은 여전히 말이 많지 않다 — 그러나 상태가 달라지면 emerald 신호가 즉시 반응한다.

배경은 매트 블랙(#05070a) — 이전의 청록빛 심우주 검정보다 더 중립적이고 어둡다. Pretendard가 본문·헤더를 담당하고, 시스템 라벨(ENV·MARKET·UPTIME)·타임스탬프·종목코드·로그 이벤트 타입에는 mono 서체가 붙는다 — 숫자·코드가 "기계가 찍어낸 값"임을 시각적으로 알린다. 인터랙션과 신호의 색은 이제 Signal Blue가 아니라 Emerald Signal이다. 색상은 여전히 장식이 아니라 신호다.

이 시스템은 소비자 투자 앱(Trading212, Robinhood)의 게임화 미학과 일반 SaaS 어드민 템플릿을 여전히 명시적으로 거부한다. 다만 이번 개편으로 "조작 가능한 워크스테이션" 무드가 한 단계 더 강해졌다 — 패널 모서리 브라켓, 상단 emerald 헤어라인, RUNNING·STREAM 인디케이터의 절제된 glow로 계기판적 질감을 더한다. 밀도와 신뢰감이라는 원래 원칙은 그대로다.

**Key Characteristics:**

- 타이포그래피 이원 체계 — Pretendard(본문·헤더) + mono(시스템 라벨·타임스탬프·코드). 숫자는 tabular-nums로 정렬
- 그림자 없음이 기본, 단 emerald glow는 RUNNING/STREAM ON 인디케이터 등 소수 지점에만 국소적으로 허용(`--glow-emerald`)
- 깊이는 배경 레이어링(void-black → carbon-panel)
- 상태 색상은 항상 레이블과 함께 — 색상 단독 의존 금지 (WCAG 1.4.1)
- 모든 핵심 제어는 현재 화면에서 — 탐색을 위한 탐색 없음
- 패널 헤더에 드래그 핸들 아이콘 + 코너 브라켓 + 상단 emerald 헤어라인 — "조작 가능한 워크스테이션" 무드의 장식적 어포던스
- 페이지 배경에 32px 그리드 텍스처(graphite-line, 극저투명도) — 계기판 질감, 콘텐츠 가독성에 영향 없는 수준으로 절제

## 2. Colors: The Operational Palette

어둠 위에 데이터만 남긴 팔레트. 중립색 두 단계가 깊이를 만들고, 의미 있는 색상만 신호로 부상한다.

### Primary

- **Emerald Signal** (#10b981): 인터랙션의 색. 탭 활성 표시, 장부금액 하이라이트, 링크·포커스 링, 패널 프레이밍(코너 브라켓·상단 라인). 화면 어디서나 Emerald Signal이 보이면 상호작용이 가능하거나 주목해야 할 수치다.
- **Emerald Deep** (#059669): Emerald Signal의 hover/active 전용. 독립적으로 쓰이지 않는다.

### Secondary

- **Live Green** (#22c55e): RUNNING 상태, 이익, 성공 피드백, Resume 버튼. Emerald Signal과 의도적으로 다른 톤(라임 쪽)을 써서 "인터랙션 색"과 "상태 색"을 구분한다.
- **Caution Amber** (#f59e0b): PAUSE/REDUCE 상태, Pause 버튼, 경고 메시지. 시스템이 동작하지만 완전하지 않다.

### Tertiary

- **Alert Red** (#ef4444): KILL 상태, 에러, 손실, Kill 버튼, 실전 환경 경고. 즉각 시각적 주의를 요구한다.

### Neutral

- **Void Black** (#05070a): 전체 배경. 매트 블랙 — 데이터를 부상시키는 기반.
- **Carbon Panel** (#10141a): 섹션 패널 배경. 두 번째 레이어.
- **Graphite Line** (#1f2630): 보더, 구분선, 배경 그리드 텍스처. 레이아웃 뼈대.
- **Ink White** (#f1f5f9): 주요 데이터, 종목 코드, 핵심 수치. 최고 대비.
- **Ghost Gray** (#6b7280): 헤더 레이블, 메타 정보, 2차 데이터. 주요 데이터와 명확히 구분.

**The Signal Rule.** Emerald Signal은 인터랙션 가능한 요소, 현재 선택 상태, 운용자가 집중해야 할 수치(장부금액), 그리고 패널 프레이밍에만 쓴다. 장식 목적으로 남용하면 신호로서의 의미가 사라진다 — "많은 무관한 액센트 색을 섞어 그린 시그널을 희석하지 않는다"는 원칙을 지킨다.

**The No-Ambiguity Rule.** positive(live-green)/negative(alert-red) 색상은 반드시 텍스트 레이블 또는 아이콘과 함께 사용한다. 색맹 사용자는 색상만으로 이익/손실을 구분할 수 없다.

## 3. Typography

**Body/Display Font:** Pretendard, -apple-system, system-ui, sans-serif
**System Label Font:** ui-monospace, SFMono-Regular, JetBrains Mono, Menlo, Consolas, monospace

**Character:** 두 패밀리가 역할을 분담한다 — Pretendard는 헤딩·본문·버튼·피드백 문구, mono는 ENV·MARKET·UPTIME 같은 상태 라벨, 타임스탬프, 종목코드(StockCell 보조 텍스트), 실시간 이벤트 로그의 타임스탬프/이벤트 타입. 웹폰트를 추가 로드하지 않고 OS 내장 모노(`ui-monospace`/`SFMono`/`Menlo`/`Consolas`) 스택만 사용해 성능 비용이 없다. 숫자 정렬이 필요한 곳(가격·수량·시각)은 `tabular-nums` 유틸리티로 해결하며, mono 서체를 쓰는 곳에서도 tabular-nums는 유지한다.

### Hierarchy

- **Display** (600 weight, 0.875rem, line-height 1.5, letter-spacing -0.01em, Pretendard): 섹션 패널 헤더. `text-sm font-semibold tracking-tight text-white`
- **Body** (400 weight, 0.875rem, line-height 1.5, Pretendard): 테이블 행 데이터, 피드백 메시지, 로그 payload. 기본 읽기 단위.
- **Label** (400 weight, 0.75rem, line-height 1.4, Pretendard): 테이블 컬럼 헤더. 데이터의 주석.
- **System Label** (400 weight, 0.75rem, mono): ENV/MARKET/UPTIME 값, 진입·주문·체결 타임스탬프, 종목코드, 로그 이벤트 타입. `font-mono`
- **Data Emphasis** (600 weight, 0.875rem, ink-white, tabular-nums, Pretendard): 종목명, 핵심 수치. 행 내에서 시선을 끄는 값.
- **Hero Numeric** (700 weight, 1.25rem, accent 또는 ink-white, tabular-nums, Pretendard): 계좌 요약의 총 매입금액처럼 카드 안에서 가장 먼저 읽혀야 하는 숫자.

**The Two Family Rule.** Pretendard와 mono, 이 두 패밀리 밖으로 늘리지 않는다. mono는 오직 "기계가 찍어낸 값"(시스템 상태·시각·코드)에만 쓰고, 사람이 읽는 문장·라벨·버튼에는 절대 쓰지 않는다. 새 영역에 강조가 필요하면 폰트를 바꾸기 전에 굵기·크기·색조를 먼저 시도한다.

## 4. Elevation

기본은 그림자 없음. 깊이는 배경색 단계로 표현하고, glow는 상태 신호 전용 예외로만 허용한다.

Void Black(`#05070a`) → Carbon Panel(`#10141a`) 두 레이어가 기본이다. 섹션 패널은 배경보다 밝은 패널 색 위에 1px 보더(graphite-line)로 경계를 만든다. 행 hover는 패널 배경에서 더 어두운 void-black으로 역전 — 어둠 속에서 행이 가라앉는 효과.

**The Restrained Glow Rule.** `box-shadow`는 기본적으로 쓰지 않는다. 예외는 `--glow-emerald` 한 가지뿐 — RUNNING 상태 점, STREAM ON 점처럼 "지금 살아있다"를 알리는 소수의 인디케이터에만 국소적으로 적용한다. 카드 전체에 glow를 씌우거나 여러 요소에 남용하지 않는다.

## 5. Components

### Buttons (Control Actions)

봇 제어 버튼은 기능의 위험 수준을 색상으로 신호한다. 단호하고 절제된 틴트 패턴: `bg-{color}/10 text-{color} border border-{color}/30`.

- **Shape:** 4px 모서리 (rounded in Tailwind) — 기능 중심, 장식 최소화
- **Pause (Caution Amber):** bg #f59e0b/10, text #f59e0b, border #f59e0b/30
- **Resume (Live Green):** bg #22c55e/10, text #22c55e, border #22c55e/30
- **Kill (Alert Red):** bg #ef4444/10, text #ef4444, border #ef4444/30. `ml-auto`로 우측 분리 — 구조적 거리가 위험성을 전달한다.
- **Hover:** 틴트 /10 → /20, transition-colors 150ms
- **Disabled:** opacity-40, cursor-not-allowed. 색상 변경 없음 — 상태 언어 유지.
- **Loading:** 텍스트만 "처리 중..."으로 교체. 인라인 상태 피드백.

### Section Panels

- **Corner Style:** 8px (rounded-lg in Tailwind)
- **Background:** Carbon Panel (#10141a)
- **Border:** 1px solid Graphite Line (#1f2630)
- **Framing:** 좌·우 상단 코너 브라켓(emerald-signal/40, 8px×8px, `pointer-events-none`) + 패널 상단 1px emerald 그라데이션 헤어라인(`from-transparent via-accent/50 to-transparent`) — 계기판 무드, 순수 장식
- **Header Pattern:** px-3 py-2.5, 하단 보더, 드래그 핸들 아이콘(ghost-gray, 장식용) + 섹션명(display weight, ink-white) + 건수(mono, ghost-gray, tabular-nums) 좌우 배치
- **Nested Cards Prohibited:** 패널 안에 패널 없음.

### Data Tables

- **Column Headers:** ghost-gray, 0.75rem, 하단 구분선. 데이터 위계의 바닥.
- **Primary Values:** ink-white, 600 weight (종목명, 핵심 수치)
- **System Values:** mono, ghost-gray (종목코드, 타임스탬프)
- **Secondary Values:** ghost-gray, Pretendard (시장 구분)
- **Financial Highlight:** Emerald Signal for 장부금액 — 운용 판단의 기준이 되는 수치
- **Row Hover:** `hover:bg-surface` — 패널에서 더 어두운 배경으로 역전
- **Row Separator:** border-b border-border, last:border-0

### Status Bar

- **구조:** sticky top bar, full-width, bg-panel, border-b graphite-line
- **레이아웃:** 브랜드명(semibold white, Pretendard) + 상태 지표 flex row(mono). 우측 스트림 연결 상태.
- **상태 신호:** RUNNING → live-green + `.glow-emerald` 점, PAUSE/REDUCE → caution-amber, KILL → alert-red
- **ENV 표시:** prod → alert-red bold, 그 외 → emerald-signal (mono)
- **STREAM 인디케이터:** 연결 시 live-green 점에 `.glow-emerald` 적용, 끊김 시 alert-red 점(glow 없음)

### Tab Navigation

- **스타일:** 하단 2px 보더. active: `border-accent text-white`. inactive: `border-transparent text-muted hover:text-white`
- **Active 표시:** Emerald Signal 하단 선이 현재 탭을 정의한다. 배경 tint 없음.

### Feedback Messages

- **Success:** bg live-green/5, text live-green, border live-green/20, font-mono text-xs
- **Error:** bg alert-red/5, text alert-red, border alert-red/20, font-mono text-xs
- **Prod Warning:** bg alert-red/5, text alert-red, border alert-red/30 — ControlPanel 하단에 고정. 절대 사라지지 않는다.

## 6. Do's and Don'ts

### Do:

- **Do** Emerald Signal을 인터랙션 가능한 요소, 현재 선택 상태, 핵심 수치 강조, 패널 프레이밍에만 사용한다.
- **Do** positive/negative 상태는 색상과 텍스트 레이블을 반드시 함께 제공한다 (WCAG 1.4.1).
- **Do** 제어 버튼의 색상 언어를 일관되게 유지한다: Pause = caution-amber, Resume = live-green, Kill = alert-red.
- **Do** 새 섹션 컨테이너는 `bg-panel border border-border rounded-lg` + 코너 브라켓/상단 헤어라인 패턴을 따른다.
- **Do** 시스템 라벨·타임스탬프·코드에는 `font-mono`, 사람이 읽는 문장·라벨에는 Pretendard를 쓴다. 숫자는 `tabular-nums`로 정렬한다.
- **Do** 빈 상태는 ghost-gray 텍스트로 명시한다 ("보유 포지션 없음" 등). 빈 화면을 남기지 않는다.
- **Do** 실전(prod) 환경 표시는 alert-red로, 명시적 경고 문구와 함께 항상 노출한다.
- **Do** Kill 버튼은 시각적·구조적으로 다른 제어 버튼과 분리한다 (`ml-auto` 또는 별도 영역).
- **Do** glow는 `--glow-emerald` 하나로 한정하고 RUNNING/STREAM ON 등 "살아있음" 신호에만 쓴다.

### Don't:

- **Don't** Trading212, Robinhood 등 소비자 투자 앱의 밝은 배경, 게임화 그래픽, 원형 진척 그래프, 응원하는 일러스트를 도입한다.
- **Don't** 일반 SaaS 어드민 템플릿의 사이드바 + 동일 크기 카드 그리드 레이아웃을 모방한다.
- **Don't** glow/코너 브라켓 외의 장식적 `box-shadow`를 사용한다. 깊이는 기본적으로 배경 틴트 차이로 표현한다.
- **Don't** `border-left` 1px 초과 컬러 스트라이프를 카드나 항목 강조에 사용한다.
- **Don't** `background-clip: text` 그라데이션 텍스트를 사용한다.
- **Don't** Pretendard·mono 외의 폰트 패밀리를 도입한다. mono를 사람이 읽는 문장에 쓰지 않는다.
- **Don't** Emerald Signal을 배경 장식, 비인터랙티브 요소에 남용해 신호를 희석한다.
- **Don't** 색상만으로 positive/negative를 전달한다. 레이블이나 아이콘이 항상 동반해야 한다.
- **Don't** Bloomberg 터미널의 정보 과밀을 복제한다. 밀도는 참고하되, 가독성 임계점은 지킨다.
- **Don't** 배경 그리드 텍스처의 불투명도를 높여 콘텐츠 가독성을 해친다 — 항상 graphite-line 극저투명도 수준을 유지한다.
