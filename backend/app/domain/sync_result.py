"""
SyncResult Domain Model - Per-Fill Sync Result Tracking

Pure dataclasses (no I/O) for structured sync reporting.
Every fill gets an explicit outcome (PROCESSED/FAILED/SKIPPED_FIFO/SKIPPED_DUPLICATE).

Used by sync_service.sync_fills() to build structured responses
that are backward-compatible with existing API consumers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


class FillOutcome:
    """Fill processing outcomes (string constants for trivial serialization)."""

    PROCESSED = "PROCESSED"
    FAILED = "FAILED"
    SKIPPED_FIFO = "SKIPPED_FIFO"
    SKIPPED_DUPLICATE = "SKIPPED_DUPLICATE"


@dataclass
class FillResult:
    """Per-fill processing result.

    Attributes:
        source_id: Binance trade ID
        fill_id: Internal ledger event ID (e.g., "binance_BTCEUR_12345")
        side: "BUY" or "SELL"
        outcome: FillOutcome constant
        error: Error message if FAILED
        timestamp: Fill timestamp (for watermark computation)
    """

    source_id: str
    fill_id: str
    side: str
    outcome: str
    error: str | None = None
    timestamp: datetime | None = None


@dataclass
class SyncResult:
    """Structured sync result with per-fill tracking.

    Provides both backward-compatible keys (status, new_fills, new_lots,
    allocations, errors, message) and new per-fill detail fields.

    Attributes:
        fills_total: Total fills fetched from Binance
        fills_new: New fills after idempotency filter
        fills_processed: Successfully processed (lot created or sell allocated)
        fills_failed: Persisted but processing failed
        fills_skipped_fifo: Skipped due to FIFO abort
        new_lots: Buy lots created
        allocations: Sell allocations created
        fill_results: Per-fill detail
        fifo_aborted: Whether FIFO abort occurred
    """

    fills_total: int = 0
    fills_new: int = 0
    fills_processed: int = 0
    fills_failed: int = 0
    fills_skipped_fifo: int = 0
    new_lots: int = 0
    allocations: int = 0
    fill_results: list[FillResult] = field(default_factory=list)
    fifo_aborted: bool = False

    @property
    def status(self) -> str:
        """Computed sync status.

        Returns:
            "no_new_fills" if fills_new==0,
            "fifo_error" if fifo_aborted,
            "partial_success" if fills_failed>0,
            else "success"
        """
        if self.fills_new == 0:
            return "no_new_fills"
        if self.fifo_aborted:
            return "fifo_error"
        if self.fills_failed > 0:
            return "partial_success"
        return "success"

    @property
    def errors(self) -> list[str]:
        """List of error strings from FAILED FillResults (backward compat)."""
        return [
            fr.error
            for fr in self.fill_results
            if fr.outcome == FillOutcome.FAILED and fr.error is not None
        ]

    @property
    def last_synced_source_id(self) -> str | None:
        """Highest source_id of successfully processed fills (watermark for resumption).

        Uses numeric comparison since Binance trade IDs are integers.
        Returns None when no fills were processed.
        """
        processed = [
            fr for fr in self.fill_results if fr.outcome == FillOutcome.PROCESSED
        ]
        if not processed:
            return None
        return max(processed, key=lambda fr: int(fr.source_id)).source_id

    def to_dict(self) -> dict[str, Any]:
        """Serialize to API-compatible dict.

        Backward-compatible with existing consumers (same keys: status,
        new_fills, new_lots, allocations, errors, message).

        Per-fill detail only for FAILED and SKIPPED_FIFO fills
        (keeps response compact).
        """
        # Backward-compatible message
        message = (
            f"Synced {self.fills_new} fills, created {self.new_lots} lots, "
            f"{self.allocations} allocations"
        )
        if self.fills_failed > 0:
            message += f", {self.fills_failed} errors"
        if self.fills_skipped_fifo > 0:
            message += f", {self.fills_skipped_fifo} skipped (FIFO abort)"

        # fill_details: only FAILED and SKIPPED_FIFO entries
        fill_details = [
            {
                "source_id": fr.source_id,
                "fill_id": fr.fill_id,
                "side": fr.side,
                "outcome": fr.outcome,
                "error": fr.error,
            }
            for fr in self.fill_results
            if fr.outcome in (FillOutcome.FAILED, FillOutcome.SKIPPED_FIFO)
        ]

        return {
            # Backward-compatible keys
            "status": self.status,
            "new_fills": self.fills_new,
            "new_lots": self.new_lots,
            "allocations": self.allocations,
            "errors": self.errors,
            "message": message,
            # New fields
            "fills_processed": self.fills_processed,
            "fills_failed": self.fills_failed,
            "fills_skipped_fifo": self.fills_skipped_fifo,
            "last_synced_source_id": self.last_synced_source_id,
            "fifo_aborted": self.fifo_aborted,
            "fill_details": fill_details,
        }
