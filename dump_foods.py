"""Inspect the food database, or dump it to JSON you can keep in git.

    python dump_foods.py                         # human-readable listing (now with the TCM line)
    python dump_foods.py --json foods.json       # full dump of every food, every field
    python dump_foods.py --tcm datasets/tcm_energetics.json
                                                 # slim TCM dataset: one record per food with name,
                                                 # brand, thermal, flavours, organs, note, source.
                                                 # This is the file you edit / review and feed back
                                                 # in with `python tcm_backfill.py import`.

The --tcm export merges with an existing file: values already in the file are kept unless
--refresh is given, so a half-reviewed dataset is never clobbered by a re-export. Records
are matched to DB rows by id first, then by (name, brand), so the dataset survives a
rebuilt database.
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

import db
import tcm as T

DEFAULT_TCM_PATH = Path("datasets/tcm_energetics.json")


def tcm_record(f: dict) -> dict:
    t = f.get("tcm") or {}
    return {
        "id": f["id"],
        "name": f["name"],
        "brand": f.get("brand"),
        "tcm_thermal": f.get("tcm_thermal"),
        "flavours": t.get("flavours", []),
        "organs": t.get("organs", []),
        "note": t.get("note"),
        "source": t.get("source"),
        "confidence": t.get("confidence"),
    }


def load_dataset(path: Path) -> dict:
    if not path.exists():
        return {"scale": "-2 cold, -1 cool, 0 neutral, +1 warm, +2 hot (half steps allowed)",
                "exported_at": None, "foods": []}
    return json.loads(path.read_text())


def save_dataset(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data["foods"].sort(key=lambda r: ((r.get("name") or "").lower(), (r.get("brand") or "").lower()))
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def match_record(records: list[dict], f: dict) -> dict | None:
    by_id = next((r for r in records if r.get("id") == f["id"]), None)
    if by_id and (by_id.get("name") or "").lower() == f["name"].lower():
        return by_id
    key = (f["name"].lower(), (f.get("brand") or "").lower())
    return next((r for r in records if ((r.get("name") or "").lower(), (r.get("brand") or "").lower()) == key), None)


def export_tcm(path: Path, refresh: bool = False) -> None:
    data = load_dataset(path)
    records = data["foods"]
    added = kept = updated = 0
    for f in db.list_foods():
        fresh = tcm_record(f)
        existing = match_record(records, f)
        if existing is None:
            records.append(fresh)
            added += 1
        elif refresh or existing.get("tcm_thermal") is None:
            if existing.get("tcm_thermal") is None and fresh["tcm_thermal"] is None:
                existing["id"], existing["brand"] = f["id"], f.get("brand")  # keep in sync, nothing to fill
                kept += 1
                continue
            existing.update(fresh)
            updated += 1
        else:
            existing["id"] = f["id"]  # dataset value wins; keep id current
            kept += 1
    data["exported_at"] = datetime.now().isoformat(timespec="seconds")
    save_dataset(path, data)
    missing = sum(1 for r in records if r.get("tcm_thermal") is None)
    print(f"{path}: {len(records)} foods ({added} added, {updated} updated from DB, {kept} kept); {missing} still without a thermal value.")


def export_json(path: Path) -> None:
    foods = db.list_foods()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"exported_at": datetime.now().isoformat(timespec="seconds"), "foods": foods},
                               indent=2, ensure_ascii=False) + "\n")
    print(f"{path}: {len(foods)} foods written.")


def print_listing() -> None:
    foods = db.list_foods()
    if not foods:
        print("No foods found in the database.")
        return

    print(f"Total foods in database: {len(foods)}\n" + "=" * 60)
    for f in foods:
        brand_str = f" ({f['brand']})" if f.get("brand") else ""
        print(f"\nID {f['id']}: {f['name']}{brand_str}")
        print(f"  Serving: {f.get('serving_size_g')}g ({f.get('serving_desc')})")
        print(
            f"  Macros (per 100g): {f.get('kcal')} kcal | "
            f"P: {f.get('protein_g')}g | C: {f.get('carbs_g')}g (sugars: {f.get('sugars_g')}g) | "
            f"F: {f.get('fat_g')}g (sat: {f.get('sat_fat_g')}g) | "
            f"Fibre: {f.get('fibre_g')}g | Salt: {f.get('salt_g')}g"
        )

        extra = f.get("extra") or {}
        if extra:
            populated_extra = [f"{k}={v}" for k, v in extra.items() if v is not None]
            print(f"  Extra ({len(populated_extra)} fields): {', '.join(populated_extra)}")
        else:
            print("  Extra: None")

        profile = f.get("profile") or {}
        if profile:
            populated_profile = {k: v for k, v in profile.items() if v}
            print(f"  Profile: {json.dumps(populated_profile, ensure_ascii=False)}")
        else:
            print("  Profile: None")

        t = f.get("tcm") or {}
        if f.get("tcm_thermal") is not None:
            bits = [f"{T.fmt(f['tcm_thermal'])} {T.band(f['tcm_thermal'])['label'].lower()}"]
            if t.get("flavours"):
                bits.append("flavours: " + ", ".join(t["flavours"]))
            if t.get("note"):
                bits.append(t["note"])
            if t.get("source"):
                bits.append(f"[{t['source']}{' · ' + t['confidence'] if t.get('confidence') else ''}]")
            print("  TCM: " + " | ".join(bits))
        else:
            print("  TCM: not assessed")

    missing = sum(1 for f in foods if f.get("tcm_thermal") is None)
    print("\n" + "=" * 60 + f"\n{missing} of {len(foods)} foods have no TCM thermal value.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", metavar="PATH", type=Path, help="write every food with every field to PATH")
    ap.add_argument("--tcm", metavar="PATH", type=Path, nargs="?", const=DEFAULT_TCM_PATH,
                    help=f"write/merge the slim TCM dataset (default {DEFAULT_TCM_PATH})")
    ap.add_argument("--refresh", action="store_true", help="with --tcm: overwrite dataset values with the DB's")
    args = ap.parse_args()

    db.init_db()
    if args.json:
        export_json(args.json)
    if args.tcm:
        export_tcm(args.tcm, refresh=args.refresh)
    if not args.json and not args.tcm:
        print_listing()


if __name__ == "__main__":
    main()
