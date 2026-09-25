"""Check the Gemini API step by step, with no input needed.

    python check_gemini.py                      # all steps, using a generated test label
    python check_gemini.py path/to/label.jpg    # same, but with your own photo in step 5
    python check_gemini.py --quick              # stop after the text check (no image calls)

Steps: key present -> SDK -> API reachable + model available -> text works ->
label image through the app's real extraction code -> name-only estimate.
Run it in the same shell you start uvicorn from, so it sees the same environment.
"""
import io
import os
import sys
import time

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")


def step(label):
    print(f"\n[{label}]")


def fail(msg, hint=None):
    print(f"  FAILED: {msg}")
    if hint:
        print(f"  Fix: {hint}")
    sys.exit(1)


def make_test_label() -> bytes:
    """Draw a plausible UK-style nutrition table so the image path can be tested without a photo."""
    from PIL import Image, ImageDraw, ImageFont
    W, H = 1100, 760
    img = Image.new("RGB", (W, H), (245, 242, 232))
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 30)
        bold = ImageFont.truetype("DejaVuSans-Bold.ttf", 34)
    except OSError:
        font = bold = ImageFont.load_default()
    d.text((40, 30), "TESTBRAND Jumbo Rolled Oats", font=bold, fill="black")
    d.text((40, 90), "Nutrition", font=bold, fill="black")
    rows = [
        ("", "Per 100g", "Per 40g serving"),
        ("Energy", "1560kJ / 370kcal", "624kJ / 148kcal"),
        ("Fat", "8.0g", "3.2g"),
        ("  of which saturates", "1.5g", "0.6g"),
        ("Carbohydrate", "60g", "24g"),
        ("  of which sugars", "1.1g", "0.4g"),
        ("Fibre", "9.0g", "3.6g"),
        ("  of which beta-glucan", "3.6g", "1.4g"),
        ("Protein", "11g", "4.4g"),
        ("Salt", "0.02g", "0.01g"),
        ("Iron", "4.2mg", "1.7mg"),
    ]
    y = 150
    for i, (a, b, c) in enumerate(rows):
        f = bold if i == 0 else font
        d.text((40, y), a, font=f, fill="black")
        d.text((440, y), b, font=f, fill="black")
        d.text((780, y), c, font=f, fill="black")
        y += 48
        d.line((40, y - 6, W - 40, y - 6), fill=(120, 120, 120), width=1)
    d.text((40, y + 20), "Ingredients: 100% wholegrain oats.", font=font, fill="black")
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def main():
    quick = "--quick" in sys.argv
    image_path = next((a for a in sys.argv[1:] if not a.startswith("--")), None)

    step("1. API key in environment")
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        fail("GEMINI_API_KEY is not set in this shell.",
             "set -a; source .env; set +a   (or export GEMINI_API_KEY=...), then restart uvicorn")
    print(f"  found, starts with {key[:6]}…, length {len(key)}")

    step("2. SDK import")
    try:
        from google import genai
        from google.genai import types
    except ImportError as e:
        fail(f"import failed: {e}", "pip install -r requirements.txt")
    print(f"  google-genai {genai.__version__}")

    client = genai.Client(http_options=types.HttpOptions(timeout=30_000))

    step("3. Reach the API and confirm the model")
    t = time.time()
    try:
        names = [m.name.replace("models/", "") for m in client.models.list()]
    except Exception as e:
        print(f"  failed after {time.time()-t:.1f}s: {type(e).__name__}: {e}")
        fail("cannot list models",
             "timeout -> proxy/VPN/firewall blocking generativelanguage.googleapis.com; "
             "400/403 -> wrong key or API disabled for the project")
    print(f"  ok in {time.time()-t:.1f}s, {len(names)} models visible")
    if MODEL in names:
        print(f"  '{MODEL}' is available to this key")
    else:
        print(f"  '{MODEL}' is NOT available. Flash models you could use instead:")
        for n in names:
            if "flash" in n and not any(x in n for x in ("image", "live", "tts", "audio")):
                print(f"    {n}")
        fail(f"model {MODEL!r} not available", "export GEMINI_MODEL=<one from the list above>")

    step("4. Text generation")
    t = time.time()
    try:
        r = client.models.generate_content(model=MODEL, contents="Reply with the single word: pong")
        print(f"  ok in {time.time()-t:.1f}s -> {r.text.strip()!r}")
    except Exception as e:
        fail(f"after {time.time()-t:.1f}s: {type(e).__name__}: {e}")

    if quick:
        print("\nText path works (--quick, image steps skipped).")
        return

    # From here on use the app's own code so the test is the real thing.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from gemini_extract import extract_label

    step("5. Label photo through the app's extraction code")
    if image_path:
        data = open(image_path, "rb").read()
        import mimetypes
        mime = mimetypes.guess_type(image_path)[0] or "image/jpeg"
        name = ""
        print(f"  using {image_path} ({len(data)/1024:.0f} KB)")
    else:
        data, mime, name = make_test_label(), "image/jpeg", "Jumbo rolled oats"
        print("  no image given: generated a synthetic oats label (370 kcal, 9 g fibre, 3.6 g beta-glucan)")
    t = time.time()
    try:
        food = extract_label(data, mime, name)
    except Exception as e:
        fail(f"after {time.time()-t:.1f}s: {type(e).__name__}: {e}")
    print(f"  ok in {time.time()-t:.1f}s")
    print(f"  name={food.get('name')!r} kcal={food.get('kcal')} fibre_g={food.get('fibre_g')} protein_g={food.get('protein_g')}")
    label = [k for k, m in food["extra_meta"].items() if m["source"] == "label"]
    est = [k for k, m in food["extra_meta"].items() if m["source"] == "estimate"]
    print(f"  from label: {label}")
    print(f"  estimated ({len(est)}): {est[:8]}{' …' if len(est) > 8 else ''}")
    print(f"  profile tags: {food['profile'].get('tags')}, feeds: {food['profile'].get('feeds')}")
    if food.get("notes"):
        print(f"  notes: {food['notes']}")
    if not image_path:
        ok = food.get("kcal") and abs(food["kcal"] - 370) < 5 and food.get("fibre_g") and abs(food["fibre_g"] - 9) < 0.5
        print("  values match the synthetic label" if ok else "  WARNING: values differ from the synthetic label; check the notes above")

    step("6. Name-only estimate (whole food, no label)")
    t = time.time()
    try:
        food = extract_label(None, None, "whole eggs")
    except Exception as e:
        fail(f"after {time.time()-t:.1f}s: {type(e).__name__}: {e}")
    print(f"  ok in {time.time()-t:.1f}s")
    print(f"  name={food.get('name')!r} serving={food.get('serving_size_g')} g ({food.get('serving_desc')}) "
          f"kcal={food.get('kcal')} protein_g={food.get('protein_g')}")
    print(f"  estimated attributes: {len(food['extra'])}")

    print("\nAll good. The app's Gemini path works from this shell. If the web app still hangs, restart uvicorn from this same shell.")


if __name__ == "__main__":
    main()
