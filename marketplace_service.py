from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException

from order_handoff import AssetReadiness, decide_handoff
from spend_guard import (
    BudgetRequest,
    HandoffWriter,
    InfraiAccountClient,
    InfraiError,
    OrderHandoff,
    OrderHandoffRequest,
)


app = FastAPI(title="Marketplace spend cap and order handoff")


def api_key() -> str:
    value = os.environ.get("INFRAI_API_KEY")
    if not value:
        raise RuntimeError("Set INFRAI_API_KEY before starting the service")
    return value


@app.put("/budget")
def configure_budget(request: BudgetRequest) -> dict[str, object]:
    client = InfraiAccountClient(api_key())
    try:
        configured = client.set_budget(request)
        current = client.get_budget()
        return {"configured": configured, "current": current}
    except InfraiError as exc:
        status = exc.status_code if 400 <= exc.status_code < 500 else 502
        raise HTTPException(status_code=status, detail=exc.detail) from exc


@app.post("/orders/handoff", response_model=OrderHandoff)
def create_handoff(request: OrderHandoffRequest) -> OrderHandoff:
    decision = decide_handoff(
        request.buyer_update.accepted,
        [
            AssetReadiness(asset_id=asset.asset_id, ready=asset.ready)
            for asset in request.seller_assets
        ],
    )
    if not decision.ready:
        raise HTTPException(status_code=409, detail=decision.reason)
    instruction = HandoffWriter(api_key()).write(request)
    return OrderHandoff(
        order_id=request.order_id,
        state="ready_for_delivery",
        instruction=instruction,
    )
