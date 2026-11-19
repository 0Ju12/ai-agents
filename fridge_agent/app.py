"""한끼. Launch from fridge_agent with python app.py."""

import hashlib
import json
import os
import re
import secrets
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from dotenv import load_dotenv

load_dotenv(HERE / ".env", override=False)
import mimetypes

# Windows 는 확장자별 형식을 레지스트리에서 읽어 .js 가 text/plain 으로 나가는 PC 가 있다.
# nosniff 헤더 때문에 브라우저가 스크립트를 실행하지 않으므로 형식을 직접 지정한다.
for _ext, _type in {".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".webp": "image/webp", ".json": "application/json"}.items():
    mimetypes.add_type(_type, _ext)
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError
from backend.api.deps import get_store
from backend.api.routers import plans, logs
from backend.events.bus import EventBus
from backend.logging_agent.agent import LoggingAgent
from api_models import ScreenState, ChatReply
from calendar_adapter import earliest_window
from domain.catalog import canonical, SUBSTITUTES
from domain.kitchen import add_lot, add_text, cook, eat, inventory, leftovers, suggest
from domain.shopping import add_shortages, comparable
from domain.training import GOALS, LEVELS, MOVES, routine
from interpretation import COMMANDS, parse
from journal import summary, weekly
from oauth_calendar import router as oauth_router
from registry import definitions
from storage import (
    KitchenDB,
    catalog,
    fingerprint,
    home_dir,
    household,
    local_store,
    ReceiptConflict,
    RevisionConflict,
    today,
)
import workflow
from workflow import execute
import autopilot
import reminders
import cook_guide
import food_tools
import media
import photos
import video_guide

app = FastAPI(title="한끼 · 냉장고 생활 코치", version="1.0.0")
app.dependency_overrides[get_store] = local_store
app.include_router(oauth_router)
app.include_router(plans.router)
app.include_router(logs.router)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")


@app.middleware("http")
async def scope_request(request, call_next):
    isolated = os.getenv("FRIDGE_MODE", "local") == "server"
    incoming = request.cookies.get("hankki_home", "")
    fresh = not re.fullmatch(r"[0-9a-f]{64}", incoming)
    token = secrets.token_hex(32) if fresh else incoming
    context = household.set(hashlib.sha256(token.encode()).hexdigest() if isolated else "local")
    try:
        origin = request.headers.get("origin")
        if (
            request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and origin
            and urlsplit(origin).netloc != request.headers.get("host")
        ):
            return JSONResponse({"detail": "같은 앱 화면에서 다시 시도하세요."}, 403)
        res = await call_next(request)
        if fresh and isolated:
            res.set_cookie(
                "hankki_home",
                token,
                httponly=True,
                secure=request.url.scheme == "https" or os.getenv("FRIDGE_HTTPS", "1") == "1",
                samesite="lax",
                max_age=31536000,
            )
        res.headers["Referrer-Policy"] = "no-referrer"
        res.headers["X-Content-Type-Options"] = "nosniff"
        if request.url.path.startswith("/api/") and not request.url.path.startswith("/api/media"):
            res.headers["Cache-Control"] = "no-store"
        return res
    finally:
        household.reset(context)


@app.exception_handler(RequestValidationError)
async def bad_request(request, exc):
    return JSONResponse({"detail": "입력 형식이나 범위를 확인하세요."}, 422)


class Message(BaseModel):
    session_id: str = Field(default="default", min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=1000)
    params: dict[str, Any] = Field(default_factory=dict, max_length=20)
    request_id: str | None = Field(default=None, min_length=1, max_length=100)


class Settings(BaseModel):
    goal: str | None = None
    level: str | None = None
    body: str | None = None
    gear: list[str] | None = Field(default=None, max_length=3)
    diet: str | None = None
    avoid: list[str] | None = Field(default=None, max_length=25)
    priority: str | None = Field(default=None, max_length=50)
    minutes: int | None = Field(default=None, ge=1, le=240)
    exercise_minutes: int | None = Field(default=None, ge=5, le=120)
    budget_krw: int | None = Field(default=None, ge=0, le=10000000)
    area: str | None = Field(default=None, max_length=60)
    targets: dict[str, float] | None = Field(default=None, max_length=6)


def update_settings(state, params):
    changes = Settings.model_validate(params).model_dump(exclude_none=True)
    limits = {"body": MOVES, "goal": GOALS, "level": LEVELS, "diet": {"균형", "식물성", "단백질 우선"}}
    for k, valid in limits.items():
        if k in changes and changes[k] not in valid:
            raise ValueError("지원하는 조건을 선택하세요.")
    if "gear" in changes and set(changes["gear"]) - {"맨몸", "덤벨"}:
        raise ValueError("기구 종류를 확인하세요.")
    if "avoid" in changes:
        changes["avoid"] = [canonical(x) for x in changes["avoid"] if x.strip() and len(x) <= 50]
    if "targets" in changes:
        maxima = {"water_ml": 10000, "protein_g": 400, "fiber_g": 100, "kcal": 8000}
        if any(k not in maxima or not 0 < v <= maxima[k] for k, v in changes["targets"].items()):
            raise ValueError("직접 설정할 목표 수치를 확인하세요.")
    state.update(changes)


def health_import(daily, params, day):
    if params.get("day") != day:
        raise ValueError("오늘 날짜의 Health Connect 합계만 가져올 수 있습니다.")
    bounds = {
        "water_ml": 30000,
        "sleep_hours": 24,
        "protein_g": 1000,
        "kcal": 30000,
        "exercise_minutes": 1440,
    }
    values = {k: float(params[k]) for k in bounds if k in params and params[k] is not None}
    if not values or any(not 0 <= v <= bounds[k] for k, v in values.items()):
        raise ValueError("건강 기록 범위를 확인하세요.")
    daily["health_connect"] = values


def kitchen_catalog(state):
    meals, refs = catalog()
    return {**meals, **state.get("imported_meals", {})}, refs


def import_recipe(state, params):
    row = state.get("external_recipes", {}).get(str(params.get("id", "")))
    if not row or not row.get("조리 순서"):
        raise ValueError("국내 레시피를 검색해 원문을 먼저 확인하세요.")
    minutes = int(params["minutes"])
    grams = {canonical(k): float(v) for k, v in params.get("grams", {}).items()}
    if (
        not 1 <= minutes <= 600
        or not 1 <= len(grams) <= 40
        or any(not k or len(k) > 40 or not 0 < v <= 10000 for k, v in grams.items())
    ):
        raise ValueError("확인한 1인분 재료 중량과 조리시간을 입력하세요.")
    title = row["메뉴"] + " · 내 레시피"
    state.setdefault("imported_meals", {})[title] = {
        "title": title,
        "minutes": minutes,
        "grams": grams,
        "steps": row["조리 순서"],
        "source": "식품안전나라 COOKRCP01 #" + str(row["id"]) + " · 사용자가 확인한 시간·1인분 분량",
    }
    state["wanted"] = title
    state["view_wanted"] = True


def change(state, cmd, arg, params, day, emit):
    daily = state["daily"].setdefault(day, {})
    meals, _ = kitchen_catalog(state)
    if cmd == "장바구니담기":
        servings = int(params.get("servings", 1))
        if not 1 <= servings <= 20:
            raise ValueError("1~20인분으로 입력하세요.")
        add_shortages(state, state.get("last_meal", {}), servings)
    elif cmd == "구매완료":
        name = canonical(arg)
        if name not in state.get("cart", {}):
            raise ValueError("장바구니에서 재료를 선택하세요.")
        if params.get("quantity") is None:
            raise ValueError("실제로 구입한 포장 용량을 입력하세요.")
        add_lot(state, name, params["quantity"], params.get("unit", "g"), params.get("expires") or None)
        remaining = round(state["cart"][name]["grams"] - state["lots"][-1]["grams"], 2)
        if remaining > 0:
            state["cart"][name]["grams"] = remaining
        else:
            del state["cart"][name]
    elif cmd == "장바구니삭제":
        state.get("cart", {}).pop(canonical(arg), None)
    elif cmd == "레시피저장":
        import_recipe(state, params)
    elif cmd == "추가":
        names = [x.strip() for x in arg.split(",") if x.strip()]
        if not names:
            raise ValueError("재료 이름을 입력하세요.")
        add_text(state, names)
    elif cmd == "입고":
        names = [x.strip() for x in str(params.get("name", "")).split(",") if x.strip()]
        if not names or len(names) > 40:
            raise ValueError("등록할 재료 이름을 확인하세요.")
        if len(names) > 1 and (params.get("quantity") is not None or params.get("expires")):
            raise ValueError("용량이나 기한을 입력할 때는 재료를 하나씩 등록하세요.")
        for name in names:
            add_lot(
                state, name, params.get("quantity"), params.get("unit", "g"), params.get("expires") or None
            )
    elif cmd == "포장삭제":
        if not any(l["id"] == arg for l in state["lots"]):
            raise ValueError("포장을 찾지 못했습니다.")
        state["lots"] = [l for l in state["lots"] if l["id"] != arg]
    elif cmd == "삭제":
        remove = {canonical(x) for x in arg.split(",")}
        state["lots"] = [l for l in state["lots"] if l["item"] not in remove]
    elif cmd == "시간":
        update_settings(state, {"minutes": int(arg.removesuffix("분"))})
    elif cmd in {"부위", "목표"}:
        update_settings(state, {{"부위": "body", "목표": "goal"}[cmd]: arg})
    elif cmd == "설정":
        update_settings(state, params)
    elif cmd == "시간대":
        if arg == "해제":
            state.pop("window", None)
        else:
            d, t = arg.split()
            date.fromisoformat(d)
            datetime.strptime(t, "%H:%M")
            state["window"] = {"day": d, "start": t}
    elif cmd == "메뉴":
        if arg not in meals and arg != "자동":
            raise ValueError(
                "레시피 목록에서 메뉴를 선택하세요. ‘레시피 메뉴명’으로 국내 레시피도 검색할 수 있습니다."
            )
        state["wanted"] = None if arg == "자동" else arg
        state["view_wanted"] = arg != "자동"
    elif cmd == "대체":
        if arg == "해제":
            state["swaps"] = {}
        else:
            pair = arg.split("/")
            original, replacement = ("대파", arg) if len(pair) == 1 else [x.strip() for x in pair]
            if replacement not in SUBSTITUTES.get(original, set()):
                raise ValueError("지원하는 대체 재료 조합을 선택하세요.")
            state.setdefault("swaps", {})[original] = replacement
    elif cmd in {"외식", "집밥"}:
        state["view_wanted"] = False
        state["out_date"] = day if cmd == "외식" else None
        emit("replan", "식사 일정 변경", reason=cmd)
    elif cmd == "물":
        if not arg.isdecimal() or not 1 <= int(arg) <= 2000:
            raise ValueError("물은 1회 1~2000mL로 입력하세요.")
        daily["water_ml"] = daily.get("water_ml", 0) + int(arg)
    elif cmd == "수면":
        hours = float(arg)
        if not 0 <= hours <= 24:
            raise ValueError("수면 시간을 0~24시간으로 입력하세요.")
        daily["sleep_hours"] = hours
    elif cmd == "조리":
        match = re.fullmatch(r"(\d+)인분 (\d+)분", arg)
        if not match:
            raise ValueError("조리 2인분 15분 형식으로 입력하세요.")
        cook(state, int(match[1]), int(match[2]), day)
        state["view_wanted"] = False
    elif cmd == "섭취":
        eat(state, arg, daily)
    elif cmd == "사진식사":
        items = params.get("items")
        if not isinstance(items, list) or not 1 <= len(items) <= 15:
            raise ValueError("확인한 음식을 1~15개 선택하세요.")
        checked = []
        for x in items:
            name, grams = canonical(str(x.get("name", ""))), float(x.get("grams") or 0)
            if not 1 <= len(name) <= 40 or not 1 <= grams <= 3000:
                raise ValueError("음식 이름과 1~3000g 사이의 양을 확인하세요.")
            checked.append({"name": name, "grams": grams})
        facts = photos.nutrition(checked, kitchen_catalog(state)[1])
        daily.setdefault("eaten", []).append(" · ".join(x["name"] for x in checked))
        daily.setdefault("intake", []).append(
            {
                "title": "사진 기록 · " + ", ".join(x["name"] for x in checked),
                "nutrients": facts["합계"] or {},
                "source": "사진 후보를 사용자가 확인 · " + facts["출처"],
                "unverified": facts["미확인"],
            }
        )
    elif cmd == "알림추가":
        reminders.add(state, params)
    elif cmd == "알림삭제":
        reminders.remove(state, arg)
    elif cmd == "알림토글":
        reminders.toggle(state, arg)
    elif cmd == "영양제복용":
        reminders.take(state, daily, arg, reminders.now_hhmm())
    elif cmd == "데모":
        autopilot.seed_demo(state, day)
    elif cmd == "영상링크":
        autopilot.add_link(state, params.get("menu"), params.get("url"))
    elif cmd == "건강연동":
        health_import(daily, params, day)
    elif cmd == "운동완료":
        effort = params.get("effort", "적당함")
        mins = int(params.get("minutes", 0))
        if effort not in {"쉬움", "적당함", "어려움"} or not 1 <= mins <= 240:
            raise ValueError("운동 시간과 체감 난이도를 확인하세요.")
        body = params.get("body") or state.get("body") or GOALS[state["goal"]]
        if body not in MOVES:
            raise ValueError("운동 부위를 확인하세요.")
        state["workouts"].append({"day": day, "body": body, "effort": effort, "minutes": mins})
        daily["exercise_minutes"] = daily.get("exercise_minutes", 0) + mins


def snapshot(state):
    day = today().isoformat()
    meals, refs = kitchen_catalog(state)
    window = state.get("window", {})
    ref = window.get("day") or day
    limit = window.get("available") if "start" in window else None
    plan = suggest(state, meals, refs, ref, limit)
    if window:
        plan["시간대"] = window
        if window.get("start") and limit is not None and plan.get("조리시간(분)"):
            h, m = map(int, window["start"].split(":"))
            end = min(1440, 60 * h + m + min(state["minutes"], limit))
            latest = end - plan["조리시간(분)"]
            plan["늦어도 조리 시작"] = f"{latest // 60:02d}:{latest % 60:02d}"
        if window.get("status") == "일정 미확인":
            plan["일정 안내"] = "캘린더를 확인하지 못해 일정 충족 여부는 미확인입니다."
    return {
        "날짜": day,
        "냉장고": sorted(inventory(state, day)),
        "포장": state["lots"],
        "장바구니": state.get("cart", {}),
        "총 가용 시간": state["minutes"],
        "목표": state["goal"],
        "계획": plan,
        "오늘 기록": state["daily"].get(day, {}),
        "건강": summary(state, day),
        "남은 음식": leftovers(state),
        "조리 기록": state["records"][-7:],
        "운동 기록": state["workouts"][-7:],
        "설정": {
            k: state.get(k)
            for k in (
                "minutes",
                "goal",
                "body",
                "level",
                "diet",
                "avoid",
                "gear",
                "priority",
                "targets",
                "exercise_minutes",
                "window",
                "wanted",
                "swaps",
                "area",
                "budget_krw",
            )
        },
        "운동 계획": routine(state, state["minutes"]),
        "메뉴 목록": list(meals),
    }


def run(message, db_path=None, session_id="default", params=None, request_id=None):
    params = params or {}
    message = message.strip()
    if not message:
        raise ValueError("요청을 입력하세요.")
    db = KitchenDB(db_path)
    signature = fingerprint(message, params)
    prior = db.receipt(session_id, request_id, signature)
    if prior is not None:
        return prior
    revision, state = db.read(session_id)
    bus = EventBus()
    steps = []
    run_id = uuid4().hex
    LoggingAgent(local_store()).attach(bus)
    bus.subscribe(lambda event: steps.append(event.to_dict()))

    def emit(kind, label, **payload):
        bus.emit(session_id, kind, label, run_id=run_id, **payload)

    emit("node_start", "분석")
    previous = state.get("previous_topic", {})
    follow = {
        "그 레시피 영상": "영상",
        "그 메뉴 영상": "영상",
        "그 재료 쇼핑": "쇼핑",
        "거기 헬스장": "헬스장",
    }
    if message in follow:
        topic = (
            state.get("area")
            if message == "거기 헬스장"
            else previous.get("ingredient")
            if message == "그 재료 쇼핑"
            else previous.get("menu")
        )
        message = follow[message] + " " + topic if topic else "확인 이전 메뉴나 지역을 먼저 알려주세요."
    intent = parse(message, emit)
    command, arg = intent.action, intent.argument
    explicit = message.partition(" ")[0] in {"알림추가", "알림삭제", "알림토글", "영양제복용"}
    spoken = None if explicit else reminders.from_text(message)  # '알려줘·알림'이 들어간 문장만
    if spoken:  # "비타민D 아침 9시에 알려줘", "물 2시간마다 알려줘"
        command, arg, params = "알림추가", "", spoken
        emit("llm_decision", "알림 해석", method="rule", decision=spoken["kind"], reason="알림 요청 문장")
    if command == "확인" and any(t in message for t in kitchen_catalog(state)[0]):
        command, arg = "추천", ""  # 메뉴 이름을 말한 상황 문장은 추천·자동 진행으로
    emit("llm_decision", "요청 분류", method="rule", decision=command, reason="요청과 변경할 조건 확인")
    emit("node_end", "분석")
    day = today().isoformat()
    add_text(state, intent.add)
    if intent.remove:
        state["lots"] = [l for l in state["lots"] if l["item"] not in {canonical(x) for x in intent.remove}]
    update_settings(
        state,
        intent.model_dump(
            include={"minutes", "goal", "body", "diet", "area", "budget_krw"}, exclude_none=True
        ),
    )
    if intent.day or intent.start or intent.end:
        window = state.setdefault("window", {})
        if intent.day:
            window["day"] = intent.day.isoformat()
        if intent.start:
            window["start"] = intent.start
        if intent.end:
            window["end"] = intent.end
    try:
        change(state, command, arg, params, day, emit)
    except (ValueError, TypeError, AttributeError) as exc:
        emit("error", "입력 확인", reason="입력 범위 또는 현재 재고 확인")
        raise ValueError(
            str(exc)
            if isinstance(exc, ValueError)
            and not isinstance(exc, ValidationError)
            and re.search("[가-힣]", str(exc))
            else "입력값의 형식이나 범위를 확인하세요."
        ) from exc
    window = state.get("window", {})
    if window.get("start") and command not in {"도움말", "확인"}:
        datekey = window.get("day", day)
        cal = execute("일정조회", datekey, lambda: {}, emit, events=steps)["조회"]
        duration = state["minutes"]
        if window.get("end"):

            def mins(t):
                h, m = map(int, t.split(":"))
                return h * 60 + m

            duration = max(0, min(duration, mins(window["end"]) - mins(window["start"])))
        window["available"] = (
            earliest_window(window["start"], duration, cal["data"]) if cal["ok"] else duration
        )
        window["status"] = "일정 확인" if cal["ok"] else "일정 미확인"
    snap = snapshot(state)
    if command == "헬스장" and not arg:
        arg = state.get("area") or ""
    natural = message.strip().partition(" ")[0] not in COMMANDS  # 명령어가 아니면 모델이 계획·응답에 참여
    auto = natural and command in {"추천", "집밥", "메뉴"}  # 상황 문장 → 자동 진행
    result = execute(
        command, arg, lambda: snap["계획"], emit, snap["냉장고"], steps,
        request=message if natural else None, speak=not auto,
    )
    if auto:
        meals, refs = kitchen_catalog(state)
        limit = window.get("available") if "start" in window else None

        def find_media(menu):
            count = len(meals.get(menu, {}).get("steps", []))
            found = video_guide.media_for(menu, meals.get(menu, {}).get("steps", []), emit)
            return autopilot.merge_links(found, state.get("media_links", {}).get(menu, []), count)

        named = next((t for t in sorted(meals, key=len, reverse=True) if t in message), None)
        extra = autopilot.run(state, message, meals, refs, day, emit, limit, find_media, named)
        snap = snapshot(state)
        result = workflow.answer(message, {**snap["계획"], **extra}, emit)
    if command == "레시피" and result.get("조회", {}).get("ok"):
        state["external_recipes"] = {str(x["id"]): x for x in result["조회"]["data"] if x.get("id")}
    if command == "쇼핑":
        upper = state.get("budget_krw") or 0
        needed = state.get("cart", {}).get(arg, {}).get("grams") or snap["계획"].get("부족량(g)", {}).get(
            arg
        )
        for provider in result.get("자료", {}).values():
            if provider.get("ok"):
                for row in provider["data"]:
                    price = row.get("price_krw")
                    row.update(comparable(row.get("title"), needed, price))
                    if upper:
                        row["예산 판정"] = (
                            "상품가 미확인"
                            if price is None
                            else "상품가 예산 이내"
                            if price <= upper
                            else "상품가 예산 초과"
                        )
        if upper:
            result["예산 안내"] = (
                f"상품 1개 표시가 기준 {upper:,}원 · 배송비와 구매 중량은 판매처에서 확인하세요."
            )
    menu = result.get("메뉴") or snap["계획"].get("메뉴")
    if menu:
        previous["menu"] = menu
    if command in {"쇼핑", "식품영양", "검색"} and arg:
        previous["ingredient"] = arg
    if command == "헬스장" and arg:
        state["area"] = arg
    state["previous_topic"] = previous
    if command == "주간계획":
        result = {"주간": weekly(state, *kitchen_catalog(state), day)}
    if snap["계획"].get("예시 1인분(g)"):
        state["last_meal"] = snap["계획"]
    elif command in {"메뉴", "외식", "설정", "추천", "시간", "삭제", "포장삭제", "시간대"}:
        state.pop("last_meal", None)
    snap.update(
        {
            "이용 안내": "일반 생활 참고 정보입니다. 질환이나 치료에 관한 결정은 의료진과 상의하세요.",
            "계획": result,
            "현재 추천": snap["계획"],
            "실행 단계": [[e["type"], e["name"]] for e in steps],
            "추적": steps,
            "실행 ID": run_id,
        }
    )
    return db.commit(session_id, revision, state, snap, request_id, signature)


@app.post("/api/chat", response_model=ChatReply)
def chat(body: Message):
    try:
        return run(body.message, session_id=body.session_id, params=body.params, request_id=body.request_id)
    except (ReceiptConflict, RevisionConflict) as exc:
        raise HTTPException(409, "기록이 갱신됐습니다. 새로고침 후 다시 시도하세요.") from exc
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            422, str(exc) if re.search("[가-힣]", str(exc)) else "입력값을 확인하세요."
        ) from exc


