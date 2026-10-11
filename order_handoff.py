from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AssetReadiness:
    asset_id: str
    ready: bool


@dataclass(frozen=True)
class HandoffDecision:
    ready: bool
    reason: str


def decide_handoff(
    buyer_accepted: bool, assets: list[AssetReadiness]
) -> HandoffDecision:
    if not buyer_accepted:
        return HandoffDecision(False, "buyer update is awaiting acceptance")
    pending = [asset.asset_id for asset in assets if not asset.ready]
    if pending:
        return HandoffDecision(False, f"seller assets still pending: {', '.join(pending)}")
    return HandoffDecision(True, "buyer accepted and every seller asset is ready")
