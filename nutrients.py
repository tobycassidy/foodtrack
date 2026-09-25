"""Canonical nutrient keys, units, groups and daily targets.

This one list drives three things:
  * the Gemini prompt (so estimates come back under consistent keys and can be summed),
  * the day report (% of target bars),
  * the edit form (labels and grouping).

Targets are EU/UK adult reference values (EU NRV, SACN fibre) as a starting point;
change them freely for your own goals. None means "track it, no target".
Everything is per day.
"""

# key, label, unit, group, daily target
REGISTRY = [
    # Fibre and prebiotic fractions: these are what the microbiome analysis leans on.
    ("fibre_soluble_g",      "Soluble fibre",        "g",  "fibre", 10),
    ("fibre_insoluble_g",    "Insoluble fibre",      "g",  "fibre", 20),
    ("beta_glucan_g",        "Beta-glucan",          "g",  "fibre", 3),
    ("resistant_starch_g",   "Resistant starch",     "g",  "fibre", 15),
    ("inulin_fructans_g",    "Inulin / fructans",    "g",  "fibre", 5),
    ("pectin_g",             "Pectin",               "g",  "fibre", None),
    ("polyphenols_mg",       "Polyphenols",          "mg", "fibre", 1000),

    # Carbohydrate quality, for glycogen and energy pacing.
    ("starch_g",             "Starch",               "g",  "carbs", None),
    ("slow_carbs_g",         "Slow-digesting carbs", "g",  "carbs", None),
    ("fast_carbs_g",         "Fast-digesting carbs", "g",  "carbs", None),

    # Fats
    ("omega3_g",             "Omega-3 (total)",      "g",  "fats", 2),
    ("epa_dha_mg",           "EPA + DHA",            "mg", "fats", 250),
    ("omega6_g",             "Omega-6",              "g",  "fats", None),
    ("mufa_g",               "Monounsaturated fat",  "g",  "fats", None),

    # Amino acids of interest for training
    ("leucine_g",            "Leucine",              "g",  "protein", 3),
    ("glycine_g",            "Glycine",              "g",  "protein", None),

    # Vitamins (EU NRV)
    ("vitamin_a_ug",         "Vitamin A",            "µg", "vitamins", 800),
    ("vitamin_c_mg",         "Vitamin C",            "mg", "vitamins", 80),
    ("vitamin_d_ug",         "Vitamin D",            "µg", "vitamins", 10),
    ("vitamin_e_mg",         "Vitamin E",            "mg", "vitamins", 12),
    ("vitamin_k_ug",         "Vitamin K",            "µg", "vitamins", 75),
    ("thiamin_b1_mg",        "Thiamin (B1)",         "mg", "vitamins", 1.1),
    ("riboflavin_b2_mg",     "Riboflavin (B2)",      "mg", "vitamins", 1.4),
    ("niacin_b3_mg",         "Niacin (B3)",          "mg", "vitamins", 16),
    ("pantothenic_b5_mg",    "Pantothenic acid (B5)","mg", "vitamins", 6),
    ("vitamin_b6_mg",        "Vitamin B6",           "mg", "vitamins", 1.4),
    ("biotin_b7_ug",         "Biotin (B7)",          "µg", "vitamins", 50),
    ("folate_b9_ug",         "Folate (B9)",          "µg", "vitamins", 200),
    ("vitamin_b12_ug",       "Vitamin B12",          "µg", "vitamins", 2.5),
    ("choline_mg",           "Choline",              "mg", "vitamins", 400),

    # Minerals (EU NRV)
    ("calcium_mg",           "Calcium",              "mg", "minerals", 800),
    ("iron_mg",              "Iron",                 "mg", "minerals", 14),
    ("magnesium_mg",         "Magnesium",            "mg", "minerals", 375),
    ("zinc_mg",              "Zinc",                 "mg", "minerals", 10),
    ("selenium_ug",          "Selenium",             "µg", "minerals", 55),
    ("copper_mg",            "Copper",               "mg", "minerals", 1),
    ("manganese_mg",         "Manganese",            "mg", "minerals", 2),
    ("potassium_mg",         "Potassium",            "mg", "minerals", 3500),
    ("phosphorus_mg",        "Phosphorus",           "mg", "minerals", 700),
    ("iodine_ug",            "Iodine",               "µg", "minerals", 150),
    ("sodium_mg",            "Sodium",               "mg", "minerals", None),

    # Other bioactives
    ("carotenoids_mg",       "Carotenoids",          "mg", "bioactives", None),
    ("lycopene_mg",          "Lycopene",             "mg", "bioactives", None),
    ("collagen_g",           "Collagen",             "g",  "bioactives", None),
    ("probiotic_cfu_log10",  "Live cultures (log10 CFU)", "", "bioactives", None),
]

GROUPS = [
    ("fibre", "Fibre and prebiotics"),
    ("carbs", "Carbohydrate quality"),
    ("fats", "Fats"),
    ("protein", "Amino acids"),
    ("vitamins", "Vitamins"),
    ("minerals", "Minerals"),
    ("bioactives", "Other bioactives"),
]

# Targets for the core label nutrients (per day). Adjust to your own plan.
CORE_TARGETS = {
    "kcal": 2500,
    "protein_g": 150,
    "carbs_g": 300,
    "fat_g": 80,
    "sat_fat_g": 25,
    "sugars_g": 60,
    "fibre_g": 30,
    "salt_g": 6,
}

BY_KEY = {r[0]: {"label": r[1], "unit": r[2], "group": r[3], "target": r[4]} for r in REGISTRY}
KEYS = [r[0] for r in REGISTRY]

# Keys that are not additive across foods (an index, not an amount). Stored in
# food.profile, never summed.
PROFILE_FIELDS = [
    ("glycemic_index", "Glycaemic index (estimate)"),
    ("fermentability", "Fermentability of fibre (low / medium / high)"),
    ("processing_level", "Processing (NOVA 1–4)"),
]


def label_for(key: str) -> str:
    if key in BY_KEY:
        return BY_KEY[key]["label"]
    return key.replace("_", " ")


def unit_for(key: str) -> str:
    if key in BY_KEY:
        return BY_KEY[key]["unit"]
    tail = key.rsplit("_", 1)[-1]
    return {"g": "g", "mg": "mg", "ug": "µg"}.get(tail, "")
