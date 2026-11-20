"""계획(규칙 + 모델) → 실행(코드) → 판정(코드) → 검증 → 응답(모델 문장) 그래프."""

import json
import os
import re
from typing import TypedDict
from urllib.parse import quote
from langgraph.graph import StateGraph, START, END
from agent_roles import FROM_RECIPE, Planner, Worker, REPLAN_LIMIT, REPAIRABLE, assess, diagnose, missing_from_recipe
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
    "결과 JSON 을 바탕으로 사용자 요청에 3~4문장 한국어로 답한다. 결과에 있는 값만 쓰고 숫자를 새로 만들지 않는다. 근거 문단이 있으면 그 문단 내용만으로 답하고 출처 이름을 밝힌다. "
    "실패한 조회는 실패했다고 말한다. 의료 진단처럼 말하지 않는다. 마크다운 기호(**, #, -, 목록)를 쓰지 않고 평문으로 쓴다."
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
    text = re.sub(r"[*#`]+", "", text).strip()
    return {**output, "답변": text[:800]}


# 요청 조건을 명세서 2.2 의 세 갈래로 나눈다: 기준(날짜·시각), 선호(목표·부위·식단·지역), 제약(시간·예산·끝 시각)
CONDITION_GROUPS = {
    "기준": ("day", "start"),
    "선호": ("goal", "body", "diet", "area"),
    "제약": ("minutes", "end", "budget_krw"),
}
NODES = ("분석", "계획", "실행", "판정", "검증", "응답")


def wire(graph):
    """분석 → 계획 → (실행 → 판정)* → 검증 → 응답. 판정은 남은 작업이 있으면 실행으로 돌아간다(재계획)."""
    graph.add_edge(START, "분석")
    graph.add_edge("분석", "계획")
    for label in ("계획", "판정"):
        graph.add_conditional_edges(label, lambda s: "실행" if s["pending"] else "검증", {"실행": "실행", "검증": "검증"})
    graph.add_edge("실행", "판정")
    graph.add_conditional_edges("검증", lambda s: "실행" if s["pending"] else "응답", {"실행": "실행", "응답": "응답"})
    graph.add_edge("응답", END)
    return graph


def structure():
    """그래프 구조(mermaid). python workflow.py 로 출력한다 (명세서 4.2 확인용)."""
    g = StateGraph(Flow)
    for label in NODES:
        g.add_node(label, lambda s: {"pending": []})
    return wire(g).compile().get_graph().draw_mermaid()


