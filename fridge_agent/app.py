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
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
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
from workflow import execute

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
        if request.url.path.startswith("/api/"):
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
    result = execute(
        command, arg, lambda: snap["계획"], emit, snap["냉장고"], steps, request=message if natural else None
    )
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
    return snapshot(KitchenDB().read(session_id)[1])


@app.get("/api/tools")
def tools():
    return definitions()


@app.get("/api/catalog")
def recipes(session_id: str = "default"):
    meals, refs = kitchen_catalog(KitchenDB().read(session_id)[1])
    return {
        "meals": list(meals.values()),
        "ingredients": list(refs.values()),
        "exercises": json.loads((HERE / "assets" / "training.json").read_text()),
    }


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
    return (HERE / "index.html").read_text()


@app.get("/privacy", response_class=HTMLResponse)
def privacy():
    return (HERE / "privacy.html").read_text()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("PORT", "8000")))
