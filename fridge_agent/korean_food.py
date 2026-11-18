"""국내 공공 식품 API. 검색 결과만 로컬 DB에 캐시하고 인증 정보는 기록하지 않는다."""
import json
import os
import sqlite3
import time
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, unquote

RECIPE = "https://openapi.foodsafetykorea.go.kr/api"
NUTRITION = "https://apis.data.go.kr/1471000/FoodNtrCpntDbInfo02/getFoodNtrCpntDbInq02"
SOURCES = {"kr_recipe":"식품안전나라 COOKRCP01","kr_nutrition":"식약처 식품영양성분DB정보"}

def fetch(tool, term, read):
    if tool == "kr_recipe":
        key = os.getenv("FOODSAFETY_API_KEY")
        if not key:
            return {"ok":False,"error":"MISSING_KEY","setting":"FOODSAFETY_API_KEY"}
        url = f"{RECIPE}/{quote(key,safe='')}/COOKRCP01/json/1/20/RCP_NM={quote(term,safe='')}"
        payload = read(url)
        block = payload.get("COOKRCP01",payload)
        code = block.get("RESULT",{}).get("CODE")
        if code not in ("INFO-000","INFO-200"):
            return {"ok":False,"error":"PROVIDER_ERROR"}
        items = [{"메뉴":r["RCP_NM"],"재료·분량":r.get("RCP_PARTS_DTLS"),
                  "조리 순서":[r[f"MANUAL{i:02}"].strip() for i in range(1,21)
                             if (r.get(f"MANUAL{i:02}") or "").strip()]}
                 for r in block.get("row",[]) if r.get("RCP_NM")]
    else:
        key = os.getenv("DATA_GO_KR_SERVICE_KEY")
        if not key:
            return {"ok":False,"error":"MISSING_KEY","setting":"DATA_GO_KR_SERVICE_KEY"}
        query = urlencode({"serviceKey":unquote(key),"FOOD_NM_KR":term,"type":"json","pageNo":1,"numOfRows":20})
        payload = read(NUTRITION+"?"+query)
        response = payload.get("response",payload)
        if str(response.get("header",{}).get("resultCode")) not in {"00","0"}:
            return {"ok":False,"error":"PROVIDER_ERROR"}
        rows = response.get("body",{}).get("items") or []
        if isinstance(rows,dict):
            rows = rows.get("item",[])
            if isinstance(rows,dict): rows=[rows]
        items = [{"식품":r["FOOD_NM_KR"],"기준량":r.get("SERVING_SIZE") or r.get("NUTRI_AMOUNT"),
                  "열량(kcal)":r.get("AMT_NUM1"),"단백질(g)":r.get("AMT_NUM3")}
                 for r in rows if r.get("FOOD_NM_KR")]
    if not items: return {"ok":False,"error":"NO_RESULT"}
    return {"ok":True,"data":items,"source":SOURCES[tool]}

def lookup(tool, argument, read):
    term = argument.strip()
    if not 1 <= len(term) <= 80: return {"ok":False,"error":"INVALID_INPUT"}
    try:
        with sqlite3.connect("food_catalog.sqlite3") as db:
            db.execute("CREATE TABLE IF NOT EXISTS searches(tool TEXT, term TEXT, fetched REAL, result TEXT, PRIMARY KEY(tool,term))")
            row = db.execute("SELECT fetched,result FROM searches WHERE tool=? AND term=?",(tool,term)).fetchone()
            if row and time.time()-row[0] < 86400: return json.loads(row[1])
            result = fetch(tool,term,read)
            if result["ok"]:
                db.execute("INSERT OR REPLACE INTO searches VALUES(?,?,?,?)",(tool,term,time.time(),json.dumps(result,ensure_ascii=False)))
            return result
    except HTTPError as exc:
        return {"ok":False,"error":"AUTH_FAILED" if exc.code in (401,403) else "SOURCE_UNAVAILABLE"}
    except (OSError,ValueError,AttributeError,TypeError,KeyError,sqlite3.Error):
        return {"ok":False,"error":"SOURCE_UNAVAILABLE"}