@app.get("/api/state", response_model=ScreenState)
def state(session_id: str = "default"):
    current = KitchenDB().read(session_id)[1]
    # 예시 냉장고: FRIDGE_DEMO=1 이고 아직 한 번도 채우지 않은 빈 냉장고면 화면이 /api/demo 를 부른다
    demo = os.getenv("FRIDGE_DEMO") == "1" and not current["lots"] and not current.get("demo_seeded")
    return {**snapshot(current), "데모 필요": demo}


@app.get("/api/reminders")
def reminder_list(session_id: str = "default"):
    """오늘 알림 일정과 상태. Android 는 이 목록으로 시스템 알림을 예약한다."""
    state = KitchenDB().read(session_id)[1]
    now = reminders.now_hhmm()
    return {"now": now, "items": reminders.overview(state, state["daily"].get(today().isoformat(), {}), now)}


@app.get("/api/reminders/due")
def reminder_due(session_id: str = "default", now: str | None = None):
    """지금 보낼 알림(물은 진도보다 뒤처졌을 때만, 영양제는 아직 안 먹었을 때만)."""
    now = now if now and reminders.HHMM.match(now) else reminders.now_hhmm()
    state = KitchenDB().read(session_id)[1]
    return {"now": now, "due": reminders.due(state, state["daily"].get(today().isoformat(), {}), now)}


