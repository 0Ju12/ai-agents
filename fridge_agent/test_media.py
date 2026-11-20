"""사진 움직임용 미디어(중계·깊이 맵·검수 클립)와 YouTube 챕터 매칭 · Instagram 임베드 자료."""

import io
import json

import pytest
from fastapi.testclient import TestClient

import app as api
import media
import video_guide

PHOTO = "https://www.foodsafetykorea.go.kr/uploadimg/cook/77_1.png"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 200
DESC = "맛있는 김치찌개\n00:00 인트로\n00:40 김치와 돼지고기 볶기\n02:10 물 붓고 끓이기\n05:30 두부 올리기\n"


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("FRIDGE_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("FRIDGE_MODE", raising=False)
    for key in ("GMS_KEY", "GMS_API_KEY", "OPENAI_API_KEY", "YOUTUBE_API_KEY", "IG_USER_ID", "IG_ACCESS_TOKEN"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def client():
    return TestClient(api.app)


STEPS = ["김치와 돼지고기를 볶는다.", "물을 붓고 10분 끓인다.", "두부를 올려 마무리한다."]


def test_chapters_follow_youtube_rules():
    chapters = video_guide.parse_chapters(DESC)
    assert [c["start"] for c in chapters] == [0, 40, 130, 330]
    assert video_guide.parse_chapters("01:00 시작\n02:00 끝") == []  # 0초 시작 · 3개 이상이 아니면 챕터가 아니다
    assert video_guide.match_rule(STEPS, chapters) == [40, 130, 330]


def test_unrelated_chapters_are_not_used():
    chapters = [
        {"start": 20, "title": "삼겹살 썰기"},
        {"start": 50, "title": "두부 굽기"},
    ]
    assert video_guide.match_rule(["삼겹살을 팬에 굽는다.", "물을 부어 끓인다."], chapters) == [None, None]


def test_youtube_videos_are_cached_and_embeddable(monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "fixture")
    calls = []

    def fake(url, *a, **k):
        calls.append(url)
        assert "videoEmbeddable=true" in url or "/videos?" in url
        if "/search?" in url:
            return {"items": [{"id": {"videoId": "abcdefghijk"}}, {"id": {"videoId": "zzzzzzzzzzz"}}]}
        return {"items": [
            {"id": "zzzzzzzzzzz", "snippet": {"title": "챕터 없음", "channelTitle": "B", "description": "설명"}, "statistics": {"viewCount": "999"}},
            {"id": "abcdefghijk", "snippet": {"title": "김치찌개 &amp; 레시피", "channelTitle": "A", "description": DESC}, "statistics": {"viewCount": "10"}},
        ]}

    monkeypatch.setattr(video_guide, "request_json", fake)
    out = video_guide.media_for("김치찌개", STEPS, lambda *a, **k: None)
    first = out["youtube"]["data"][0]
    assert first["id"] == "abcdefghijk" and first["title"] == "김치찌개 & 레시피"  # 챕터 있는 영상 우선
    assert first["step_starts"] == [40, 130, 330]
    assert len(out["youtube"]["data"]) == 1  # 제목이 메뉴와 무관한 영상은 숨긴다
    video_guide.youtube_videos("김치찌개")
    assert len(calls) == 2  # 두 번째는 24시간 캐시


def test_media_endpoint_without_keys(client):
    r = client.post("/api/guide/media", json={"menu": "김치찌개", "steps": STEPS}).json()
    assert r["youtube"]["error"] == "MISSING_KEY" and r["instagram"]["error"] == "MISSING_KEY"
    assert r["직접 검색"]["Instagram"].startswith("https://www.instagram.com/explore/tags/")


def test_photo_proxy_only_allows_public_recipe_host(monkeypatch, client):
    class Res(io.BytesIO):
        def geturl(self):
            return PHOTO

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    fetched = []
    monkeypatch.setattr(media, "urlopen", lambda req, timeout: fetched.append(req.full_url) or Res(PNG))
    r = client.get("/api/media", params={"u": PHOTO})
    assert r.status_code == 200 and r.headers["content-type"] == "image/png" and "max-age" in r.headers["cache-control"]
    client.get("/api/media", params={"u": PHOTO})
    assert len(fetched) == 1  # 디스크 캐시
    assert client.get("/api/media", params={"u": "https://evil.example/x.png"}).status_code == 404
    assert client.get("/api/media", params={"u": PHOTO.replace("https", "http")}).status_code == 404


def test_decorate_depth_and_reviewed_clips(client):
    guide = {"단계": [{"순서": 1, "사진": PHOTO}, {"순서": 2, "사진": None}], "대표 사진": None}
    (media.root() / (media.key(PHOTO) + ".depth.png")).write_bytes(PNG)
    clips = media.root() / "clips"
    clips.mkdir()
    (clips / "c.mp4").write_bytes(b"0" * 2000)
    k = media.key("kr:77")
    media.save_manifest({k: {"2": {"recipe": "kr:77", "file": "c.mp4", "approved": False}}})
    media.decorate(guide, "kr:77")
    first, second = guide["단계"]
    assert first["사진"].startswith("/api/media?u=") and first["깊이"].startswith("/api/media/depth?u=")
    assert second["클립"] is None and client.get(f"/api/media/clip/{k}/2").status_code == 404  # 검수 전 비공개
    media.save_manifest({k: {"2": {"recipe": "kr:77", "file": "c.mp4", "approved": True}}})
    assert media.clip_url("kr:77", 2) == f"/api/media/clip/{k}/2"
    assert client.get(f"/api/media/clip/{k}/2").status_code == 200
    assert client.get("/api/media/depth", params={"u": PHOTO}).status_code == 200
