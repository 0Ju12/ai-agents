"""Read-only public data tools. TheMealDB ingredient and instruction text is English."""

import json
from korean_food import lookup
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from registry import definitions

CATALOG = definitions()

ENGLISH = {"달걀": "egg", "두부": "tofu", "닭가슴살": "chicken breast", "양파": "onion", "감자": "potato"}


def read(url):
    req = Request(url, headers={"User-Agent": "FridgeAgent/1.0 (github.com/0Ju12/ai-agents)"})
    with urlopen(req, timeout=5) as response:
        return json.load(response)


def call(tool, argument=None, **unexpected):
    if unexpected or not isinstance(argument, str) or not argument.strip():
        return {"ok": False, "error": "INVALID_INPUT"}

    from connections import EXTERNAL, lookup as source_lookup

    if tool in EXTERNAL:
        return source_lookup(tool, argument)
    if tool == "knowledge":
        from knowledge import search

        return search(argument)
    if tool in {"calendar_list", "calendar_register"}:
        from calendar_adapter import calendar

        return calendar(tool, argument)
    if tool == "wger":
        if not argument.isdecimal():
            return {"ok": False, "error": "INVALID_INPUT"}
        try:
            url = "https://wger.de/api/v2/exerciseinfo/" + argument + "/"
            row = read(url)
            en = next((x for x in row["translations"] if x["language"] == 2), None)
            return {
                "ok": True,
                "source": "wger",
                "data": {
                    "id": row["id"],
                    "title": en["name"] if en else argument,
                    "equipment": [x["name"] for x in row["equipment"]],
                    "url": "https://wger.de/en/exercise/" + argument + "/view/",
                    "license": row["license"]["url"],
                },
            }
        except (OSError, KeyError, TypeError, ValueError):
            return {"ok": False, "error": "SOURCE_UNAVAILABLE"}
    if tool in {"kr_recipe", "kr_nutrition"}:
        return lookup(tool, argument, read)
    import os

    base = "https://www.themealdb.com/api/json/v1/" + (os.getenv("MEALDB_API_KEY") or "1") + "/"
    try:
        if tool == "search":
            url = base + "filter.php?" + urlencode({"i": ENGLISH.get(argument, argument)})
            rows = read(url).get("meals") or []
            data = [{"id": r["idMeal"], "title": r["strMeal"]} for r in rows[:4]]
        elif tool == "detail":
            url = base + "lookup.php?" + urlencode({"i": argument})
            rows = read(url).get("meals") or []
            data = None
            if rows:
                meal = rows[0]
                data = {
                    "title": meal["strMeal"],
                    "id": meal.get("idMeal", argument),
                    "category": meal.get("strCategory"),
                    "country": meal.get("strArea"),
                    "url": "https://www.themealdb.com/meal/" + str(argument),
                    "instructions": meal.get("strInstructions") or "",
                    "ingredients": [
                        meal[f"strIngredient{i}"].strip()
                        for i in range(1, 21)
                        if (meal.get(f"strIngredient{i}") or "").strip()
                    ],
                }
        elif tool == "nutrition" and re.fullmatch(r"\d{8,14}", argument):
            url = f"https://world.openfoodfacts.org/api/v2/product/{argument}.json?fields=product_name,nutriments"
            product = read(url).get("product")
            data = None
            if product:
                nutrients = product.get("nutriments", {})
                data = {
                    "product": product.get("product_name"),
                    "kcal": nutrients.get("energy-kcal_100g"),
                    "protein_g": nutrients.get("proteins_100g"),
                    "basis": "100g",
                }
        else:
            return {"ok": False, "error": "INVALID_INPUT"}
        if not data:
            return {"ok": False, "error": "NO_RESULT"}
        return {
            "ok": True,
            "data": data,
            "source": "Open Food Facts" if tool == "nutrition" else "TheMealDB",
        }
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return {"ok": False, "error": "SOURCE_UNAVAILABLE"}