class DemoRequest(BaseModel):
    session_id: str = Field(default="default", min_length=1, max_length=80)


@app.post("/api/demo")
def demo(body: DemoRequest):
    """예시 재료로 냉장고 채우기 (소비기한이 다른 18가지)."""
    return run("데모", session_id=body.session_id)


@app.get("/api/tools")
def tools():
    return definitions()


@app.get("/api/catalog")
def recipes(session_id: str = "default"):
    meals, refs = kitchen_catalog(KitchenDB().read(session_id)[1])
    return {
        "meals": list(meals.values()),
        "ingredients": list(refs.values()),
        "exercises": json.loads((HERE / "assets" / "training.json").read_text(encoding="utf-8")),
    }


def tracer(session_id):
    """채팅 밖 기능(사진·조리 모드)도 같은 로깅 Agent 로 실행 이벤트를 남긴다."""
    bus, steps, run_id = EventBus(), [], uuid4().hex
    LoggingAgent(local_store()).attach(bus)
    bus.subscribe(lambda event: steps.append(event.to_dict()))
    return (lambda kind, label, **p: bus.emit(session_id, kind, label, run_id=run_id, **p)), steps


class GuideRequest(BaseModel):
    session_id: str = Field(default="default", min_length=1, max_length=80)
    title: str | None = Field(default=None, max_length=80)
    recipe_id: str | None = Field(default=None, max_length=40)
    servings: int = Field(default=1, ge=1, le=20)


