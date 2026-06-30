"""
Claude Haiku AI 중요도 필터.

뉴스 제목·본문을 받아 SK하이닉스 주가 영향도를 HIGH/MEDIUM/LOW로 분류한다.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Literal

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 사전 필터 키워드 (Claude 호출 전 LOW 제거 → API 비용 절감)
# ---------------------------------------------------------------------------

CRITICAL_KEYWORDS: list[str] = [
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

_SYSTEM_PROMPT = """너는 한국 주식시장 전문 트레이더야.
다음 뉴스가 SK하이닉스(000660) 단기 주가에
중요한 영향을 줄지 판단해줘.

중요도 기준:
- HIGH: FOMC 결정, 미중 반도체 규제, NVDA/MU/TSM 실적,
        SK하이닉스 직접 공시, 금리 서프라이즈, 환율 급변(±1%↑)
- MEDIUM: 메모리 업황, 반도체 수출입 통계, AMD/AVGO 실적,
          환율 중간 변동(±0.5~1%), 중국 PMI
- LOW: 일반 경제지표, 무관한 기업뉴스

JSON으로만 응답:
{"score": "HIGH/MEDIUM/LOW", "reason": "이유 한줄", "action": "매수검토/매도검토/관망"}"""


# ---------------------------------------------------------------------------
# 결과 타입
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FilterResult:
    """Claude 필터 분류 결과."""

    score: Literal["HIGH", "MEDIUM", "LOW"]
    reason: str
    action: Literal["매수검토", "매도검토", "관망"]


# ---------------------------------------------------------------------------
# 필터 구현
# ---------------------------------------------------------------------------


class ClaudeFilter:
    """Claude Haiku 기반 뉴스 중요도 분류기."""

    MODEL = "claude-haiku-4-5-20251001"

    def __init__(self, api_key: str, notifier=None) -> None:
        self._api_key = api_key
        self._notifier = notifier  # 2단 폴백 시 운영자 긴급 알람용

    def _keyword_score(self, text: str) -> FilterResult:
        """CRITICAL_KEYWORDS 매칭 수 기반 1단 폴백."""
        count = sum(1 for kw in CRITICAL_KEYWORDS if kw.lower() in text.lower())
        if count >= 2:
            return FilterResult(
                score="MEDIUM",
                reason=f"[DEGRADED MODE] 키워드 {count}개 매칭 (Claude API 장애)",
                action="관망",
            )
        return FilterResult(
            score="LOW",
            reason="[DEGRADED MODE] 키워드 매칭 미달 (Claude API 장애)",
            action="관망",
        )

    def _passes_keyword_prefilter(self, title: str, body: str) -> bool:
        """CRITICAL_KEYWORDS 사전 필터 — 하나도 없으면 LOW 처리, Claude 미호출."""
        text = f"{title} {body}".lower()
        return any(kw.lower() in text for kw in CRITICAL_KEYWORDS)

    async def classify(self, title: str, body: str) -> FilterResult:
        """뉴스를 HIGH/MEDIUM/LOW로 분류한다.

        Claude API 실패 시 1단 폴백(키워드 매칭),
        키워드 리스트 비정상 시 2단 폴백(운영자 알람 + LOW 반환).
        """
        # 2단 폴백: 키워드 리스트 자체가 비어 있는 경우
        if not CRITICAL_KEYWORDS:
            logger.error("CRITICAL_KEYWORDS 리스트가 비어 있습니다. 2단 폴백 진행.")
            await self._send_operator_alert("CRITICAL_KEYWORDS 리스트 비어 있음 — 점검 필요")
            return FilterResult(
                score="LOW",
                reason="[DEGRADED MODE] CRITICAL_KEYWORDS 비어 있음 — 운영자 알람 발송",
                action="관망",
            )

        # 사전 필터: 키워드 없으면 Claude 호출 생략
        if not self._passes_keyword_prefilter(title, body):
            return FilterResult(score="LOW", reason="키워드 미해당", action="관망")

        try:
            return await self._call_claude(title, body)
        except Exception as exc:
            logger.error("Claude API 호출 실패, 1단 폴백 진행: %s", exc)
            text = f"{title} {body}"
            return self._keyword_score(text)

    async def _call_claude(self, title: str, body: str) -> FilterResult:
        """Anthropic API 직접 호출."""
        user_msg = f"제목: {title}\n내용: {body[:500]}"

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.MODEL,
                    "max_tokens": 150,
                    "system": _SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": user_msg}],
                },
            )
            resp.raise_for_status()
            data = resp.json()

        raw_text = data["content"][0]["text"].strip()
        return self._parse_response(raw_text)

    def _parse_response(self, raw: str) -> FilterResult:
        """JSON 응답을 FilterResult로 변환한다."""
        # JSON 블록 추출
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError(f"JSON을 파싱할 수 없습니다: {raw!r}")

        obj = json.loads(raw[start:end])

        score = obj.get("score", "")
        if score not in ("HIGH", "MEDIUM", "LOW"):
            raise ValueError(f"score 필드 유효하지 않음: {score!r}")

        reason = obj.get("reason", "")
        if not reason:
            raise ValueError("reason 필드 비어 있음")

        action = obj.get("action", "관망")
        if action not in ("매수검토", "매도검토", "관망"):
            action = "관망"

        return FilterResult(score=score, reason=reason, action=action)  # type: ignore[arg-type]

    async def _send_operator_alert(self, message: str) -> None:
        """운영자 긴급 알람 (Notifier 주입된 경우)."""
        if self._notifier is None:
            return
        try:
            from core.notifier.base import NotifyEvent, NotifyLevel

            await self._notifier.send(
                NotifyEvent(
                    level=NotifyLevel.CRITICAL,
                    title="[ClaudeFilter] 긴급 장애",
                    body=message,
                    source="ClaudeFilter",
                )
            )
        except Exception as e:
            logger.error("운영자 알람 발송 실패: %s", e)
