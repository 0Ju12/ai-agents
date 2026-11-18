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
