"""Backfill TCM energetics for foods that were saved before the feature existed.

The dataset file (default datasets/tcm_energetics.json, created by
`python dump_foods.py --tcm`) is the thing you version-control and review. This script
fills gaps in it and pushes it back into the database:

    python tcm_backfill.py status                 # how many foods / dataset records lack a value
    python tcm_backfill.py suggest                # fill blanks from the built-in reference table
    python tcm_backfill.py suggest --gemini       # ...and ask Gemini for whatever is still blank
    python tcm_backfill.py suggest --gemini --all # ask Gemini even for ones the table matched
    python tcm_backfill.py import                 # write dataset values into the DB (blank rows only)
    python tcm_backfill.py import --overwrite     # dataset wins over whatever is in the DB
    python tcm_backfill.py import --dry-run       # show what would change

Nothing in `suggest` touches the database: review the JSON (git diff is ideal), adjust any
values you disagree with, then `import`. Records are matched to DB rows by id, falling back
to (name, brand), so the same dataset can be imported into a rebuilt or copied database.
Set --file to use a different dataset path.
"""
import argparse
import json
import sys
from pathlib import Path

import db
import tcm as T
import tcm_reference as R
from dump_foods import DEFAULT_TCM_PATH, load_dataset, match_record, save_dataset, tcm_record


def _records_for_db(path: Path) -> tuple[dict, list[dict]]:
    data = load_dataset(path)
    if not data["foods"]:
        print(f"{path} is empty or missing; run `python dump_foods.py --tcm {path}` first.", file=sys.stderr)
        sys.exit(1)
    return data, data["foods"]


def cmd_status(args) -> None:
    foods = db.list_foods()
    missing_db = [f for f in foods if f.get("tcm_thermal") is None]
    print(f"Database: {len(foods)} foods, {len(missing_db)} without a TCM thermal value.")
    if args.file.exists():
        data = load_dataset(args.file)
        recs = data["foods"]
        missing_ds = [r for r in recs if r.get("tcm_thermal") is None]
        print(f"Dataset {args.file}: {len(recs)} records, {len(missing_ds)} without a value (exported {data.get('exported_at')}).")
        not_in_ds = [f["name"] for f in foods if match_record(recs, f) is None]
        if not_in_ds:
            print(f"  {len(not_in_ds)} DB foods not in the dataset yet (re-run dump_foods.py --tcm): "
                  + ", ".join(not_in_ds[:8]) + (" ..." if len(not_in_ds) > 8 else ""))
    else:
        print(f"Dataset {args.file} does not exist yet; run `python dump_foods.py --tcm`.")
    if missing_db and args.verbose:
        print("Missing in DB:")
        for f in missing_db:
            print(f"  {f['id']:>4}  {f['name']}" + (f" ({f['brand']})" if f.get("brand") else ""))


def _suggest_reference(records: list[dict], force: bool) -> int:
    n = 0
    for r in records:
        if r.get("tcm_thermal") is not None and not force:
            continue
        hit = R.lookup(r.get("name", ""))
        if not hit:
            continue
        thermal, flavours, note, key = hit
        r.update({"tcm_thermal": thermal, "flavours": flavours, "note": note,
                  "source": "reference-table", "confidence": "medium",
                  "matched": key})
        n += 1
    return n


