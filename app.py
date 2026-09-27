"""FoodTrack: a small personal food logger.

Run:  uvicorn app:app --host 0.0.0.0 --port 8000 --reload
Then open http://<laptop-ip>:8000 on your phone.
"""
import csv
import io
import uuid
from datetime import date, datetime
from pathlib import Path

from fastapi import FastAPI, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import db
import nutrients as N
from gemini_extract import extract_label, summarize_nutrition

BASE = Path(__file__).parent
app = FastAPI(title="FoodTrack")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")
templates.env.globals["NUTRIENTS"] = db.NUTRIENTS
templates.env.globals["MEALS"] = db.MEALS
templates.env.globals["N"] = N
templates.env.filters["dateord"] = lambda n: date.fromordinal(n).isoformat()


@app.on_event("startup")
def _startup() -> None:
    db.init_db()
    app.mount("/labels", StaticFiles(directory=db.IMAGE_DIR), name="labels")


def _num(v: str | None) -> float | None:
    v = (v or "").strip().replace(",", ".")
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _food_from_form(form) -> dict:
    """Parse the review/edit form, including dynamic extra-attribute rows."""
    data = {
        "name": form.get("name", "").strip(),
        "brand": form.get("brand", "").strip() or None,
        "serving_size_g": _num(form.get("serving_size_g")),
        "serving_desc": form.get("serving_desc", "").strip() or None,
        "label_image": form.get("label_image") or None,
        "source": form.get("source") or "manual",
    }
    for col in db.NUTRIENT_COLS:
        data[col] = _num(form.get(col))
    extra, meta = {}, {}
    rows = zip(form.getlist("extra_key"), form.getlist("extra_value"),
               form.getlist("extra_source"), form.getlist("extra_confidence"), form.getlist("extra_basis"))
    for key, val, source, conf, basis in rows:
        key = key.strip().replace(" ", "_").lower()
        num = _num(val)
        if key and num is not None:
            extra[key] = num
            meta[key] = {"source": source or "manual", "confidence": conf or "high", "basis": basis or None}
    data["extra"], data["extra_meta"] = extra, meta

    profile = {}
    for key, _label in N.PROFILE_FIELDS:
        v = form.get(f"profile_{key}", "").strip()
        if v:
            profile[key] = int(v) if v.isdigit() else v
    for key in ("fibre_types", "feeds", "tags", "notable_compounds"):
        v = [x.strip() for x in form.get(f"profile_{key}", "").split(",") if x.strip()]
        if v:
            profile[key] = v
    for key in ("training_note", "microbiome_note"):
        v = form.get(f"profile_{key}", "").strip()
        if v:
            profile[key] = v
    data["profile"] = profile
    return data


# ---------- today / log ----------

@app.get("/", response_class=HTMLResponse)
def index(request: Request, day: str | None = None, log: int | None = None):
    d = date.fromisoformat(day) if day else date.today()
    entries, totals = db.day_log(d)
    return templates.TemplateResponse(request, "index.html", {
        "day": d, "day_label": f"{d:%A} {d.day} {d:%B}", "entries": entries, "totals": totals,
        "recent": db.search_foods("", limit=8),
        "prefill": db.get_food(log) if log else None,
    })


@app.get("/search", response_class=HTMLResponse)
def search(request: Request, q: str = ""):
    return templates.TemplateResponse(request, "_results.html", {
        "foods": db.search_foods(q), "q": q,
    })


@app.post("/log")
async def log(request: Request):
    """Log a whole meal at once: parallel food_id[] / grams[] lists plus one meal name."""
    form = await request.form()
    day, meal, note = form.get("day", ""), form.get("meal", "snack"), form.get("note", "").strip() or None
    items = []
    for fid, g in zip(form.getlist("food_id"), form.getlist("grams")):
        grams = _num(g)
        if fid and grams:
            items.append((int(fid), grams))
    logged_at = None
    if day and day != date.today().isoformat():
        logged_at = f"{day} {datetime.now().strftime('%H:%M:%S')}"
    if items:
        db.add_logs(items, meal, note, logged_at)
    return RedirectResponse(f"/?day={day}" if day else "/", status_code=303)


@app.post("/summary")
async def summary(request: Request):
    """Generate a Gemini summary for a specific scope (daily, meal, or basket)."""
    data = await request.json()
    scope = data.get("scope")
    day = data.get("day")
    meal = data.get("meal")
    basket = data.get("basket", [])

    agg = {"scope": scope, "foods": []}
    for c in db.NUTRIENT_COLS:
        agg[c] = 0.0
    agg["extra"] = {}

    if scope in ("daily", "meal") and day:
        d = date.fromisoformat(day)
        entries, totals = db.day_log(d)
        if scope == "daily":
            for c in db.NUTRIENT_COLS:
                agg[c] = totals.get(c, 0.0)
            agg["extra"] = totals.get("extra", {})
            agg["foods"] = [e["name"] for e in entries]
        else:
            mtotals = totals["meals"].get(meal, db._empty_totals())
            for c in db.NUTRIENT_COLS:
                agg[c] = mtotals.get(c, 0.0)
            agg["extra"] = mtotals.get("extra", {})
            agg["foods"] = [e["name"] for e in entries if e["meal"] == meal]
    elif scope == "basket":
        for item in basket:
            food = db.get_food(int(item["id"]))
            if not food:
                continue
            grams = float(item["grams"] or 0)
            factor = grams / 100.0
            agg["foods"].append(food["name"])
            for c in db.NUTRIENT_COLS:
                if food.get(c) is not None:
                    agg[c] += food[c] * factor
            for k, v in food.get("extra", {}).items():
                if isinstance(v, (int, float)):
                    agg["extra"][k] = agg["extra"].get(k, 0.0) + v * factor

    try:
        text = summarize_nutrition(agg)
    except Exception as e:
        text = f"Error generating summary: {e}"
    return {"summary": text}


