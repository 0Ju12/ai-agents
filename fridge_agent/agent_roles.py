"""Structured Planner, bounded Worker, and independent run evaluator."""

from time import monotonic
import os
import re
from pydantic import BaseModel, Field
import gateway
import food_tools
from domain.catalog import canonical
from registry import META, Task, WorkerResult

REPLAN_LIMIT = 3
REPAIRABLE = {"NO_RESULT", "NOT_FOUND", "INVALID_INPUT"}


def assess(events):
    planned = set()
    called = set()
    warnings = []
    previous_failed_tool = None
    evidence = False
    n = 0
    for e in events:
        kind = e["type"]
        p = e["payload"]
        if kind == "plan":
            planned.update(p.get("tools", []))
            evidence = True
        elif kind == "tool_call":
            key = (e["name"], p.get("argument", ""))
            if e["name"] not in planned:
                warnings.append("계획 밖 호출 · " + e["name"])
            if key in called:
                warnings.append("같은 입력 반복 · " + e["name"])
            called.add(key)
            evidence = True
        elif kind == "tool_result":
            failed_tool = e["name"] if p.get("ok") is False else None
            if failed_tool and failed_tool == previous_failed_tool:
                warning = "도구 연속 실패 · " + failed_tool
                if warning not in warnings:
                    warnings.append(warning)
            previous_failed_tool = failed_tool
            evidence = True
        elif kind == "replan":
            n += 1
            evidence = True
    if n >= REPLAN_LIMIT:
        warnings.append("재계획 상한 도달")
    return {
        "status": "이상" if warnings else "정상" if evidence else "판정 불가",
        "warnings": warnings,
        "replans": n,
    }


# 모델 계획을 받는 명령: 핵심 작업(규칙)은 그대로 두고, 요청에 필요한 보조 도구를 모델이 고른다.
PLANNABLE = {"추천", "외식", "집밥", "메뉴", "레시피", "식품영양", "질문"}
# 모델이 고를 수 있는 보조 도구. 후보 탐색(search/detail)은 재계획 루프가 맡고, 일정 등록은 사용자 확인 후에만 한다.
EXTRA_TOOLS = (
    "kr_recipe", "kr_nutrition", "nutrition", "usda", "naver", "coupang",
    "youtube", "instagram", "gyms", "wger", "calendar_list", "knowledge",
)
FROM_RECIPE = "$부족재료"  # 앞 단계(kr_recipe) 결과에서 재고에 없는 재료로 바꿔 넣는 자리표시
MAX_TASKS = 6


class PlanStep(BaseModel):
    tool: str = Field(description="도구 이름. 목록에 있는 것만")
    argument: str = Field(default="", max_length=80, description="도구 입력. 레시피의 부족 재료를 쓰려면 $부족재료")
    purpose: str = Field(default="", max_length=80, description="이 도구를 부르는 이유")


class Plan(BaseModel):
    """모델이 채울 계획서 양식 (2일차 step4 의 Plan 과 같은 역할)."""

    steps: list[PlanStep] = Field(default_factory=list, max_length=5)
    reason: str = Field(default="", max_length=200, description="이 순서를 고른 이유 한 문장")


PLAN_PROMPT = (
    "사용자 요청을 처리할 도구 실행 순서를 정한다. 기본 작업은 이미 정해져 있으니 요청에 꼭 필요한 보조 도구만 추가한다. "
    "필요 없으면 steps 를 비운다. 목록에 없는 도구는 쓰지 않는다. "
    "먹고 싶은 음식의 재료를 사야 하면 kr_recipe(메뉴명) 다음에 naver 또는 coupang 의 argument 를 $부족재료 로 둔다. "
    "다이어트·인기 레시피 영상은 youtube/instagram, 재료 영양은 kr_nutrition, 지역 헬스장은 gyms, 일정 확인은 calendar_list(YYYY-MM-DD). "
    "수량·영양·시간 판단은 코드가 하므로 값을 지어내지 않는다."
)


