"""테스트용 대역 모델 — 2일차 실습의 fake_plan · fake_answer 처럼, 키·네트워크 없이 그래프를 돌린다.

gateway.ChatOpenAI 자리에 FakeChat 을 끼우면 decide(JSON) · structured(Plan) · write(문장) 이
정해 둔 응답을 돌려준다. 앱 코드에서는 쓰지 않는다.
"""

import json
from types import SimpleNamespace


class FakeChat:
    calls = []

    def __init__(self, decide=None, plan=None, answer="확인한 결과를 정리했습니다.", **kwargs):
        self.kwargs, self._decide, self._plan, self._answer = kwargs, decide or {}, plan, answer
        self._mode, self._schema = "text", None

    @classmethod
    def factory(cls, **script):
        def make(**kwargs):
            chat = cls(**script, **kwargs)
            cls.calls.append(chat)
            return chat

        return make

    def bind(self, **_):
        self._mode = "json"
        return self

    def with_structured_output(self, schema):
        self._mode, self._schema = "structured", schema
        return self

    def invoke(self, messages):
        if self._mode == "structured":
            script = self._plan or {}
            # 양식 이름(Plan, GuideDraft, Sight …)으로 응답을 나눠 둘 수 있다
            script = script.get(self._schema.__name__, script) if self._schema.__name__ in script else script
            return self._schema.model_validate(script)
        if self._mode == "json":
            return SimpleNamespace(text=json.dumps(self._decide, ensure_ascii=False))
        return SimpleNamespace(text=self._answer)
