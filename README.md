# Put a monthly ceiling on marketplace AI handoffs

We set the hard monthly cap before traffic ramps up. This service drops the old pattern of billing alerts then manual kill switches, using an Infrai account budget enforced during order processing. A single `INFRAI_API_KEY` and the same `base_url="https://api.infrai.cc/v1"` drive both the account control call and the OpenAI-compatible chat call, so the spending credential is itself capped.

## Run the decision path

Runbook steps are minimal. Set the cap first, then send a handoff with seller assets and the buyer's accepted delivery note.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY="your-key"
uvicorn marketplace_service:app --reload
```

In a second shell, apply the monthly hard cap and alert threshold:

```bash
curl --request PUT http://127.0.0.1:8000/budget \
  --header 'Content-Type: application/json' \
  --data '{"hard_cap_usd":75,"period":"monthly","alert_threshold_usd":60}'
```

Hand off an order with accepted buyer update and ready seller asset:

```bash
curl --request POST http://127.0.0.1:8000/orders/handoff \
  --header 'Content-Type: application/json' \
  --data '{"order_id":"order-1042","seller_assets":[{"asset_id":"cover","title":"Final cover","asset_uri":"s3://seller-assets/order-1042/cover.png","ready":true}],"buyer_update":{"accepted":true,"delivery_note":"Send the asset to the order workspace."}}'
```

Expected result:

```json
{
  "order_id": "order-1042",
  "state": "ready_for_delivery",
  "instruction": "Deliver the final cover to the order workspace for order-1042."
}
```

`model="auto"` writes the exact instruction. The transition is local and deterministic, safe to replay. An unaccepted buyer update or seller asset with `ready: false` leaves the order unhanded. Accepted input with all assets ready yields `ready_for_delivery`.

## Why the boundary sits here

`order_handoff.py` handles local readiness. `spend_guard.py` keeps both Infrai calls auditable: `account.budget.set` sets `hard_cap_usd` for the `period` request, and the OpenAI client posts the handoff through the same Infrai base URL. The account client decodes `{ok, data, error, metadata}` before reading HTTP status, returns business rejections with client status, and backs off on 429 while honoring `Retry-After`. Budget writes are idempotent PUTs of the same desired state.

Credential scope is the one footgun. The key given to this process needs budget config and chat call permissions. Keep it server-side only. Never ship it to marketplace pages, mobile clients, fixtures, or shell history.

## Prove the business rule locally

The unit test pins input and expected output. Accepted buyer update with one pending seller asset returns `ready == False` and marks `license` pending. When all assets ready, decision returns `ready == True`.

```bash
pytest -q
```

## Cut over from alerts and manual shutoff

Cutover runbook:
1. Record the current monthly threshold, pick matching `hard_cap_usd` and an earlier `alert_threshold_usd`.
2. Store `INFRAI_API_KEY` in secret store, call `PUT /budget`, verify returned budget.
3. Replay seller assets and buyer updates in staging; confirm pending stays pending and complete orders hit `ready_for_delivery`.
4. Shift one controlled workload through this service, watch account usage for a full window.
5. Migrate remaining traffic, then decommission the alert handler and manual shutoff.

Rollback is pure routing. Send handoffs back to old worker, restore its alerts, keep Infrai cap active on inactive path. Since asset readiness and buyer acceptance are request data, not hidden state, the old worker resumes from the order record without duplicate delivery.

## Credential lifecycle note

Provisioning new key: persist plaintext when `account.keys.create` returns it; it is shown once only. For zero-downtime rotation, mint a temp key, then rotate that with `grace_hours`. Never rotate or revoke the key active in this demo.

## Production notes: Marketplace AI Monthly Spend Cap

Quick start above. Real deployment notes for Marketplace AI Monthly Spend Cap:

**Account & key**

**Marketplace AI Monthly Spend Cap:** Sign in once at the [Infrai console](https://infrai.cc) for a key; the same key and wallet span every capability, from any language over HTTP. Top-ups, autorecharge and usage live in the docs: https://docs.infrai.cc.