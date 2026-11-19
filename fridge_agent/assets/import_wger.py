"""Import a compact, attributed exercise reference. Run from any directory."""

import json, pathlib, sys
from urllib.request import Request, urlopen

OUTPUT = pathlib.Path(__file__).with_name("training.json")
IDS = {12, 20, 56, 73, 75, 81, 92, 124}


def parse(data):
    result = []
    for row in data["results"]:
        if row["id"] not in IDS:
            continue
        en = next((t for t in row["translations"] if t["language"] == 2), None)
        if not en:
            continue
        result.append(
            {
                "id": row["id"],
                "title": en["name"],
                "category": row["category"]["name"],
                "muscles": [m["name_en"] or m["name"] for m in row["muscles"]],
                "equipment": [x["name"] for x in row["equipment"]],
                "authors": en.get("author_history")
                or row.get("total_authors_history")
                or [row.get("license_author") or "wger contributors"],
                "license": row["license"]["url"],
                "url": "https://wger.de/en/exercise/" + str(row["id"]) + "/view/",
            }
        )
    return result


if __name__ == "__main__":
    data = (
        json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
        if len(sys.argv) > 1
        else json.load(
            urlopen(
                Request(
                    "https://wger.de/api/v2/exerciseinfo/?limit=50", headers={"User-Agent": "Hankki/1.0"}
                ),
                timeout=8,
            )
        )
    )
    OUTPUT.write_text(json.dumps(parse(data), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
