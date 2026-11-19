"""Generate inspectable evaluation records. Uses temporary synthetic households only."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter
from unittest.mock import patch
from datetime import datetime
from zoneinfo import ZoneInfo
import app, food_tools, gateway, workflow
from agent_roles import assess

HERE = Path(__file__).resolve().parent
OUT = HERE / "docs" / "evidence"
BASE = "01d54bc46a9465d5213739886e2a0c8dfee85316"


def save(name, obj):
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def use(fn):
    tick = perf_counter()
    result = fn()
    return result, round((perf_counter() - tick) * 1000, 1)


def fixture(tool, term):
    if tool == "search":
        if term == "콩 가공품":
            return {"ok": False, "error": "NO_RESULT"}
        return {
            "ok": True,
            "data": [{"id": str(i), "title": "검증 메뉴 " + str(i)} for i in range(6)],
            "source": "고정 시험 자료",
        }
    if tool == "detail":
        return {
            "ok": True,
            "data": {
                "title": "검증 메뉴 " + term,
                "ingredients": ["egg"] if term == "1" else ["salmon"],
                "instructions": "조리법",
            },
            "source": "고정 시험 자료",
        }
    return {"ok": False, "error": "MISSING_KEY"}


def scenario_eval():
    output = []
    specs = [
        ("재료 충분", "추가 달걀, 두부", "meal", "두부 달걀찜"),
        ("후보 재계획", "검색 달걀", "replans", 1),
        ("상한", "검색 양파", "replans", 3),
        ("제공처 키 누락", "식품영양 두부", "error", "MISSING_KEY"),
        ("도구 불필요", "도움말", "tool_calls", 0),
        ("시간 제약", "시간 1", "notice", True),
    ]
    for i, (name, msg, metric, expected) in enumerate(specs):
        session = "scenario-" + str(i)
        if i in (1, 5):
            app.run("추가 달걀", session_id=session)
        response, ms = use(lambda: app.run(msg, session_id=session))
        trace = response["추적"]
        p = response["계획"]
        values = {
            "meal": p.get("메뉴"),
            "replans": sum(e["type"] == "replan" for e in trace),
            "tool_calls": sum(e["type"] == "tool_call" for e in trace),
            "error": p.get("조회", {}).get("error"),
            "notice": bool(p.get("안내")),
        }
        output.append(
            {
                "scenario": name,
                "request": msg,
                "metric": metric,
                "expected": expected,
                "actual": values[metric],
                "pass": values[metric] == expected,
                "latency_ms": ms,
                "calls": values["tool_calls"],
                "replans": values["replans"],
            }
        )
        if i == 1:
            save("one-run.json", {"input": msg, "plan": p, "full_events": trace})
    return output


def inventory_eval():
    from domain.kitchen import inventory, shortages

    day = "2026-11-19"
    cases = [
        ("빈 재고", [], 100, "부족"),
        ("동일 용량", [(100, None)], 100, "충족"),
        ("1g 부족", [(99, None)], 100, "부족"),
        ("기한 지남", [(150, "2026-11-18")], 100, "부족"),
        ("오늘까지", [(100, day)], 100, "충족"),
        ("미계량", [(None, None)], 100, "확인 필요"),
        ("두 포장 합계", [(40, None), (60, None)], 100, "충족"),
        ("기한 혼합", [(60, None), (70, "2026-11-17")], 100, "부족"),
        ("충족과 미계량", [(100, None), (None, None)], 100, "충족"),
        ("2인분 부족", [(150, None)], 200, "부족"),
    ]
    rows = []
    for name, inputs, needed, expected in cases:
        lots = [{"item": "두부", "grams": v, "expires": e} for v, e in inputs]
        need, unknown = shortages({"두부": needed}, inventory({"lots": lots}, day))
        actual = "부족" if need else "확인 필요" if unknown else "충족"
        rows.append(
            {"case": name, "expected": expected, "name_only": "충족" if lots else "부족", "lots": actual}
        )
    return {
        "scope": "수기로 정답을 지정한 경계 조건 10개. 사용자 성과 또는 운영 정확도 추정에는 사용할 수 없음.",
        "cases": rows,
        "correct": {key: sum(r[key] == r["expected"] for r in rows) for key in ("name_only", "lots")},
        "n": len(rows),
    }


def compare(tmp):
    blob = subprocess.run(
        ["git", "show", BASE + ":fridge_agent/workflow.py"], cwd=HERE, capture_output=True
    )
    variations = [("현재 · Worker LLM 끔", workflow, False), ("현재 · Worker LLM 켬", workflow, True)]
    if blob.returncode == 0:
        source = Path(tmp) / "baseline.py"
        source.write_bytes(blob.stdout)
        spec = importlib.util.spec_from_file_location("baseline_flow", source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        variations.insert(0, ("변경 전 " + BASE[:7], module, False))
    rows = []
    for label, module, on in variations:
        timings = []
        stats = {}
        for i in range(5):
            events = []
            decisions = []

            def emit(t, n, **p):
                events.append({"type": t, "name": n, "payload": p})

            def chooser(*_):
                decisions.append(1)
                return {"decision": "retry", "argument": "tofu"}

            with (
                patch.dict(os.environ, {"WORKER_LLM": "1" if on else "0"}),
                patch.object(gateway, "configured", return_value=True),
                patch.object(gateway, "decide", side_effect=chooser),
            ):
                args = ("요리코치", "두부찜 / 콩 가공품", lambda: {}, emit, [])
                res, ms = use(
                    lambda: module.execute(*args, **({"events": events} if module is workflow else {}))
                )
            timings.append(ms)
            stats = {
                "replans": sum(e["type"] == "replan" for e in events),
                "model_calls": len(decisions),
                "tool_calls": sum(e["type"] == "tool_call" for e in events),
                "found_detail": bool(res.get("대안 상세", {}).get("ok")),
            }
        rows.append({"mode": label, **stats, "median_ms": median(timings), "repetitions": 5})
    return {
        "method": "동일한 외부 실패·성공 응답과 결정 스텁으로 제어 흐름만 비교. 모델 네트워크 지연·비용·정확도는 포함되지 않음.",
        "rows": rows,
    }


def main(live):
    OUT.mkdir(exist_ok=True, parents=True)
    if live:
        rows = []
        for tool, arg in (
            ("search", "달걀"),
            ("nutrition", "3017620422003"),
            ("usda", "tofu"),
            ("wger", "81"),
        ):
            r, ms = use(lambda: food_tools.call(tool, arg))
            row = r.get("data")
            sample = row[0] if isinstance(row, list) and row else row
            rows.append(
                {
                    "tool": tool,
                    "argument": arg,
                    "ok": r["ok"],
                    "source": r.get("source"),
                    "error": r.get("error"),
                    "fields": list(sample) if isinstance(sample, dict) else [],
                    "sample_id": sample.get("id") if isinstance(sample, dict) else None,
                    "ms": ms,
                }
            )
            if tool == "search" and r["ok"]:
                detail, t = use(lambda: food_tools.call("detail", str(row[0]["id"])))
                rows.append(
                    {
                        "tool": "detail",
                        "from_search_id": row[0]["id"],
                        "ok": detail["ok"],
                        "title": detail.get("data", {}).get("title"),
                        "ms": t,
                    }
                )
        save(
            "live-apis.json",
            {
                "observed_kst": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds"),
                "calls": rows,
            },
        )
    with (
        TemporaryDirectory() as tmp,
        patch.dict(os.environ, {"FRIDGE_DATA_DIR": tmp}),
        patch.object(food_tools, "call", side_effect=fixture),
        patch.object(gateway, "configured", return_value=False),
    ):
        checks = scenario_eval()
        save("scenarios.json", checks)
        save("inventory-comparison.json", inventory_eval())
        save("roles-comparison.json", compare(tmp))
        assert all(x["pass"] for x in checks), checks


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    main(parser.parse_args().live)
