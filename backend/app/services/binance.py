"""
Binance API Client

Holt Trades/Fills von Binance und konvertiert zu Ledger Events
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from binance.client import Client
from binance.exceptions import BinanceAPIException

logger = logging.getLogger(__name__)

from app.domain.models import LedgerEvent, EventType, EventSource, TradeSide
from app.symbol_registry import get_base_asset
from app.utils.retry import retry_on_transient_error


class BinanceService:
    """
    Binance API Integration

    Resilienz:
    - Rate Limiting wird von python-binance Library gehandelt
    - Exponential Backoff fuer 429/5xx via @retry_on_transient_error
    """

    def __init__(self, api_key: str, api_secret: str, testnet: bool = False):
        """
        Initialisiert Binance Client

        Args:
            api_key: Binance API Key
            api_secret: Binance API Secret
            testnet: True für Testnet, False für Production
        """
        if testnet:
            self.client = Client(api_key, api_secret, testnet=True)
        else:
            self.client = Client(api_key, api_secret)

    def fetch_trades(
        self,
        symbol: str = "BTCEUR",
        start_time: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[LedgerEvent]:
        """
        Holt Trades von Binance und konvertiert zu Ledger Events.

        Paginiert automatisch via fromId wenn >1000 Trades vorhanden.

        Args:
            symbol: Trading Pair (Default: BTCEUR)
            start_time: Optional - nur Trades nach diesem Zeitpunkt
            limit: Max Anzahl Trades pro API-Call (max 1000)

        Returns:
            Liste von LedgerEvents (chronologisch)

        Raises:
            BinanceAPIException: Bei API-Fehlern
        """
        all_events = []
        from_id = None

        while True:
            batch = self._fetch_trades_page(symbol, start_time, limit, from_id)
            if not batch:
                break

            all_events.extend(batch)

            # Wenn weniger als limit zurueckgegeben, sind wir fertig
            if len(batch) < limit:
                break

            # Naechste Seite: fromId = letzter Trade-ID + 1
            last_source_id = batch[-1].source_id
            from_id = int(last_source_id) + 1

        return all_events

    @retry_on_transient_error()
    def _fetch_trades_page(
        self,
        symbol: str,
        start_time: Optional[datetime],
        limit: int,
        from_id: Optional[int] = None,
    ) -> List[LedgerEvent]:
        """Einzelne Seite von Trades holen (retryable)."""
        params = {"symbol": symbol, "limit": limit}
        if from_id is not None:
            params["fromId"] = from_id
        elif start_time:
            params["startTime"] = int(start_time.timestamp() * 1000)

        trades = self.client.get_my_trades(**params)

        events = []
        for trade in trades:
            event = self._trade_to_ledger_event(trade, symbol)
            events.append(event)

        return events

    @retry_on_transient_error()
    def get_current_price(self, symbol: str = "BTCEUR") -> Decimal:
        """
        Holt aktuellen Marktpreis

        Args:
            symbol: Trading Pair

        Returns:
            Aktueller Preis als Decimal
        """
        ticker = self.client.get_symbol_ticker(symbol=symbol)
        return Decimal(ticker["price"])

    @retry_on_transient_error()
    def get_historical_price(self, symbol: str, timestamp: datetime) -> Decimal:
        """
        Holt den historischen Preis fuer ein Symbol zum angegebenen Zeitpunkt.

        Verwendet die Binance Klines API mit 1-Minuten-Intervall.
        Gibt den Close-Preis der Minute zurueck, in der der Timestamp liegt.

        Args:
            symbol: Trading Pair (z.B. "BNBEUR")
            timestamp: Zeitpunkt fuer den historischen Preis

        Returns:
            Close-Preis als Decimal

        Raises:
            Exception: Wenn keine Kline-Daten verfuegbar
        """
        from app.services.binance_public_client import get_binance_public_client

        ts_ms = int(timestamp.timestamp() * 1000)
        client = get_binance_public_client()
        klines = client.get_klines(symbol, "1m", limit=1, start_time=ts_ms)

        if not klines:
            raise Exception(f"No kline data for {symbol} at {timestamp}")

        return Decimal(str(klines[0][4]))

    def _trade_to_ledger_event(self, trade: dict, symbol: str) -> LedgerEvent:
        """
        Konvertiert Binance Trade zu LedgerEvent

        Binance Trade Format:
        {
            'id': 123456,
            'orderId': 789012,
            'symbol': 'BTCEUR',
            'price': '50000.00',
            'qty': '0.01',
            'quoteQty': '500.00',
            'commission': '0.00001',
            'commissionAsset': 'BTC',
            'time': 1640000000000,
            'isBuyer': True,
            'isMaker': False,
            ...
        }

        Args:
            trade: Binance Trade Dict
            symbol: Trading Pair

        Returns:
            LedgerEvent
        """
        trade_id = str(trade["id"])
        price = Decimal(trade["price"])
        qty = Decimal(trade["qty"])
        commission = Decimal(trade["commission"])
        commission_asset = trade["commissionAsset"]
        # WICHTIG: Binance gibt UTC Timestamps - immer UTC verwenden!
        timestamp = datetime.fromtimestamp(
            trade["time"] / 1000, tz=timezone.utc
        ).replace(tzinfo=None)
        is_buyer = trade["isBuyer"]

        # Buy oder Sell?
        side = TradeSide.BUY if is_buyer else TradeSide.SELL

        # WICHTIG: qty von Binance ist BRUTTO (VOR Fee-Abzug)!
        # Wenn Fee in BTC: qty muss um fee_amount reduziert werden (Consumer-Logik)
        # Wenn Fee in EUR/BNB: qty ist die tatsächliche BTC-Menge (Fee betrifft EUR/BNB)

        # Asset bestimmen (Base-Asset des Trading Pairs)
        asset = get_base_asset(symbol)

        return LedgerEvent(
            id=f"binance_{symbol}_{trade_id}",
            type=EventType.TRADE_FILL,
            timestamp=timestamp,
            asset=asset,
            amount=qty,  # Bei BUY/SELL ist das die BTC-Menge
            symbol=symbol,
            price=price,
            side=side,
            fee_asset=commission_asset,
            fee_amount=commission if commission > 0 else None,
            source=EventSource.BINANCE,
            source_id=trade_id,
            raw_payload=trade,
        )

    @retry_on_transient_error()
    def fetch_account_balance(self) -> dict:
        """
        Holt aktuelle Wallet-Balances

        Returns:
            Dict mit Balances: {"BTC": Decimal("0.01"), "EUR": Decimal("1000.00")}
        """
        account = self.client.get_account()
        balances = {}

        for balance in account["balances"]:
            asset = balance["asset"]
            free = Decimal(balance["free"])
            locked = Decimal(balance["locked"])
            total = free + locked

            if total > 0:
                balances[asset] = {"free": free, "locked": locked, "total": total}

        return balances

    def fetch_deposit_history(
        self,
        coin: Optional[str] = None,
        start_time: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[LedgerEvent]:
        """
        Holt Deposit-Historie von Binance und konvertiert zu Ledger Events.

        Paginiert automatisch via offset wenn >limit Deposits vorhanden.

        Args:
            coin: Optional - Filter nach Coin (z.B. "EUR", "BTC")
            start_time: Optional - nur Deposits nach diesem Zeitpunkt
            limit: Max Anzahl Deposits pro API-Call (max 1000)

        Returns:
            Liste von LedgerEvents

        Raises:
            BinanceAPIException: Bei API-Fehlern
        """
        all_events = []
        offset = 0

        while True:
            batch = self._fetch_deposit_page(coin, start_time, limit, offset)
            all_events.extend(batch)

            if len(batch) < limit:
                break
            offset += limit

        return all_events

    @retry_on_transient_error()
    def _fetch_deposit_page(
        self,
        coin: Optional[str],
        start_time: Optional[datetime],
        limit: int,
        offset: int,
    ) -> List[LedgerEvent]:
        """Einzelne Seite von Deposits holen (retryable)."""
        params = {"limit": limit, "offset": offset}
        if coin:
            params["coin"] = coin
        if start_time:
            params["startTime"] = int(start_time.timestamp() * 1000)

        deposits = self.client.get_deposit_history(**params)

        events = []
        for deposit in deposits:
            if deposit["status"] != 1:  # 1 = Success
                continue
            event = self._deposit_to_ledger_event(deposit)
            events.append(event)

        return events

    def fetch_withdrawal_history(
        self,
        coin: Optional[str] = None,
        start_time: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[LedgerEvent]:
        """
        Holt Withdrawal-Historie von Binance und konvertiert zu Ledger Events.

        Paginiert automatisch via offset wenn >limit Withdrawals vorhanden.

        Args:
            coin: Optional - Filter nach Coin (z.B. "EUR", "BTC")
            start_time: Optional - nur Withdrawals nach diesem Zeitpunkt
            limit: Max Anzahl Withdrawals pro API-Call (max 1000)

        Returns:
            Liste von LedgerEvents

        Raises:
            BinanceAPIException: Bei API-Fehlern
        """
        all_events = []
        offset = 0

        while True:
            batch = self._fetch_withdrawal_page(coin, start_time, limit, offset)
            all_events.extend(batch)

            if len(batch) < limit:
                break
            offset += limit

        return all_events

    @retry_on_transient_error()
    def _fetch_withdrawal_page(
        self,
        coin: Optional[str],
        start_time: Optional[datetime],
        limit: int,
        offset: int,
    ) -> List[LedgerEvent]:
        """Einzelne Seite von Withdrawals holen (retryable)."""
        params = {"limit": limit, "offset": offset}
        if coin:
            params["coin"] = coin
        if start_time:
            params["startTime"] = int(start_time.timestamp() * 1000)

        withdrawals = self.client.get_withdraw_history(**params)

        events = []
        for withdrawal in withdrawals:
            if withdrawal["status"] != 6:  # 6 = Completed
                continue
            event = self._withdrawal_to_ledger_event(withdrawal)
            events.append(event)

        return events

    def _deposit_to_ledger_event(self, deposit: dict) -> LedgerEvent:
        """
        Konvertiert Binance Deposit zu LedgerEvent

        Binance Deposit Format:
        {
            'id': '123456',
            'amount': '100.0',
            'coin': 'EUR',
            'network': 'EUR',
            'status': 1,
            'insertTime': 1640000000000,
            'txId': 'internal',
            ...
        }

        Args:
            deposit: Binance Deposit Dict

        Returns:
            LedgerEvent (DEPOSIT für BTC, EXTERNAL_CASHFLOW für EUR)
        """
        deposit_id = deposit["id"]
        amount = Decimal(deposit["amount"])
        coin = deposit["coin"]
        # WICHTIG: Binance gibt UTC Timestamps - immer UTC verwenden!
        timestamp = datetime.fromtimestamp(
            deposit["insertTime"] / 1000, tz=timezone.utc
        ).replace(tzinfo=None)

        # EUR-Deposits sind EXTERNAL_CASHFLOW (Bank → Binance)
        # BTC-Deposits sind DEPOSIT (externe Wallet → Binance)
        event_type = EventType.EXTERNAL_CASHFLOW if coin == "EUR" else EventType.DEPOSIT

        return LedgerEvent(
            id=f"binance_deposit_{coin}_{deposit_id}",
            type=event_type,
            timestamp=timestamp,
            asset=coin,
            amount=amount,
            source=EventSource.BINANCE,
            source_id=deposit_id,
            note=f"{coin} deposit to Binance",
            raw_payload=deposit,
        )

    def _withdrawal_to_ledger_event(self, withdrawal: dict) -> LedgerEvent:
        """
        Konvertiert Binance Withdrawal zu LedgerEvent

        Binance Withdrawal Format:
        {
            'id': '123456',
            'amount': '50.0',
            'coin': 'EUR',
            'network': 'EUR',
            'status': 6,
            'applyTime': 1640000000000,
            'txFee': '0.5',
            ...
        }

        Args:
            withdrawal: Binance Withdrawal Dict

        Returns:
            LedgerEvent (WITHDRAWAL für BTC, EXTERNAL_CASHFLOW für EUR)
        """
        withdrawal_id = withdrawal["id"]
        # Amount ist bereits NETTO (nach Fees)
        amount = Decimal(withdrawal["amount"])
        coin = withdrawal["coin"]
        # WICHTIG: Binance gibt UTC Timestamps - immer UTC verwenden!
        timestamp = datetime.fromtimestamp(
            withdrawal["applyTime"] / 1000, tz=timezone.utc
        ).replace(tzinfo=None)

        # EUR-Withdrawals sind EXTERNAL_CASHFLOW (Binance → Bank)
        # BTC-Withdrawals sind WITHDRAWAL (Binance → externe Wallet)
        event_type = (
            EventType.EXTERNAL_CASHFLOW if coin == "EUR" else EventType.WITHDRAWAL
        )

        # Bei EXTERNAL_CASHFLOW: Negativ, weil Geld rausgeht
        if event_type == EventType.EXTERNAL_CASHFLOW:
            amount = -amount

        return LedgerEvent(
            id=f"binance_withdrawal_{coin}_{withdrawal_id}",
            type=event_type,
            timestamp=timestamp,
            asset=coin,
            amount=amount,
            source=EventSource.BINANCE,
            source_id=withdrawal_id,
            note=f"{coin} withdrawal from Binance",
            raw_payload=withdrawal,
        )

    # ===== FIAT (EUR SEPA) Endpunkte =====
    # Diese verwenden /sapi/v1/fiat/orders (separater Endpunkt für Fiat!)

    @retry_on_transient_error()
    def fetch_fiat_deposit_history(
        self,
        begin_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[LedgerEvent]:
        """
        Holt Fiat-Deposit-Historie (EUR SEPA-Überweisungen) von Binance

        WICHTIG: get_deposit_history() liefert nur Krypto-Deposits!
        Für EUR SEPA muss /sapi/v1/fiat/orders verwendet werden.

        Args:
            begin_time: Optional - nur Deposits nach diesem Zeitpunkt
            end_time: Optional - nur Deposits vor diesem Zeitpunkt

        Returns:
            Liste von LedgerEvents (typ: EXTERNAL_CASHFLOW)
        """
        all_deposits = []
        page = 1

        while True:
            params = {
                "transactionType": "0",  # 0 = Deposit
                "page": page,
                "rows": 500,  # Max pro Seite
            }
            if begin_time:
                params["beginTime"] = int(begin_time.timestamp() * 1000)
            if end_time:
                params["endTime"] = int(end_time.timestamp() * 1000)

            result = self.client.get_fiat_deposit_withdraw_history(**params)
            data = result.get("data", [])

            if not data:
                break

            for entry in data:
                if entry.get("status") == "Successful":
                    event = self._fiat_deposit_to_ledger_event(entry)
                    all_deposits.append(event)

            # Pagination: Wenn weniger als 500, sind wir fertig
            if len(data) < 500:
                break
            page += 1

        return all_deposits

    @retry_on_transient_error()
    def fetch_fiat_withdrawal_history(
        self,
        begin_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[LedgerEvent]:
        """
        Holt Fiat-Withdrawal-Historie (EUR SEPA-Auszahlungen) von Binance

        Args:
            begin_time: Optional - nur Withdrawals nach diesem Zeitpunkt
            end_time: Optional - nur Withdrawals vor diesem Zeitpunkt

        Returns:
            Liste von LedgerEvents (typ: EXTERNAL_CASHFLOW, negativ)
        """
        all_withdrawals = []
        page = 1

        while True:
            params = {
                "transactionType": "1",  # 1 = Withdrawal
                "page": page,
                "rows": 500,
            }
            if begin_time:
                params["beginTime"] = int(begin_time.timestamp() * 1000)
            if end_time:
                params["endTime"] = int(end_time.timestamp() * 1000)

            result = self.client.get_fiat_deposit_withdraw_history(**params)
            data = result.get("data", [])

            if not data:
                break

            for entry in data:
                if entry.get("status") == "Successful":
                    event = self._fiat_withdrawal_to_ledger_event(entry)
                    all_withdrawals.append(event)

            if len(data) < 500:
                break
            page += 1

        return all_withdrawals

    def _fiat_deposit_to_ledger_event(self, entry: dict) -> LedgerEvent:
        """
        Konvertiert Binance Fiat-Deposit zu LedgerEvent

        Fiat Deposit Format:
        {
            'orderNo': '25ced37075c...',
            'fiatCurrency': 'EUR',
            'indicatedAmount': '1000.00',
            'amount': '1000.00',
            'totalFee': '0.00',
            'method': 'BankTransfer',
            'status': 'Successful',
            'createTime': 1640000000000,
            'updateTime': 1640000100000
        }
        """
        order_no = entry["orderNo"]
        amount = Decimal(entry["amount"])
        fee = Decimal(entry.get("totalFee", "0"))
        currency = entry.get("fiatCurrency", "EUR")
        timestamp = datetime.fromtimestamp(
            entry["createTime"] / 1000, tz=timezone.utc
        ).replace(tzinfo=None)

        # Netto-Betrag (nach Fees)
        net_amount = amount - fee

        return LedgerEvent(
            id=f"binance_fiat_deposit_{order_no}",
            type=EventType.EXTERNAL_CASHFLOW,
            timestamp=timestamp,
            asset=currency,
            amount=net_amount,
            source=EventSource.BINANCE,
            source_id=order_no,
            fee_asset=currency if fee > 0 else None,
            fee_amount=fee if fee > 0 else None,
            note=f"{currency} SEPA deposit to Binance ({entry.get('method', 'unknown')})",
            raw_payload=entry,
        )

    def _fiat_withdrawal_to_ledger_event(self, entry: dict) -> LedgerEvent:
        """
        Konvertiert Binance Fiat-Withdrawal zu LedgerEvent

        Fiat Withdrawal Format: gleich wie Deposit, aber transactionType=1
        """
        order_no = entry["orderNo"]
        amount = Decimal(entry["amount"])
        fee = Decimal(entry.get("totalFee", "0"))
        currency = entry.get("fiatCurrency", "EUR")
        timestamp = datetime.fromtimestamp(
            entry["createTime"] / 1000, tz=timezone.utc
        ).replace(tzinfo=None)

        # Negativ, weil Geld rausgeht
        net_amount = -(amount - fee)

        return LedgerEvent(
            id=f"binance_fiat_withdrawal_{order_no}",
            type=EventType.EXTERNAL_CASHFLOW,
            timestamp=timestamp,
            asset=currency,
            amount=net_amount,
            source=EventSource.BINANCE,
            source_id=order_no,
            fee_asset=currency if fee > 0 else None,
            fee_amount=fee if fee > 0 else None,
            note=f"{currency} SEPA withdrawal from Binance ({entry.get('method', 'unknown')})",
            raw_payload=entry,
        )
