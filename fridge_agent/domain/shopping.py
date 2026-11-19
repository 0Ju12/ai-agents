"""Keep only defensible package sizes. Mixed options and promotional bundles need confirmation."""

import math
import re
from .catalog import canonical


def add_shortages(state, plan, servings):
    required = plan.get("예시 1인분(g)")
    if not required:
        raise ValueError("먼저 장볼 메뉴를 선택하세요.")
    from .kitchen import inventory, shortages
    from storage import today

    missing, unchecked = shortages(required, inventory(state, today().isoformat()), servings)
    cart = state.setdefault("cart", {})
    for name, grams in missing.items():
        previous = cart.get(name, {})
        cart[name] = {"grams": max(grams, previous.get("grams") or 0), "meal": plan["메뉴"]}
    return missing, unchecked


def comparable(title, needed, price):
    if not isinstance(title, str) or not isinstance(price, (float, int)) or price <= 0:
        return {}
    if re.search(r"\+|~|/|랜덤|옵션|선택|증정|혼합", title):
        return {}
    weights = re.findall(r"(?<![\d.,])(\d+(?:\.\d+)?)\s*(kg|g)(?![a-z])", title, re.I)
    if len(weights) != 1:
        return {}
    value, unit = weights[0]
    packs = re.findall(r"(?:[xX×]\s*)?(\d+)\s*(?:개입|개|팩|봉|통|병|세트)", title)
    if len(packs) > 1:
        return {}
    count = int(packs[0]) if packs else 1
    if not packs and re.search(r"[xX×]\s*\d+", title):
        return {}
    grams = float(value) * (1000 if unit.lower() == "kg" else 1) * count
    if not 0 < grams <= 100000:
        return {}
    out = {"표기 포장(g)": round(grams, 2), "100g당 표시가(원)": round(100 * price / grams)}
    if needed:
        n = math.ceil(needed / grams)
        out.update({"필요 포장 수": n, "필요량 구매 표시가(원)": n * price})
    return out