@app.get("/report", response_class=HTMLResponse)
def report(request: Request, day: str | None = None):
    d = date.fromisoformat(day) if day else date.today()
    entries, totals = db.day_log(d)
    macro_kcal = {"protein": totals["protein_g"] * 4, "carbs": totals["carbs_g"] * 4, "fat": totals["fat_g"] * 9}
    macro_sum = sum(macro_kcal.values()) or 1
    groups = []
    for gkey, gtitle in N.GROUPS:
        rows = []
        for k in N.KEYS:
            if N.BY_KEY[k]["group"] != gkey or k not in totals["extra"]:
                continue
            v, t = totals["extra"][k], N.BY_KEY[k]["target"]
            rows.append({"key": k, "label": N.BY_KEY[k]["label"], "unit": N.BY_KEY[k]["unit"],
                         "value": v, "target": t, "pct": (v / t * 100) if t else None})
        if rows:
            groups.append((gtitle, rows))
    unknown = sorted(k for k in totals["extra"] if k not in N.BY_KEY)
    return templates.TemplateResponse(request, "report.html", {
        "day": d, "day_label": f"{d:%A} {d.day} {d:%B}", "entries": entries, "totals": totals,
        "macro_kcal": macro_kcal, "macro_pct": {k: v / macro_sum * 100 for k, v in macro_kcal.items()},
        "groups": groups, "unknown": unknown, "core_targets": N.CORE_TARGETS,
    })


@app.post("/log/{entry_id}/delete")
def log_delete(entry_id: int, day: str = Form("")):
    db.delete_log(entry_id)
    return RedirectResponse(f"/?day={day}" if day else "/", status_code=303)


# ---------- foods ----------

@app.get("/foods", response_class=HTMLResponse)
def foods(request: Request):
    return templates.TemplateResponse(request, "foods.html", {"foods": db.list_foods()})


@app.get("/foods/new", response_class=HTMLResponse)
def food_new(request: Request, name: str = ""):
    return templates.TemplateResponse(request, "food_new.html", {"name": name, "error": None})


@app.post("/foods/extract", response_class=HTMLResponse)
async def food_extract(request: Request, name: str = Form(""), photo: UploadFile | None = None):
    """With a photo: read the label and estimate the rest. Without: estimate everything from the name."""
    name = name.strip()
    image_bytes, mime, filename = None, None, None
    if photo is not None and photo.filename:
        image_bytes = await photo.read()
        mime = photo.content_type or "image/jpeg"
        ext = {"image/png": ".png", "image/webp": ".webp", "image/heic": ".heic"}.get(mime, ".jpg")
        filename = f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}{ext}"
        (db.IMAGE_DIR / filename).write_bytes(image_bytes)
    if image_bytes is None and not name:
        return templates.TemplateResponse(request, "food_new.html", {
            "name": "", "error": "Give a name, a label photo, or both."})

    error = None
    try:
        food = extract_label(image_bytes, mime, name)
    except Exception as exc:  # show the error on the form rather than a 500
        error = f"Gemini extraction failed: {exc}"
        food = {"name": name, "extra": {}, "extra_meta": {}, "profile": {}}
    if name and not food.get("name"):
        food["name"] = name
    food["label_image"] = filename
    food["source"] = "gemini-label" if image_bytes else "gemini-estimate"
    return templates.TemplateResponse(request, "food_form.html", {
        "food": food, "food_id": None, "error": error, "notes": food.get("notes"),
        "title": "Check the extracted values" if image_bytes else "Check the estimated values",
        "estimated_all": image_bytes is None,
    })


@app.get("/foods/manual", response_class=HTMLResponse)
def food_manual(request: Request, name: str = ""):
    return templates.TemplateResponse(request, "food_form.html", {
        "food": {"name": name, "extra": {}, "extra_meta": {}, "profile": {}}, "food_id": None, "error": None,
        "notes": None, "title": "Enter values by hand",
    })


@app.post("/foods")
async def food_create(request: Request):
    form = await request.form()
    data = _food_from_form(form)
    if not data["name"]:
        return templates.TemplateResponse(request, "food_form.html", {
            "food": data, "food_id": None, "error": "A name is required.",
            "notes": None, "title": "Check the extracted values",
        })
    food_id = db.save_food(data)
    return RedirectResponse(f"/?log={food_id}", status_code=303)


@app.get("/foods/{food_id}/edit", response_class=HTMLResponse)
def food_edit(request: Request, food_id: int):
    food = db.get_food(food_id)
    return templates.TemplateResponse(request, "food_form.html", {
        "food": food, "food_id": food_id, "error": None, "notes": None, "title": "Edit food",
    })


@app.post("/foods/{food_id}")
async def food_update(request: Request, food_id: int):
    form = await request.form()
    db.save_food(_food_from_form(form), food_id)
    return RedirectResponse("/foods", status_code=303)


@app.post("/foods/{food_id}/delete")
def food_delete(food_id: int):
    db.delete_food(food_id)
    return RedirectResponse("/foods", status_code=303)


# ---------- export ----------

@app.get("/export.csv")
def export_csv():
    rows = db.export_rows()
    buf = io.StringIO()
    if rows:
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    buf.seek(0)
    return StreamingResponse(buf, media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=foodtrack.csv"})
