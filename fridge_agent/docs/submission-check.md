# AI 코어 프로젝트 3회차 제출 검증

2026년 11월 20일 서울 시간 기준으로 한끼를 요구사항 번호에 맞춰 다시 검토했다. 세부 설계는 [Agent 설계](design.md), 공급자 약관은 [데이터 출처](data.md), 실행 절차는 [시연 가이드](demo-guide.md)에 있다. 영화 시나리오는 과제의 예시이며, 한끼는 레시피·냉장고·생활 일정으로 같은 요구사항을 검증한다.

| 번호 | 구현과 재현 근거 |
|---|---|
| F3001 | `GET /api/tools`가 외부/로컬 분류, 입력, 응답, 오류 코드를 제공한다. [Tool 정의](tools.md) |
| F3002 | TheMealDB 후보 ID를 사용한다. 기준 날짜를 지정하더라도 조회 시점 카탈로그를 사용한다는 사실을 표시한다. 결과가 없거나 후보를 다 확인하면 설정된 국내 레시피 도구를 확인한다. [테스트](../test_agent.py) |
| F3003 | 후보 ID로 상세 레시피를 가져온다. 상세 재료 정보가 비면 충족으로 판정하지 않는다. [실제 후보→상세 조회](evidence/live-apis.json) |
| F3004 | Open Food Facts 제품 영양, USDA 식품 참조, wger 운동 정보를 서로 다른 제공처에서 호출했다. 주소·링크가 있는 쇼핑·지도 도구도 검증한다. [실호출](evidence/live-apis.json) · [제공처 계약 시험](../test_final.py) |
| F3005 | 기준·선호·제약 조건을 분리해 이벤트에 출력한다. 지역이 없는 헬스장 요청은 되묻는다. [테스트](../test_autopilot.py) |
| F3006 | LangGraph에서 Planner가 필요한 작업만 선언한다. 인사와 도움말은 도구 호출 0건이다. [그래프와 입력·출력](design.md) |
| F3007 | 조회 후보 ID를 상세 조회로 넘기고, 국내 레시피 부족 재료를 상품 조회 인자로 사용한다. 일부 제공처 실패는 오류 코드로 반환한다. [테스트](../test_planner.py) |
| F3008 | 재고량과 소비기한, 인분, 조리 시간, 다음 일정까지 남은 시간을 계산한다. 늦어도 조리 시작 시각을 도출하되, 일정 미확인과 일정 충족을 구분한다. [테스트](../test_final.py) |
| F3009 | 이미 확보한 검색 결과에서 다음 상세 후보를 조회한다. 재계획 상한은 3회다. 조건에 맞는 대안이 있으면 Worker 실패를 Planner에 전달해 추가 실행한다. [후보 교체 로그](evidence/one-run.json) · [상한 포함 검증](evidence/scenarios.json) |
| F3010 | 세션별 마지막 메뉴·재료와 추천 조건을 저장한다. 후속 요청에서 기존 제약과 제외 재료를 적용한다. [테스트](../test_autopilot.py) |
| F3011 | 후보별 시간·영양·재고 근거와 제외 사유를 보여 준다. 생활 건강 안내에 의료진 상담 문구를 표시한다. [화면](../screens/meal-mobile.webp) |
| F3012 | 단계 진입·종료, 도구 호출·결과·소요시간, 모델 판단을 실행 ID로 연결한다. 조리 영상·사진·국내 레시피 조회에도 소요시간을 남긴다. [대표 요청 로그](evidence/agent-one-run.json) |
| F3013 | 구독형 LoggingAgent가 세션별 원본 이벤트를 저장한다. 구독 분리와 구독자 오류 이후 실행을 확인했다. [테스트](../../tests/test_events_logging.py) |
| F3014 | 세션 목록·상세·삭제, 실행 ID 필터를 검증한다. PUT 요청은 405다. [테스트](../test_final.py) · [API](openapi.json) |
| F3015 | 추천한 메뉴·인분이나 운동을 화면에서 일정으로 저장한다. 날짜·시각·생성일시·항목을 상세에서 조회한다. 겹치는 일정도 저장하고 충돌을 함께 알려 준다. [화면](../screens/coach-plan-mobile.webp) |
| F3016 | 계획 수정 및 삭제를 FastAPI와 화면에 연결한다. 종료가 시작보다 이른 입력을 막는다. [테스트](../test_final.py) |
| F3017 | 대화, 계획, 로그에 Pydantic 요청·응답 계약을 적용한다. [OpenAPI](openapi.json) · [Swagger 화면](../screens/fastapi-docs.webp) |
| F3018 | 대화·계획 관리 화면이 FastAPI 데이터를 쓴다. [브라우저 검증 코드](../system_check.py) |
| F3019 | 처리 진행 상태와 실패를 알리고 요청별 실행 과정을 순서대로 표시한다. 재계획을 구분하고 지난 대화의 해당 실행을 다시 조회할 수 있다. [화면](../screens/coach-saved-trace-mobile.webp) |
| F3020 | LoggingAgent 쪽 검증기가 계획 밖 호출, 같은 입력 반복, 연속 실패, 과다 재계획을 판정한다. 근거가 비면 판정 불가로 기록한다. 이상에서만 모델 진단을 시도한다. [테스트](../test_final.py) |
| F3021 | Planner와 Worker가 Task와 WorkerResult를 주고받는다. 인자 보정은 같은 도구에서 최대 한 번이며 고정 인자를 보호한다. 대안이 있으면 로깅 검증에서 Planner가 재계획하고 그래프가 새 작업을 실행한다. [전후 비교](evidence/roles-comparison.json) · [테스트](../test_agent.py) |
| F3022 | 건강 질의는 한끼 Chroma 색인을 검색한다. 2회차 국가유산 Chroma 연결도 추가했다. 동일한 컬렉션 구조의 시험 색인으로 문서·출처 응답과 `NO_INDEX`를 검증했다. [테스트](../test_rag.py) |
| F3023 | 같은 Tool 계약으로 로컬·Google 구현체를 교체한다. 일정 조회 결과를 조리 계획에 반영한다. 자동 검증은 로컬과 Google 응답 대역을 사용했다. [테스트](../test_final.py) |
| NF3001~NF3002 | 환경변수 기반으로 자격 증명을 읽는다. Anthropic·외부 제공처 실패 응답에서 원문 오류와 키를 숨긴다. [테스트](../test_gateway.py) |
| NF3003~NF3004 | 도구 오류를 구조화하고 호출·재계획 상한을 적용한다. [후보 상한과 도구 실패 결과](evidence/scenarios.json) |
| NF3005 | 로컬 대화 시나리오와 외부 단일 도구 처리 시간을 각각 기록했다. 인증된 모델의 실제 지연은 계정 환경에서 확인해야 한다. [대화 측정](evidence/agent-scenarios.json) · [외부 호출 측정](evidence/live-apis.json) |
| NF3006~NF3007 | Agent·Tool·이벤트·저장소·서버·화면을 모듈로 분리하고 제공처 출처와 이용 조건을 문서화했다. [설계](design.md) · [출처](data.md) |