def _suggest_gemini(records: list[dict], force: bool, batch: int = 25) -> int:
    """Ask Gemini to classify foods by name in batches; results marked source=gemini-estimate."""
    from pydantic import BaseModel, Field
    from typing import Literal
    from google import genai
    from google.genai import types
    import gemini_extract as G

    class Item(BaseModel):
        name: str
        thermal: float = Field(description="-2 cold, -1 cool, 0 neutral, +1 warm, +2 hot; half steps allowed")
        flavours: list[str] = Field(default_factory=list)
        organs: list[str] = Field(default_factory=list)
        note: str | None = None
        confidence: Literal["high", "medium", "low"] = "medium"

    class Batch(BaseModel):
        items: list[Item]

    todo = [r for r in records if (r.get("tcm_thermal") is None) or (force and r.get("source") != "manual")]
    if not todo:
        return 0
    client = genai.Client(http_options=types.HttpOptions(timeout=G.TIMEOUT_MS))
    config = types.GenerateContentConfig(response_mime_type="application/json", response_schema=Batch)
    done = 0
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        names = [f"- {r['name']}" + (f" ({r['brand']})" if r.get("brand") else "") for r in chunk]
        prompt = f"""You are a practitioner of Chinese dietary therapy. For each food below give its thermal
nature in Traditional Chinese Medicine on this scale: -2 cold, -1 cool, 0 neutral, +1 warm, +2 hot
(half steps allowed). Use the standard classifications (mung bean, watermelon, cucumber, crab, banana: cold;
most leafy greens, tofu, pear, barley, wheat: cool; rice, oats, eggs, pork, carrot, potato: neutral; chicken,
onion, walnut, salmon, cherry: warm; chilli, pepper, lamb, dried ginger, cinnamon: hot). For a branded or
composite product, weigh the main ingredients and the processing (roasting, frying, drying and spices warm;
raw, watery and chilled cool) and give a lower confidence. Also give the flavours (sweet, sour, bitter,
pungent, salty, bland), organ affinities and a one-sentence classical action.
Return one item per food, with `name` copied exactly as given (without the bracketed brand).

Foods:
{chr(10).join(names)}"""
        print(f"[gemini] classifying {len(chunk)} foods ({i + 1}-{i + len(chunk)} of {len(todo)})...")
        response, _model = G._generate_with_fallback(client, [prompt], config)
        parsed = Batch.model_validate_json(response.text)
        by_name = {it.name.strip().lower(): it for it in parsed.items}
        for r in chunk:
            it = by_name.get(r["name"].strip().lower())
            if it is None:  # tolerate small name drift: substring either way
                it = next((v for k, v in by_name.items() if k in r["name"].lower() or r["name"].lower() in k), None)
            if it is None:
                print(f"  no answer for: {r['name']}")
                continue
            r.update({"tcm_thermal": T.parse_thermal(it.thermal), "flavours": it.flavours, "organs": it.organs,
                      "note": it.note, "source": "gemini-estimate", "confidence": it.confidence})
            r.pop("matched", None)
            done += 1
    return done


def cmd_suggest(args) -> None:
    data, records = _records_for_db(args.file)
    before = sum(1 for r in records if r.get("tcm_thermal") is None)
    n_ref = 0 if args.gemini_only else _suggest_reference(records, force=False)
    n_gem = _suggest_gemini(records, force=args.all) if args.gemini else 0
    save_dataset(args.file, data)
    after = sum(1 for r in records if r.get("tcm_thermal") is None)
    print(f"Reference table filled {n_ref}, Gemini filled {n_gem}. Blank records: {before} -> {after}.")
    if after and not args.gemini:
        print("Re-run with --gemini to classify the rest, or edit the JSON by hand.")
    print(f"Review {args.file} (git diff), then `python tcm_backfill.py import`.")


def cmd_import(args) -> None:
    _data, records = _records_for_db(args.file)
    foods = db.list_foods()
    changed = skipped = unmatched = 0
    for r in records:
        if r.get("tcm_thermal") is None:
            continue
        food = next((f for f in foods if f["id"] == r.get("id") and f["name"].lower() == (r.get("name") or "").lower()), None)
        if food is None:
            food = db.find_food(r.get("name") or "", r.get("brand"))
        if food is None:
            unmatched += 1
            if args.verbose:
                print(f"  no DB row for: {r.get('name')}")
            continue
        new_thermal = T.parse_thermal(r["tcm_thermal"])
        new_tcm = {k: r[k] for k in ("flavours", "organs", "note", "source", "confidence") if r.get(k)}
        if food.get("tcm_thermal") is not None and not args.overwrite:
            skipped += 1
            continue
        if food.get("tcm_thermal") == new_thermal and (food.get("tcm") or {}) == new_tcm:
            continue
        print(f"  {food['id']:>4}  {food['name']:<40} {T.fmt(food.get('tcm_thermal')):>4} -> {T.fmt(new_thermal):>4}  [{new_tcm.get('source', '?')}]")
        if not args.dry_run:
            db.set_food_tcm(food["id"], new_thermal, new_tcm)
        changed += 1
    verb = "Would update" if args.dry_run else "Updated"
    print(f"{verb} {changed} foods; {skipped} already had a value (use --overwrite); {unmatched} dataset records had no DB row.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", type=Path, default=DEFAULT_TCM_PATH, help=f"dataset path (default {DEFAULT_TCM_PATH})")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="count missing values in DB and dataset").set_defaults(fn=cmd_status)
    s = sub.add_parser("suggest", help="fill blank dataset records (reference table, optionally Gemini)")
    s.add_argument("--gemini", action="store_true", help="ask Gemini for records still blank")
    s.add_argument("--gemini-only", action="store_true", help="skip the reference table")
    s.add_argument("--all", action="store_true", help="with --gemini: re-classify everything except manual values")
    s.set_defaults(fn=cmd_suggest)
    i = sub.add_parser("import", help="write dataset values into the database")
    i.add_argument("--overwrite", action="store_true", help="replace values already in the DB")
    i.add_argument("--dry-run", action="store_true")
    i.set_defaults(fn=cmd_import)

    args = ap.parse_args()
    db.init_db()
    args.fn(args)


if __name__ == "__main__":
    main()
