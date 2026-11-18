# 냉장고 식단·운동 에이전트

Python 3.10+에서 저장소를 내려받은 뒤 실행합니다.

```bash
cd fridge_agent
python -m pip install -r requirements.txt
python app.py
```

브라우저에서 http://127.0.0.1:8000 을 엽니다. API 명세는 /docs 에 있습니다. 단일 사용자용 로컬 서비스이며 기본 세션은 default입니다. 자유 대화에는 OPENAI_API_KEY가 필요합니다. 운동·영양 정보는 생활 기록용이며 개인별 의학적 판단은 전문가와 상담하세요.

## 대표 시나리오

| 입력 | 기대 결과 |
|---|---|
| 추가 달걀, 양파, 식용유 → 메뉴 대파 달걀볶음 → 대체 양파 | 부족한 대파 대신 양파를 적용하고 열량과 구매 목록 재계산 |
| 조리 2인분 16분 → 섭취 양파 달걀볶음 | 1인분 남음. 최근 5회 실제 조리시간 평균을 이후 같은 메뉴에 사용 |
| 외식 → 집밥 | 재고와 남은 음식을 보존하고 식사·운동 계획 전환 |
| 검색 달걀 | 후보 검색 결과의 식별자로 상세 조회. 재료가 일치하지 않으면 최대 3회 다른 후보를 조회 |
| 영양 3017620422003 | 제품의 100g 기준 열량·단백질 조회. 누락 값은 null |
| 도움말 | 외부 호출 없이 사용법 안내 |

재고는 재료 보유 여부로 입력합니다. 조리 분량은 남은 음식으로 기록되며 원재료 중량은 직접 확인해야 합니다. 외부 레시피의 조리시간과 섭취 열량은 추정하지 않습니다.

## 설계와 검증

LangGraph는 분석 → 계획 → 실행 → 판정 → 응답으로 진행합니다. 상세 조회 시 기존 후보 목록을 재사용하고, 재계획 3회 뒤 확인된 후보 중 미확인 재료 수가 최소인 것을 반환합니다. 영어 재료명 일치는 제한된 한영 사전과 정확 일치 기준입니다. 통신 장애는 SOURCE_UNAVAILABLE로 반환합니다. 자료가 없는 경우 NO_RESULT입니다. 로컬 추천은 외부 통신 없이 동작합니다. LoggingAgent는 EventBus를 구독해 실행 순서, 도구 입력·결과·소요시간을 SQLite에 저장합니다. 저장 실패는 메인 응답을 막지 않습니다.

| 요구사항 | 구현 위치와 확인 방법 |
|---|---|
| F3001–3004 | food_tools.py 및 GET /api/tools. TheMealDB 후보·상세, Open Food Facts 영양 조회 |
| F3005–3011 | app.py와 workflow.py. POST /api/chat에 message와 session_id를 전달. 세션별 조건을 SQLite에 보존 |
| F3012–3014 | backend의 EventBus·LoggingAgent 재사용. GET /api/logs, GET 또는 DELETE /api/logs/{session_id} |
| F3015–3019 | /api/plans 목록·생성·상세·수정·삭제, 겹침 알림, 웹 화면의 실행 단계·계획 관리 |
| NF3001–3007 | 환경변수 키, 고정 HTTPS 출처, 실패 응답과 상한, 소요시간 기록, 별도 화면·도구 모듈 |

외부 데이터는 [TheMealDB 교육용 API](https://www.themealdb.com/api.php)와 [Open Food Facts API](https://openfoodfacts.github.io/openfoodfacts-server/api/)를 사용합니다. TheMealDB 공개 개발 키 1은 학습용이며 앱 출시 시 이용 조건을 다시 확인해야 합니다. Open Food Facts 데이터는 ODbL이며 공급자의 엔드포인트별 호출 제한이 적용됩니다. 후보·상세·영양 세 엔드포인트는 두 제공처에서 제공합니다.

```bash
python -m pip install pytest httpx
python -m pytest -q test_agent.py
```

필수 흐름의 일부를 자동화한 테스트입니다. 예외·재계획 상한은 대역 도구로 재현합니다. 3회차 최종 제출에는 수업에서 제공하는 셀프 체크리스트와 시연 화면 캡처를 추가해야 합니다.

## 국내 레시피와 영양 정보

서버 환경변수 또는 저장소 루트의 로컬 .env에 FOODSAFETY_API_KEY(식품안전나라 인증키)와 DATA_GO_KR_SERVICE_KEY(공공데이터포털 서비스키)를 설정합니다. 모델 키와 별개입니다.

- `레시피 달걀찜`은 [COOKRCP01](https://www.foodsafetykorea.go.kr/api/openApiInfo.do?svc_no=COOKRCP01)에서 메뉴명으로 검색해 재료·분량 원문과 조리 순서를 가져옵니다.
- `식품영양 두부`는 [식품영양성분 DB](https://www.data.go.kr/data/15127578/openapi.do)에서 식품별 기준량·열량·단백질을 조회합니다. 식품명과 기준량을 확인한 뒤 사용하세요.
- 성공한 검색 결과는 food_catalog.sqlite3에 24시간 캐시합니다. 누락 영양값은 추정하지 않습니다. 명령을 실행하면 화면과 API에 동일한 결과가 표시됩니다.
