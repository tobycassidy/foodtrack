import json
import db


def main():
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


if __name__ == "__main__":
    main()
