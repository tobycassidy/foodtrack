"""SQLite storage for foods and the daily log.

All nutrient values on a food are stored PER 100 g, so any portion is a
simple multiplication. Anything beyond the core nutrients lives in the
`extra` JSON column, e.g. {"fibre_soluble_g": 1.2, "fibre_insoluble_g": 2.8}.
"""
import json
import os
import sqlite3
from datetime import date
from pathlib import Path

DATA_DIR = Path(os.environ.get("FOODTRACK_DATA", "./data"))
DB_PATH = DATA_DIR / "food.db"
IMAGE_DIR = DATA_DIR / "labels"

# (column, label shown in the UI, unit). Order is the display order everywhere.
NUTRIENTS = [
    ("kcal", "Energy", "kcal"),
    ("fat_g", "Fat", "g"),
    ("sat_fat_g", "of which saturates", "g"),
    ("carbs_g", "Carbohydrate", "g"),
    ("sugars_g", "of which sugars", "g"),
    ("fibre_g", "Fibre", "g"),
    ("protein_g", "Protein", "g"),
    ("salt_g", "Salt", "g"),
]
NUTRIENT_COLS = [n[0] for n in NUTRIENTS]
MEALS = ["breakfast", "lunch", "dinner", "snack", "pre-workout", "post-workout"]

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS foods (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    brand           TEXT,
    serving_size_g  REAL,
    serving_desc    TEXT,
    {', '.join(f'{c} REAL' for c in NUTRIENT_COLS)},
    extra           TEXT NOT NULL DEFAULT '{{}}',
    extra_meta      TEXT NOT NULL DEFAULT '{{}}',
    profile         TEXT NOT NULL DEFAULT '{{}}',
    label_image     TEXT,
    source          TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE VIRTUAL TABLE IF NOT EXISTS foods_fts USING fts5(
    name, brand, content='foods', content_rowid='id', tokenize='unicode61'
);
CREATE TRIGGER IF NOT EXISTS foods_ai AFTER INSERT ON foods BEGIN
    INSERT INTO foods_fts(rowid, name, brand) VALUES (new.id, new.name, new.brand);
END;
CREATE TRIGGER IF NOT EXISTS foods_ad AFTER DELETE ON foods BEGIN
    INSERT INTO foods_fts(foods_fts, rowid, name, brand) VALUES ('delete', old.id, old.name, old.brand);
END;
CREATE TRIGGER IF NOT EXISTS foods_au AFTER UPDATE ON foods BEGIN
    INSERT INTO foods_fts(foods_fts, rowid, name, brand) VALUES ('delete', old.id, old.name, old.brand);
    INSERT INTO foods_fts(rowid, name, brand) VALUES (new.id, new.name, new.brand);
END;

CREATE TABLE IF NOT EXISTS log_entries (
    id         INTEGER PRIMARY KEY,
    food_id    INTEGER NOT NULL REFERENCES foods(id),
    logged_at  TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    meal       TEXT NOT NULL DEFAULT 'snack',
    grams      REAL NOT NULL,
    note       TEXT
);
CREATE INDEX IF NOT EXISTS log_entries_day ON log_entries(logged_at);
"""


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


# Columns added after the first release: (table, column, DDL). init_db adds any that are missing.
MIGRATIONS = [
    ("foods", "extra_meta", "TEXT NOT NULL DEFAULT '{}'"),
    ("foods", "profile", "TEXT NOT NULL DEFAULT '{}'"),
    ("log_entries", "meal", "TEXT NOT NULL DEFAULT 'snack'"),
]


def init_db() -> None:
    with connect() as con:
        con.executescript(SCHEMA)
        for table, col, ddl in MIGRATIONS:
            existing = {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}
            if col not in existing:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")


def _row_to_food(row: sqlite3.Row) -> dict:
    d = dict(row)
    for j in ("extra", "extra_meta", "profile"):
        d[j] = json.loads(d.get(j) or "{}")
    return d


# ---------- foods ----------

def search_foods(q: str, limit: int = 10) -> list[dict]:
    q = q.strip()
    with connect() as con:
        if not q:
            rows = con.execute(
                "SELECT f.* FROM foods f LEFT JOIN log_entries l ON l.food_id = f.id "
                "GROUP BY f.id ORDER BY MAX(l.logged_at) DESC NULLS LAST, f.name LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            # Prefix-match every word; quote tokens so punctuation can't break the FTS query.
            tokens = [t.replace('"', '') for t in q.split()]
            match = " ".join(f'"{t}"*' for t in tokens if t)
            rows = con.execute(
                "SELECT f.* FROM foods_fts s JOIN foods f ON f.id = s.rowid "
                "WHERE foods_fts MATCH ? ORDER BY bm25(foods_fts) LIMIT ?",
                (match, limit),
            ).fetchall()
    return [_row_to_food(r) for r in rows]


def get_food(food_id: int) -> dict | None:
    with connect() as con:
        row = con.execute("SELECT * FROM foods WHERE id = ?", (food_id,)).fetchone()
    return _row_to_food(row) if row else None


def list_foods() -> list[dict]:
    with connect() as con:
        rows = con.execute("SELECT * FROM foods ORDER BY name").fetchall()
    return [_row_to_food(r) for r in rows]


def save_food(data: dict, food_id: int | None = None) -> int:
    """Insert (food_id=None) or update a food. `data['extra']` is a dict."""
    cols = ["name", "brand", "serving_size_g", "serving_desc", *NUTRIENT_COLS,
            "extra", "extra_meta", "profile", "label_image", "source"]
    values = [data.get(c) for c in cols]
    for j in ("extra", "extra_meta", "profile"):
        values[cols.index(j)] = json.dumps(data.get(j) or {})
    with connect() as con:
        if food_id is None:
            cur = con.execute(
                f"INSERT INTO foods ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                values,
            )
            return cur.lastrowid
        con.execute(
            f"UPDATE foods SET {', '.join(f'{c} = ?' for c in cols)} WHERE id = ?",
            [*values, food_id],
        )
        return food_id


def delete_food(food_id: int) -> None:
    with connect() as con:
        con.execute("DELETE FROM log_entries WHERE food_id = ?", (food_id,))
        con.execute("DELETE FROM foods WHERE id = ?", (food_id,))


# ---------- log ----------

def add_logs(items: list[tuple[int, float]], meal: str, note: str | None = None,
             logged_at: str | None = None) -> None:
    """Log several (food_id, grams) at once under one meal, e.g. the whole breakfast."""
    meal = meal if meal in MEALS else "snack"
    with connect() as con:
        for food_id, grams in items:
            if logged_at:
                con.execute(
                    "INSERT INTO log_entries (food_id, grams, meal, note, logged_at) VALUES (?, ?, ?, ?, ?)",
                    (food_id, grams, meal, note, logged_at),
                )
            else:
                con.execute(
                    "INSERT INTO log_entries (food_id, grams, meal, note) VALUES (?, ?, ?, ?)",
                    (food_id, grams, meal, note),
                )


def delete_log(entry_id: int) -> None:
    with connect() as con:
        con.execute("DELETE FROM log_entries WHERE id = ?", (entry_id,))


def _empty_totals() -> dict:
    return {**{c: 0.0 for c in NUTRIENT_COLS}, "extra": {}}


def _accumulate(totals: dict, row, factor: float, extra: dict) -> None:
    for c in NUTRIENT_COLS:
        if row[c] is not None:
            totals[c] += row[c] * factor
    for k, v in extra.items():
        if isinstance(v, (int, float)):
            totals["extra"][k] = totals["extra"].get(k, 0.0) + v * factor


def day_log(day: date) -> tuple[list[dict], dict]:
    """Entries for one day (each with scaled nutrients and its meal), plus totals.
    totals["meals"] holds a per-meal totals dict; totals["tags"] counts profile tags;
    totals["feeds"] counts bacteria genera mentioned across the day's foods."""
    with connect() as con:
        rows = con.execute(
            "SELECT l.id AS entry_id, l.logged_at, l.grams, l.meal, l.note, f.* "
            "FROM log_entries l JOIN foods f ON f.id = l.food_id "
            "WHERE date(l.logged_at) = ? ORDER BY l.logged_at",
            (day.isoformat(),),
        ).fetchall()

    entries, totals = [], _empty_totals()
    totals["meals"], totals["tags"], totals["feeds"] = {}, {}, {}
    for r in rows:
        e = _row_to_food(r)
        e["entry_id"], e["meal"], e["grams"] = r["entry_id"], r["meal"], r["grams"]
        factor = (r["grams"] or 0) / 100.0
        e["scaled"] = {c: (None if r[c] is None else r[c] * factor) for c in NUTRIENT_COLS}
        _accumulate(totals, r, factor, e["extra"])
        meal_tot = totals["meals"].setdefault(r["meal"], _empty_totals())
        _accumulate(meal_tot, r, factor, e["extra"])
        for t in e["profile"].get("tags", []):
            totals["tags"][t] = totals["tags"].get(t, 0) + 1
        for g in e["profile"].get("feeds", []):
            totals["feeds"][g] = totals["feeds"].get(g, 0) + 1
        entries.append(e)
    return entries, totals


def export_rows() -> list[dict]:
    with connect() as con:
        rows = con.execute(
            "SELECT l.id, l.logged_at, l.meal, l.grams, l.note, f.name, f.brand, "
            f"{', '.join('f.' + c for c in NUTRIENT_COLS)}, f.extra "
            "FROM log_entries l JOIN foods f ON f.id = l.food_id ORDER BY l.logged_at"
        ).fetchall()
    return [dict(r) for r in rows]
