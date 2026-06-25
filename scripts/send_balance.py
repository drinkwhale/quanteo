"""
모의투자 계좌 잔고를 Telegram으로 전송하는 스크립트.

사용법:
    uv run scripts/send_balance.py
    uv run scripts/send_balance.py --env prod   # 실전 계좌
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime

from core.adapters.kis.auth import KisAuth
from core.adapters.kis.rest import KisRestClient
from core.config.settings import Env, Market, load_settings
from core.notifier.base import NotifyEvent, NotifyLevel
from core.notifier.telegram import TelegramNotifier

logging.basicConfig(level=logging.WARNING)


def _format_balance_message(client: KisRestClient, balance, env: Env) -> NotifyEvent:
    env_label = "모의투자" if env == Env.VPS else "실전투자"
    market_label = "국내" if client.market == Market.DOMESTIC else "해외"

    lines = [f"💰 <b>{env_label} {market_label} 잔고 조회</b>", ""]

    if balance.items:
        lines.append("📋 <b>보유 종목</b>")
        for item in balance.items:
            pl_sign = "+" if item.profit_loss >= 0 else ""
            lines.append(
                f"  <b>{item.symbol_name}</b> ({item.symbol})\n"
                f"  {item.qty}주 | 평균 {item.avg_price:,.0f}원 | 현재 {item.current_price:,.0f}원\n"
                f"  평가 {item.eval_amount:,.0f}원 | 손익 {pl_sign}{item.profit_loss:,.0f}원 ({pl_sign}{item.profit_loss_rate:.2f}%)"
            )
        lines.append("")

    total_pl_sign = "+" if balance.total_profit_loss >= 0 else ""
    lines.append("📊 <b>계좌 요약</b>")
    lines.append(f"  예수금: {balance.deposit:,.0f}원")
    lines.append(f"  평가금액: {balance.total_eval_amount:,.0f}원")
    lines.append(f"  평가손익: {total_pl_sign}{balance.total_profit_loss:,.0f}원")

    body = "\n".join(lines[2:])  # title 이후부터 body
    return NotifyEvent(
        level=NotifyLevel.INFO,
        title=f"{env_label} {market_label} 잔고",
        body=body,
        source="send_balance",
        timestamp=datetime.now(),
    )


async def main(env: Env) -> None:
    settings = load_settings(env=env)

    if not settings.telegram.enabled:
        print("⚠️  Telegram이 비활성화되어 있습니다. kis_devlp.yaml에서 telegram.enabled: true 설정 후 재실행하세요.")
        return

    auth = KisAuth(env=env, credentials=settings.credentials)
    rest = KisRestClient(auth=auth, env=env, market=Market.DOMESTIC)

    print(f"잔고 조회 중... (환경: {'모의투자' if env == Env.VPS else '실전투자'})")
    balance = await rest.get_balance()

    notifier = TelegramNotifier(
        bot_token=settings.telegram.bot_token.get_secret_value(),
        chat_id=settings.telegram.chat_id,
        min_level=NotifyLevel[settings.telegram.level],
    )

    event = _format_balance_message(rest, balance, env)
    # 단발 전송: run() 루프 없이 직접 전송 후 세션 종료
    await notifier._send_message(event)
    await notifier._bot.session.close()

    print("✅ Telegram 전송 완료")
    _print_balance(balance, env)


def _print_balance(balance, env: Env) -> None:
    env_label = "모의투자" if env == Env.VPS else "실전투자"
    print(f"\n=== {env_label} 잔고 ===")
    print(f"예수금:   {balance.deposit:>15,.0f}원")
    print(f"평가금액: {balance.total_eval_amount:>15,.0f}원")
    pl_sign = "+" if balance.total_profit_loss >= 0 else ""
    print(f"평가손익: {pl_sign}{balance.total_profit_loss:>14,.0f}원")
    if balance.items:
        print("\n보유 종목:")
        for item in balance.items:
            pl_sign = "+" if item.profit_loss >= 0 else ""
            print(f"  {item.symbol_name}({item.symbol}) {item.qty}주 | {pl_sign}{item.profit_loss:,.0f}원 ({pl_sign}{item.profit_loss_rate:.2f}%)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="잔고를 Telegram으로 전송")
    parser.add_argument("--env", choices=["vps", "prod"], default="vps", help="투자 환경 (기본: vps=모의투자)")
    args = parser.parse_args()

    env = Env.VPS if args.env == "vps" else Env.PROD
    asyncio.run(main(env))
