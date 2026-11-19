"""계획(규칙 + 모델) → 실행(코드) → 판정(코드) → 검증 → 응답(모델 문장) 그래프."""

import json
import os
from typing import TypedDict
from urllib.parse import quote
from langgraph.graph import StateGraph, START, END
from agent_roles import FROM_RECIPE, Planner, Worker, REPLAN_LIMIT, assess, diagnose, missing_from_recipe
import gateway
from registry import Task
from food_tools import ENGLISH


class Flow(TypedDict, total=False):
    pending: list
    output: dict
    index: int
    replans: int
    results: dict
    candidates: list
    best: list
    trail: list


ANSWER_PROMPT = (
    "결과 JSON 을 바탕으로 사용자 요청에 3~4문장 한국어로 답한다. 결과에 있는 값만 쓰고 숫자를 새로 만들지 않는다. "
    "실패한 조회는 실패했다고 말한다. 의료 진단처럼 말하지 않는다."
)


def answer(request, output, emit):
    """모델이 결과를 문장으로 정리한다 (실습 step4 의 llm_answer). 판단은 이미 코드가 끝낸 뒤다."""
    if not request or os.getenv("ANSWER_LLM", "1") != "1" or not gateway.configured():
        return output
    try:
        text = gateway.write("응답", ANSWER_PROMPT, {"request": request, "result": json.dumps(output, ensure_ascii=False, default=str)[:6000]})
    except (ValueError, OSError):
        emit("error", "응답 문장", reason="구조화 결과만 반환")
        return output
    emit("llm_decision", "응답 문장", method="model", decision="answer", reason="확인된 결과 요약")
    return {"답변": text[:800], **output}


