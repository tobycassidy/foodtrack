"""Turn a label photo + the food name you typed into structured nutrition data.

Two kinds of numbers come back and are kept apart in the UI and the DB:
  * label values   – read off the photo (source = "label")
  * estimates      – Gemini's knowledge of this food, anchored on the label
                     (source = "estimate", with a confidence). Soluble/insoluble
                     fibre, beta-glucan, vitamins, minerals, omega-3 and so on.
Estimates use the canonical keys in nutrients.py so they can be summed across a day.

Requires GEMINI_API_KEY in the environment.
"""
import json
import os
from typing import Literal

from pydantic import BaseModel, Field

import nutrients as N

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")


class Nutrient(BaseModel):
    key: str = Field(description="One of the canonical keys listed in the prompt, or a new snake_case key ending in its unit")
    value: float = Field(description="Amount per 100 g")
    confidence: Literal["high", "medium", "low"] = Field(description="'high' only for values read directly off the label")
    basis: str | None = Field(default=None, description="One short phrase on where the number comes from")


class Profile(BaseModel):
    glycemic_index: int | None = Field(default=None, description="Estimated GI 0–100")
    fermentability: Literal["low", "medium", "high"] | None = Field(default=None, description="How readily gut bacteria ferment this food's fibre")
    processing_level: int | None = Field(default=None, description="NOVA 1–4")
    fibre_types: list[str] = Field(default_factory=list, description="Named fibre types present, e.g. beta-glucan, arabinoxylan, inulin, pectin, resistant starch")
    feeds: list[str] = Field(default_factory=list, description="Gut bacteria genera this food's fibres preferentially feed, e.g. Bifidobacterium, Faecalibacterium, Akkermansia")
    tags: list[str] = Field(default_factory=list, description="Short functional tags: prebiotic, fermented, polyphenol-rich, slow carbs, fast carbs, high leucine, collagen support, antioxidant, anti-inflammatory, high glycaemic, ultra-processed")
    training_note: str | None = Field(default=None, description="One sentence: role for glycogen/energy pacing and recovery")
    microbiome_note: str | None = Field(default=None, description="One sentence on microbiome effect")
    notable_compounds: list[str] = Field(default_factory=list, description="e.g. avenanthramides, lycopene, sulforaphane, quercetin")


class Extraction(BaseModel):
    name: str
    brand: str | None = None
    serving_size_g: float | None = None
    serving_desc: str | None = None
    # Core label fields, per 100 g, read from the photo
    kcal: float | None = None
    fat_g: float | None = None
    sat_fat_g: float | None = None
    carbs_g: float | None = None
    sugars_g: float | None = None
    fibre_g: float | None = None
    protein_g: float | None = None
    salt_g: float | None = None
    label_extra: list[Nutrient] = Field(default_factory=list, description="Any other nutrient printed on the label (vitamins, minerals, polyols...)")
    estimates: list[Nutrient] = Field(default_factory=list, description="Estimated nutrients NOT printed on the label")
    profile: Profile
    notes: str | None = Field(default=None, description="Anything the user should double-check")


def _key_table() -> str:
    lines = []
    for group, title in N.GROUPS:
        keys = [k for k in N.KEYS if N.BY_KEY[k]["group"] == group]
        lines.append(f"  {title}: " + ", ".join(keys))
    return "\n".join(lines)


def build_prompt(food_name: str) -> str:
    return f"""You are a nutrition scientist helping build a personal food database.

INPUT
- Food as typed by the user: "{food_name or 'not given'}"
- A photo of the nutrition label (attached).

TASK 1 – READ THE LABEL (source of truth)
Extract every printed nutrient PER 100 g (per 100 ml for drinks) into the core fields and `label_extra`.
- Convert kJ to kcal (÷4.184) and sodium to salt (×2.5) if needed; say so in notes.
- If only per-serving values are printed, convert using the serving size and say so in notes.
- Never guess a digit you cannot read: leave it null and flag it in notes.
- Do not include % reference intake figures.

TASK 2 – ESTIMATE WHAT THE LABEL DOESN'T SAY
Using the typed name, the ingredients if visible, and your knowledge of this kind of food, estimate
per-100 g values for as many of the canonical keys below as are meaningfully present. Anchor every
estimate on the label: soluble + insoluble fibre must equal the label's fibre_g; beta-glucan, resistant
starch, inulin and pectin are sub-fractions of that fibre; slow_carbs_g + fast_carbs_g should equal
carbs_g; EPA+DHA is part of omega3_g. Give a confidence and a short basis for each.
Prioritise, in this order:
  1. Fibre fractions and prebiotic compounds (soluble/insoluble, beta-glucan, resistant starch, inulin/fructans, pectin, polyphenols).
  2. Carbohydrate quality (slow vs fast carbs, starch) for glycogen and energy pacing.
  3. Vitamins and minerals, especially vitamin C, A, E, D, zinc, selenium, copper, iron, magnesium, B vitamins, iodine, potassium.
  4. Fats: omega-3 total and EPA+DHA, omega-6, MUFA.
  5. Leucine and glycine; collagen; carotenoids/lycopene; live cultures if fermented.
Skip keys that are genuinely zero or irrelevant rather than padding with zeros. Use only the canonical keys
(a new key is allowed if it ends with _g, _mg or _ug).

Canonical keys:
{_key_table()}

TASK 3 – PROFILE
Fill the profile: estimated glycaemic index, fibre fermentability, NOVA processing level, the fibre types
present, which gut bacteria genera they preferentially feed, functional tags, notable bioactive compounds,
and one-sentence notes on training/energy relevance and microbiome relevance.

Return JSON only, matching the schema. Use the typed name as the food name unless it is clearly wrong."""


def extract_label(image_bytes: bytes, mime_type: str, food_name: str = "") -> dict:
    """Return a food dict ready for the review form:
    core fields, extra {key: value}, extra_meta {key: {source, confidence, basis}}, profile {...}, notes."""
    from google import genai
    from google.genai import types

    client = genai.Client()  # reads GEMINI_API_KEY
    response = client.models.generate_content(
        model=MODEL,
        contents=[types.Part.from_bytes(data=image_bytes, mime_type=mime_type), build_prompt(food_name)],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=Extraction,
            temperature=0,
        ),
    )
    parsed = Extraction.model_validate_json(response.text)
    out = parsed.model_dump(exclude={"label_extra", "estimates", "profile"})
    out["extra"], out["extra_meta"] = {}, {}
    for n in parsed.label_extra:
        out["extra"][n.key] = n.value
        out["extra_meta"][n.key] = {"source": "label", "confidence": "high", "basis": n.basis}
    for n in parsed.estimates:
        if n.key in out["extra"]:
            continue  # the label wins over an estimate
        out["extra"][n.key] = n.value
        out["extra_meta"][n.key] = {"source": "estimate", "confidence": n.confidence, "basis": n.basis}
    out["profile"] = parsed.profile.model_dump()
    return out


if __name__ == "__main__":
    # Quick CLI test:  python gemini_extract.py path/to/label.jpg "porridge oats"
    import mimetypes
    import sys

    path = sys.argv[1]
    name = sys.argv[2] if len(sys.argv) > 2 else ""
    mime = mimetypes.guess_type(path)[0] or "image/jpeg"
    with open(path, "rb") as f:
        print(json.dumps(extract_label(f.read(), mime, name), indent=2))