@app.post("/api/guide")
def guide(body: GuideRequest):
    """조리 모드 단계 카드. 내 레시피 목록(title) 또는 조회한 국내 레시피(recipe_id)."""
    state = KitchenDB().read(body.session_id)[1]
    emit, steps = tracer(body.session_id)
    emit("node_start", "조리 가이드")
    stock = snapshot(state)["냉장고"]
    try:
        if body.recipe_id:
            row = state.get("external_recipes", {}).get(body.recipe_id)
            if not row:
                raise ValueError("국내 레시피를 먼저 조회하세요.")
            result = cook_guide.build(
                row["메뉴"], row.get("조리 순서", []), raw_ingredients=row.get("재료·분량"),
                photos=row.get("단계 사진"), servings=body.servings, stock=stock,
                source="식품안전나라 COOKRCP01 #" + str(row["id"]), emit=emit,
            )
            result["대표 사진"] = row.get("대표 사진")
            media.decorate(result, "kr:" + body.recipe_id)
        else:
            meal = kitchen_catalog(state)[0].get(body.title or "")
            if not meal:
                raise ValueError("레시피 목록에서 메뉴를 선택하세요.")
            result = cook_guide.build(
                meal["title"], meal["steps"], grams=meal["grams"], servings=body.servings,
                stock=stock, source=meal.get("source", ""), emit=emit,
            )
            media.decorate(result, "meal:" + meal["title"])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    emit("node_end", "조리 가이드")
    return {**result, "추적": steps}


