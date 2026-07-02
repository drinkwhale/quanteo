---
name: Quanteo Dashboard
description: 자동매매 봇 실시간 운용 대시보드
colors:
  space-black: "#0f1117"
  midnight-panel: "#1a1d27"
  structural-line: "#2a2d3a"
  signal-blue: "#3b82f6"
  signal-blue-deep: "#2563eb"
  live-green: "#22c55e"
  alert-red: "#ef4444"
  caution-amber: "#f59e0b"
  ghost-gray: "#6b7280"
  ink-white: "#f1f5f9"
typography:
  display:
    fontFamily: "JetBrains Mono, Fira Code, monospace"
    fontSize: "0.875rem"
    fontWeight: 600
    lineHeight: 1.5
    letterSpacing: "0.05em"
  body:
    fontFamily: "JetBrains Mono, Fira Code, monospace"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "normal"
  label:
    fontFamily: "JetBrains Mono, Fira Code, monospace"
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "normal"
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
    backgroundColor: "{colors.midnight-panel}"
    textColor: "{colors.ink-white}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
---

# Design System: Quanteo Dashboard

## 1. Overview

**Creative North Star: "The Silent Exchange"**

Quanteo 대시보드는 시장의 소음 속에서 침묵의 교환이 이루어지는 공간이다. 봇이 돌아가는 동안 운용자는 한 화면에서 모든 것을 읽어낸다 — 포지션, 주문, 체결, 전략 실행 흐름까지. 화면은 말하지 않는다. 그러나 상태가 달라지면 바로 안다. 그것이 이 시스템의 역할이다.

