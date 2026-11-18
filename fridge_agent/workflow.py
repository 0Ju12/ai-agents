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
        tool = {"레시피":"kr_recipe","식품영양":"kr_nutrition","검색":"search","영양":"nutrition","도움말":"help"}.get(s["command"],"local")
        return {"tool":tool,"attempts":0}

    def perform(s):
        tool=s["tool"]
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
