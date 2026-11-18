"""1인용 냉장고·운동 에이전트. 실행: python app.py"""
import json
import os
import re
import sqlite3
import sys
from datetime import date
from functools import lru_cache

from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.events.bus import EventBus
from backend.logging_agent.agent import LoggingAgent
from backend.store.db import Store
from backend.api.deps import get_store
from backend.api.routers import plans, logs
from workflow import execute
from food_tools import CATALOG

app = FastAPI(title="냉장고 한 끼")
@lru_cache
def history(path):
    return Store(path)

def local_store():
    return history(str(Path("fridge_history.sqlite3").resolve()))

app.dependency_overrides[get_store] = local_store
app.include_router(plans.router)
app.include_router(logs.router)

@app.get("/api/tools")
def tools():
    return CATALOG

# 이름, 조리 분, 1인분 예시 중량(g), 조리 안내. 물은 기본 제공.
RECIPES = [
    ("두부 달걀찜", 15, {"두부": 100, "달걀": 50}, "으깬 두부와 달걀, 물을 섞어 속까지 익도록 찝니다."),
    ("삶은 달걀", 12, {"달걀": 50}, "달걀을 물에 넣고 완전히 익힌 뒤 껍질을 벗깁니다."),
    ("두부구이", 12, {"두부": 150, "식용유": 3}, "물기를 제거한 두부를 기름을 두른 팬에 앞뒤로 굽습니다."),
    ("김치볶음밥", 15, {"김치": 50, "밥": 180, "식용유": 5}, "기름에 김치를 볶은 뒤 밥을 넣고 골고루 익힙니다."),
    ("바나나 요거트", 3, {"바나나": 80, "플레인요거트": 100}, "바나나를 잘라 요거트에 넣습니다."),
    ("대파 달걀볶음", 10, {"대파": 20, "달걀": 100, "식용유": 3}, "팬에 대파를 볶다가 달걀을 넣고 완전히 익힙니다."),
]
KCAL = {"양파":40,"두부":80,"달걀":143,"식용유":884,"김치":23,"밥":150,"바나나":89,"플레인요거트":61,"대파":32}
ROUTINES = {"하체":"의자 앉았다 일어나기", "상체":"벽 밀기", "코어":"버드독", "전신":"제자리 걷기"}
GOALS = {"체력":"전신","근력":"하체","체중 관리":"전신"}

class Intent(BaseModel):
    action: str | None = None
    argument: str = ""
    add: list[str] = Field(default_factory=list, max_length=60)
    remove: list[str] = Field(default_factory=list, max_length=60)
    minutes: int | None = Field(default=None, ge=1, le=240)
    body: str | None = None
    goal: str | None = None

class Message(BaseModel):
    session_id: str = Field(default="default", min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=1000)

def name(value):
    value = value.strip()
    return {"계란":"달걀","플레인 요거트":"플레인요거트"}.get(value,value)

def interpret(message):
    action, _, value = message.partition(" ")
    value = value.strip()
    if action in ("추가","삭제") and value:
        items = [name(x) for x in value.split(",") if x.strip()]
        return Intent(**{"add" if action=="추가" else "remove":items})
    if action=="시간" and re.fullmatch(r"\d+분?",value):
        return Intent(minutes=int(value.rstrip("분")))
    if action=="부위" and value in ROUTINES: return Intent(body=value)
    if action=="목표" and value in GOALS: return Intent(goal=value)
    if message=="추천": return Intent()
    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("명령 예시: 추가 두부, 계란 / 삭제 달걀 / 시간 30 / 부위 코어 / 목표 체력 / 추천")
    prompt = ("한국어 생활 계획 요청에서 명시한 재고 변경과 조건만 JSON으로 추출한다. "
              "add/remove는 재료명 배열, minutes는 식사와 운동의 총 가용 분, body는 하체/상체/코어/전신, "
              "goal은 체력/근력/체중 관리. 외식, 집밥, 메뉴, 대체, 검색, 영양 요청은 action과 argument로 추출한다. 대체는 양파 또는 해제, 검색은 재료, 영양은 바코드, 메뉴는 메뉴 이름이다. 언급되지 않은 필드는 생략한다. 질문이나 가정은 재고 변경이 아니다.")
    payload = {"model":os.getenv("OPENAI_MODEL","gpt-4o-mini"),"response_format":{"type":"json_object"},
               "messages":[{"role":"system","content":prompt},{"role":"user","content":message}]}
    req = Request("https://api.openai.com/v1/chat/completions",json.dumps(payload).encode(),
                  {"Content-Type":"application/json","Authorization":"Bearer "+os.environ["OPENAI_API_KEY"]})
    with urlopen(req,timeout=20) as response:
        content = json.load(response)["choices"][0]["message"]["content"]
    return Intent.model_validate_json(content)