def catalog():
    """모델에게 넘기는 도구 명함 목록 (이름·설명·입력)."""
    return [{"name": k, "description": META[k][1], "input": META[k][2]} for k in EXTRA_TOOLS]


def recipe_ingredients(text):
    """식약처 RCP_PARTS_DTLS 원문에서 재료 이름만 뽑는다. 예: '●주재료 : 연두부 75g, 새우 20g' → ['연두부', '새우']"""
    names = []
    for part in re.split(r"[,\n]", str(text or "")):
        part = re.sub(r"^.*?:", "", part).strip(" ●·-")
        m = re.match(r"([가-힣A-Za-z ]+?)\s*(?:\d|약간|적당|조금|\(|$)", part)
        if m and m[1].strip() and m[1].strip() not in names:
            names.append(m[1].strip())
    return names


def missing_from_recipe(result, stock):
    if not result or not result.get("ok") or not result.get("data"):
        return None
    have = {canonical(x) for x in stock}
    return [n for n in recipe_ingredients(result["data"][0].get("재료·분량")) if canonical(n) not in have]


class Planner:
    @staticmethod
    def plan(command, arg, request=None, emit=lambda *a, **k: None, stock=()):
        """규칙 작업 + (자연어 요청이면) 모델이 고른 보조 작업. 모델이 없거나 실패하면 규칙 작업만."""
        base = Planner.tasks(command, arg)
        if (
            not request
            or command not in PLANNABLE
            or os.getenv("PLANNER_LLM", "1") != "1"
            or not gateway.configured()
        ):
            return base, "요청과 입력 조건에 필요한 작업 선택"
        try:
            plan = gateway.structured(
                "Planner",
                PLAN_PROMPT,
                {
                    "request": request,
                    "command": command,
                    "argument": arg,
                    "stock": list(stock)[:40],
                    "base_tasks": [t.tool for t in base],
                    "tools": catalog(),
                },
                Plan,
            )
        except (ValueError, OSError):
            emit("error", "모델 계획", reason="규칙 계획 사용")
            return base, "모델 계획 실패 · 규칙 계획 사용"
        tasks, rejected = list(base), []
        seen = {(t.tool, t.argument) for t in tasks}
        for step in plan.steps:
            argument = step.argument.strip()
            ok = (
                step.tool in EXTRA_TOOLS
                and argument
                and (step.tool, argument) not in seen
                and (argument != FROM_RECIPE or any(t.tool == "kr_recipe" for t in tasks))
                and len(tasks) < MAX_TASKS
            )
            if not ok:
                rejected.append(step.tool)
                continue
            seen.add((step.tool, argument))
            tasks.append(
                Task(
                    tool=step.tool,
                    argument=argument,
                    fixed=argument == FROM_RECIPE,
                    purpose=step.purpose or META[step.tool][1],
                )
            )
        emit(
            "llm_decision",
            "Planner 작업 계획",
            method="model",
            decision=[t.tool for t in tasks],
            rejected=rejected,
            reason=plan.reason[:200],
        )
        return tasks, plan.reason[:200] or "모델이 요청에 필요한 도구 선택"

    @staticmethod
    def tasks(command, arg):
        direct = {
            "검색": "search",
            "레시피": "kr_recipe",
            "질문": "knowledge",
            "식품영양": "kr_nutrition",
            "영양": "nutrition",
            "일정조회": "calendar_list",
            "일정등록": "calendar_register",
            "헬스장": "gyms",
            "미국영양": "usda",
            "운동자료": "wger",
        }
        if command in direct:
            return [Task(tool=direct[command], argument=arg, fixed=True, purpose="요청한 자료 확인")]
        if command in {"쇼핑", "영상"}:
            return [
                Task(tool=key, argument=arg, purpose="출처별 결과 비교")
                for key in (("naver", "coupang") if command == "쇼핑" else ("youtube", "instagram"))
            ]
        if command == "요리코치":
            parts = [x.strip() for x in arg.split("/")]
            if len(parts) not in (2, 3) or not all(parts):
                return []
            menu, food = parts[:2]
            food = "달걀" if food == "계란" else food
            spec = [("kr_recipe", menu), ("kr_nutrition", food), ("search", food)]
            if len(parts) == 3:
                spec.append(("nutrition", parts[2]))
            return [
                Task(tool=t, argument=a, fixed=t != "search", purpose="조리법·재료 영양·대안 확인")
                for t, a in spec
            ]
        if command in {"도움말", "확인"}:
            return []
        return [Task(tool="local", argument="", purpose="등록한 조건에서 식사와 운동 계산")]


