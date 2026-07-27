"""LLM 근거 요약 생성 (Claude API).

Reporter(T105)가 이미 걸러낸 상위 N개(기본 10개) 종목에 대해서만
호출한다 — 비용 통제. ClaudeFilter(T058)와 동일한 2단 폴백 원칙: API
실패 시 정량 데이터만으로 대체 문구를 생성하고 무음 누락하지 않는다.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import httpx
import pandas as pd

if TYPE_CHECKING:
    from core.strategy.plugins.bbc_buy import BbcBuySignal
    from screener.data.collectors.dart_client import Disclosure

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """너는 한국 주식시장 정량 스크리닝 결과를 요약하는 애널리스트야.
아래 정량 데이터와 최근 공시를 바탕으로 사실 요약만 생성해줘.

**절대 금지: 매수/매도 판단, 투자 권유, "사세요"/"파세요"/"매수 추천" 등의 표현.**
너는 데이터를 요약할 뿐, 투자 결정을 내리지 않는다.

JSON으로만 응답 (다른 텍스트 없이):
{"one_line_thesis": "한 줄 요약(사실 기반)", "protips": ["근거 1", "근거 2"], "risk_flags": ["리스크 요인 1"]}"""

# 후처리 차단 키워드 — 시스템 프롬프트로 막았어도 재검증 (단순 부분 문자열 매칭)
_FORBIDDEN_PHRASES: tuple[str, ...] = (
    "매수 추천",
    "매도 추천",
    "사세요",
    "파세요",
    "지금 사",
    "지금 팔",
    "투자 권유",
    "적극 매수",
    "적극 매도",
    "매수하세요",
    "매도하세요",
)

_FALLBACK_THESIS = "정량 지표 기준 상위 랭크"

# 배치 폴링 설정 — report_top_n(기본 10)건 배치 처리 시간은 Anthropic 큐 상태에 따라
# 달라질 수 있어 20분 상한을 넉넉히 잡는다.
_BATCH_POLL_INTERVAL_SECONDS = 10.0
_BATCH_MAX_WAIT_SECONDS = 1200.0  # 20분
# 배치가 이미 완료(ended)된 뒤 결과 조회 자체가 일시적으로 실패하는 경우를 위한 재시도.
# 여기서 실패하면 이미 완료·과금된 배치 전체가 헛되이 폴백되므로 최소한의 재시도를 둔다.
_RESULTS_FETCH_MAX_RETRIES = 3
_RESULTS_FETCH_RETRY_DELAY_SECONDS = 2.0


@dataclass(frozen=True)
class RankedStock:
    """Ranker/Reporter가 넘기는 상위 종목 1건 — 프롬프트 입력."""

    ticker: str
    name: str
    rank: int
    weighted_score: float
    score_breakdown: dict[str, int] = field(default_factory=dict)
    per: float | None = None
    pbr: float | None = None
    foreign_institution_streak: int = 0
    volume_surge_ratio: float | None = None

    @classmethod
    def from_row(cls, row: pd.Series) -> RankedStock:
        def _get_float(key: str) -> float | None:
            val = row.get(key)
            return float(val) if val is not None and not pd.isna(val) else None

        return cls(
            ticker=str(row.get("ticker", "")),
            name=str(row.get("name", "")),
            rank=int(row.get("rank", 0)),
            weighted_score=float(row.get("weighted_score", 0.0)),
            score_breakdown={
                axis: int(row[axis])
                for axis in ("growth", "profitability", "cashflow", "stability", "valuation")
                if axis in row and not pd.isna(row[axis])
            },
            per=_get_float("per"),
            pbr=_get_float("pbr"),
            foreign_institution_streak=int(row.get("foreign_institution_streak") or 0),
            volume_surge_ratio=_get_float("volume_surge_ratio"),
        )


@dataclass(frozen=True)
class StockSummary:
    """스펙 6절 JSON 스키마.

    bbc_principle/bbc_reason은 LLM 출력이 아니라 screener.pipeline.bbc_timing의
    결정론적 판정 결과다 — Claude API 실패 시 폴백 경로에서도 그대로 유지된다.
    """

    ticker: str
    name: str
    one_line_thesis: str
    protips: list[str]
    risk_flags: list[str]
    score_breakdown: dict[str, int]
    bbc_principle: int | None = None
    bbc_reason: str | None = None


class AnalystAgent:
    """Claude API 기반 종목 요약 생성기."""

    def __init__(
        self, api_key: str, model: str = "claude-sonnet-4-6", max_tokens: int = 400
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._max_tokens = max_tokens

    async def summarize(
        self,
        stock: RankedStock,
        disclosures: list[Disclosure],
        bbc_signal: BbcBuySignal | None = None,
    ) -> StockSummary:
        try:
            thesis, protips, risk_flags = await self._call_claude(stock, disclosures, bbc_signal)
        except Exception as exc:
            logger.error("Claude 요약 생성 실패(%s): %s — 정량 폴백", stock.ticker, exc)
            return self._fallback_summary(stock, bbc_signal)

        thesis, protips, risk_flags = self._enforce_no_advice(thesis, protips, risk_flags)
        return StockSummary(
            ticker=stock.ticker,
            name=stock.name,
            one_line_thesis=thesis,
            protips=protips,
            risk_flags=risk_flags,
            score_breakdown=stock.score_breakdown,
            bbc_principle=bbc_signal.principle if bbc_signal else None,
            bbc_reason=bbc_signal.reason if bbc_signal else None,
        )

    async def summarize_batch(
        self,
        items: list[tuple[RankedStock, list[Disclosure], BbcBuySignal | None]],
    ) -> dict[str, StockSummary]:
        """상위 N개 종목을 Claude Batches API로 한 번에 요약한다 (실시간 대비 50% 할인).

        DailyJob은 하루 1회, 지연 시간에 민감하지 않은 배치 작업이므로 실시간
        엔드포인트 대신 Batches API를 사용해 동일 품질을 절반 비용에 얻는다.
        배치 생성/폴링 자체가 실패하면 전체를, 개별 항목만 실패하면 해당
        종목만 summarize()와 동일한 정량 폴백으로 대체한다 — 무음 누락하지 않는다.
        """
        if not items:
            return {}

        try:
            texts = await self._run_batch(items)
        except Exception as exc:
            logger.error(
                "Claude Batches API 실패, 전체 정량 폴백(%d건): %s",
                len(items),
                exc,
                exc_info=True,
            )
            return {
                stock.ticker: self._fallback_summary(stock, bbc_signal)
                for stock, _, bbc_signal in items
            }

        summaries: dict[str, StockSummary] = {}
        for stock, _, bbc_signal in items:
            raw = texts.get(stock.ticker)
            if raw is None:
                logger.error("Claude 배치 결과 누락(%s) — 정량 폴백", stock.ticker)
                summaries[stock.ticker] = self._fallback_summary(stock, bbc_signal)
                continue
            try:
                thesis, protips, risk_flags = self._parse_response(raw)
                thesis, protips, risk_flags = self._enforce_no_advice(thesis, protips, risk_flags)
                summaries[stock.ticker] = StockSummary(
                    ticker=stock.ticker,
                    name=stock.name,
                    one_line_thesis=thesis,
                    protips=protips,
                    risk_flags=risk_flags,
                    score_breakdown=stock.score_breakdown,
                    bbc_principle=bbc_signal.principle if bbc_signal else None,
                    bbc_reason=bbc_signal.reason if bbc_signal else None,
                )
            except Exception as exc:
                logger.error(
                    "Claude 배치 응답 파싱 실패(%s): %s — 정량 폴백",
                    stock.ticker,
                    exc,
                    exc_info=True,
                )
                summaries[stock.ticker] = self._fallback_summary(stock, bbc_signal)

        return summaries

    async def _run_batch(
        self,
        items: list[tuple[RankedStock, list[Disclosure], BbcBuySignal | None]],
    ) -> dict[str, str]:
        """배치를 생성·폴링하고 custom_id(ticker) → 원문 응답 텍스트 매핑을 반환한다.

        배치 생성 자체가 실패하면 예외를 그대로 전파해 전체 폴백을 유도한다.
        생성 이후 단계(상태 폴링, 결과 조회, 개별 라인 파싱)에서의 일시적 오류는
        여기서 흡수한다 — 폴링 도중 한 번의 네트워크 오류로 이미 완료된(또는
        완료 예정인) 배치 전체를 헛되이 폴백시키지 않기 위함이다.
        """
        requests = [
            {
                "custom_id": stock.ticker,
                "params": {
                    "model": self._model,
                    "max_tokens": self._max_tokens,
                    "system": _SYSTEM_PROMPT,
                    "messages": [
                        {
                            "role": "user",
                            "content": self._build_prompt(stock, disclosures, bbc_signal),
                        }
                    ],
                },
            }
            for stock, disclosures, bbc_signal in items
        ]

        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            create_resp = await client.post(
                "https://api.anthropic.com/v1/messages/batches",
                headers=headers,
                json={"requests": requests},
            )
            create_resp.raise_for_status()
            batch_id = create_resp.json()["id"]

            elapsed = 0.0
            while elapsed < _BATCH_MAX_WAIT_SECONDS:
                try:
                    status_resp = await client.get(
                        f"https://api.anthropic.com/v1/messages/batches/{batch_id}",
                        headers=headers,
                    )
                    status_resp.raise_for_status()
                    if status_resp.json()["processing_status"] == "ended":
                        break
                except httpx.HTTPError as exc:
                    # 상태 조회 자체의 일시적 실패(타임아웃/5xx 등)는 배치가 아직
                    # 끝나지 않은 것으로 간주하고 계속 폴링한다 — 여기서 즉시
                    # 실패시키면 이미 완료됐을 수도 있는 배치 전체가 헛되이 폴백된다.
                    logger.warning(
                        "Claude 배치(%s) 상태 조회 일시 실패, 계속 폴링: %s", batch_id, exc
                    )
                await asyncio.sleep(_BATCH_POLL_INTERVAL_SECONDS)
                elapsed += _BATCH_POLL_INTERVAL_SECONDS
            else:
                raise TimeoutError(
                    f"Claude 배치({batch_id})가 {_BATCH_MAX_WAIT_SECONDS:.0f}초 내에 "
                    "완료되지 않았습니다"
                )

            results_resp = None
            last_exc: httpx.HTTPError | None = None
            for attempt in range(_RESULTS_FETCH_MAX_RETRIES):
                try:
                    results_resp = await client.get(
                        f"https://api.anthropic.com/v1/messages/batches/{batch_id}/results",
                        headers=headers,
                    )
                    results_resp.raise_for_status()
                    break
                except httpx.HTTPError as exc:
                    last_exc = exc
                    logger.warning(
                        "Claude 배치(%s) 결과 조회 실패(%d/%d), 재시도: %s",
                        batch_id,
                        attempt + 1,
                        _RESULTS_FETCH_MAX_RETRIES,
                        exc,
                    )
                    if attempt < _RESULTS_FETCH_MAX_RETRIES - 1:
                        await asyncio.sleep(_RESULTS_FETCH_RETRY_DELAY_SECONDS)
            else:
                raise RuntimeError(
                    f"Claude 배치({batch_id}) 결과 조회가 {_RESULTS_FETCH_MAX_RETRIES}회 "
                    "재시도 후에도 실패했습니다"
                ) from last_exc

        texts: dict[str, str] = {}
        for line in results_resp.text.splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                result = entry.get("result", {})
                if result.get("type") != "succeeded":
                    logger.warning(
                        "Claude 배치(%s) 항목 실패(%s): %s",
                        batch_id,
                        entry.get("custom_id"),
                        result.get("type"),
                    )
                    continue
                texts[entry["custom_id"]] = result["message"]["content"][0]["text"].strip()
            except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
                # 한 줄만 깨져도 나머지 결과가 이미 존재한다 — 해당 줄만
                # 건너뛰고, 대응하는 종목은 이후 정량 폴백으로 처리된다.
                logger.warning(
                    "Claude 배치(%s) 결과 라인 파싱 실패, 해당 줄 건너뜀: %s", batch_id, exc
                )

        return texts

    def _fallback_summary(
        self, stock: RankedStock, bbc_signal: BbcBuySignal | None = None
    ) -> StockSummary:
        return StockSummary(
            ticker=stock.ticker,
            name=stock.name,
            one_line_thesis=_FALLBACK_THESIS,
            protips=[],
            risk_flags=["[DEGRADED MODE] Claude API 장애 — 정량 데이터만 제공"],
            score_breakdown=stock.score_breakdown,
            bbc_principle=bbc_signal.principle if bbc_signal else None,
            bbc_reason=bbc_signal.reason if bbc_signal else None,
        )

    async def _call_claude(
        self,
        stock: RankedStock,
        disclosures: list[Disclosure],
        bbc_signal: BbcBuySignal | None = None,
    ) -> tuple[str, list[str], list[str]]:
        user_msg = self._build_prompt(stock, disclosures, bbc_signal)

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self._model,
                    "max_tokens": self._max_tokens,
                    "system": _SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": user_msg}],
                },
            )
            resp.raise_for_status()
            data = resp.json()

        raw_text = data["content"][0]["text"].strip()
        if data.get("stop_reason") == "max_tokens":
            # JSON이 닫히기 전에 잘렸을 가능성이 높다 — 파싱 실패 메시지만 보면
            # 원인을 알기 어려우므로 여기서 먼저 명확히 표시한다.
            raise ValueError(
                f"Claude 응답이 max_tokens({self._max_tokens})에서 잘렸습니다 — "
                f"screener/config/settings.yaml의 llm.max_tokens_per_stock 상향 검토 필요"
            )
        return self._parse_response(raw_text)

    def _build_prompt(
        self,
        stock: RankedStock,
        disclosures: list[Disclosure],
        bbc_signal: BbcBuySignal | None = None,
    ) -> str:
        lines = [
            f"종목: {stock.name} ({stock.ticker})",
            f"종합 스코어: {stock.weighted_score:.1f}/5 (순위 {stock.rank})",
            f"항목별 스코어: {stock.score_breakdown}",
        ]
        if stock.per is not None:
            pbr_part = f", PBR {stock.pbr:.1f}" if stock.pbr is not None else ""
            lines.append(f"PER {stock.per:.1f}{pbr_part}")
        if stock.foreign_institution_streak:
            lines.append(f"외인+기관 {stock.foreign_institution_streak}일 연속 순매수")
        if stock.volume_surge_ratio is not None:
            lines.append(f"거래량 급증 배수: {stock.volume_surge_ratio:.1f}배")
        if bbc_signal is not None:
            lines.append(
                f"박병창 매수 원칙 판정: 제{bbc_signal.principle}원칙 해당 — {bbc_signal.reason}"
            )
        else:
            lines.append("박병창 매수 원칙 판정: 현재 해당하는 원칙 없음")
        if disclosures:
            lines.append("최근 공시:")
            for d in disclosures[:5]:
                lines.append(f"- {d.title} ({d.report_type})")
        return "\n".join(lines)

    def _parse_response(self, raw: str) -> tuple[str, list[str], list[str]]:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError(f"JSON을 파싱할 수 없습니다: {raw!r}")

        obj = json.loads(raw[start:end])

        thesis = obj.get("one_line_thesis", "")
        if not thesis:
            raise ValueError("one_line_thesis 필드가 비어 있습니다")

        protips = obj.get("protips", [])
        if not isinstance(protips, list):
            protips = []

        risk_flags = obj.get("risk_flags", [])
        if not isinstance(risk_flags, list):
            risk_flags = []

        return thesis, protips, risk_flags

    def _enforce_no_advice(
        self, thesis: str, protips: list[str], risk_flags: list[str]
    ) -> tuple[str, list[str], list[str]]:
        """매수/매도 권유 표현 감지 시 해당 문장을 제거하고 risk_flags에 표시한다."""
        triggered = False

        if any(phrase in thesis for phrase in _FORBIDDEN_PHRASES):
            logger.warning("AnalystAgent: thesis에서 금지 표현 감지 — 대체: %r", thesis)
            thesis = _FALLBACK_THESIS
            triggered = True

        clean_protips = []
        for tip in protips:
            if any(phrase in tip for phrase in _FORBIDDEN_PHRASES):
                logger.warning("AnalystAgent: protip에서 금지 표현 감지 — 제거: %r", tip)
                triggered = True
                continue
            clean_protips.append(tip)

        if triggered:
            risk_flags = [
                *risk_flags,
                "[REVIEW REQUIRED] 매수/매도 권유 표현이 감지되어 일부 문장이 제거되었습니다",
            ]

        return thesis, clean_protips, risk_flags