## 재실행과 제출 증거

```sh
python -m pytest -rs --junitxml=hankki-tests.xml
python fridge_agent/validate.py --live
python fridge_agent/validate_agent.py
python fridge_agent/system_check.py --screens my-screens
```

- 요구사항 정의서, 설계 문서, Tool 정의서, OpenAPI, 실행 로그 샘플과 구현 소스는 저장소에서 찾을 수 있다. [제출물 목차](../../README.md)
- 필수 대표 사례 6개와 대화형 사례 11개를 실행했다. 대표 대화 전체와 후보 교체 로그를 제공한다. [대표 응답](evidence/agent-one-run.json) · [후보 교체](evidence/one-run.json)
- 자동 실계정 검증은 Claude 동일 질문, Claude 계획·응답, Google 일정 조회, Google 일정 등록·재조회 네 건으로 구성한다. 이번 환경에서는 인증 설정 없이 실행했다. [실계정 테스트 방법](course-check.md)
- 2회차 실데이터 검증에는 기존 Chroma DB 경로와 해당 임베딩 키가 필요하다. 이번 환경에는 2회차 구현 코드는 있었고 원본 Chroma 파일은 없었다. [연결 방법](tools.md)
- PDF는 별도로 배포되는 3일차 오후 공식 셀프 체크리스트를 참조한다. 업로드 자료에서 확인 가능한 1·15·25번과 이 표의 전체 번호별 확인 결과를 남겼다. SSAFY Lab 제출 여부는 계정에서 확인해야 한다. [체크 결과](course-check.md)
