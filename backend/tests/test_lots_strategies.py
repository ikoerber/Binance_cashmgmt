"""
Unit Tests fuer Alternative Sell Allocation Strategien (LIFO, HIGHEST_COST)

Testet allocate_sell_with_strategy(), _sort_lots_by_strategy(),
und Overflow-Strategie in allocate_sell_to_lot().
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal

from app.domain.models import (
    EventType,
    EventSource,
    LedgerEvent,
    TradeSide,
    LotStatus,
    TradeLot,
    AllocationStrategy,
)
from app.domain.lots import (
    allocate_sell_with_strategy,
    allocate_sell_fifo,
    allocate_sell_to_lot,
    _sort_lots_by_strategy,
)

# ============================================================
# Helpers
# ============================================================


def _make_buy_lot(lot_id, created_at, qty, price):
    """Erstellt ein TradeLot mit gegebenen Parametern."""
    return TradeLot(
        id=lot_id,
        created_from_fill_id=f"fill_{lot_id}",
        created_at=created_at,
        qty_base_initial=qty,
        qty_base_open=qty,
        cost_quote=qty * price,
        status=LotStatus.OPEN,
    )


def _make_sell_event(sell_id, amount, price, timestamp=None):
    """Erstellt ein Sell LedgerEvent."""
    return LedgerEvent(
        id=sell_id,
        type=EventType.TRADE_FILL,
        timestamp=timestamp or datetime(2024, 6, 1, 12, 0),
        asset="BTC",
        amount=amount,
        symbol="BTCEUR",
        price=price,
        side=TradeSide.SELL,
        source=EventSource.BINANCE,
    )


# 3 Lots: unterschiedliche Preise und Zeitstempel
BASE_TIME = datetime(2024, 1, 1, 12, 0)

LOT_OLD_CHEAP = _make_buy_lot("lot_A", BASE_TIME, Decimal("0.01"), Decimal("40000"))
# Break-even: 40000, aeltestes

LOT_MID_EXPENSIVE = _make_buy_lot(
    "lot_B", BASE_TIME + timedelta(days=30), Decimal("0.01"), Decimal("60000")
)
# Break-even: 60000, mittleres Alter

LOT_NEW_MID = _make_buy_lot(
    "lot_C", BASE_TIME + timedelta(days=60), Decimal("0.01"), Decimal("50000")
)
# Break-even: 50000, neuestes


# ============================================================
# _sort_lots_by_strategy Tests
# ============================================================


def test_sort_fifo():
    """FIFO: Sortiert nach created_at aufsteigend (aelteste zuerst)."""
    lots = [LOT_NEW_MID, LOT_OLD_CHEAP, LOT_MID_EXPENSIVE]
    sorted_lots = _sort_lots_by_strategy(lots, AllocationStrategy.FIFO)
    assert [l.id for l in sorted_lots] == ["lot_A", "lot_B", "lot_C"]


def test_sort_lifo():
    """LIFO: Sortiert nach created_at absteigend (neueste zuerst)."""
    lots = [LOT_OLD_CHEAP, LOT_MID_EXPENSIVE, LOT_NEW_MID]
    sorted_lots = _sort_lots_by_strategy(lots, AllocationStrategy.LIFO)
    assert [l.id for l in sorted_lots] == ["lot_C", "lot_B", "lot_A"]


def test_sort_highest_cost():
    """HIGHEST_COST: Sortiert nach break_even absteigend (teuerste zuerst)."""
    lots = [LOT_OLD_CHEAP, LOT_NEW_MID, LOT_MID_EXPENSIVE]
    sorted_lots = _sort_lots_by_strategy(lots, AllocationStrategy.HIGHEST_COST)
    # 60000 > 50000 > 40000
    assert [l.id for l in sorted_lots] == ["lot_B", "lot_C", "lot_A"]


def test_sort_highest_cost_tie_breaking():
    """HIGHEST_COST: Bei gleichem Break-even wird nach created_at desc sortiert (neueste zuerst)."""
    lot_1 = _make_buy_lot("lot_1", BASE_TIME, Decimal("0.01"), Decimal("50000"))
    lot_2 = _make_buy_lot(
        "lot_2", BASE_TIME + timedelta(days=10), Decimal("0.01"), Decimal("50000")
    )
    lot_3 = _make_buy_lot(
        "lot_3", BASE_TIME + timedelta(days=20), Decimal("0.01"), Decimal("50000")
    )

    sorted_lots = _sort_lots_by_strategy(
        [lot_1, lot_3, lot_2], AllocationStrategy.HIGHEST_COST
    )
    # Gleicher Break-even → neueste zuerst
    assert [l.id for l in sorted_lots] == ["lot_3", "lot_2", "lot_1"]


def test_sort_unknown_strategy_raises():
    """Unbekannte Strategie wirft ValueError."""
    with pytest.raises(ValueError, match="Unknown allocation strategy"):
        _sort_lots_by_strategy([LOT_OLD_CHEAP], "UNKNOWN")


# ============================================================
# allocate_sell_with_strategy Tests
# ============================================================


def test_strategy_fifo_allocates_oldest_first():
    """FIFO: Verkauf schliesst aeltestes Lot zuerst."""
    lots = [LOT_OLD_CHEAP, LOT_MID_EXPENSIVE, LOT_NEW_MID]
    sell = _make_sell_event("sell_1", Decimal("0.01"), Decimal("55000"))

    updated, allocs = allocate_sell_with_strategy(sell, lots, AllocationStrategy.FIFO)

    assert len(allocs) == 1
    assert allocs[0].trade_lot_id == "lot_A"  # aeltestes
    # P&L: (55000 - 40000) * 0.01 = +150 EUR
    assert allocs[0].realized_pnl_quote == Decimal("150.00")


def test_strategy_lifo_allocates_newest_first():
    """LIFO: Verkauf schliesst neuestes Lot zuerst."""
    lots = [LOT_OLD_CHEAP, LOT_MID_EXPENSIVE, LOT_NEW_MID]
    sell = _make_sell_event("sell_1", Decimal("0.01"), Decimal("55000"))

    updated, allocs = allocate_sell_with_strategy(sell, lots, AllocationStrategy.LIFO)

    assert len(allocs) == 1
    assert allocs[0].trade_lot_id == "lot_C"  # neuestes
    # P&L: (55000 - 50000) * 0.01 = +50 EUR
    assert allocs[0].realized_pnl_quote == Decimal("50.00")


def test_strategy_highest_cost_allocates_most_expensive_first():
    """HIGHEST_COST: Verkauf schliesst teuerstes Lot zuerst."""
    lots = [LOT_OLD_CHEAP, LOT_MID_EXPENSIVE, LOT_NEW_MID]
    sell = _make_sell_event("sell_1", Decimal("0.01"), Decimal("55000"))

    updated, allocs = allocate_sell_with_strategy(
        sell, lots, AllocationStrategy.HIGHEST_COST
    )

    assert len(allocs) == 1
    assert allocs[0].trade_lot_id == "lot_B"  # teuerstes (60000)
    # P&L: (55000 - 60000) * 0.01 = -50 EUR (Verlust realisiert)
    assert allocs[0].realized_pnl_quote == Decimal("-50.00")


def test_fifo_vs_lifo_different_lots_closed():
    """FIFO und LIFO schliessen unterschiedliche Lots bei Teilverkauf."""
    lots = [LOT_OLD_CHEAP, LOT_MID_EXPENSIVE, LOT_NEW_MID]
    sell = _make_sell_event("sell_1", Decimal("0.015"), Decimal("55000"))

    _, fifo_allocs = allocate_sell_with_strategy(sell, lots, AllocationStrategy.FIFO)
    # Neu erstellen da Lots durch allocate_sell_with_strategy mutiert werden (dataclass replace)
    lots2 = [
        _make_buy_lot("lot_A", BASE_TIME, Decimal("0.01"), Decimal("40000")),
        _make_buy_lot(
            "lot_B", BASE_TIME + timedelta(days=30), Decimal("0.01"), Decimal("60000")
        ),
        _make_buy_lot(
            "lot_C", BASE_TIME + timedelta(days=60), Decimal("0.01"), Decimal("50000")
        ),
    ]
    _, lifo_allocs = allocate_sell_with_strategy(sell, lots2, AllocationStrategy.LIFO)

    fifo_lot_ids = [a.trade_lot_id for a in fifo_allocs]
    lifo_lot_ids = [a.trade_lot_id for a in lifo_allocs]

    # FIFO: A (voll 0.01) + B (teilweise 0.005)
    assert fifo_lot_ids == ["lot_A", "lot_B"]
    # LIFO: C (voll 0.01) + B (teilweise 0.005)
    assert lifo_lot_ids == ["lot_C", "lot_B"]


def test_all_strategies_same_total_pnl():
    """Alle Strategien produzieren die gleiche Gesamt-P&L bei vollstaendigem Verkauf."""
    sell = _make_sell_event("sell_1", Decimal("0.03"), Decimal("55000"))

    results = {}
    for strategy in AllocationStrategy:
        lots = [
            _make_buy_lot("lot_A", BASE_TIME, Decimal("0.01"), Decimal("40000")),
            _make_buy_lot(
                "lot_B",
                BASE_TIME + timedelta(days=30),
                Decimal("0.01"),
                Decimal("60000"),
            ),
            _make_buy_lot(
                "lot_C",
                BASE_TIME + timedelta(days=60),
                Decimal("0.01"),
                Decimal("50000"),
            ),
        ]
        _, allocs = allocate_sell_with_strategy(sell, lots, strategy)
        total_pnl = sum(a.realized_pnl_quote for a in allocs)
        results[strategy] = total_pnl

    # Alle Strategien: gleiche Gesamt-P&L
    pnls = list(results.values())
    assert all(pnl == pnls[0] for pnl in pnls)
    # Erwartete Gesamt-P&L: (55000 - 50000) * 0.03 = 150 EUR
    # (Durchschnittlicher Break-even: (400+600+500)/3 = 500 EUR * 100 = 50000)
    assert pnls[0] == Decimal("150.00")


def test_strategy_with_fee():
    """Strategie funktioniert korrekt mit EUR Fee."""
    lots = [
        _make_buy_lot("lot_A", BASE_TIME, Decimal("0.01"), Decimal("40000")),
        _make_buy_lot(
            "lot_B", BASE_TIME + timedelta(days=30), Decimal("0.01"), Decimal("60000")
        ),
    ]
    sell = LedgerEvent(
        id="sell_1",
        type=EventType.TRADE_FILL,
        timestamp=datetime(2024, 6, 1),
        asset="BTC",
        amount=Decimal("0.01"),
        symbol="BTCEUR",
        price=Decimal("55000"),
        side=TradeSide.SELL,
        source=EventSource.BINANCE,
        fee_asset="EUR",
        fee_amount=Decimal("5.50"),
    )

    # HIGHEST_COST: Lot B (60000) zuerst → realisierter Verlust
    _, allocs = allocate_sell_with_strategy(sell, lots, AllocationStrategy.HIGHEST_COST)
    assert allocs[0].trade_lot_id == "lot_B"
    # P&L: (55000 - 5.50/0.01 - 60000) * 0.01 = (55000 - 550 - 60000) * 0.01 = -55.50
    net_proceeds_per_base = Decimal("55000") - (Decimal("5.50") / Decimal("0.01"))
    expected_pnl = (net_proceeds_per_base - Decimal("60000")) * Decimal("0.01")
    assert allocs[0].realized_pnl_quote == expected_pnl


def test_strategy_single_lot():
    """Alle Strategien verhalten sich identisch bei einem einzelnen Lot."""
    sell = _make_sell_event("sell_1", Decimal("0.01"), Decimal("55000"))

    for strategy in AllocationStrategy:
        lot = _make_buy_lot("lot_A", BASE_TIME, Decimal("0.01"), Decimal("50000"))
        updated, allocs = allocate_sell_with_strategy(sell, [lot], strategy)

        assert len(allocs) == 1
        assert allocs[0].trade_lot_id == "lot_A"
        assert allocs[0].realized_pnl_quote == Decimal("50.00")
        # Lot muss CLOSED sein
        closed_lot = [l for l in updated if l.id == "lot_A"][0]
        assert closed_lot.status == LotStatus.CLOSED
        assert closed_lot.qty_base_open == Decimal("0")


def test_strategy_insufficient_lots_raises():
    """Nicht genug offene Lots wirft ValueError fuer alle Strategien."""
    lot = _make_buy_lot("lot_A", BASE_TIME, Decimal("0.005"), Decimal("50000"))
    sell = _make_sell_event("sell_1", Decimal("0.01"), Decimal("55000"))

    for strategy in AllocationStrategy:
        with pytest.raises(ValueError, match="Not enough open lots"):
            allocate_sell_with_strategy(sell, [lot], strategy)


# ============================================================
# allocate_sell_fifo Wrapper Tests (Rueckwaertskompatibilitaet)
# ============================================================


def test_fifo_wrapper_delegates_correctly():
    """allocate_sell_fifo() delegiert korrekt an allocate_sell_with_strategy(FIFO)."""
    lots = [LOT_NEW_MID, LOT_OLD_CHEAP, LOT_MID_EXPENSIVE]
    sell = _make_sell_event("sell_1", Decimal("0.01"), Decimal("55000"))

    # Frische Lots fuer beide Aufrufe
    lots1 = [
        _make_buy_lot(
            "lot_C", BASE_TIME + timedelta(days=60), Decimal("0.01"), Decimal("50000")
        ),
        _make_buy_lot("lot_A", BASE_TIME, Decimal("0.01"), Decimal("40000")),
        _make_buy_lot(
            "lot_B", BASE_TIME + timedelta(days=30), Decimal("0.01"), Decimal("60000")
        ),
    ]
    lots2 = [
        _make_buy_lot(
            "lot_C", BASE_TIME + timedelta(days=60), Decimal("0.01"), Decimal("50000")
        ),
        _make_buy_lot("lot_A", BASE_TIME, Decimal("0.01"), Decimal("40000")),
        _make_buy_lot(
            "lot_B", BASE_TIME + timedelta(days=30), Decimal("0.01"), Decimal("60000")
        ),
    ]

    _, allocs_wrapper = allocate_sell_fifo(sell, lots1)

    sell2 = _make_sell_event("sell_1", Decimal("0.01"), Decimal("55000"))
    _, allocs_direct = allocate_sell_with_strategy(
        sell2, lots2, AllocationStrategy.FIFO
    )

    assert [a.trade_lot_id for a in allocs_wrapper] == [
        a.trade_lot_id for a in allocs_direct
    ]
    assert [a.realized_pnl_quote for a in allocs_wrapper] == [
        a.realized_pnl_quote for a in allocs_direct
    ]


# ============================================================
# allocate_sell_to_lot Overflow-Strategie Tests
# ============================================================


def test_lot_specific_overflow_fifo():
    """Lot-spezifisch: Overflow geht via FIFO an restliche Lots."""
    target = _make_buy_lot(
        "lot_target", BASE_TIME + timedelta(days=60), Decimal("0.005"), Decimal("50000")
    )
    remaining = [
        _make_buy_lot("lot_old", BASE_TIME, Decimal("0.01"), Decimal("40000")),
        _make_buy_lot(
            "lot_new", BASE_TIME + timedelta(days=30), Decimal("0.01"), Decimal("60000")
        ),
    ]
    sell = _make_sell_event("sell_1", Decimal("0.01"), Decimal("55000"))

    updated, allocs = allocate_sell_to_lot(
        sell, target, remaining, overflow_strategy=AllocationStrategy.FIFO
    )

    assert len(allocs) == 2
    assert allocs[0].trade_lot_id == "lot_target"  # Ziel zuerst
    assert allocs[0].qty_allocated == Decimal("0.005")
    assert allocs[1].trade_lot_id == "lot_old"  # FIFO: aeltestes
    assert allocs[1].qty_allocated == Decimal("0.005")


def test_lot_specific_overflow_lifo():
    """Lot-spezifisch: Overflow geht via LIFO an restliche Lots."""
    target = _make_buy_lot(
        "lot_target", BASE_TIME + timedelta(days=60), Decimal("0.005"), Decimal("50000")
    )
    remaining = [
        _make_buy_lot("lot_old", BASE_TIME, Decimal("0.01"), Decimal("40000")),
        _make_buy_lot(
            "lot_new", BASE_TIME + timedelta(days=30), Decimal("0.01"), Decimal("60000")
        ),
    ]
    sell = _make_sell_event("sell_1", Decimal("0.01"), Decimal("55000"))

    updated, allocs = allocate_sell_to_lot(
        sell, target, remaining, overflow_strategy=AllocationStrategy.LIFO
    )

    assert len(allocs) == 2
    assert allocs[0].trade_lot_id == "lot_target"
    assert allocs[1].trade_lot_id == "lot_new"  # LIFO: neuestes


def test_lot_specific_overflow_highest_cost():
    """Lot-spezifisch: Overflow geht via HIGHEST_COST an restliche Lots."""
    target = _make_buy_lot(
        "lot_target", BASE_TIME + timedelta(days=60), Decimal("0.005"), Decimal("50000")
    )
    remaining = [
        _make_buy_lot("lot_cheap", BASE_TIME, Decimal("0.01"), Decimal("40000")),
        _make_buy_lot(
            "lot_expensive",
            BASE_TIME + timedelta(days=30),
            Decimal("0.01"),
            Decimal("60000"),
        ),
    ]
    sell = _make_sell_event("sell_1", Decimal("0.01"), Decimal("55000"))

    updated, allocs = allocate_sell_to_lot(
        sell, target, remaining, overflow_strategy=AllocationStrategy.HIGHEST_COST
    )

    assert len(allocs) == 2
    assert allocs[0].trade_lot_id == "lot_target"
    assert allocs[1].trade_lot_id == "lot_expensive"  # Hoechster Break-even


def test_lot_specific_no_overflow_ignores_strategy():
    """Lot-spezifisch: Ohne Overflow ist die Strategie irrelevant."""
    target = _make_buy_lot("lot_target", BASE_TIME, Decimal("0.01"), Decimal("50000"))
    remaining = [
        _make_buy_lot(
            "lot_other",
            BASE_TIME + timedelta(days=30),
            Decimal("0.01"),
            Decimal("60000"),
        ),
    ]
    sell = _make_sell_event("sell_1", Decimal("0.01"), Decimal("55000"))

    for strategy in AllocationStrategy:
        target_fresh = _make_buy_lot(
            "lot_target", BASE_TIME, Decimal("0.01"), Decimal("50000")
        )
        remaining_fresh = [
            _make_buy_lot(
                "lot_other",
                BASE_TIME + timedelta(days=30),
                Decimal("0.01"),
                Decimal("60000"),
            ),
        ]
        updated, allocs = allocate_sell_to_lot(
            sell, target_fresh, remaining_fresh, overflow_strategy=strategy
        )

        assert len(allocs) == 1
        assert allocs[0].trade_lot_id == "lot_target"
