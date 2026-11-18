"""Read-only public data tools. TheMealDB ingredient and instruction text is English."""
import json
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CATALOG = {
    "search": ("재료로 레시피 후보를 검색", "ingredient", "id, title 목록"),
    "detail": ("후보 식별자로 재료와 조리법 확인", "meal_id", "title, ingredients, instructions"),
    "nutrition": ("제품 바코드로 100g당 영양정보 확인", "barcode", "product, kcal, protein"),
}
ENGLISH = {"달걀":"egg","두부":"tofu","닭가슴살":"chicken breast","양파":"onion","감자":"potato"}

def read(url):
    req = Request(url, headers={"User-Agent":"FridgeAgent/1.0 (github.com/0Ju12/ai-agents)"})
    with urlopen(req, timeout=6) as response:
        return json.load(response)

def call(tool, argument):
    base = "https://www.themealdb.com/api/json/v1/1/"
    try:
        if tool == "search":
            url = base + "filter.php?" + urlencode({"i":ENGLISH.get(argument,argument)})
            rows = read(url).get("meals") or []
            data = [{"id":r["idMeal"],"title":r["strMeal"]} for r in rows[:4]]
        elif tool == "detail":
            url = base + "lookup.php?" + urlencode({"i":argument})
            rows = read(url).get("meals") or []
            data = None
            if rows:
                meal = rows[0]
                data = {"title":meal["strMeal"], "instructions":meal["strInstructions"],
                        "ingredients":[meal[f"strIngredient{i}"].strip() for i in range(1,21)
                                       if (meal.get(f"strIngredient{i}") or "").strip()]}
        elif tool == "nutrition" and re.fullmatch(r"\d{8,14}",argument):
            url = f"https://world.openfoodfacts.org/api/v2/product/{argument}.json?fields=product_name,nutriments"
            product = read(url).get("product")
            data = None
            if product:
                nutrients = product.get("nutriments",{})
                data = {"product":product.get("product_name"),"kcal":nutrients.get("energy-kcal_100g"),
                        "protein_g":nutrients.get("proteins_100g"),"basis":"100g"}
        else:
            return {"ok":False,"error":"INVALID_INPUT"}
        if not data: return {"ok":False,"error":"NO_RESULT"}
        return {"ok":True,"data":data,"source":url}
    except (OSError,ValueError,TypeError,KeyError,AttributeError):
        return {"ok":False,"error":"SOURCE_UNAVAILABLE"}
