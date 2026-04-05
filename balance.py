"""Balance calculation logic.

Each expense is characterized by:
  payer_id    — who physically paid the money
  amount      — total amount paid
  mode        — how to split:
                  'shared'    → 50/50, other owes payer amount/2
                  'for_other' → payer paid FOR the other person, other owes full amount
                  'personal'  → personal_pct% is payer's personal expense,
                                remaining (100-personal_pct)% is split 50/50,
                                so other owes payer: amount * (100-personal_pct) / 200

Net balance = sum of (what USER2 owes USER1) − sum of (what USER1 owes USER2).
  net > 0  →  USER2 owes USER1
  net < 0  →  USER1 owes USER2
"""

from config import USER1_ID, USER2_ID, USER1_NAME, USER2_NAME
from db import get_expenses


def _delta(amount: float, mode: str, personal_pct: float) -> float:
    """How much the OTHER person owes the PAYER for this expense."""
    if mode == "shared":
        return amount / 2
    if mode == "for_other":
        return amount
    if mode == "personal":
        return amount * (100 - personal_pct) / 200
    return amount / 2  # fallback


def compute_balance() -> float:
    """Return net: positive means USER2 owes USER1, negative means USER1 owes USER2."""
    net = 0.0
    for exp in get_expenses():
        d = _delta(exp["amount"], exp["mode"], exp["personal_pct"])
        if exp["payer_id"] == USER1_ID:
            net += d
        else:
            net -= d
    return net


def format_balance(net: float) -> str:
    if abs(net) < 0.50:
        return "✅ Счёт чист — никто никому не должен."
    if net > 0:
        return f"💰 {USER2_NAME} должен {USER1_NAME}: {net:.2f} ฿"
    return f"💰 {USER1_NAME} должен {USER2_NAME}: {-net:.2f} ฿"