class Worker:
    def __init__(self, emit, local, clock=monotonic):
        self.emit, self.local, self.clock = emit, local, clock
        self.cache = {}
        self.deadline = clock() + 24

    def perform(self, task):
        original = task
        for attempt in (1, 2):
            key = (task.tool, task.argument)
            if key in self.cache:
                self.emit("cache_hit", task.tool, argument=task.argument)
                result = self.cache[key]
            elif self.clock() > self.deadline:
                result = {"ok": False, "error": "TIME_BUDGET"}
            else:
                self.emit("tool_call", task.tool, argument=task.argument)
                start = self.clock()
                if task.tool == "local":
                    result = {"ok": True, "data": self.local()}
                else:
                    try:
                        result = food_tools.call(*key)
                    except (OSError, TypeError, KeyError, ValueError, TimeoutError):
                        result = {"ok": False, "error": "SOURCE_UNAVAILABLE"}
                self.cache[key] = result
                self.emit(
                    "tool_result",
                    task.tool,
                    ok=result["ok"],
                    error=result.get("error"),
                    source=result.get("source"),
                    count=len(result["data"]) if isinstance(result.get("data"), list) else None,
                    ms=round((self.clock() - start) * 1000),
                )
            if result["ok"]:
                return WorkerResult(task=original, result=result, attempts=attempt)
            decision = "escalate"
            if (
                attempt == 1
                and task.argument
                and result.get("error") in REPAIRABLE
                and os.getenv("WORKER_LLM", "1") == "1"
                and gateway.configured()
            ):
                try:
                    fix = gateway.decide(
                        "Worker",
                        "decision은 retry, skip, escalate 중 하나. 같은 도구에만 재시도. fixed인 인자를 수정하지 않는다. argument는 문자열.",
                        {"task": task.model_dump(), "error": result["error"]},
                    )
                except (ValueError, OSError, KeyError, IndexError):
                    fix = {}
                action = fix.get("decision")
                new = fix.get("argument")
                valid = (
                    action == "retry"
                    and not task.fixed
                    and isinstance(new, str)
                    and 0 < len(new) <= 80
                    and new != task.argument
                )
                self.emit(
                    "llm_decision",
                    "Worker",
                    method="model",
                    decision="retry" if valid else "skip" if action == "skip" else "escalate",
                    reason=result["error"],
                )
                if valid:
                    task = task.model_copy(update={"argument": new})
                    continue
                if action == "skip":
                    decision = "skip"
            self.emit("worker_result", task.tool, decision=decision, reason=result.get("error"))
            return WorkerResult(task=original, result=result, decision=decision, attempts=attempt)


def diagnose(assessment, emit):
    if assessment["status"] != "이상" or not gateway.configured():
        return
    try:
        result = gateway.decide(
            "Logger", "경고의 담당 role과 개선 action을 짧게 JSON으로 쓴다.", assessment
        )
        emit(
            "diagnosis",
            "로깅 Agent 진단",
            method="model",
            role=str(result.get("role", ""))[:60],
            action=str(result.get("action", ""))[:240],
        )
    except (ValueError, OSError, KeyError, IndexError):
        emit("diagnosis", "진단 보류", method="model")
