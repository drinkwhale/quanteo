"""
환율-주가 상관 해석 룰 테이블.

스펙 2-5절 기준 — 상황별 해석과 대응을 반환한다.
"""

from __future__ import annotations


def interpret_fx(usdkrw_change_pct: float, dxy_change_pct: float) -> str:
    """USD/KRW 변동과 DXY 변동을 종합해 SK하이닉스 영향 한줄 평가를 반환한다."""
    usd_up = usdkrw_change_pct > 0  # 원화 약세
    dxy_up = dxy_change_pct > 0.3   # 달러 강세

    if usd_up and dxy_up:
        return "달러 강세 + 원화 약세 → 글로벌 리스크오프 가능성, 외국인 매도 주의"
    elif usd_up and not dxy_up:
        return "원화 약세 → SK하이닉스 달러 매출 원화 환산 이익 증가 (긍정)"
    elif not usd_up and dxy_up:
        return "달러 강세 + 원화 강세 → 수출 이익 감소 가능성 (부정)"
    else:
        return "원화 강세 → 수출 이익 감소 (부정)"


def interpret_jpy(jpykrw_change_pct: float) -> str:
    """JPY/KRW 변동 해석."""
    if jpykrw_change_pct < -1.0:
        return "엔화 급약세 → 일본 메모리 경쟁사 가격경쟁력 저하 (긍정)"
    elif jpykrw_change_pct > 1.0:
        return "엔화 강세 → 일본 경쟁사 가격경쟁력 상승 (주의)"
    return "엔화 안정"