class MediaRequest(BaseModel):
    session_id: str = Field(default="default", min_length=1, max_length=80)
    menu: str = Field(min_length=1, max_length=80)
    steps: list[str] = Field(default_factory=list, max_length=40)


@app.post("/api/guide/media")
def guide_media(body: MediaRequest):
    """조리 모드 영상 탭: YouTube 영상(단계별 시작 초)과 Instagram 게시물."""
    emit, steps = tracer(body.session_id)
    emit("node_start", "조리 영상")
    menu = body.menu.strip()
    result = video_guide.media_for(menu, [s[:300] for s in body.steps], emit)
    links = KitchenDB().read(body.session_id)[1].get("media_links", {}).get(menu, [])
    result = autopilot.merge_links(result, links, len(body.steps))
    emit("node_end", "조리 영상")
    return {**result, "추적": steps}


@app.get("/api/media")
def media_photo(u: str):
    try:
        path, mime = media.cached(u)
    except (ValueError, OSError) as exc:
        raise HTTPException(404, "사진을 불러오지 못했어요.") from exc
    return FileResponse(path, media_type=mime, headers={"Cache-Control": "public, max-age=604800"})


@app.get("/api/media/depth")
def media_depth(u: str):
    path = media.depth_path(u) if media.allowed(u) else None
    if not path:
        raise HTTPException(404, "깊이 맵이 없습니다.")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "public, max-age=604800"})