def recommend(state):
    stock = set(state["stock"])
    options = []
    for title, minutes, grams, guide in RECIPES:
        if state.get("wanted") and title != state["wanted"]: continue
        if title=="대파 달걀볶음" and state.get("substitute") and "대파" not in stock and "양파" in stock:
            title="양파 달걀볶음"
            grams={"양파":20,"달걀":100,"식용유":3}
            guide=guide.replace("대파","양파")
        samples=[x["actual"] for x in state.get("records",[]) if x["meal"]==title]
        if samples: minutes=round(sum(samples[-5:])/len(samples[-5:]))
        if minutes > state["minutes"]: continue
        missing = sorted(grams.keys()-stock)
        options.append((len(missing),-len(grams),minutes,title,grams,guide,missing))
    if not options: return {"안내":"시간 안에 가능한 예시 메뉴가 없습니다. 시간을 조정해 주세요."}
    count, _, minutes, title, grams, guide, missing = min(options)
    available = state["minutes"] - minutes
    body = state.get("body") or GOALS[state["goal"]]
    return {"메뉴":title,"상태":"추가 구매 필요" if count else "재료 보유","부족분":missing,
            "쿠팡":{x:"https://www.coupang.com/np/search?q="+quote(x) for x in missing},
            "조리시간(분)":minutes,"예시 1인분(g)":grams,"예상 kcal":round(sum(g*KCAL[k]/100 for k,g in grams.items())),
            "조리법":guide,"유튜브":"https://www.youtube.com/results?search_query="+quote(title+" 레시피"),
            "인스타그램":"https://www.instagram.com/explore/tags/"+quote(title.replace(" ",""))+"/",
            "운동":f"{body} · {ROUTINES[body]} · 휴식 포함 {min(available,10)}분" if available>=5 else "운동 시간 부족 · 다른 시간에 배치"}

SPECIAL={"외식","집밥","메뉴","대체","조리","섭취","검색","영양","도움말"}

