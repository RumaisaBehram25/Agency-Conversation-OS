"""Follow-up engine skips subscribers who already bought (Hyros or stage)."""

from types import SimpleNamespace

from app.models.base import BuyerStage
from app.services.follow_up_engine import _has_purchased


def test_has_purchased_true_when_hyros_purchased() -> None:
    sub = SimpleNamespace(
        hyros_purchased=True,
        buyer_stage=BuyerStage.AWARENESS,
    )
    assert _has_purchased(sub) is True


def test_has_purchased_false_when_not_hyros_and_not_purchase_stage() -> None:
    sub = SimpleNamespace(
        hyros_purchased=False,
        buyer_stage=BuyerStage.AWARENESS,
    )
    assert _has_purchased(sub) is False


def test_has_purchased_true_when_buyer_stage_purchase() -> None:
    sub = SimpleNamespace(
        hyros_purchased=False,
        buyer_stage=BuyerStage.PURCHASE,
    )
    assert _has_purchased(sub) is True