@app.get("/api/media/clip/{recipe_key}/{step}")
def media_clip(recipe_key: str, step: int):
    if not re.fullmatch(r"[0-9a-f]{32}", recipe_key) or not 1 <= step <= 40:
        raise HTTPException(404, "클립이 없습니다.")
    path = media.clip_by_key(recipe_key, step)
    if not path:
        raise HTTPException(404, "검수 승인된 클립이 없습니다.")
    return FileResponse(path, media_type="video/mp4")


class PhotoRequest(BaseModel):
    session_id: str = Field(default="default", min_length=1, max_length=80)
    kind: str = Field(pattern="^(meal|fridge)$")
    image: str = Field(min_length=100, max_length=7_000_000)


@app.post("/api/photo")
def photo(body: PhotoRequest):
    """식사·냉장고 사진 → 후보 목록. 저장은 사용자가 확인한 뒤 /api/chat 의 사진식사·입고로 한다."""
    state = KitchenDB().read(body.session_id)[1]
    emit, steps = tracer(body.session_id)
    emit("node_start", "사진 분석")
    try:
        result = photos.analyze(body.kind, body.image, kitchen_catalog(state)[1], snapshot(state)["냉장고"], emit)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    emit("node_end", "사진 분석")
    return {**result, "추적": steps}


