"""Rebuild the bundled public-domain SR Legacy subset from USDA's original CSV ZIP."""

import csv
import io
import json
import sys
import zipfile
from pathlib import Path

FOODS = {
    "달걀": 171287,
    "두부": 172476,
    "양파": 170000,
    "대파": 170005,
    "밥": 168932,
    "식용유": 172336,
    "참기름": 171016,
    "김치": 170392,
    "바나나": 173944,
    "플레인요거트": 171284,
    "오이": 168409,
    "당근": 170393,
    "토마토": 170457,
    "양송이버섯": 169251,
    "감자": 170026,
    "고구마": 168482,
    "오트밀": 173904,
    "시금치": 168462,
    "브로콜리": 170379,
    "간장": 174277,
    "마늘": 169230,
    "닭가슴살": 171509,
    "참치": 173709,
    "딸기": 167762,
    "렌틸콩": 172421,
}
FIELDS = {
    "1008": "kcal",
    "1003": "protein_g",
    "1004": "fat_g",
    "1005": "carb_g",
    "1079": "fiber_g",
    "1093": "sodium_mg",
}


def main(archive):
    with zipfile.ZipFile(archive) as z:

        def rows(filename):
            member = next(n for n in z.namelist() if n.endswith("/" + filename))
            return csv.DictReader(io.TextIOWrapper(z.open(member), encoding="utf-8-sig"))

        index = {str(uid): {"name": name, "fdc_id": uid} for name, uid in FOODS.items()}
        for row in rows("food.csv"):
            if row["fdc_id"] in index:
                index[row["fdc_id"]]["reference_food"] = row["description"]
        for row in rows("food_nutrient.csv"):
            item = index.get(row["fdc_id"])
            if item and row["nutrient_id"] in FIELDS and row["amount"]:
                item[FIELDS[row["nutrient_id"]]] = float(row["amount"])
        Path(__file__).with_name("nutrition.json").write_text(
            json.dumps(list(index.values()), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main(sys.argv[1])