def run(message, db_path="fridge.sqlite3", session_id="default"):
    message=message.strip()
    command,_,argument=message.partition(" ")
    if command in SPECIAL:
        intent=Intent()
    else:
        intent=interpret(message)
        if intent.action in {"외식","집밥","메뉴","대체","검색","영양"}:
            command,argument=intent.action,intent.argument.strip()
    if intent.body is not None and intent.body not in ROUTINES: raise ValueError("지원하지 않는 운동 부위")
    if intent.goal is not None and intent.goal not in GOALS: raise ValueError("지원하지 않는 목표")
    bus=EventBus()
    LoggingAgent(local_store()).attach(bus)
    steps=[]
    bus.subscribe(lambda event: steps.append(event.to_dict()))
    def emit(kind,label,**payload):
        bus.emit(session_id,kind,label,**payload)
    emit("llm_decision","요청 분류",method="command" if command in SPECIAL|{"추가","삭제","부위","목표","시간","추천"} else "model",
         decision=command if command in SPECIAL else "재고·조건 갱신")
    with sqlite3.connect(db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY, state TEXT, result TEXT)")
        if "session" not in {row[1] for row in db.execute("pragma table_info(runs)")}:
            db.execute("ALTER TABLE runs ADD COLUMN session TEXT DEFAULT 'default'")
        last=db.execute("SELECT state FROM runs WHERE session=? ORDER BY id DESC LIMIT 1",(session_id,)).fetchone()
        state=json.loads(last[0]) if last else {"stock":[],"minutes":30,"goal":"체력"}
        stock=set(state["stock"])
        stock.update(name(x) for x in intent.add if x.strip())
        stock.difference_update(name(x) for x in intent.remove)
        state["stock"]=sorted(stock)
        for key in ("minutes","body","goal"):
            if getattr(intent,key) is not None: state[key]=getattr(intent,key)
        if command=="메뉴":
            if argument not in {r[0] for r in RECIPES}|{"자동"}: raise ValueError("등록된 메뉴 이름 또는 자동을 입력하세요.")
            state["wanted"]=None if argument=="자동" else argument
        if command=="대체":
            if argument not in {"양파","해제"}: raise ValueError("대체 양파 또는 대체 해제")
            state["substitute"]=argument=="양파"
        if command in {"외식","집밥"}:
            state["out_date"]=date.today().isoformat() if command=="외식" else None
            emit("replan","식사 일정 변경",reason=command)
        leftovers=state.setdefault("leftovers",{})
        records=state.setdefault("records",[])
        if command=="조리":
            match=re.fullmatch(r"(\d+)인분 (\d+)분",argument)
            previous=state.get("last_meal",{})
            if not match or previous.get("상태")!="재료 보유": raise ValueError("재료 보유 메뉴 추천 후 조리 2인분 15분 형식으로 입력하세요.")
            servings,actual=map(int,match.groups())
            if not 1<=servings<=20 or not 1<=actual<=600: raise ValueError("분량 또는 시간 범위를 확인하세요.")
            title=previous["메뉴"]
            leftovers[title]=leftovers.get(title,0)+servings
            records.append({"meal":title,"actual":actual,"planned":previous["조리시간(분)"],"servings":servings})
        if command=="섭취":
            if leftovers.get(argument,0)<1: raise ValueError("남은 음식에서 메뉴 이름을 선택하세요.")
            leftovers[argument]-=1
            if not leftovers[argument]: del leftovers[argument]
        def local():
            body=state.get("body") or GOALS[state["goal"]]
            exercise=f"{body} · {ROUTINES[body]} · 휴식 포함 {min(10,state['minutes'])}분"
            if state.get("out_date")==date.today().isoformat():
                return {"안내":"오늘은 외식 · 재료 보존","운동":exercise}
            if leftovers:
                return {"남은 음식 우선":dict(leftovers),"운동":exercise}
            return recommend(state) if stock or state.get("wanted") else {"안내":"냉장고 재료를 먼저 추가해 주세요."}
        result=execute(command,argument,local,emit,stock)
        if command not in {"검색","영양","도움말"}: state["last_meal"]=result
        db.execute("INSERT INTO runs(state,result,session) VALUES (?,?,?)",(json.dumps(state),json.dumps(result),session_id))
    return {"냉장고":state["stock"],"총 가용 시간":state["minutes"],"목표":state["goal"],"계획":result,
            "남은 음식":leftovers,"조리 기록":records[-5:],"실행 단계":[[x["type"],x["name"]] for x in steps]}

@app.post("/api/chat")
def chat(body:Message):
    try: return run(body.message,session_id=body.session_id)
    except ValueError as exc: raise HTTPException(422,str(exc)) from exc
    except (OSError,KeyError,IndexError) as exc: raise HTTPException(503,"모델 연결 또는 응답 확인 필요. 명령형 입력을 사용할 수 있습니다.") from exc

@app.get("/",response_class=HTMLResponse)
def home():
    return Path(__file__).with_name("index.html").read_text(encoding="utf8")

if __name__=="__main__":
    import uvicorn
    uvicorn.run(app,host="127.0.0.1",port=8000)
