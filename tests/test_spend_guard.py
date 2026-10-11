from order_handoff import AssetReadiness, decide_handoff


def test_handoff_waits_for_every_seller_asset() -> None:
    assets = [
        AssetReadiness(asset_id="cover", ready=True),
        AssetReadiness(asset_id="license", ready=False),
    ]

    decision = decide_handoff(True, assets)

    assert decision.ready is False
    assert decision.reason == "seller assets still pending: license"


def test_handoff_proceeds_after_buyer_acceptance_and_asset_readiness() -> None:
    assets = [AssetReadiness(asset_id="cover", ready=True)]

    decision = decide_handoff(True, assets)

    assert decision.ready is True
    assert decision.reason == "buyer accepted and every seller asset is ready"
