"""Structured Planner, bounded Worker, and independent run evaluator."""

from time import monotonic
import os
import gateway
import food_tools
from registry import Task, WorkerResult

REPLAN_LIMIT = 3
REPAIRABLE = {"NO_RESULT", "NOT_FOUND", "INVALID_INPUT"}


def assess(events):
    planned = set()
    called = set()
    warnings = []
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
        elif kind == "replan":
            n += 1
            evidence = True
    if n > REPLAN_LIMIT:
        warnings.append("재계획 상한 초과")
    return {
        "status": "이상" if warnings else "정상" if evidence else "판정 불가",
        "warnings": warnings,
        "replans": n,
    }


class Planner:
    @staticmethod
    def tasks(command, arg):
        direct = {
            "검색": "search",
            "레시피": "kr_recipe",
            "식품영양": "kr_nutrition",
            "영양": "nutrition",
            "해설": "knowledge",
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
