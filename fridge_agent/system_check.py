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
        page.get_by_role("button", name="선택", exact=True).click()
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
        page.goto(base + "/#today")
        page.get_by_role("button", name="한끼 코치에게 물어보기").click()
        d = page.locator("dialog[open]")
        d.locator("textarea").fill("도움말")
        d.get_by_role("button", name="코치에게 보내기").click()
        d.get_by_text("이번 실행 과정", exact=False).click()
        snap("trace-mobile")
        assert not errs, errs
        print(
            "PASS · mobile pantry, cook, intake, workout view, water, desktop shopping, calendar create, mobile execution trace"
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
        env = {**os.environ, "FRIDGE_DATA_DIR": tmp, "FRIDGE_MODE": "local", "PORT": str(port)}
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
