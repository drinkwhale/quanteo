"""TR_ID 매핑 테이블 단위 테스트."""

import pytest

from core.adapters.kis.tr_ids import (
    get_rest_domain,
    get_tr_ids,
    get_ws_domain,
)
from core.config.settings import Env, Market


class TestGetTrIds:
    def test_domestic_prod_buy_differs_from_vps(self) -> None:
        prod = get_tr_ids(Env.PROD, Market.DOMESTIC)
        vps = get_tr_ids(Env.VPS, Market.DOMESTIC)
        assert prod.buy != vps.buy

    def test_domestic_prod_sell_differs_from_vps(self) -> None:
        prod = get_tr_ids(Env.PROD, Market.DOMESTIC)
        vps = get_tr_ids(Env.VPS, Market.DOMESTIC)
        assert prod.sell != vps.sell

    def test_domestic_balance_differs_by_env(self) -> None:
        prod = get_tr_ids(Env.PROD, Market.DOMESTIC)
        vps = get_tr_ids(Env.VPS, Market.DOMESTIC)
        assert prod.balance != vps.balance

    def test_vps_tr_ids_start_with_v(self) -> None:
        vps = get_tr_ids(Env.VPS, Market.DOMESTIC)
        assert vps.buy.startswith("V")
        assert vps.sell.startswith("V")
        assert vps.balance.startswith("V")

    def test_prod_tr_ids_start_with_t(self) -> None:
        prod = get_tr_ids(Env.PROD, Market.DOMESTIC)
        assert prod.buy.startswith("T")
        assert prod.sell.startswith("T")

    def test_domestic_has_ws_quote_and_fill(self) -> None:
        ids = get_tr_ids(Env.VPS, Market.DOMESTIC)
        assert ids.ws_quote is not None
        assert ids.ws_fill is not None

    def test_overseas_ws_quote_is_none(self) -> None:
        ids = get_tr_ids(Env.VPS, Market.OVERSEAS)
        assert ids.ws_quote is None

    def test_overseas_prod_buy_differs_from_vps(self) -> None:
        prod = get_tr_ids(Env.PROD, Market.OVERSEAS)
        vps = get_tr_ids(Env.VPS, Market.OVERSEAS)
        assert prod.buy != vps.buy

    def test_tr_id_set_is_frozen(self) -> None:
        ids = get_tr_ids(Env.VPS, Market.DOMESTIC)
        with pytest.raises(AttributeError):
            ids.buy = "MODIFIED"  # type: ignore[misc]


class TestDomains:
    def test_rest_domains_differ_by_env(self) -> None:
        prod = get_rest_domain(Env.PROD)
        vps = get_rest_domain(Env.VPS)
        assert prod != vps
        assert "9443" in prod
        assert "29443" in vps

    def test_ws_domains_differ_by_env(self) -> None:
        prod = get_ws_domain(Env.PROD)
        vps = get_ws_domain(Env.VPS)
        assert prod != vps
        assert "21000" in prod
        assert "31000" in vps

    def test_rest_domain_starts_with_https(self) -> None:
        assert get_rest_domain(Env.PROD).startswith("https://")
        assert get_rest_domain(Env.VPS).startswith("https://")

    def test_ws_domain_starts_with_ws(self) -> None:
        assert get_ws_domain(Env.PROD).startswith("ws://")
        assert get_ws_domain(Env.VPS).startswith("ws://")
