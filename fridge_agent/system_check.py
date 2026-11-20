"""Run the first-party Chromium flow against a new temporary server; write screenshots to the chosen directory."""

import argparse
import io
import os
from pathlib import Path
import pathlib
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import monotonic, sleep
from urllib.request import urlopen
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from PIL import Image
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent


def check(out, base, executable):
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=executable, args=["--no-sandbox", "--no-proxy-server"])
        c = b.new_context(
            viewport={"width": 390, "height": 844},
            device_scale_factor=1,
            locale="ko-KR",
            timezone_id="Asia/Seoul",
            is_mobile=True,
            has_touch=True,
        )
        page = c.new_page()
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.goto(base, wait_until="networkidle")
        page.get_by_role("heading", name="오늘의 한끼").wait_for()

        def snap(name):
            page.locator("#toast").evaluate("(el)=>el.classList.remove('on')")
            page.wait_for_timeout(150)
            Image.open(io.BytesIO(page.screenshot())).convert("RGB").save(
                out / (name + ".webp"), quality=86, method=6
            )
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth"), name

        snap("today-mobile")
        for name, qty, unit in [("두부", "300", "g"), ("달걀", "3", "개")]:
            page.get_by_role("button", name="재료 추가", exact=True).first.click()
            d = page.locator("dialog[open]")
            d.get_by_label("재료 이름").fill(name)
            d.get_by_label("포장 용량").fill(qty)
            d.get_by_label("단위", exact=True).select_option(unit)
            d.get_by_label("소비기한").fill(
                (datetime.now(ZoneInfo("Asia/Seoul")).date() + timedelta(days=2)).isoformat()
            )
            d.get_by_role("button", name="냉장고에 넣기").click()
            d.wait_for(state="hidden")
        page.locator("#mobile-nav").get_by_text("냉장고", exact=True).click()
        snap("pantry-mobile")
        page.get_by_role("button", name="식단 확인").click()
        d = page.locator("dialog[open]")
        d.get_by_role("heading", name="1인분 재료").wait_for()
        snap("meal-mobile")
        d.get_by_role("button", name="조리 기록").click()
        d.get_by_label("만든 분량").fill("2")
        d.get_by_label("실제 조리시간").fill("14")
        d.get_by_role("button", name="조리 완료").click()
        page.get_by_role("button", name="1인분 섭취").click()
        page.wait_for_function("document.body.getAttribute('aria-busy')!=='true'")
        page.locator("#mobile-nav").get_by_text("운동", exact=True).click()
        snap("workout-mobile")
        page.locator("#mobile-nav").get_by_text("기록", exact=True).click()
        page.get_by_role("button", name="물 더하기").click()
        page.locator("dialog[open]").get_by_role("button", name="기록하기").click()
        page.locator("dialog[open]").wait_for(state="hidden")
        snap("journal-mobile")
        page.set_viewport_size({"width": 1440, "height": 940})
        page.goto(base + "/#today", wait_until="networkidle")
        snap("today-desktop")
        page.goto(base + "/#pantry")
        page.get_by_role("heading", name="나의 냉장고").wait_for()
        page.goto(base + "/#recipes")
        page.locator("#meal-filter").fill("김치볶음밥")
        page.locator('#meal-list button[data-do="choose"][data-arg="김치볶음밥"]').click()
        page.get_by_role("button", name="부족분 장바구니에 담기").click()
        page.get_by_role("button", name="장바구니에 담기", exact=True).click()
        page.locator("dialog[open]").wait_for(state="hidden")
        page.goto(base + "/#pantry")
        page.get_by_role("button", name="구입 후 입고").first.wait_for()
        snap("shopping-desktop")
        page.goto(base + "/#journal")
        page.get_by_role("button", name="계획과 일정").click()
        d = page.locator("dialog[open]")
        d.get_by_label("계획명", exact=True).fill("저녁 준비")
        d.get_by_role("button", name="계획 저장").click()
        page.get_by_text("계획을 저장했어요.").wait_for()
        page.keyboard.press("Escape")
        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(base + "/#agent")
        page.get_by_role("heading", name="한끼 코치").wait_for()
        welcome = page.locator(".bubble.welcome")
        for role in ("ai", "chef", "trainer"):
            image = welcome.locator(f".avatar.{role} img")
            image.evaluate("(img) => img.decode()")
            assert image.get_attribute("src") == f"/static/personas/{role}.webp"
        snap("coach-mobile")

        def ask(message, role):
            count = page.locator(".chat-log .agent[id]").count()
            page.get_by_label("지금 상황").fill(message)
            page.get_by_role("button", name="보내기", exact=True).click()
            card = page.locator(".chat-log .agent[id]").nth(count)
            card.wait_for()
            avatar = card.locator(f".avatar.{role} img")
            avatar.evaluate("(img) => img.decode()")
            assert avatar.get_attribute("src") == f"/static/personas/{role}.webp"
            return card

        ask("안녕", "ai")
        trainer = ask("어깨 운동 30분 하고 싶어", "trainer")
        trainer.locator(".persona-name").evaluate("(el) => el.scrollIntoView({block: 'start'})")
        snap("trainer-mobile")
        ask("헬스장 강남역", "trainer").get_by_role("link", name="카카오맵 검색").wait_for()
        ask("영상 두부구이", "chef").get_by_role("link", name="YouTube 검색").wait_for()
        chef = ask("두부로 저녁 추천해줘", "chef")
        chef.locator(".persona-name").evaluate("(el) => el.scrollIntoView({block: 'start'})")
        snap("chef-mobile")
        chef.get_by_role("button", name="이번 실행 과정").click()
        d.get_by_role("heading", name="이번 실행 과정").wait_for()
        assert d.locator(".trace li").count() > 3
        snap("coach-saved-trace-mobile")
        page.keyboard.press("Escape")
        chef.get_by_role("button", name="이 메뉴 일정 저장").click()
        start = d.get_by_label("시작", exact=True).input_value()
        end = d.get_by_label("종료", exact=True).input_value()
        assert start < end
        d.get_by_role("button", name="계획 저장").click()
        d.get_by_text("저장됨 · 겹치는 계획", exact=False).wait_for()
        rows = page.request.get(base + "/api/plans").json()
        saved = next(row for row in rows if any(item.get("kind") == "meal" and item["servings"] == 1 for item in row["items"]))
        detail = page.request.get(base + "/api/plans/" + str(saved["id"])).json()
        assert detail == saved
        snap("coach-plan-mobile")
        page.keyboard.press("Escape")
        ask("레시피 두부구이", "chef").get_by_role("button", name="결과 자세히 보기").click()
        page.locator("dialog[open]").get_by_text("이번 실행 과정", exact=False).click()
        snap("trace-mobile")
        page.keyboard.press("Escape")

        def water():
            return page.request.get(base + "/api/state").json()["건강"]["totals"]["water_ml"]["value"]

        before = water()
        ids = []

        def lose_first_reply(route):
            ids.append(route.request.post_data_json["request_id"])
            response = route.fetch()
            assert response.ok
            if len(ids) == 1:
                route.abort()
            else:
                route.fulfill(response=response)

        page.route("**/api/chat", lose_first_reply)
        page.get_by_label("지금 상황").fill("물 500ml")
        page.get_by_role("button", name="보내기", exact=True).click()
        retry = page.get_by_role("button", name="다시 보내기")
        retry.wait_for()
        assert water() == before + 500
        page.reload()
        retry.click()
        retry.wait_for(state="hidden")
        assert len(ids) == 2 and ids[0] == ids[1]
        assert water() == before + 500
        page.unroute("**/api/chat", lose_first_reply)
        page.goto(base + "/#pantry")
        page.get_by_role("button", name="재료 추가", exact=True).first.click()
        d = page.locator("dialog[open]")
        d.get_by_label("재료 이름").fill("양배추")
        d.get_by_role("button", name="냉장고에 넣기").click()
        d.wait_for(state="hidden")
        page.goto(base + "/#recipes")
        page.get_by_label("메뉴 검색").fill("양배추 두부덮밥")
        recipe = page.locator("#meal-list .recipe-entry").first
        recipe.get_by_role("button", name="찜하기").click()
        recipe.get_by_role("button", name="찜 해제").wait_for()
        page.reload()
        page.get_by_role("button", name="찜한 레시피", exact=True).click()
        assert page.locator("#meal-list .recipe-entry").count() == 1
        recipe.get_by_role("button", name="조리 모드").click()
        d.get_by_role("button", name="+", exact=True).click()
        d.get_by_text("2인분", exact=True).wait_for()
        d.get_by_role("button", name="분량 입력").click()
        d.get_by_label("남은 양").fill("140")
        d.get_by_role("button", name="냉장고에 반영").click()
        d.get_by_text("60g 부족", exact=True).wait_for()
        snap("recipe-portions-mobile")
        d.get_by_role("button", name="2단계", exact=True).click()
        technique = d.locator(".technique-photo img")
        technique.evaluate("(img) => img.decode()")
        assert technique.get_attribute("src") == "/static/techniques/chop.webp"
        snap("cabbage-chopping-mobile")
        d.get_by_role("button", name="1단계", exact=True).click()
        cart = d.locator('[data-do="guideCart"]')
        cart.click()
        page.wait_for_url("**/#pantry")
        page.get_by_text("양배추 · 60g", exact=True).wait_for()
        page.goto(base + "/#recipes")
        page.get_by_role("button", name="최근 조리", exact=True).click()
        assert page.locator("#meal-list .recipe-entry").count() >= 1
        page.get_by_role("button", name="전체", exact=True).click()
        page.get_by_label("메뉴 검색").fill("사과 아몬드 오트죽")
        page.locator("#meal-list").get_by_role("button", name="조리 모드").click()
        d.get_by_role("button", name="3단계", exact=True).click()
        page.clock.install()
        d.get_by_role("button", name="시작", exact=True).click()
        page.clock.fast_forward(360_000)
        d.get_by_role("button", name="다시 시작").wait_for()
        assert d.locator("#cook-clock").inner_text() == "00:00"
        d.get_by_role("button", name="다시 시작").click()
        assert d.locator("#cook-clock").inner_text() == "06:00"
        page.keyboard.press("Escape")
        page.goto(base + "/#recipes")
        page.get_by_label("메뉴 검색").fill("새우 가지 토마토스튜")
        page.locator("#meal-list").get_by_role("button", name="조리 모드").click()
        d.get_by_role("button", name="2단계", exact=True).wait_for()
        page.keyboard.press("Escape")
        page.goto(base + "/#agent")
        page.evaluate("""() => {
          const rows = JSON.parse(localStorage.getItem("hk-thread-v1"));
          rows.push({role: "user", text: "어제 기록", at: Date.now() - 86400000});
          localStorage.setItem("hk-thread-v1", JSON.stringify(rows));
        }""")
        page.reload()
        days = page.get_by_label("대화 날짜")
        days.wait_for()
        assert page.get_by_text("어제 기록", exact=True).count() == 0
        days.select_option(index=1)
        page.get_by_text("어제 기록", exact=True).wait_for()
        page.get_by_role("button", name="문구 수정").click()
        d.get_by_label("기록할 문구").fill("어제 저녁 기록")
        d.get_by_role("button", name="저장", exact=True).click()
        page.get_by_text("어제 저녁 기록", exact=True).wait_for()
        snap("coach-history-mobile")
        page.once("dialog", lambda prompt: prompt.dismiss())
        page.get_by_role("button", name="이 날짜 대화 지우기").click()
        page.get_by_text("어제 저녁 기록", exact=True).wait_for()
        page.once("dialog", lambda prompt: prompt.accept())
        page.get_by_role("button", name="이 날짜 대화 지우기").click()
        assert days.locator("option").count() == 1
        assert page.locator(".bubble.user").count() > 0
        page.once("dialog", lambda prompt: prompt.accept())
        page.get_by_role("button", name="전체 대화 초기화").click()
        page.reload()
        days.wait_for()
        assert page.locator(".bubble.user").count() == 0
        assert water() == before + 500
        paths = page.request.get(base + "/openapi.json").json()["paths"]
        assert {"/api/chat", "/api/plans", "/api/logs", "/api/logs/{session_id}"} <= paths.keys()
        assert not errs, errs
        print(
            "PASS · pantry, cook, intake, exercise, water, shopping, calendar, coach portraits, search cards, execution trace, retry after reload, saved recipes, measured lots, multi-serving cart and timer restart"
        )
        b.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--screens", type=Path)
    parser.add_argument("--chromium", default=None)
    arg = parser.parse_args()
    with TemporaryDirectory() as tmp, socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        base = f"http://127.0.0.1:{port}"
        dest = arg.screens or Path(tmp) / "screens"
        dest.mkdir(parents=True, exist_ok=True)
        env = {**os.environ, "FRIDGE_DATA_DIR": tmp, "FRIDGE_MODE": "local", "FRIDGE_DEMO": "0", "PORT": str(port)}
        server = subprocess.Popen(
            [sys.executable, str(HERE / "app.py")],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            stop = monotonic() + 30
            while monotonic() < stop:
                try:
                    with urlopen(base + "/api/state", timeout=1):
                        break
                except OSError:
                    sleep(0.15)
            check(dest, base, arg.chromium)
        finally:
            server.terminate()
            server.wait(timeout=10)