@app.get("/api/barcode/{code}")
def barcode(code: str):
    """바코드 → 제품명·표시 영양 (Open Food Facts). 냉장고 등록 양식을 미리 채우는 데 쓴다."""
    if not re.fullmatch(r"\d{8,14}", code):
        raise HTTPException(422, "바코드 숫자 8~14자리를 확인하세요.")
    try:
        return food_tools.call("nutrition", code)
    except (OSError, ValueError, KeyError, TypeError):
        return {"ok": False, "error": "SOURCE_UNAVAILABLE"}


@app.get("/api/export")
def export(session_id: str = "default"):
    return {"version": 1, "kitchen": KitchenDB().read(session_id)[1], "plans": local_store().list_plans()}


@app.delete("/api/data", status_code=204)
def erase(confirm: str = ""):
    if confirm != "삭제":
        raise HTTPException(422, "삭제 확인이 필요합니다.")
    for key in ("fridge.sqlite3", "fridge_history.sqlite3", "calendar.sqlite3"):
        file = home_dir() / key
        if not file.exists():
            continue
        allowed = {
            "fridge.sqlite3": ["receipts", "days", "batches", "lots", "kitchens", "runs"],
            "fridge_history.sqlite3": ["run_logs", "plans"],
            "calendar.sqlite3": ["events", "oauth"],
        }[key]
        with sqlite3.connect(file) as db:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for t in allowed:
                if t in tables:
                    db.execute("DELETE FROM " + t)
    (home_dir() / "google-calendar.json").unlink(missing_ok=True)


@app.get("/", response_class=HTMLResponse)
def home():
    return (HERE / "index.html").read_text(encoding="utf-8")


@app.get("/privacy", response_class=HTMLResponse)
def privacy():
    return (HERE / "privacy.html").read_text(encoding="utf-8")


if __name__ == "__main__":
    import uvicorn

    os.environ.setdefault("FRIDGE_DEMO", "1")  # python app.py 로 켜면 빈 냉장고를 예시 재료로 채운다

    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("PORT", "8000")))
