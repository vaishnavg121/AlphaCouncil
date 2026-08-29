"""Provider position reconciliation for M7."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Literal, cast

from app.alpaca.gateway import AlpacaGateway
from app.alpaca.models import PositionSnapshot as AlpacaPositionSnapshot
from app.positions.models import (
    PositionReconciliationResult,
    PositionStoreRecord,
)
from app.positions.store import PositionStore

if TYPE_CHECKING:
    from app.positions.store import PositionStore


class PositionReconciler:
    """Reconciles local managed positions with Alpaca provider state."""

    def __init__(
        self,
        alpaca_gateway: AlpacaGateway,
        position_store: PositionStore | None = None,
    ) -> None:
        self._alpaca = alpaca_gateway
        self._store = position_store

    def reconcile_all(self) -> list[PositionReconciliationResult]:
        """Reconcile all managed positions against provider."""
        if self._store is None:
            return []

        records = self._store.get_open_positions()
        results = []

        for record in records:
            result = self._reconcile_position(record)
            results.append(result)

        return results

    def reconcile_position(self, position_id: str) -> PositionReconciliationResult | None:
        """Reconcile a specific position by ID."""
        if self._store is None:
            return None

        record = self._store.get_by_position_id(position_id)
        if not record:
            return None

        return self._reconcile_position(record)

    def _reconcile_position(self, record: PositionStoreRecord) -> PositionReconciliationResult:
        """Reconcile a single managed position against provider."""
        # Fetch provider position
        provider_positions = self._get_provider_positions()
        provider_pos = provider_positions.get(record.symbol)

        local_qty = record.current_quantity
        local_notional = record.current_notional
        local_side = record.side
        assert local_side in ("LONG", "SHORT")
        local_side_lit = cast(Literal["LONG", "SHORT"], local_side)

        if provider_pos is None:
            # Position missing at provider - was it closed externally?
            return PositionReconciliationResult(
                position_id=record.position_id,
                symbol=record.symbol,
                local_quantity=local_qty,
                provider_quantity=Decimal("0"),
                local_notional=local_notional,
                provider_notional=Decimal("0"),
                reconciled=False,
                action_required=True,
                mismatch_detected=True,
                position_missing_at_provider=True,
                local_side=local_side_lit,
                provider_side=None,
                details=(f"Local position {local_qty} {local_side} {record.symbol} not found at provider",),
                reconciled_at=datetime.now(UTC),
            )

        # Parse provider data
        provider_qty = Decimal(str(provider_pos.qty))
        provider_notional = Decimal(str(provider_pos.market_value)) if provider_pos.market_value else Decimal("0")
        provider_side: Literal["LONG", "SHORT"] = "LONG" if provider_qty > 0 else "SHORT"
        provider_qty = abs(provider_qty)

        # Check for side mismatch
        side_mismatch = local_side != provider_side
        qty_mismatch = local_qty != provider_qty

        details = []
        action_required = False
        mismatch_detected = False

        if side_mismatch:
            details.append(f"Side mismatch: local={local_side}, provider={provider_side}")
            mismatch_detected = True
            action_required = True

        if qty_mismatch:
            details.append(f"Quantity mismatch: local={local_qty}, provider={provider_qty}")
            mismatch_detected = True
            action_required = True

        # Update local store with reconciled quantity if it differs
        if qty_mismatch and not side_mismatch:
            # Use provider quantity as source of truth for current position
            # (but don't overwrite entry quantities)
            pass  # Store update handled by caller

        return PositionReconciliationResult(
            position_id=record.position_id,
            symbol=record.symbol,
            local_quantity=local_qty,
            provider_quantity=provider_qty,
            local_notional=local_notional,
            provider_notional=provider_notional,
            reconciled=not mismatch_detected,
            action_required=action_required,
            mismatch_detected=mismatch_detected,
            position_missing_at_provider=False,
            unexpected_provider_position=False,
            local_side=local_side_lit,
            provider_side=provider_side,
            details=tuple(details),
            reconciled_at=datetime.now(UTC),
        )

    def _get_provider_positions(self) -> dict[str, AlpacaPositionSnapshot]:
        """Fetch all provider positions as a dict by symbol."""
        positions = self._alpaca.list_positions()
        return {pos.symbol: pos for pos in positions}

    def find_unmanaged_provider_positions(self, managed_symbols: set[str]) -> list[AlpacaPositionSnapshot]:
        """Find provider positions that have no AlphaCouncil ownership."""
        all_provider = self._get_provider_positions()
        unmanaged = []

        for symbol, pos in all_provider.items():
            if symbol not in managed_symbols:
                unmanaged.append(pos)

        return unmanaged


def create_position_reconciler(
    alpaca_gateway: AlpacaGateway,
    position_store: PositionStore | None = None,
) -> PositionReconciler:
    """Factory function to create position reconciler."""
    return PositionReconciler(alpaca_gateway, position_store)