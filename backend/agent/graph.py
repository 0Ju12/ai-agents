"""LangGraph 실행 그래프: 분석 → 계획 → 실행 → 판정 → 응답 (검증 4.2: 그래프 구조 출력용)."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from . import nodes as n
from .state import TripState


def build_graph():
    g = StateGraph(TripState)
    g.add_node("analyze_intent", n.analyze_intent)
    g.add_node("extract_conditions", n.extract_conditions)
    g.add_node("plan", n.plan)
    g.add_node("execute", n.execute)
    g.add_node("judge", n.judge)
    g.add_node("replan", n.replan)
    g.add_node("ask_back", n.ask_back)
    g.add_node("respond", n.respond)

    g.add_edge(START, "analyze_intent")
    g.add_edge("analyze_intent", "extract_conditions")
    g.add_conditional_edges("extract_conditions", n.route_after_extract, ["plan", "ask_back", "respond"])
    g.add_edge("plan", "execute")
    g.add_edge("execute", "judge")
    g.add_conditional_edges("judge", n.route_after_judge, ["replan", "respond"])
    g.add_edge("replan", "execute")
    g.add_edge("ask_back", END)
    g.add_edge("respond", END)
    return g.compile()


if __name__ == "__main__":  # python -m backend.agent.graph → 그래프 구조(mermaid) 출력
    print(build_graph().get_graph().draw_mermaid())
