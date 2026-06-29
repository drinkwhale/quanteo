# Google Calendar 초기 설정 가이드

## 1. GCP 프로젝트 생성 & Calendar API 활성화

1. [Google Cloud Console](https://console.cloud.google.com) 접속
2. 새 프로젝트 생성 (예: `quanteo-calendar`)
3. **API 및 서비스 → 라이브러리** 에서 "Google Calendar API" 검색 후 활성화

## 2. OAuth2 자격증명 다운로드

1. **API 및 서비스 → 사용자 인증 정보** 이동
2. **사용자 인증 정보 만들기 → OAuth 클라이언트 ID** 선택
3. 애플리케이션 유형: **데스크톱 앱** 선택
4. 생성 후 `credentials.json` 다운로드
5. 저장 위치: `~/.quanteo/google/credentials.json`

```bash
mkdir -p ~/.quanteo/google
mv ~/Downloads/credentials.json ~/.quanteo/google/credentials.json
```

## 3. quanteo.yaml 설정

```yaml
info:
  enabled: true
  google_calendar:
    credentials_path: "~/.quanteo/google/credentials.json"
```

## 4. 최초 실행 — OAuth 동의 화면

최초 실행 시 `gcsa`가 브라우저를 열어 Google 계정 동의 화면을 표시합니다:

```bash
uv run quanteo --with-info
```

동의 후 토큰이 `~/.quanteo/google/token.json`에 자동 저장됩니다.

## 5. 이후 실행

캐시된 토큰을 자동으로 사용합니다. 토큰 만료(7일) 시 자동 갱신됩니다.

> **주의:** `credentials.json`과 `token.json`은 절대 커밋하지 마세요.
> `.gitignore`에 `~/.quanteo/` 경로는 저장소 밖이므로 자동으로 제외됩니다.
