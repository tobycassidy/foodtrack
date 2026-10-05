"""A small reference table of common foods' thermal natures, for backfilling offline.

Values follow the mainstream Chinese dietetic classifications (Pitchford, Flaws, Kastner and
the standard TCM food-therapy tables broadly agree on these). Sources disagree at the edges
(e.g. tomato is listed cool or neutral; cooked oats neutral or warm), so each entry is a
sensible middle value with a one-line action. Treat these as starting points to review in
the dataset file, not as gospel. Anything not here goes to Gemini (`tcm_backfill.py suggest`).

Scale: -2 cold, -1 cool, 0 neutral, +1 warm, +2 hot.
"""

# keyword(s) matched against the food name (lower-cased, substring) -> (thermal, flavours, note)
# More specific keys must come before general ones: "sweet potato" before "potato".
REFERENCE = [
    # ---- cold (-2) ----
    (["watermelon"],                     -2, ["sweet"],            "clears summer heat, promotes urination"),
    (["mung bean", "mung"],              -2, ["sweet"],            "clears heat and toxins, drains damp"),
    (["cucumber"],                       -2, ["sweet"],            "clears heat, quenches thirst"),
    (["banana"],                         -2, ["sweet"],            "clears heat, moistens the intestines"),
    (["crab"],                           -2, ["salty"],            "clears heat, moves blood"),
    (["seaweed", "kelp", "nori", "kombu", "wakame"], -2, ["salty"], "softens hardness, clears heat and phlegm"),
    (["bitter melon", "bitter gourd"],   -2, ["bitter"],           "clears heat and summer heat"),
    (["grapefruit"],                     -2, ["sweet", "sour"],    "clears heat, moves qi, resolves phlegm"),
    (["persimmon"],                      -2, ["sweet"],            "clears heat, moistens the lung"),
    (["kiwi"],                           -2, ["sweet", "sour"],    "clears heat, promotes urination"),
    (["tomato"],                        -1.5, ["sweet", "sour"],   "clears heat, generates fluids"),
    (["lettuce"],                       -1.5, ["bitter", "sweet"], "clears heat, promotes urination"),
    (["celery"],                        -1.5, ["sweet", "bitter"], "clears heat, calms the liver"),
    (["pear"],                          -1.5, ["sweet"],           "moistens the lung, clears heat"),
    (["yoghurt", "yogurt", "skyr", "kefir"], -1, ["sour", "sweet"], "moistens, cooling to the stomach; damp-forming in excess"),
    (["spinach"],                        -1, ["sweet"],            "nourishes blood, moistens dryness"),
    (["tofu", "soy milk", "soya milk"],  -1, ["sweet"],            "clears heat, moistens dryness"),
    (["barley"],                         -1, ["sweet", "salty"],   "strengthens the spleen, drains damp"),
    (["wheat", "bread", "pasta", "noodle", "couscous", "flour", "cracker", "bagel", "wrap", "tortilla"], -1, ["sweet"], "nourishes the heart, calms the spirit; damp-forming if refined"),
    (["buckwheat"],                      -1, ["sweet"],            "descends qi, clears heat"),
    (["millet"],                         -1, ["sweet", "salty"],   "strengthens the spleen, clears heat"),
    (["apple"],                          -1, ["sweet", "sour"],    "generates fluids, moistens the lung"),
    (["orange", "mandarin", "clementine", "satsuma"], -1, ["sweet", "sour"], "generates fluids, moves qi"),
    (["lemon", "lime"],                  -1, ["sour"],             "generates fluids, resolves phlegm"),
    (["strawberr"],                      -1, ["sweet", "sour"],    "moistens the lung, generates fluids"),
    (["blueberr", "bilberr"],            -1, ["sweet", "sour"],    "nourishes yin, benefits the eyes"),
    (["mango"],                          -1, ["sweet", "sour"],    "generates fluids, stops thirst"),
    (["pineapple"],                      -1, ["sweet", "sour"],    "clears summer heat, aids digestion"),
    (["melon", "cantaloupe", "honeydew"], -1, ["sweet"],           "clears heat, quenches thirst"),
    (["broccoli"],                       -1, ["sweet", "bitter"],  "clears heat, brightens the eyes"),
    (["cauliflower"],                    -1, ["sweet"],            "strengthens the spleen mildly"),
    (["courgette", "zucchini", "marrow", "squash"], -1, ["sweet"], "clears heat, promotes urination"),
    (["aubergine", "eggplant"],          -1, ["sweet"],            "clears heat, moves blood"),
    (["mushroom", "shiitake"],           -1, ["sweet"],            "tonifies qi, resolves phlegm"),
    (["asparagus"],                      -1, ["sweet", "bitter"],  "clears heat, promotes urination"),
    (["pea", "peas"],                     0, ["sweet"],            "harmonises the middle, drains damp"),
    (["avocado"],                        -1, ["sweet"],            "nourishes blood and yin, moistens"),
    (["cottage cheese", "cream cheese", "mozzarella", "feta"], -1, ["sweet", "sour"], "moistens, nourishes yin; damp-forming"),
    (["milk"],                           -0.5, ["sweet"],          "nourishes yin, moistens dryness; damp-forming"),
    (["duck"],                           -0.5, ["sweet", "salty"], "nourishes yin, benefits the stomach"),
    (["rabbit"],                         -0.5, ["sweet"],          "tonifies qi, cools"),
    (["pork"],                           -0.5, ["sweet", "salty"], "nourishes yin and blood, moistens dryness"),
    (["white fish", "cod", "haddock", "pollock", "sea bass", "tilapia", "plaice"], 0, ["sweet"], "tonifies qi and blood"),
    (["egg"],                             0, ["sweet"],            "nourishes yin and blood, calms the spirit"),
    (["rice", "congee"],                  0, ["sweet"],            "tonifies the spleen and stomach qi"),
    (["potato"],                          0, ["sweet"],            "tonifies spleen qi, harmonises the stomach"),
    (["corn", "maize", "polenta", "sweetcorn"], 0, ["sweet"],      "tonifies the middle, drains damp"),
    (["carrot"],                          0, ["sweet"],            "strengthens the spleen, brightens the eyes"),
    (["cabbage"],                         0, ["sweet"],            "harmonises the stomach, benefits the kidney"),
    (["kale"],                            0, ["sweet", "bitter"],  "strengthens the stomach, clears heat mildly"),
    (["beetroot", "beet"],                0, ["sweet"],            "nourishes blood, moves blood"),
    (["green bean", "french bean", "string bean"], 0, ["sweet"],   "tonifies the spleen and kidney"),
    (["lentil"],                          0, ["sweet"],            "strengthens the spleen, tonifies qi"),
    (["chickpea", "hummus", "houmous"],   0, ["sweet"],            "strengthens the spleen, drains damp"),
    (["kidney bean", "black bean", "pinto", "haricot", "cannellini", "butter bean", "edamame", "soy bean", "soya bean"], 0, ["sweet"], "tonifies the spleen and kidney, drains damp"),
    (["peanut"],                          0, ["sweet"],            "moistens the lung, harmonises the stomach"),
    (["almond"],                          0, ["sweet"],            "moistens the lung, moistens the intestines"),
    (["cashew"],                          0, ["sweet"],            "tonifies the kidney, moistens"),
    (["sesame", "tahini"],                0, ["sweet"],            "nourishes liver and kidney yin, moistens"),
    (["sunflower seed", "pumpkin seed", "flax", "linseed", "chia", "hemp"], 0, ["sweet"], "moistens the intestines, nourishes"),
    (["olive oil", "olive"],              0, ["sweet"],            "moistens, clears heat mildly"),
    (["honey"],                           0, ["sweet"],            "tonifies the middle, moistens dryness"),
    (["grape", "raisin", "sultana"],      0, ["sweet", "sour"],    "tonifies qi and blood, strengthens sinews"),
    (["fig"],                             0, ["sweet"],            "moistens the lung and intestines"),
    (["plum", "prune"],                   0, ["sweet", "sour"],    "generates fluids, moistens the intestines"),
    (["apricot"],                         0, ["sweet", "sour"],    "moistens the lung, generates fluids"),
    (["tuna", "mackerel", "sardine", "anchov", "herring", "trout"], 0.5, ["sweet", "salty"], "tonifies qi and blood, strengthens the kidney"),
    (["beef"],                           0.5, ["sweet"],           "tonifies spleen and stomach qi, strengthens sinews and bones"),
    (["turkey"],                         0.5, ["sweet"],           "tonifies qi, warms the middle mildly"),
    (["sweet potato", "yam"],            0.5, ["sweet"],           "tonifies spleen qi, generates fluids"),
    (["pumpkin", "butternut"],           0.5, ["sweet"],           "tonifies the middle, drains damp"),
    (["oat", "porridge"],                0.5, ["sweet"],           "tonifies qi, strengthens the spleen"),
    (["quinoa"],                         0.5, ["sweet", "sour"],   "tonifies qi, warms the middle mildly"),
    (["cherry"],                           1, ["sweet"],           "tonifies qi and blood, warms the middle"),
    (["peach", "nectarine"],               1, ["sweet", "sour"],   "generates fluids, moves blood"),
    (["raspberr", "blackberr"],            1, ["sweet", "sour"],   "tonifies the kidney, astringes"),
    (["date", "medjool", "jujube"],        1, ["sweet"],           "tonifies spleen qi and blood, calms the spirit"),
    (["chicken"],                          1, ["sweet"],           "tonifies qi and blood, warms the middle"),
    (["salmon"],                           1, ["sweet"],           "tonifies qi and blood, warms the middle"),
    (["prawn", "shrimp"],                  1, ["sweet", "salty"],  "tonifies kidney yang"),
    (["mussel"],                           1, ["salty"],           "tonifies liver and kidney"),
    (["walnut"],                           1, ["sweet"],           "tonifies kidney yang, warms the lung"),
    (["pistachio", "pecan", "hazelnut", "macadamia", "brazil nut"], 1, ["sweet"], "tonifies qi and kidney, warms"),
    (["coconut"],                          1, ["sweet"],           "tonifies qi, warms the middle"),
    (["onion", "shallot", "spring onion", "scallion"], 1, ["pungent", "sweet"], "warms the middle, moves qi, resolves phlegm"),
    (["leek"],                             1, ["pungent"],         "warms the middle, moves qi and blood"),
    (["garlic"],                           1, ["pungent"],         "warms the middle, dispels cold, kills parasites"),
    (["fresh ginger", "ginger"],           1, ["pungent"],         "warms the middle, dispels cold, stops nausea"),
    (["fennel"],                           1, ["pungent", "sweet"], "warms the kidney, moves qi"),
    (["basil", "rosemary", "thyme", "oregano", "dill", "coriander", "cilantro"], 1, ["pungent"], "moves qi, warms, releases the exterior"),
    (["coffee"],                           1, ["bitter"],          "warms, moves qi, dries; drains kidney yin in excess"),
    (["butter", "ghee"],                   1, ["sweet"],           "tonifies qi and blood, moistens; damp-forming"),
    (["cheese", "cheddar", "parmesan", "brie", "gouda"], 0.5, ["sweet", "sour"], "nourishes yin, moistens; damp- and phlegm-forming"),
    (["chocolate", "cocoa", "cacao"],      1, ["bitter", "sweet"], "warms, moves qi and blood; stimulating"),
    (["lamb", "mutton"],                   2, ["sweet"],           "tonifies qi and yang, warms the middle, dispels cold"),
    (["venison"],                        1.5, ["sweet"],           "tonifies kidney yang, warms"),
    (["chilli", "chili", "cayenne", "jalape", "sriracha", "hot sauce", "tabasco"], 2, ["pungent"], "warms the middle, dispels cold, strongly moving"),
    (["black pepper", "white pepper", "peppercorn"], 2, ["pungent"], "warms the middle, dispels cold"),
    (["dried ginger"],                     2, ["pungent"],         "warms the middle and the lung, dispels cold"),
    (["cinnamon", "cassia"],               2, ["pungent", "sweet"], "warms kidney yang, dispels cold, moves blood"),
    (["clove"],                            2, ["pungent"],         "warms the middle and kidney, descends rebellious qi"),
    (["nutmeg"],                           2, ["pungent"],         "warms the middle, astringes the intestines"),
    (["mustard", "wasabi", "horseradish"], 2, ["pungent"],         "warms the lung, resolves phlegm"),
    (["cumin", "cardamom", "star anise", "fenugreek", "turmeric", "curry"], 1.5, ["pungent"], "warms the middle, moves qi and blood"),
    (["alcohol", "wine", "beer", "whisky", "vodka", "gin", "rum", "lager", "cider"], 2, ["pungent", "sweet", "bitter"], "warms, moves blood; damp-heat forming in excess"),
    (["ice cream", "gelato", "sorbet"],   -2, ["sweet"],           "cold and damp-forming; injures spleen yang"),
]


def lookup(name: str) -> tuple[float, list[str], str, str] | None:
    """Return (thermal, flavours, note, matched_keyword) for the first reference entry whose
    keyword appears in the name. Longer keywords are checked first so 'sweet potato' beats
    'potato' and 'dried ginger' beats 'ginger'."""
    n = (name or "").lower()
    best = None
    for keys, thermal, flavours, note in REFERENCE:
        for k in keys:
            if k in n and (best is None or len(k) > len(best[3])):
                best = (float(thermal), list(flavours), note, k)
    return best
