# 도구와 API 명세

도구가 성공하면 ok, data와 출처를 반환한다. 실패하면 ok=false와 구조화한 error를 반환한다. 설정 누락 시에는 필요한 환경변수 이름을 제공한다. /api/tools 에서 기계 판독 명세를 읽을 수 있다.

| 도구 | 종류 | 용도 | 입력 | 성공 데이터 |
|---|---|---|---|---|
| search | 외부 | TheMealDB 재료별 후보 | 재료명 | `[{id,title}]` |
| detail | 외부 | TheMealDB 후보 상세 | 후보 id | `{title,ingredients,instructions}` |
| nutrition | 외부 | Open Food Facts 제품 표시 영양 | 제품 바코드 8~14자리 | `{product,basis,kcal,protein_g}` |
| kr_recipe | 외부 | 식품안전나라 국내 레시피 | 메뉴명 | `[{id,메뉴,재료·분량,조리 순서}]` |
| kr_nutrition | 외부 | 식약처 식품영양성분 | 식품명 | `[{식품,기준량,열량(kcal),단백질(g)}]` |
| usda | 외부 | USDA 100g 영양 참조 | 영어 식품명 | `[{id,title,url,nutrients_per_100g}]` |
| naver | 외부 | 네이버 장보기 | 제품 검색어 | `[{id,title,price_krw,merchant,url}]` |
| coupang | 외부 | 쿠팡 파트너스 상품 검색 | 제품 검색어 | `[{id,title,price_krw,merchant,url}]` |
| youtube | 외부 | YouTube 최근 30일 요리 영상 | 메뉴명 | `[{title,url,published,views,views_per_day}]` |
| instagram | 외부 | Instagram 최근 해시태그 | 메뉴명 | `[{title,url,published,likes,comments}]` |
| gyms | 외부 | Kakao 지역 헬스장 | 지역·역명 | `[{id,title,url,address}]` |
| wger | 외부 | wger 운동 참고자료 | 운동 id | `{id,title,equipment,url,license}` |
| calendar_list | 로컬 / 외부 | 지정일 등록 일정 조회 | YYYY-MM-DD | `[{id,title,start,end}]` |
| calendar_register | 로컬 / 외부 | 저장 계획 일정 등록 | 저장한 계획 id | `{id,title,start,end,day}` |
| local | 로컬 | 재료·식사·운동 계산 | 현재 조건 | `{메뉴?,안내?,근거?,루틴?}` |

외부 연결을 확장할 때는 registry.META에 계약을 추가하고, 제공처 호출을 connections 또는 food_tools에 연결한다. Planner.tasks에서 필요한 요청에만 배치하고 키 누락, 결과 없음, 단위와 출처를 검증한다. 고정 입력과 보정 가능 인자를 구분한다.

## API 예시

~~~http
POST /api/chat
Content-Type: application/json

{"message":"입고","params":{"name":"두부","quantity":300,"unit":"g","expires":"2026-12-17"},"request_id":"lot-101"}
~~~

성공 시 200과 냉장고·포장·현재 추천·실행 ID·순서 있는 추적을 돌려준다. 수량이나 날짜 오류는 422, 충돌한 요청은 409다. 계획 생성은 201과 겹친 계획 목록, 삭제는 204를 돌려준다. 경로별 파라미터와 응답은 [OpenAPI JSON](openapi.json)에 담았다.

| 경로 | 메서드 |
|---|---|
| `/api/calendar/status` | GET |
| `/api/calendar/connect` | GET |
| `/api/calendar/callback` | GET |
| `/api/calendar/connection` | DELETE |
| `/api/plans` | GET, POST |
| `/api/plans/{plan_id}` | GET, PATCH, DELETE |
| `/api/logs` | GET |
| `/api/logs/{session_id}` | GET, DELETE |
| `/api/chat` | POST |
| `/api/state` | GET |
| `/api/tools` | GET |
| `/api/catalog` | GET |
| `/api/export` | GET |
| `/api/data` | DELETE |
| `/` | GET |
| `/privacy` | GET |
| knowledge | 로컬 벡터 DB(Chroma) | 식품·영양·운동·생활 안내 문서 근거 검색 | 질문 문장 | `[{id,title,excerpt,source,url,distance}]` · 실패: NO_INDEX, NO_RESULT, RAG_DEPENDENCY_MISSING |

`GET /api/logs/{session_id}?run_id={run_id}`는 그 세션의 특정 응답에 해당하는 이벤트만 반환한다. 세션 조회와 삭제의 범위는 기존과 같다.

`유산근거 <질문>`은 2회차 국가유산 Chroma를 검색한다. 2회차의 Chroma 저장 폴더를 `HERITAGE_CHROMA_DIR`로 설정하고, 질의 벡터에 사용할 GMS 또는 OpenAI 임베딩 키를 등록한다. 문서 컬렉션은 `heritage_docs`이며 출처와 링크를 반환한다. 색인이 연결되지 않거나 비어 있으면 `NO_INDEX`를 반환한다.
