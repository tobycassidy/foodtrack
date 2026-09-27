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

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
# Tried in order if MODEL is overloaded (503) or rate-limited (429). Comma-separated to override.
FALLBACK_MODELS = [m.strip() for m in os.environ.get(
    "GEMINI_FALLBACK_MODELS", "gemini-3.6-flash,gemini-3.1-flash-lite,gemini-3.8-flash").split(",") if m.strip()]
RETRIES_PER_MODEL = 3
TIMEOUT_MS = int(os.environ.get("GEMINI_TIMEOUT_S", "90")) * 1000
MAX_EDGE = 1600  # px; labels are legible well below this and uploads get much faster


def shrink_image(data: bytes, mime: str) -> tuple[bytes, str]:
    """Downscale big phone photos and convert HEIC etc. to JPEG. Falls back to the original on any failure."""
    try:
        import io
        from PIL import Image, ImageOps
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img).convert("RGB")
        if max(img.size) > MAX_EDGE:
            img.thumbnail((MAX_EDGE, MAX_EDGE))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=85)
        return buf.getvalue(), "image/jpeg"
    except Exception:
        return data, mime


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


def build_prompt(food_name: str, has_image: bool = True) -> str:
    if has_image:
        inputs = f"""- Food as typed by the user: "{food_name or 'not given'}"
- A photo of the nutrition label (attached)."""
        task1 = "TASK 1 – READ THE LABEL (source of truth)"
    else:
        inputs = f"""- Food as typed by the user: "{food_name}"
- No label photo: this is a whole or unpackaged food (eggs, chicken thigh, 95/5 beef mince, an apple...)."""
        task1 = """TASK 1 – FILL THE CORE FIELDS FROM REFERENCE DATA
There is no label. Use standard composition tables (USDA FoodData Central, McCance & Widdowson) for this
exact food as described, raw unless the name says cooked. Assume typical UK/EU retail products. Mark every
value as an estimate and state the reference food you used in notes.
Set serving_size_g to the natural unit of this food and describe it in serving_desc, e.g.
  eggs -> serving_size_g 55, serving_desc "1 medium egg (55 g)"
  chicken drumstick -> ~95 g edible with bone removed, "1 drumstick (approx 95 g, meat only)"
  chicken thigh -> "1 thigh, boneless skinless (approx 110 g)"; whole chicken leg -> thigh + drumstick
  beef mince, rice, oats, vegetables sold loose -> 100 g, "100 g"
State clearly in serving_desc whether weight is raw or cooked and with or without bone/skin."""

    return f"""You are a nutrition scientist helping build a personal food database.

INPUT
{inputs}

{task1}
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


def extract_label(image_bytes: bytes | None, mime_type: str | None, food_name: str = "") -> dict:
    """Return a food dict ready for the review form:
    core fields, extra {key: value}, extra_meta {key: {source, confidence, basis}}, profile {...}, notes.
    With image_bytes=None the food is estimated from its name alone (whole/unpackaged foods)."""
    from google import genai
    from google.genai import types

    has_image = image_bytes is not None
    contents = [build_prompt(food_name, has_image)]
    if has_image:
        image_bytes, mime_type = shrink_image(image_bytes, mime_type)
        contents.insert(0, types.Part.from_bytes(data=image_bytes, mime_type=mime_type))
    client = genai.Client(http_options=types.HttpOptions(timeout=TIMEOUT_MS))  # reads GEMINI_API_KEY
    config = types.GenerateContentConfig(
        response_mime_type="application/json", response_schema=Extraction)
    response, used_model = _generate_with_fallback(client, contents, config)
    parsed = Extraction.model_validate_json(response.text)
    out = parsed.model_dump(exclude={"label_extra", "estimates", "profile"})
    out["extra"], out["extra_meta"] = {}, {}
    label_source = "label" if has_image else "estimate"
    for n in parsed.label_extra:
        out["extra"][n.key] = n.value
        out["extra_meta"][n.key] = {"source": label_source, "confidence": "high" if has_image else n.confidence, "basis": n.basis}
    for n in parsed.estimates:
        if n.key in out["extra"]:
            continue  # the label wins over an estimate
        out["extra"][n.key] = n.value
        out["extra_meta"][n.key] = {"source": "estimate", "confidence": n.confidence, "basis": n.basis}
    out["profile"] = parsed.profile.model_dump()
    if used_model != MODEL:
        out["notes"] = f"(answered by fallback model {used_model}) " + (out.get("notes") or "")
    return out


def _generate_with_fallback(client, contents, config):
    """Retry with backoff on 503/429, then move down the model list. Raises the last error."""
    import time

    last_error = None
    for model in [MODEL, *[m for m in FALLBACK_MODELS if m != MODEL]]:
        for attempt in range(RETRIES_PER_MODEL):
            try:
                return client.models.generate_content(model=model, contents=contents, config=config), model
            except Exception as exc:
                last_error = exc
                code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
                text = str(exc)
                busy = code in (429, 503) or "503" in text or "429" in text or "UNAVAILABLE" in text or "RESOURCE_EXHAUSTED" in text
                if not busy:
                    raise
                wait = 2 * (attempt + 1)
                print(f"[gemini] {model} busy ({code or 'overloaded'}), attempt {attempt + 1}/{RETRIES_PER_MODEL}, waiting {wait}s")
                time.sleep(wait)
        print(f"[gemini] giving up on {model}, trying next model")
    raise last_error


def summarize_nutrition(data: dict) -> str:
    """Ask Gemini to critique the scaled nutritional totals for a meal/day/basket."""
    from google import genai
    from google.genai import types
    
    prompt = f"""You are a sports nutritionist and microbiome expert.
Analyze the following scaled nutritional totals for a {data.get('scope', 'collection of foods')}.
The data has already been scaled to the exact portion weights consumed.
Keep your response to 2-3 short paragraphs focusing on macros, leucine, fast/slow carbs, gut feeds, and overall quality.

Data:
{json.dumps(data, indent=2)}
"""
    client = genai.Client(http_options=types.HttpOptions(timeout=TIMEOUT_MS))
    config = types.GenerateContentConfig(response_mime_type="text/plain")
    response, _ = _generate_with_fallback(client, [prompt], config)
    return response.text


if __name__ == "__main__":
    # Label:      python gemini_extract.py path/to/label.jpg "porridge oats"
    # Name only:  python gemini_extract.py --name "whole eggs"
    import mimetypes
    import sys

    if sys.argv[1] == "--name":
        print(json.dumps(extract_label(None, None, sys.argv[2]), indent=2))
    else:
        path = sys.argv[1]
        name = sys.argv[2] if len(sys.argv) > 2 else ""
        mime = mimetypes.guess_type(path)[0] or "image/jpeg"
        with open(path, "rb") as f:
            print(json.dumps(extract_label(f.read(), mime, name), indent=2))
