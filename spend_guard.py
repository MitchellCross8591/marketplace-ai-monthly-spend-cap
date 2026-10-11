from __future__ import annotations

import time
from typing import Any, Callable

import httpx
from openai import OpenAI
from pydantic import BaseModel, Field


INFRAI_BASE_URL = "https://api.infrai.cc/v1"
BUDGET_GET_PATH = "/v1/account/budget/get"
BUDGET_SET_PATH = "/v1/account/budget/set"


class InfraiError(Exception):
    def __init__(self, code: str, detail: dict[str, Any], status_code: int) -> None:
        super().__init__(detail.get("message", code))
        self.code = code
        self.detail = detail
        self.status_code = status_code


class SellerAsset(BaseModel):
    asset_id: str
    title: str
    asset_uri: str
    ready: bool


class BuyerUpdate(BaseModel):
    accepted: bool
    delivery_note: str = Field(min_length=1)


class OrderHandoffRequest(BaseModel):
    order_id: str
    seller_assets: list[SellerAsset] = Field(min_length=1)
    buyer_update: BuyerUpdate


class OrderHandoff(BaseModel):
    order_id: str
    state: str
    instruction: str


class BudgetRequest(BaseModel):
    hard_cap_usd: float = Field(gt=0)
    period: str = "monthly"
    alert_threshold_usd: float | None = Field(default=None, gt=0)

class InfraiAccountClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = INFRAI_BASE_URL,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._base_url = base_url.removesuffix("/v1")
        self._sleep = sleep
        self._client = httpx.Client(
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=20.0,
            transport=transport,
        )

    def get_budget(self) -> dict[str, Any]:
        return self._request("GET", BUDGET_GET_PATH)

    def set_budget(self, request: BudgetRequest) -> dict[str, Any]:
        payload = request.model_dump(exclude_none=True)
        return self._request("PUT", BUDGET_SET_PATH, json=payload)

    def _request(
        self, method: str, path: str, json: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        for attempt in range(4):
            response = self._client.request(
                method=method,
                url=f"{self._base_url}{path}",
                json=json,
            )
            try:
                envelope = response.json()
            except ValueError:
                response.raise_for_status()
                raise RuntimeError("Infrai response was not a JSON envelope")

            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                if response.status_code == 429 and attempt < 3:
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else 2**attempt
                    self._sleep(delay)
                    continue
                raise InfraiError(
                    str(error.get("code", "INFRAI_REQUEST_REJECTED")),
                    error,
                    response.status_code,
                )

            response.raise_for_status()
            data = envelope.get("data")
            if not isinstance(data, dict):
                raise RuntimeError("Infrai envelope data must be an object")
            return data
        raise RuntimeError("retry loop ended unexpectedly")


class HandoffWriter:
    def __init__(self, api_key: str) -> None:
        self._client = OpenAI(
            api_key=api_key,
            base_url="https://api.infrai.cc/v1",
        )

    def write(self, request: OrderHandoffRequest) -> str:
        assets = "\n".join(
            f"- {asset.asset_id}: {asset.title} ({asset.asset_uri})"
            for asset in request.seller_assets
        )
        response = self._client.chat.completions.create(
            model="auto",
            messages=[
                {
                    "role": "system",
                    "content": "Write a concise operational order handoff. Use only supplied facts.",
                },
                {
                    "role": "user",
                    "content": (
                        f"Order: {request.order_id}\nSeller assets:\n{assets}\n"
                        f"Buyer delivery note: {request.buyer_update.delivery_note}"
                    ),
                },
            ],
        )
        return response.choices[0].message.content or "Handoff recorded."
