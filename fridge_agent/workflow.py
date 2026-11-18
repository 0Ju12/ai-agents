from time import monotonic
from typing import TypedDict
from langgraph.graph import END, START, StateGraph
import food_tools

class Flow(TypedDict,total=False):
    command:str
    argument:str
    tool:str
    candidates:list
    attempts:int
    output:dict
    again:bool

def execute(command, argument, local, emit, stock=()):
    best = []
    def analyze(s):
        if s["command"]=="검색" and not s["argument"]:
            return {"output":{"안내":"검색할 재료 이름을 알려주세요."}}
        return {}

    def plan(s):
        tool = {"요리코치":"coach","레시피":"kr_recipe","식품영양":"kr_nutrition","검색":"search","영양":"nutrition","도움말":"help"}.get(s["command"],"local")
        return {"tool":tool,"attempts":0}

    def query(tool, arg):
        start = monotonic()
        emit("tool_call", tool, argument=arg)
        result = food_tools.call(tool, arg)
        emit("tool_result", tool, result=result, ms=round((monotonic()-start)*1000))
        return result

    def cooking_guide(argument):
        parts = [part.strip() for part in argument.split("/")]
        if len(parts) not in (2, 3) or not all(parts):
            return {"안내":"요리코치 메뉴 / 먼저 쓸 재료 형식으로 입력하세요. 제품 바코드를 끝에 추가할 수 있습니다."}
        menu, ingredient = parts[:2]
        ingredient = "달걀" if ingredient == "계란" else ingredient
        recipes = query("kr_recipe", menu)
        nutrients = query("kr_nutrition", ingredient)
        alternatives = query("search", ingredient)
        guide = {"요청 메뉴":menu, "먼저 쓸 재료":ingredient,
                 "재고 확인":"등록됨" if ingredient in stock else "미등록",
                 "국내 레시피":recipes, "재료 영양":nutrients, "대안 메뉴":alternatives}
        if recipes["ok"]:
            rows = recipes["data"]
            selected = next((row for row in rows if row["메뉴"] == menu), rows[0])
            guide.update({"메뉴":selected["메뉴"], "조리 단계":selected["조리 순서"],
                          "필요 재료 원문":selected["재료·분량"]})
        elif alternatives["ok"]:
            detail = query("detail", alternatives["data"][0]["id"])
            guide["대안 상세"] = detail
            if detail["ok"]:
                meal = detail["data"]
                guide.update({"메뉴":meal["title"], "조리 단계":meal["instructions"].splitlines(),
                              "필요 재료 원문":meal["ingredients"]})
        if len(parts) == 3:
            guide["제품 영양"] = query("nutrition", parts[2])
        return guide

    def perform(s):
        tool=s["tool"]
        if tool=="coach":
            return {"output":cooking_guide(s["argument"])}
        if tool=="help":
            return {"output":{"안내":"예: 추가 계란, 두부 / 외식 / 검색 달걀 / 영양 3017620422003"}}
        arg=s["argument"]
        if tool=="detail": arg=s["candidates"][s["attempts"]]["id"]
        start=monotonic()
        emit("tool_call",tool,argument=arg)
        result={"ok":True,"data":local()} if tool=="local" else food_tools.call(tool,arg)
        emit("tool_result",tool,result=result,ms=round((monotonic()-start)*1000))
        if tool=="search" and result["ok"]:
            return {"candidates":result["data"],"tool":"detail","again":True}
        updates={"again":False,"output":result["data"] if tool=="local" else {"조회":result}}
        if tool=="detail" and result["ok"]:
            known={food_tools.ENGLISH.get(item,item).lower() for item in stock}
            detail=result["data"]
            missing=[item for item in detail["ingredients"] if item.lower() not in known]
            candidate={"조회":result,"미확인 재료":missing,"판정":"영문 재료명 일치 기준"}
            best.append((len(missing),candidate))
            updates["output"]=min(best,key=lambda item:item[0])[1]
            if missing and s["attempts"]+1 < min(4,len(s["candidates"])):
                emit("replan","다음 레시피 검토",reason="보유 미확인 재료",attempt=s["attempts"]+1)
                updates.update(again=True,attempts=s["attempts"]+1)
            elif missing:
                updates["output"]["안내"]="후보 범위에서 미확인 재료가 가장 적은 메뉴입니다."
        if tool=="detail" and not result["ok"] and best:
            updates["output"]=dict(min(best,key=lambda item:item[0])[1],안내="일부 후보 상세 조회 실패")
        if tool=="detail" and not result["ok"] and result["error"]=="NO_RESULT":
            next_index=s["attempts"]+1
            if next_index<min(4,len(s["candidates"])):
                emit("replan","다음 후보",reason="상세정보 없음",attempt=next_index)
                updates.update(again=True,attempts=next_index)
            else:
                updates["output"]["안내"]="후보 소진 또는 재계획 상한 도달"
        return updates

    def traced(name,fn):
        def invoke(state):
            emit("node_start",name)
            result=fn(state)
            emit("node_end",name)
            return result
        return invoke
    graph=StateGraph(Flow)
    for label,fn in [("분석",analyze),("계획",plan),("실행",perform),("판정",lambda s:{}),("응답",lambda s:{})]:
        graph.add_node(label,traced(label,fn))
    graph.add_edge(START,"분석")
    graph.add_conditional_edges("분석",lambda s:"응답" if "output" in s else "계획")
    graph.add_edge("계획","실행")
    graph.add_edge("실행","판정")
    graph.add_conditional_edges("판정",lambda s:"실행" if s.get("again") else "응답")
    graph.add_edge("응답",END)
    return graph.compile().invoke({"command":command,"argument":argument})["output"]