배경은 심우주 검정(#0f1117). 데이터는 어둠 속에서 부상한다. JetBrains Mono 단일 패밀리가 숫자, 기호, 레이블 모두를 같은 그리드 위에 정렬한다. Signal Blue는 클릭 가능하고 제어 가능한 것에만 쓴다 — 나머지는 위계 속에 침묵한다. 색상은 장식이 아니라 신호다.

이 시스템은 소비자 투자 앱(Trading212, Robinhood)의 게임화 미학을 명시적으로 거부한다. 밝은 배경, 원형 진척 그래프, 그라데이션 강조, 균일한 카드 그리드는 이 공간에 없다. 일반 SaaS 어드민 템플릿의 무색무취한 사이드바 레이아웃도 아니다. 운용자가 장중에 쓰는 도구는 시장의 전문성을 반영해야 한다.

**Key Characteristics:**

- 모노스페이스 타이포그래피 일원화 — 단일 폰트 패밀리, 크기/굵기/색상으로만 위계
- 그림자 없음, 깊이는 배경 레이어링(space-black → midnight-panel)
- 상태 색상은 항상 레이블과 함께 — 색상 단독 의존 금지 (WCAG 1.4.1)
- 모든 핵심 제어는 현재 화면에서 — 탐색을 위한 탐색 없음

## 2. Colors: The Operational Palette

어둠 위에 데이터만 남긴 팔레트. 중립색 두 단계가 깊이를 만들고, 의미 있는 색상만 신호로 부상한다.

### Primary

- **Signal Blue** (#3b82f6): 인터랙션의 색. 탭 활성 표시, 장부금액 하이라이트, 링크·포커스 링. 화면 어디서나 Signal Blue가 보이면 상호작용이 가능하거나 주목해야 할 수치다.
- **Signal Blue Deep** (#2563eb): Signal Blue의 hover/active 전용. 독립적으로 쓰이지 않는다.

### Secondary

- **Live Green** (#22c55e): RUNNING 상태, 이익, 성공 피드백, Resume 버튼. 봇이 정상 가동 중임을 알린다.
- **Caution Amber** (#f59e0b): PAUSE/REDUCE 상태, Pause 버튼, 경고 메시지. 시스템이 동작하지만 완전하지 않다.

### Tertiary

- **Alert Red** (#ef4444): KILL 상태, 에러, 손실, Kill 버튼, 실전 환경 경고. 즉각 시각적 주의를 요구한다.

### Neutral

- **Space Black** (#0f1117): 전체 배경. 데이터를 부상시키는 기반.
- **Midnight Panel** (#1a1d27): 섹션 패널 배경. 두 번째 레이어.
- **Structural Line** (#2a2d3a): 보더, 구분선. 레이아웃 뼈대.
- **Ink White** (#f1f5f9): 주요 데이터, 종목 코드, 핵심 수치. 최고 대비.
- **Ghost Gray** (#6b7280): 헤더 레이블, 메타 정보, 2차 데이터. 주요 데이터와 명확히 구분.

**The Signal Rule.** Signal Blue는 인터랙션 가능한 요소, 현재 선택 상태, 그리고 운용자가 집중해야 할 수치(장부금액)에만 쓴다. 장식 목적으로 사용하는 순간 신호로서의 의미가 사라진다.

**The No-Ambiguity Rule.** positive(live-green)/negative(alert-red) 색상은 반드시 텍스트 레이블 또는 아이콘과 함께 사용한다. 색맹 사용자는 색상만으로 이익/손실을 구분할 수 없다.

## 3. Typography

**All Roles Font:** JetBrains Mono, Fira Code, monospace

**Character:** 단일 모노스페이스 패밀리가 전부를 담당한다. 숫자, 기호, 한글 레이블, 영문 식별자가 모두 같은 그리드 위에 정렬된다. 타이포그래피 혼합은 없다 — 대신 크기, 굵기, 색조로 위계를 만든다. 이것은 결함이 아니라 의도다: 이 대시보드는 터미널에서 왔다.

### Hierarchy

- **Display** (600 weight, 0.875rem, line-height 1.5, letter-spacing 0.05em): 섹션 패널 헤더. 전체 화면에서 레이블 역할. `text-sm font-semibold tracking-wider text-white`
- **Body** (400 weight, 0.875rem, line-height 1.5): 테이블 행 데이터, 피드백 메시지. 기본 읽기 단위.
- **Label** (400 weight, 0.75rem, line-height 1.4): 테이블 컬럼 헤더, 시각 정보, 건수. 데이터의 주석.
- **Data Emphasis** (600 weight, 0.875rem, ink-white): 종목 코드, 핵심 수치. 행 내에서 시선을 끄는 값.

**The One Family Rule.** 폰트 패밀리를 추가하지 않는다. JetBrains Mono 단일 패밀리가 이 시스템의 정체성이다. 새로운 영역에 다른 폰트가 필요하다고 느껴지면, 폰트를 바꾸기 전에 굵기와 크기로 먼저 시도한다.

## 4. Elevation

그림자 없음. 깊이는 배경색 단계로만 표현한다.

Space Black(`#0f1117`) → Midnight Panel(`#1a1d27`) 두 레이어가 전부다. 섹션 패널은 배경보다 밝은 패널 색 위에 1px 보더(structural-line)로 경계를 만든다. 행 hover는 패널 배경에서 더 어두운 space-black으로 역전 — 어둠 속에서 행이 가라앉는 효과.

**The Flat-by-Default Rule.** `box-shadow`는 이 시스템에 없다. 요소의 깊이는 배경색 차이로만 만든다. 그림자가 필요한 것처럼 느껴진다면, 그 요소의 배경 레이어 배치가 잘못된 것이다.

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
- **Background:** Midnight Panel (#1a1d27)
- **Border:** 1px solid Structural Line (#2a2d3a)
- **Header Pattern:** px-4 py-3, 하단 보더, 섹션명(display weight, ink-white) + 건수(label, ghost-gray) 좌우 배치
- **Nested Cards Prohibited:** 패널 안에 패널 없음.

### Data Tables

- **Column Headers:** ghost-gray, 0.75rem, 하단 구분선. 데이터 위계의 바닥.
- **Primary Values:** ink-white, 600 weight (종목 코드, 핵심 수치)
- **Secondary Values:** ghost-gray (시장 구분, 시각 정보)
- **Financial Highlight:** Signal Blue for 장부금액 — 운용 판단의 기준이 되는 수치
- **Row Hover:** `hover:bg-surface` — 패널에서 더 어두운 배경으로 역전
- **Row Separator:** border-b border-border, last:border-0

### Status Bar

- **구조:** sticky top bar, full-width, bg-panel, border-b structural-line
- **레이아웃:** 브랜드명(semibold white) + 상태 지표 flex row. 우측 스트림 연결 상태.
- **상태 신호:** RUNNING → live-green, PAUSE/REDUCE → caution-amber, KILL → alert-red
- **ENV 표시:** prod → alert-red bold, 그 외 → signal-blue

### Tab Navigation

- **스타일:** 하단 2px 보더. active: `border-accent text-white`. inactive: `border-transparent text-muted hover:text-white`
- **Active 표시:** Signal Blue 하단 선이 현재 탭을 정의한다. 배경 tint 없음.

### Feedback Messages

- **Success:** bg live-green/5, text live-green, border live-green/20, font-mono text-xs
- **Error:** bg alert-red/5, text alert-red, border alert-red/20, font-mono text-xs
- **Prod Warning:** bg alert-red/5, text alert-red, border alert-red/30 — ControlPanel 하단에 고정. 절대 사라지지 않는다.

## 6. Do's and Don'ts

### Do:

- **Do** Signal Blue를 인터랙션 가능한 요소, 현재 선택 상태, 핵심 수치 강조에만 사용한다.
- **Do** positive/negative 상태는 색상과 텍스트 레이블을 반드시 함께 제공한다 (WCAG 1.4.1).
- **Do** 제어 버튼의 색상 언어를 일관되게 유지한다: Pause = caution-amber, Resume = live-green, Kill = alert-red.
- **Do** 새 섹션 컨테이너는 `bg-panel border border-border rounded-lg` 패턴을 따른다.
- **Do** 타이포그래피는 JetBrains Mono 내에서 크기·굵기·색상으로만 위계를 만든다.
- **Do** 빈 상태는 ghost-gray 텍스트로 명시한다 ("보유 포지션 없음" 등). 빈 화면을 남기지 않는다.
- **Do** 실전(prod) 환경 표시는 alert-red로, 명시적 경고 문구와 함께 항상 노출한다.
- **Do** Kill 버튼은 시각적·구조적으로 다른 제어 버튼과 분리한다 (`ml-auto` 또는 별도 영역).

### Don't:

- **Don't** Trading212, Robinhood 등 소비자 투자 앱의 밝은 배경, 게임화 그래픽, 원형 진척 그래프, 응원하는 일러스트를 도입한다.
- **Don't** 일반 SaaS 어드민 템플릿의 사이드바 + 동일 크기 카드 그리드 레이아웃을 모방한다.
- **Don't** `box-shadow`를 사용한다. 깊이는 배경 틴트 차이로만 표현한다.
- **Don't** `border-left` 1px 초과 컬러 스트라이프를 카드나 항목 강조에 사용한다.
- **Don't** `background-clip: text` 그라데이션 텍스트를 사용한다.
- **Don't** JetBrains Mono 외의 폰트 패밀리를 도입한다. 다른 폰트가 필요하다고 느껴지면 굵기와 크기를 먼저 조정한다.
- **Don't** Signal Blue를 배경 장식, 그라데이션, 비인터랙티브 요소에 사용한다.
- **Don't** 색상만으로 positive/negative를 전달한다. 레이블이나 아이콘이 항상 동반해야 한다.
- **Don't** Bloomberg 터미널의 정보 과밀을 복제한다. 밀도는 참고하되, 가독성 임계점은 지킨다.