def execute(command, argument, local, emit, stock=(), events=None, request=None, speak=True, conditions=None):
    events = events if events is not None else []
    if command in {"도움말", "확인"} or command in {"검색", "유산근거"} and not argument:
        emit("node_start", "응답")
        output = {
            "안내": argument
            if command == "확인"
            else "검색할 재료 이름을 알려주세요."
            if command == "검색"
            else "찾을 국가유산 또는 국보 이름을 입력해 주세요."
            if command == "유산근거"
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

    def analyze(s):
        # 앞 단계(해석)가 뽑은 조건만 정리한다. 요청에 없던 조건은 채우지 않는다.
        given = {k: v for k, v in (conditions or {}).items() if v not in (None, "", [])}
        groups = {g: {k: given[k] for k in keys if k in given} for g, keys in CONDITION_GROUPS.items()}
        emit("conditions", "요청 조건", command=command, argument=argument, **groups,
             tool_needed=command not in {"도움말", "확인"})
        return {}

    def plan(s):
        # 자동 진행(speak=False)은 뒤에서 모델이 할 일을 고르므로 여기서는 규칙 계획만 써서 호출을 줄인다
        tasks, reason = Planner.plan(command, argument, request if speak else None, emit, stock)
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

    def alternate(s, reason):
        tasks = Planner.fallback_search(argument, s["results"]) if command == "검색" else []
        if not tasks or s["replans"] >= REPLAN_LIMIT:
            return {}
        count = s["replans"] + 1
        emit("replan", "국내 후보 조회", attempt=count, reason=reason, reused=list(s["results"]))
        declare(tasks, "같은 요청을 다른 출처에서 확인")
        return {"pending": s["pending"] + tasks, "replans": count}

    def verify(s):
        tool = s["output"]["tool"]
        r = s["results"][tool]
        candidates = s["candidates"]
        index = s["index"]
        best = list(s["best"])
        if tool == "search" and not r["ok"]:
            if s["output"]["decision"] == "escalate" and r.get("error") in REPAIRABLE:
                return alternate(s, r["error"])
            return {}
        if tool == "search" and r["ok"]:
            candidates = list({str(x["id"]): x for x in r["data"] if x.get("id") is not None}.values())
            if command == "요리코치" and s["results"]["kr_recipe"]["ok"]:
                candidates = []
            index = 0
        elif tool == "detail":
            if r["ok"]:
                known = {ENGLISH.get(item, item).lower() for item in stock}
                ingredients = r["data"].get("ingredients") or []
                missing = [x for x in ingredients if x.lower() not in known] if ingredients else ["제공처 재료 정보 없음"]
                best.append({"조회": r, "미확인 재료": missing, "판정": "영문 재료명 일치 기준"})
                if not missing or command == "요리코치":
                    return {"best": best}
            elif r.get("error") != "NO_RESULT":
                return {"best": best}
            index += 1
        else:
            return {}
        if index >= len(candidates) or index > REPLAN_LIMIT:
            return {"best": best, "candidates": candidates, "index": index, **alternate(s, "기존 후보에서 재료가 확인된 메뉴를 찾지 못함")}
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
        if a["status"] == "이상":
            return alternate(s, a["warnings"])
        return {}

    def respond(s):
        out = compose(s)["output"]
        extra = [x for x in s.get("trail", []) if x["도구"] not in base_tools]
        if extra and isinstance(out, dict):
            out = {**out, "추가 조회": extra}
        return {"output": answer(request, out, emit) if speak else out}

    def compose(s):
        results = s["results"]
        if command in {"질문", "유산근거"}:
            r = results["heritage_knowledge" if command == "유산근거" else "knowledge"]
            if not r["ok"]:
                if command == "유산근거":
                    message = {
                        "NO_INDEX": "2회차 국가유산 색인이 아직 연결되지 않았습니다.",
                        "MISSING_KEY": "국가유산 검색에 사용할 임베딩 키를 설정하세요.",
                    }.get(r["error"], "국가유산 색인에서 근거를 가져오지 못했습니다.")
                    return {"output": {"안내": message, "근거 문서": [], "오류": r["error"]}}
                why = {"NO_RESULT": "한끼 안내 문서에서 관련 근거를 찾지 못했어요. 식단·운동·식품 안전·생활 습관 질문을 해 주세요.", "NO_INDEX": "근거 문서 색인을 만들지 못했어요.", "RAG_DEPENDENCY_MISSING": "근거 검색 라이브러리(chromadb)가 설치되지 않았어요."}
                return {"output": {"안내": why.get(r["error"], "근거를 찾지 못했어요."), "근거 문서": [], "오류": r["error"]}}
            top = r["data"][0]
            return {"output": {"질문": argument, "근거 문서": r["data"], "출처": r["source"], "답변": f"{top['excerpt']} (출처: {top['source']})"}}
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
            result["후보 조회 기준"] = {
                "요청 날짜": (conditions or {}).get("day"),
                "실제 기준": "호출 시점의 카탈로그",
                "안내": "날짜별 카탈로그가 없어 조회 시점의 메뉴 목록을 사용합니다.",
            }
            if "kr_recipe" in results:
                result["국내 대안"] = results["kr_recipe"]
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
    for label, fn in zip(NODES, (analyze, plan, perform, verify, audit, respond)):
        graph.add_node(label, traced(label, fn))
    return wire(graph).compile().invoke({}, config={"recursion_limit": 40})["output"]


if __name__ == "__main__":
    print(structure())
