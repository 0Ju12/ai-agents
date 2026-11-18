"""검증 4.1 — Tool 명세 · 실패 응답 형식 · 예외가 밖으로 나오지 않는지."""

from backend.tools import registry
from backend.tools.base import Err, Tool
from backend.tools.content import make_insta_links
from backend.tools.heritage import parse_items, to_place

EXPECTED = {"search_heritage", "search_tour", "search_place", "get_visit_info", "plan_leg", "get_weather",
            "get_holidays", "get_crowd", "get_videos", "make_insta_links", "ask_heritage"}


def test_catalog_has_name_description_schema_only():
    cat = registry.catalog()
    assert {c["name"] for c in cat} == EXPECTED
    for c in cat:
        assert set(c) == {"name", "description", "parameters"}
        assert c["description"] and c["parameters"]["type"] == "object"


def test_missing_key_returns_invalid_key_not_exception():
    cases = [
        ("search_tour", {"lat": 35.8, "lon": 129.2}),
        ("search_place", {"lat": 35.8, "lon": 129.2}),
        ("get_visit_info", {"content_id": "123"}),
        ("get_holidays", {"year": 2026, "month": 11}),
        ("get_videos", {"query": "경주 석굴암"}),
        ("plan_leg", {"mode": "train", "origin": {"name": "서울"}, "destination": {"name": "경주"}}),
    ]
    for name, args in cases:
        res = registry.run(name, **args)
        assert res["ok"] is False, name
        assert res["error"]["code"] == Err.INVALID_KEY, name
        assert "meta" in res and res["meta"]["tool"] == name


def test_bad_arguments_and_unknown_tool():
    assert registry.run("search_heritage", region="")["error"]["code"] == Err.BAD_ARGUMENT
    assert registry.run("search_heritage", wrong_arg=1)["error"]["code"] == Err.BAD_ARGUMENT
    assert registry.run("plan_leg", mode="boat", origin={"name": "a"}, destination={"name": "b"})["error"]["code"] == Err.BAD_ARGUMENT
    assert registry.run("no_such_tool")["error"]["code"] == Err.NOT_FOUND


def test_tool_run_never_raises():
    def boom():
        raise RuntimeError("secret-key-in-url")

    res = Tool("boom", "테스트", {"type": "object", "properties": {}}, boom).run()
    assert res["ok"] is False and res["error"]["code"] == Err.UPSTREAM_ERROR
    assert "secret" not in res["error"]["message"]  # 원문을 노출하지 않음 (NF3002)


def test_heritage_xml_parse_euc_kr_and_missing_coord():
    xml = ('<?xml version="1.0" encoding="EUC-KR"?><result><item><ccbaKdcd>11</ccbaKdcd><ccbaAsno>00240000</ccbaAsno>'
           '<ccbaCtcd>37</ccbaCtcd><ccbaMnm1>경주 석굴암 석굴</ccbaMnm1><longitude>129.349</longitude><latitude>35.795</latitude></item>'
           '<item><ccbaKdcd>11</ccbaKdcd><ccbaAsno>00990000</ccbaAsno><ccbaCtcd>37</ccbaCtcd><ccbaMnm1>좌표 없는 유산</ccbaMnm1>'
           '<longitude>0</longitude><latitude>0</latitude></item></result>').encode("cp949")
    items = parse_items(xml)
    first, second = to_place(items[0]), to_place(items[1])
    assert first.name == "경주 석굴암 석굴" and first.has_coord
    assert not second.has_coord  # 0 좌표는 없는 값으로 둠 (임의로 채우지 않음)
    assert first.open_time is None  # 관람시간은 국가유산청 목록에 없음 → 판정 보류


def test_ask_heritage_without_index():
    assert registry.run("ask_heritage", question="석굴암은 왜 국보야?")["error"]["code"] == Err.NO_INDEX


def test_insta_links():
    res = make_insta_links(["석굴암", "황리단길 카페!"], region="경주")
    tags = [link["tag"] for link in res["data"]["links"]]
    assert tags[:2] == ["#석굴암", "#황리단길카페"]
    assert "#경주맛집" in tags
    assert all(link["url"].startswith("https://www.instagram.com/explore/tags/") for link in res["data"]["links"])