def execute(command, argument, local, emit, stock=(), events=None, request=None):
    events = events if events is not None else []
    if command in {"도움말", "확인"} or command == "검색" and not argument:
        emit("node_start", "응답")
        output = {
            "안내": argument
            if command == "확인"
            else "검색할 재료 이름을 알려주세요."
            if command == "검색"
            else "추가 두부, 계란 · 물 250 · 검색 달걀 · 메뉴 두부구이"
        }
        emit("evaluation", "실행 검증", **assess(events))
        emit("node_end", "응답")
        return output
    worker = Worker(emit, local)

    def declare(tasks, reason):
        emit(
            "plan",
            "작업 목록",
            tools=[t.tool for t in tasks],
            tasks=[t.model_dump() for t in tasks],
            reason=reason,
        )

    base_tools = set()

    def plan(s):
        tasks, reason = Planner.plan(command, argument, request, emit, stock)
        if command == "검색" and not argument:
            tasks = []
        base_tools.update(t.tool for t in Planner.tasks(command, argument))
        declare(tasks, reason)
        return {"pending": tasks, "index": 0, "replans": 0, "best": [], "results": {}, "candidates": [], "trail": []}

    def perform(s):
        task, rest = s["pending"][0], s["pending"][1:]
        if task.argument == FROM_RECIPE:  # 앞 단계 레시피 결과를 다음 도구 입력으로 (F3007)
            missing = missing_from_recipe(s["results"].get("kr_recipe"), stock)
            if not missing:
                emit("worker_result", task.tool, decision="skip", reason="레시피 결과 없음" if missing is None else "부족한 재료 없음")
                result = {"ok": True, "data": [], "source": "재고 비교", "안내": "사야 할 재료가 없습니다." if missing == [] else "레시피를 찾지 못해 재료를 비교하지 못했습니다."}
                return {"pending": rest, "results": {**s["results"], task.tool: result}, "trail": s["trail"] + [{"도구": task.tool, "입력": FROM_RECIPE, "결과": result}], "output": {"tool": task.tool, "decision": "skip"}}
            expanded = [task.model_copy(update={"argument": name}) for name in missing[:3]]
            declare(expanded, "레시피 재료 중 재고에 없는 재료로 입력 확정")
            task, rest = expanded[0], expanded[1:] + rest
        report = worker.perform(task)
        results = {**s["results"], task.tool: report.result}
        return {
            "pending": rest,
            "results": results,
            "trail": s["trail"] + [{"도구": task.tool, "입력": task.argument, "결과": report.result}],
            "output": {"tool": task.tool, "decision": report.decision},
        }

    def verify(s):
        tool = s["output"]["tool"]
        r = s["results"][tool]
        candidates = s["candidates"]
        index = s["index"]
        best = list(s["best"])
        if tool == "search" and r["ok"]:
            candidates = list({str(x["id"]): x for x in r["data"] if x.get("id") is not None}.values())
            if command == "요리코치" and s["results"]["kr_recipe"]["ok"]:
                candidates = []
            index = 0
        elif tool == "detail":
            if r["ok"]:
                known = {ENGLISH.get(item, item).lower() for item in stock}
                missing = [x for x in r["data"]["ingredients"] if x.lower() not in known]
                best.append({"조회": r, "미확인 재료": missing, "판정": "영문 재료명 일치 기준"})
                if not missing or command == "요리코치":
                    return {"best": best}
            elif r.get("error") != "NO_RESULT":
                return {"best": best}
            index += 1
        else:
            return {}
        if index >= len(candidates) or index > REPLAN_LIMIT:
            return {"best": best, "candidates": candidates, "index": index}
        count = s["replans"]
        if tool == "detail":
            if count >= REPLAN_LIMIT:
                return {"best": best}
            count += 1
            emit(
                "replan",
                "다음 상세 후보",
                attempt=count,
                reason="미확인 재료 또는 상세 조회 실패",
                reused=["search"],
            )
        task = Task(
            tool="detail",
            argument=str(candidates[index]["id"]),
            purpose="검색 결과 id로 조리법과 제약 확인",
        )
        declare([task], "기존 후보 목록 재사용")
        return {
            "pending": s["pending"] + [task],
            "index": index,
            "best": best,
            "replans": count,
            "candidates": candidates,
        }

    def audit(s):
        a = assess(events)
        emit("evaluation", "실행 검증", **a)
        diagnose(a, emit)
        if a["status"] == "이상" and s["replans"] < REPLAN_LIMIT:
            emit("replan", "검증 경고 반영", reason=a["warnings"], attempt=s["replans"] + 1)
            declare([], "중복 또는 비계획 작업을 제외하고 확인된 결과로 종료")
            return {"pending": [], "replans": s["replans"] + 1}
        return {}

    def respond(s):
        out = compose(s)["output"]
        extra = [x for x in s.get("trail", []) if x["도구"] not in base_tools]
        if extra and isinstance(out, dict):
            out = {**out, "추가 조회": extra}
        return {"output": answer(request, out, emit)}

    def compose(s):
        results = s["results"]
        if not results:
            message = {
                "검색": "검색할 재료 이름을 알려주세요.",
                "요리코치": "요리코치 메뉴 / 먼저 쓸 재료 형식으로 입력하세요.",
                "확인": argument or "원하는 작업을 조금 더 자세히 알려주세요.",
            }.get(command, "추가 두부, 계란 · 물 250 · 검색 달걀 · 메뉴 두부구이")
            return {"output": {"안내": message}}
        if "local" in results:
            return {"output": results["local"]["data"]}
        if command == "요리코치":
            menu, food, *_ = map(str.strip, argument.split("/"))
            food = "달걀" if food == "계란" else food
            guide = {
                "요청 메뉴": menu,
                "먼저 쓸 재료": food,
                "재고 확인": "등록됨" if food in stock else "미등록",
                "국내 레시피": results["kr_recipe"],
                "재료 영양": results["kr_nutrition"],
                "대안 메뉴": results["search"],
            }
            if results["kr_recipe"]["ok"]:
                rows = results["kr_recipe"]["data"]
                row = next((x for x in rows if x["메뉴"] == menu), rows[0])
                guide.update(
                    {"메뉴": row["메뉴"], "조리 단계": row["조리 순서"], "필요 재료 원문": row["재료·분량"]}
                )
            elif "detail" in results:
                guide["대안 상세"] = results["detail"]
                if results["detail"]["ok"]:
                    row = results["detail"]["data"]
                    guide.update(
                        {
                            "메뉴": row["title"],
                            "조리 단계": row["instructions"].splitlines(),
                            "필요 재료 원문": row["ingredients"],
                        }
                    )
            if "nutrition" in results:
                guide["제품 영양"] = results["nutrition"]
            return {"output": guide}
        if command == "검색":
            result = (
                dict(min(s["best"], key=lambda x: len(x["미확인 재료"])))
                if s["best"]
                else {"조회": results.get("detail", results["search"])}
            )
            if s["replans"] >= REPLAN_LIMIT:
                result["안내"] = "재계획 상한 도달 · 확인한 후보에서 선택했습니다."
            elif result.get("미확인 재료"):
                result["안내"] = "조리 전 미확인 재료의 보유 여부를 확인하세요."
            return {"output": result}
        if command in {"쇼핑", "영상", "헬스장"}:
            term = quote(argument)
            links = {
                "쇼핑": {
                    "쿠팡 검색": "https://www.coupang.com/np/search?q=" + term,
                    "네이버 검색": "https://search.shopping.naver.com/search/all?query=" + term,
                },
                "영상": {
                    "YouTube 검색": "https://www.youtube.com/results?search_query="
                    + quote(argument + " 레시피"),
                    "Instagram 태그": "https://www.instagram.com/explore/tags/"
                    + quote(argument.replace(" ", ""))
                    + "/",
                },
                "헬스장": {"카카오맵 검색": "https://map.kakao.com/?q=" + quote(argument + " 헬스장")},
            }
            return {"output": {"검색어": argument, "자료": results, "직접 검색": links[command]}}
        return {"output": {"조회": next(iter(results.values()))}}

    def traced(name, fn):
        def wrapped(s):
            emit("node_start", name)
            out = fn(s)
            emit("node_end", name)
            return out

        return wrapped

    graph = StateGraph(Flow)
    for label, fn in [
        ("계획", plan),
        ("실행", perform),
        ("판정", verify),
        ("검증", audit),
        ("응답", respond),
    ]:
        graph.add_node(label, traced(label, fn))
    graph.add_edge(START, "계획")
    for label in ("계획", "판정"):
        graph.add_conditional_edges(label, lambda s: "실행" if s["pending"] else "검증")
    graph.add_edge("실행", "판정")
    graph.add_edge("검증", "응답")
    graph.add_edge("응답", END)
    return graph.compile().invoke({}, config={"recursion_limit": 40})["output"]
