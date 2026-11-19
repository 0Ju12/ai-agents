"""대화형 대표 시나리오 검증: 요청마다 기대 동작과 실제 결과, 도구 호출, 재계획, 처리 시간을 기록한다.

    python validate_agent.py            → docs/evidence/agent-scenarios.json, docs/evidence/agent-one-run.json

임시 데이터 폴더와 예시 냉장고에서 실행하고, 모델·외부 API 키는 쓰지 않는다(규칙 경로).
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from time import perf_counter

HERE = Path(__file__).resolve().parent
os.environ["FRIDGE_DATA_DIR"] = tempfile.mkdtemp()
for k in ("GMS_KEY", "GMS_API_KEY", "OPENAI_API_KEY", "YOUTUBE_API_KEY", "FOODSAFETY_API_KEY"):
    os.environ.pop(k, None)
sys.path.insert(0, str(HERE))
import app  # noqa: E402

CASES = [
    ("제약을 한 번에 충족", "퇴근했는데 20분밖에 없어. 단백질 위주로 먹고 싶어", lambda p: p.get("추천 후보") and all(x["조리시간(분)"] <= 20 for x in p["추천 후보"]), "20분 이내 메뉴만 후보, 1순위 확정"),
    ("말한 메뉴가 시간 초과 → 시간 조정", "김치찌개 먹고 싶어", lambda p: p["자동 진행"][0]["작업"] == "가용 시간 조정" and "김치찌개" in p["메뉴"], "가용 시간을 늘리고 되돌리기 제공"),
    ("인원 반영 장보기", "파스타 해먹고 싶어 둘이서", lambda p: any(d["작업"] == "장바구니 담기" for d in p["자동 진행"]), "2인분 부족분만 장바구니"),
    ("다른 후보(재계획)", "다른 추천후보 알려줘", lambda p: p.get("더보기") is True, "이미 보여 준 메뉴를 빼고 새 후보"),
    ("RAG 근거 질문", "단백질 하루 권장량이 얼마야?", lambda p: p.get("근거 문서") and "출처" in p.get("답변", ""), "근거 문서와 출처"),
    ("근거 없는 질문", "오늘 주가 어때?", lambda p: p.get("오류") == "NO_RESULT" or "찾지 못했어요" in p.get("안내", ""), "지어내지 않고 근거 없음 안내"),
    ("Tool 실패(키 누락)", "식품영양 두부", lambda p: p.get("조회", {}).get("error") == "MISSING_KEY", "실패 사유를 남기고 서비스 계속"),
    ("Tool 불필요", "안녕", lambda p: p.get("안내", "").startswith("안녕하세요"), "도구 호출 없이 안내"),
    ("운동 요청", "어깨 운동 30분 하고 싶어", lambda p: p.get("운동 루틴", {}).get("body") == "어깨", "어깨 30분 트레이너 루틴"),
    ("알림 요청", "비타민D 아침 9시에 알려줘", lambda p: "알림" in p.get("안내", ""), "영양제 알림 등록"),
    ("기록 요청", "물 500ml", lambda p: "500mL" in p.get("안내", ""), "물 기록과 오늘 합계"),
]


def main():
    app.run("데모")
    rows, sample = [], None
    for name, request, check, expected in CASES:
        t = perf_counter()
        out = app.run(request)
        ms = round((perf_counter() - t) * 1000, 1)
        p, events = out["계획"], out["추적"]
        ok = bool(check(p))
        rows.append({
            "시나리오": name, "요청": request, "기대 동작": expected, "통과": ok, "처리 시간(ms)": ms,
            "도구 호출": [e["name"] for e in events if e["type"] == "tool_call"],
            "재계획": sum(e["type"] == "replan" for e in events),
            "실행 단계": [e["name"] for e in events if e["type"] == "node_start"],
            "결과 요약": (p.get("답변") or p.get("안내") or p.get("메뉴") or "")[:120],
        })
        if request.startswith("퇴근"):
            sample = {"요청": request, "이벤트": events}
    (HERE / "docs" / "evidence" / "agent-scenarios.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (HERE / "docs" / "evidence" / "agent-one-run.json").write_text(json.dumps(sample, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    passed = sum(r["통과"] for r in rows)
    print(f"{passed}/{len(rows)} 통과")
    for r in rows:
        print(("✓" if r["통과"] else "✗"), r["시나리오"], r["처리 시간(ms)"], "ms", r["도구 호출"])
    return passed == len(rows)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
