from fastapi.testclient import TestClient
from app import app

def test_flow(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = TestClient(app)
    def send(message):
        return client.post("/api/chat",json={"message":message})
    assert send("추천").json()["냉장고"] == []
    assert send("추가 두부, 계란, 달걀").json()["계획"]["메뉴"] == "두부 달걀찜"
    assert "코어" in send("부위 코어").json()["계획"]["운동"]
    assert send("삭제 계란").json()["계획"]["부족분"]
    assert send("시간 0").status_code == 422
    assert send("시간 1").json()["계획"].get("안내")
    assert send("추천").json()["냉장고"] == ["두부"]
    assert client.get("/").status_code == 200

def test_kitchen(tmp_path, monkeypatch):
    from app import run
    monkeypatch.chdir(tmp_path)
    run("추가 달걀, 양파, 식용유")
    run("메뉴 대파 달걀볶음")
    assert run("대체 양파")["계획"]["메뉴"]=="양파 달걀볶음"
    assert run("조리 2인분 16분")["조리 기록"][-1]["planned"]==10
    assert run("섭취 양파 달걀볶음")["남은 음식"]=={"양파 달걀볶음":1}
    assert "외식" in run("외식")["계획"]["안내"]
    assert run("집밥")["계획"]["남은 음식 우선"]
    assert run("섭취 양파 달걀볶음")["계획"]["조리시간(분)"]==16
    assert run("추천",session_id="another")["냉장고"]==[]

def test_graph_scenarios(tmp_path, monkeypatch):
    import food_tools
    from app import run
    monkeypatch.chdir(tmp_path)
    calls=[]
    def missing(tool,argument):
        calls.append((tool,argument))
        if tool=="search":
            return {"ok":True,"data":[{"id":str(i)} for i in range(6)]}
        return {"ok":False,"error":"NO_RESULT"}
    monkeypatch.setattr(food_tools,"call",missing)
    assert "상한" in run("검색 달걀")["계획"]["안내"]
    assert calls==[("search","달걀")]+[("detail",str(i)) for i in range(4)]
    run("도움말")
    assert len(calls)==5
    client=TestClient(app)
    assert client.get("/api/logs/default").json()
    assert client.delete("/api/logs/default").status_code==204
    assert client.get("/api/logs/default").status_code==404

def test_korean_sources(tmp_path,monkeypatch):
    import food_tools
    monkeypatch.chdir(tmp_path)
    client=TestClient(app)
    def query(msg): return client.post("/api/chat",json={"message":msg}).json()["계획"]["조회"]
    monkeypatch.delenv("FOODSAFETY_API_KEY",raising=False)
    assert query("레시피 달걀찜")["error"]=="MISSING_KEY"
    monkeypatch.setenv("FOODSAFETY_API_KEY","test-recipe")
    monkeypatch.setenv("DATA_GO_KR_SERVICE_KEY","test-food")
    calls=[]
    def read(url):
        calls.append(url)
        if "COOKRCP01" in url:
            return {"COOKRCP01":{"RESULT":{"CODE":"INFO-000"},"row":[{"RCP_NM":"달걀찜","MANUAL01":"찐다","RCP_PARTS_DTLS":"달걀 50g"}]}}
        return {"header":{"resultCode":"00"},"body":{"items":[{"FOOD_NM_KR":"두부","SERVING_SIZE":"100g","AMT_NUM1":"80","AMT_NUM3":"8"}]}}
    monkeypatch.setattr(food_tools,"read",read)
    assert query("레시피 달걀찜")["data"][0]["조리 순서"]==["찐다"]
    assert query("레시피 달걀찜")["ok"]
    assert query("식품영양 두부")["data"][0]["단백질(g)"]=="8"
    assert len(calls)==2

def test_coach_sources(tmp_path,monkeypatch):
    import food_tools
    from app import run
    monkeypatch.chdir(tmp_path)
    calls=[]
    def fixture(tool,arg):
        calls.append(tool)
        if tool=="kr_recipe":
            return {"ok":True,"data":[{"메뉴":"달걀찜","조리 순서":["섞기","찌기"],"재료·분량":"달걀 50g"}]}
        return {"ok":False,"error":"SOURCE_UNAVAILABLE"}
    monkeypatch.setattr(food_tools,"call",fixture)
    run("추가 계란")
    guide=run("요리코치 달걀찜 / 계란 / 3017620422003")["계획"]
    assert calls==["kr_recipe","kr_nutrition","search","nutrition"]
    assert guide["재고 확인"]=="등록됨" and guide["조리 단계"]==["섞기","찌기"]
    assert guide["재료 영양"]["error"]=="SOURCE_UNAVAILABLE"
    assert "안내" in run("요리코치 달걀찜")["계획"]

def test_daily_journal(tmp_path,monkeypatch):
    from app import run
    monkeypatch.chdir(tmp_path)
    assert run("물 250")["오늘 기록"]["water_ml"]==250
    assert run("물 100")["오늘 기록"]["water_ml"]==350
    assert run("수면 7.5")["오늘 기록"]["sleep_hours"]==7.5
    assert run("추천",session_id="other")["오늘 기록"]=={}


def test_static_types_are_explicit():
    """Windows 레지스트리와 상관없이 스크립트·스타일 형식이 맞아야 화면이 뜬다 (nosniff)."""
    import mimetypes
    mimetypes.add_type("text/plain", ".js")  # 잘못 등록된 PC 흉내
    import importlib, app as module
    importlib.reload(module)
    client = TestClient(module.app)
    assert client.get("/static/app.js").headers["content-type"].startswith("text/javascript")
    assert client.get("/static/app.css").headers["content-type"].startswith("text/css")
    assert client.get("/static/icons.svg").headers["content-type"].startswith("image/svg+xml")


def test_command_words_inside_sentences(tmp_path, monkeypatch):
    """첫 단어가 명령어와 같은 일반 문장, 단위가 붙은 기록, 내부 오류 문구 비노출."""
    monkeypatch.setenv("FRIDGE_DATA_DIR", str(tmp_path))
    client = TestClient(app)
    send = lambda m: client.post("/api/chat", json={"message": m})
    assert send("메뉴 추천해줘").status_code == 200  # 메뉴 이름이 아니면 일반 문장으로 다시 해석
    assert send("물 500ml").json()["오늘 기록"]["water_ml"] == 500
    assert send("물 한 잔").json()["오늘 기록"]["water_ml"] == 750
    assert send("수면 7시간 30분").json()["오늘 기록"]["sleep_hours"] == 7.5
    assert send("목표 다이어트").json()["설정"]["goal"] == "체중 관리"
    bad = send("수면 일곱시간")
    assert bad.status_code == 422 and "convert" not in bad.json()["detail"]
    assert send("시간 0").status_code == 422  # 잘못된 명령은 그대로 알려 준다
    reply = send("유산균 아침 8시에 알려줘").json()  # '유산'이 국가유산 해설로 새지 않는다
    assert reply["계획"].get("안내") != "해설"


def test_text_files_are_ascii():
    """Windows pip 은 requirements 를 cp949 로 읽는다. 저장소의 .txt 파일에는 한글을 쓰지 않는다."""
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    files = subprocess.run(["git", "ls-files", "*.txt"], cwd=root, capture_output=True, text=True).stdout.split()
    assert files and all((root / f).read_bytes().isascii() for f in files), files
