"""Public nutrient reference and versioned, one-serving recipe catalog."""

import json
import sqlite3
from pathlib import Path

from .menu_variations import combinations

ASSETS = Path(__file__).resolve().parents[1] / "assets"
FIELDS = ("kcal", "protein_g", "carb_g", "fat_g", "fiber_g", "sodium_mg")
ALIASES = {
    "계란": "달걀",
    "파": "대파",
    "플레인 요거트": "플레인요거트",
    "요거트": "플레인요거트",
    "쌀밥": "밥",
    "찬밥": "밥",
    "오트": "오트밀",
}
ALLERGENS = {
    "달걀": {"달걀", "난류"},
    "두부": {"대두", "콩"},
    "간장": {"대두", "콩", "밀"},
    "플레인요거트": {"우유", "유제품"},
    "참치": {"생선", "참치"},
    "참기름": {"참깨"},
    "오트밀": {"귀리"},
    "김치": {"새우", "생선"},
    "고등어": {"생선"}, "연어": {"생선"},
    "버터": {"우유", "유제품"}, "치즈": {"우유", "유제품"}, "우유": {"유제품"},
    "밀가루": {"밀"}, "파스타": {"밀"}, "소면": {"밀"}, "식빵": {"밀"},
    "된장": {"대두", "콩"}, "콩나물": {"대두", "콩"}, "깨": {"참깨"},
    "닭가슴살": {"닭고기"}, "닭다리살": {"닭고기"}, "새우": {"갑각류"},
    "아몬드": {"견과류"},
}
ANIMAL = {
    "달걀", "닭가슴살", "닭다리살", "돼지고기", "소고기", "고등어", "연어", "참치",
    "새우", "우유", "치즈", "버터", "플레인요거트", "김치",
}
SUBSTITUTES = {"대파": {"양파"}, "양송이버섯": {"양파"}, "브로콜리": {"시금치"}, "딸기": {"바나나"}}


def canonical(value):
    value = value.strip()
    return ALIASES.get(value, value)


def load_catalog(path):
    ingredients = json.loads((ASSETS / "nutrition.json").read_text(encoding="utf-8"))
    recipes = json.loads((ASSETS / "recipes.json").read_text(encoding="utf-8"))
    with sqlite3.connect(path) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS ingredients(name TEXT PRIMARY KEY, fdc_id INTEGER, reference TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS recipes(title TEXT PRIMARY KEY, minutes INTEGER, steps TEXT, source TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS portions(title TEXT, name TEXT, grams REAL, PRIMARY KEY(title,name));
        """)
        db.execute(
            "CREATE TABLE IF NOT EXISTS exercises(id INTEGER PRIMARY KEY, category TEXT, record TEXT)"
        )
        db.executemany(
            "INSERT OR REPLACE INTO exercises VALUES(?,?,?)",
            [
                (e["id"], e["category"], json.dumps(e, ensure_ascii=False))
                for e in json.loads((ASSETS / "training.json").read_text(encoding="utf-8"))
            ],
        )
        db.executemany(
            "INSERT OR REPLACE INTO ingredients VALUES(?,?,?)",
            [(r["name"], r["fdc_id"], json.dumps(r, ensure_ascii=False)) for r in ingredients],
        )
        original_titles = {row[0] for row in recipes}
        recipes.extend(row for row in combinations() if row[0] not in original_titles)
        for title, minutes, parts, steps in recipes:
            db.execute(
                "INSERT OR REPLACE INTO recipes VALUES(?,?,?,?)",
                (title, minutes, json.dumps(steps, ensure_ascii=False), "한 끼 · 1인분 기준 레시피" if title in original_titles else "한끼 조합 레시피 · 1인분"),
            )
            db.execute("DELETE FROM portions WHERE title=?", (title,))
            db.executemany("INSERT INTO portions VALUES(?,?,?)", [(title, k, v) for k, v in parts.items()])
        nutrients = {
            name: json.loads(record)
            for name, record in db.execute("SELECT name,reference FROM ingredients")
        }
        all_parts = {}
        for title, name, grams in db.execute("SELECT title,name,grams FROM portions"):
            all_parts.setdefault(title, {})[name] = grams
        meals = {
            title: {
                "title": title,
                "minutes": mins,
                "steps": json.loads(steps),
                "grams": all_parts[title],
                "source": source,
            }
            for title, mins, steps, source in db.execute("SELECT * FROM recipes")
        }
    return meals, nutrients


def nutrient_totals(grams, references):
    totals = {}
    for key in FIELDS:
        if any(references.get(name, {}).get(key) is None for name in grams):
            totals[key] = None
        else:
            totals[key] = round(
                sum(weight * references[name][key] / 100 for name, weight in grams.items()), 1
            )
    return totals
