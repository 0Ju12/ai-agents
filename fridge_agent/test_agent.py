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
