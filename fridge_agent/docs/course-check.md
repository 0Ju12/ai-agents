# 한끼 2·3일차 실행 점검표

2026-11-20 실행 결과는 100건 통과, 0건 실패, 실계정 점검 4건 미확인이다. 아래 테스트 이름으로 각 결과를 다시 확인할 수 있다. 괄호 안 번호는 첨부 실습에 번호가 명시된 체크리스트 항목이다.

| 실습 | 한끼에서 확인한 동작 | 결과 | 대표 테스트 |
|---|---|---|---|
| 2일차 ① | 도구 없이 같은 냉장고 질문을 GMS에 두 번 독립 전송하고 두 답을 출력 | 미확인 · GMS 키 필요 | test_gms_same_question_twice |
| 2일차 ② · 3일차 ⑤ (1번) | 레시피 조회 성공, 키 누락, 인자 누락·빈 값·잘못된 형식·추가 인자의 실패 응답 | 통과 | test_korean_sources, test_tool_contract_rejects_invalid_arguments |
| 2일차 ③ | 식재료 검색 결과 ID로 상세 레시피 조회, 다음 후보로 재계획, 호출 수 제한 | 통과 | test_graph_scenarios |
| 2일차 ④ | 구조화된 계획에서 레시피와 재고를 비교해 부족한 재료만 쇼핑 도구에 전달 | 통과 · 모델 대역 | test_model_plans_recipe_then_shopping_for_missing_items |
| 2일차 ④ | GMS가 앱의 실제 계획·응답 양식을 처리하는지 확인 | 미확인 · GMS 키 필요 | test_live_planner_and_answer |
| 2일차 ⑤ · 3일차 ① (15번) | 구독 중 세션별 순서 보존, 구독 해제 후 물 기록 성공 및 로그 0건 | 통과 | test_logging_agent_stores_by_session_in_order, test_log_http_contract_and_detached_agent |
| 3일차 ② | 로그 목록·상세 조회, 수정 요청 405, 삭제 204 및 재조회 404 | 통과 | test_log_http_contract_and_detached_agent |
| 3일차 ③ | 계획 밖 호출, 같은 인자 반복, 같은 도구의 연속 실패, 재계획 3회 도달 경고. 빈 기록 판정 보류 및 경고 시 모델 진단 분리 | 통과 | test_logger_and_worker_contract, test_consecutive_tool_failures, test_replan_warning_boundary, test_graph_scenarios |
| 3일차 ④ | 저장된 계획을 로컬 일정에 등록, 겹침과 남은 시간 계산, Google 응답을 동일 형식으로 변환 | 통과 · 로컬 및 Google 모의 응답 | test_plans_calendar_and_deadline, test_google_adapter_and_gms_routing |
| 3일차 ④ | 실제 Google Calendar 조회 / 지정 계획 등록 후 같은 이벤트와 시작·종료 시각 재조회 | 미확인 · Google OAuth 연결 및 테스트용 계획 필요 | test_google_calendar_read, test_google_calendar_register_and_read_back |
| 3일차 ⑤ (25번) | 원문 오류 URL에 포함한 테스트용 비밀값이 사용자 결과와 실행 추적에 노출되는지 확인 | 통과 | test_model_failure_falls_back_to_rule_plan |

## 재실행

저장소 루트에서 개발 의존성을 설치한 뒤 실행한다. JUnit 결과에는 테스트별 통과·실패·건너뛴 사유가 남는다.

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -rs --junitxml=/tmp/hankki-check.xml
```

실계정 점검은 따로 실행한다. GMS는 서버 환경의 `GMS_API_KEY` 또는 `GMS_KEY`와 사용 가능한 `GMS_MODEL`을 사용한다. Google은 로컬 모드에서 앱의 OAuth 연결을 마친 테스트용 데이터 폴더를 `FRIDGE_DATA_DIR`로 지정한다. `HANKKI_CHECK_PLAN_ID`를 설정하면 해당 저장 계획을 연결된 캘린더에 실제로 등록하거나 같은 이벤트를 갱신하고 다시 읽는다. 등록한 일정은 캘린더에 남는다. ID를 생략하면 Google 조회만 실행할 수 있다.

```sh
HANKKI_COURSE_LIVE=1 python -m pytest fridge_agent/test_course_live.py -rs -s --junitxml=/tmp/hankki-live.xml
```

GMS에서 같은 질문에 같은 답이 나오는 경우도 유효한 관찰 결과다. 이 실습은 답변 두 개를 비교하기 위한 것이며, 재고의 실제 수량은 앱의 냉장고 데이터로 확인한다.
