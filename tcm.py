"""TCM energetics: the warming/cooling "thermal nature" of foods and how to score a meal.

Every food carries one number, `tcm_thermal`, on a five-point scale:

    -2  cold      (watermelon, cucumber, mung bean, crab, banana)
    -1  cool      (most leafy greens, tofu, pear, barley, wheat)
     0  neutral   (rice, oats, eggs, pork, carrot, potato)
    +1  warm      (chicken, oats-with-ginger, onion, walnut, salmon, cherry)
    +2  hot       (chilli, black pepper, lamb, dried ginger, cinnamon, alcohol)

Half steps are fine ("+0.5": slightly warming). None means "not yet assessed".

Descriptive extras (flavours, organs, note, where the value came from) live in the
`tcm` JSON column so the number stays a plain, summable column.

Scoring a meal
--------------
A meal's score is the weighted mean of its items' thermal values, so it lands on the
same -2..+2 scale as a single food. Weighting matters: 100 g of mung beans should pull
a meal cooler than 50 g does, so by default the weight is grams. `WEIGHTING` lets you
switch to kcal (so watery vegetables don't dominate) or to equal weight per item.
Items with no thermal value are left out of the mean but counted in `coverage`, so the
UI can say "based on 70% of this meal by weight".
"""
from __future__ import annotations

import os

# Which weight each item contributes to the mean: "grams" | "kcal" | "equal"
WEIGHTING = os.environ.get("TCM_WEIGHTING", "grams")

SCALE_MIN, SCALE_MAX = -2.0, 2.0

# (upper bound inclusive, key, label, colour). Order matters: first match wins.
BANDS = [
    (-1.5, "cold",    "Cold",    "#2a6fd6"),
    (-0.5, "cool",    "Cool",    "#5aa0e6"),
    (0.5,  "neutral", "Neutral", "#8c938e"),
    (1.5,  "warm",    "Warm",    "#e08a3c"),
    (99,   "hot",     "Hot",     "#c9452b"),
]

# Options offered in the food form / Gemini schema; value -> label.
THERMAL_CHOICES = [
    (-2, "Cold (−2)"),
    (-1.5, "Cold–cool (−1.5)"),
    (-1, "Cool (−1)"),
    (-0.5, "Slightly cooling (−0.5)"),
    (0, "Neutral (0)"),
    (0.5, "Slightly warming (+0.5)"),
    (1, "Warm (+1)"),
    (1.5, "Warm–hot (+1.5)"),
    (2, "Hot (+2)"),
]

FLAVOURS = ["sweet", "sour", "bitter", "pungent", "salty", "bland"]
ORGANS = ["spleen", "stomach", "lung", "large intestine", "kidney", "bladder",
          "liver", "gallbladder", "heart", "small intestine"]


def clamp(v: float) -> float:
    return max(SCALE_MIN, min(SCALE_MAX, float(v)))


def band(value: float | None) -> dict:
    """Band info for a thermal value: {key, label, colour}. None -> unknown."""
    if value is None:
        return {"key": "unknown", "label": "Not assessed", "colour": "#c9c6bc"}
    for upper, key, label, colour in BANDS:
        if value <= upper:
            return {"key": key, "label": label, "colour": colour}
    return {"key": "hot", "label": "Hot", "colour": BANDS[-1][3]}


def fmt(value: float | None) -> str:
    """'+1', '−0.5', '0', or '?'."""
    if value is None:
        return "?"
    v = round(float(value), 1)
    if v == 0:
        return "0"
    s = f"{abs(v):g}"
    return ("+" if v > 0 else "−") + s


def pct_position(value: float | None) -> float:
    """Where on a 0..100% gauge a value sits (used for the marker)."""
    if value is None:
        return 50.0
    return (clamp(value) - SCALE_MIN) / (SCALE_MAX - SCALE_MIN) * 100


def _weight(grams: float, kcal: float | None) -> float:
    if WEIGHTING == "kcal":
        return max(kcal or 0.0, 0.0)
    if WEIGHTING == "equal":
        return 1.0
    return max(grams or 0.0, 0.0)


def empty_totals() -> dict:
    """Accumulator stored under totals['tcm'] by db.day_log."""
    return {"weighted": 0.0, "weight_known": 0.0, "weight_total": 0.0, "items": 0, "items_known": 0}


def accumulate(tot: dict, thermal: float | None, grams: float, kcal: float | None) -> None:
    w = _weight(grams, kcal)
    tot["weight_total"] += w
    tot["items"] += 1
    if thermal is not None:
        tot["weighted"] += float(thermal) * w
        tot["weight_known"] += w
        tot["items_known"] += 1


def score(tot: dict | None) -> dict:
    """Turn an accumulator into something a template can show.

    Returns {value, band, label, colour, text, pct, coverage, items, items_known, known}.
    value is None when nothing in the meal has been assessed.
    """
    if not tot or not tot["weight_known"]:
        b = band(None)
        return {"value": None, "band": b["key"], "label": b["label"], "colour": b["colour"], "text": "?",
                "pct": 50.0, "coverage": 0.0, "items": (tot or {}).get("items", 0),
                "items_known": 0, "known": False}
    value = tot["weighted"] / tot["weight_known"]
    coverage = (tot["weight_known"] / tot["weight_total"] * 100) if tot["weight_total"] else 100.0
    b = band(value)
    return {"value": round(value, 2), "band": b["key"], "label": b["label"], "colour": b["colour"],
            "text": fmt(value), "pct": pct_position(value), "coverage": round(coverage),
            "items": tot["items"], "items_known": tot["items_known"], "known": True}


def score_items(items: list[tuple[float | None, float, float | None]]) -> dict:
    """Convenience: score a list of (thermal, grams, kcal) tuples (used for the basket)."""
    tot = empty_totals()
    for thermal, grams, kcal in items:
        accumulate(tot, thermal, grams, kcal)
    return score(tot)


def what_if(tot: dict, add_thermal: float, add_grams: float = 100.0, add_kcal: float | None = None) -> float | None:
    """Score after adding `add_grams` of a food with the given thermal value. Drives the
    basket hint: 'adding 100 g of a +1 food takes this meal to +0.4'."""
    w = _weight(add_grams, add_kcal)
    known = tot["weight_known"] + w
    if not known:
        return None
    return round((tot["weighted"] + add_thermal * w) / known, 2)


def parse_thermal(v) -> float | None:
    """Accept '', None, '+1', '-0.5', 'warm', 'cool' ... and return a clamped float or None."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return clamp(v)
    s = str(v).strip().lower().replace("−", "-").replace("+", "")
    if not s:
        return None
    words = {"cold": -2, "cool": -1, "neutral": 0, "warm": 1, "hot": 2,
             "slightly cool": -0.5, "slightly cooling": -0.5, "slightly warm": 0.5, "slightly warming": 0.5}
    if s in words:
        return float(words[s])
    try:
        return clamp(float(s))
    except ValueError:
        return None
