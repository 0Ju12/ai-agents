# 한끼 기획 및 설계

## 문제와 사용자

냉장고에는 두부가 있어도 2인분에 충분한지, 이번 주 안에 쓸 수 있는지, 조리 뒤 운동할 시간이 남는지는 각각 확인해야 한다. 한끼는 한 사람이 포장 단위로 재료를 적으면 조리 가능한 메뉴를 찾고, 부족한 g 수와 조리 후 남는 시간을 계산한다. 실제 조리와 섭취는 별도 사건으로 기록한다. 사용자에게 메뉴를 제안한 횟수와 실제로 먹은 횟수를 구분할 수 있다.

## 유스케이스 다이어그램

~~~mermaid
flowchart LR
 U([사용자])
 subgraph H[한끼]
  I([포장과 소비기한 등록])
  P([목표와 제약 설정])
  M([식단과 운동 추천])
  B([부족분과 구매 후보 조회])
  V([조리 단계와 영상 조회])
  J([조리·섭취·운동 기록])
  D([기기 건강 합계 가져오기])
  C([계획 저장과 일정 등록])
  T([판단 근거와 실행 이력 조회])
 end
 U --> I
 U --> P
 U --> M
 U --> J
 U --> D
 U --> C
 U --> T
 M -->|메뉴 선택| V
 M -->|부족할 때| B
 S([식품·쇼핑·영상 제공처]) --- B
 S --- V
 A([Health Connect]) --- D
 G([Google Calendar]) --- C
~~~

## 시스템 디자인

한국어 웹 화면은 모바일 하단 탭과 데스크톱 사이드바를 공유한다. 첫 방문에서는 편집 레시피와 빈 냉장고를 보여준다. 식품 이미지 분석은 첫 등록 작업에서 제외하고, 재료 이름만으로 포장을 만들 수 있다. 화면은 도메인 판단을 서버 API에 맡긴다. Android 셸은 HTTPS WebView, 외부 링크 이동, Health Connect 동의 및 일일 합계 미리보기를 담당한다.

~~~mermaid
flowchart LR
 Web[브라우저] --> API[FastAPI]
 Android[Android 앱] --> API
 HC[Health Connect] -->|동의한 합계| Android
 API --> Graph[LangGraph의 Planner와 Worker]
 Graph --> Tools[외부 도구·캘린더·색인]
 Graph --> Bus[EventBus]
 Bus --> Logger[LoggingAgent]
 API --> Data[(개인 SQLite)]
 Logger --> Data
 Graph --> Domain[재고·식단·운동 계산]
 Domain --> Ref[(공용 식품·운동 DB)]
~~~

## ERD

공용 카탈로그와 기기별 데이터는 다른 SQLite 파일을 사용한다. 아래 관계는 앱이 유지하는 논리 관계다. 사용자가 가져온 레시피·목표·운동 이력은 kitchens.settings, 섭취한 영양 스냅샷은 days.body에 보존한다.

~~~mermaid
erDiagram
 KITCHENS ||--o{ LOTS : stores
 KITCHENS ||--o{ BATCHES : cooks
 KITCHENS ||--o{ DAYS : records
 KITCHENS ||--o{ RECEIPTS : deduplicates
 RECIPES ||--|{ PORTIONS : needs
 INGREDIENTS ||--o{ PORTIONS : measures
 KITCHENS ||--o{ RUN_LOGS : traces
 PLANS ||--o| EVENTS : registers
 KITCHENS { string session PK int revision string settings }
 LOTS { string session PK string id PK string item float grams date expires }
 BATCHES { string session PK string id PK string title int servings string facts }
 DAYS { string session PK date day PK string body }
 RECEIPTS { string session PK string id PK string fingerprint string reply }
 RECIPES { string title PK int minutes string steps string source }
 INGREDIENTS { string name PK int fdc_id string reference }
 PORTIONS { string title PK string name PK float grams }
 EXERCISES { int id PK string category string record }
 SEARCHES { string tool PK string term PK float fetched string result }
 PLANS { int id PK date trip_date string start_time string end_time string items_json }
 EVENTS { string id PK date day string start string end }
 RUN_LOGS { int id PK string session_id int seq string type string payload }
~~~

## 클래스 다이어그램

~~~mermaid
classDiagram
 class KitchenDB {
  +read(session)
  +receipt(session, id, fingerprint)
  +commit(session, revision, state, reply, id, fingerprint)
 }
 class Planner { +tasks(command, argument) }
 class Task { +tool +argument +fixed +purpose }
 class Worker { +perform(task) }
 class WorkerResult { +task +result +decision +attempts }
 class EventBus { +emit() +subscribe() }
 class LoggingAgent { +attach(bus) +handle(event) }
 class Store { +create_plan() +append_log() +get_session_logs() }
 Planner --> Task
 Worker --> Task
 Worker --> WorkerResult
 EventBus --> LoggingAgent : publish
 LoggingAgent --> Store
 class ChatService {
  <<module app>>
  +run()
  +snapshot()
 }
 ChatService --> KitchenDB
 ChatService --> Planner
 ChatService --> Worker
 ChatService --> EventBus
~~~

## 시퀀스 다이어그램

~~~mermaid
sequenceDiagram
 actor U as 사용자
 participant UI as 화면
 participant A as FastAPI
 participant D as KitchenDB
 participant P as Planner
 participant W as Worker
 participant T as 식품 도구
 participant L as EventBus와 Logger
 U->>UI: 검색 달걀
 UI->>A: 메시지와 요청 식별자
 A->>D: 이전 응답과 재고·조건 조회
 A->>P: 달걀 레시피 후보 검색
 P-->>L: 도구 계획 발행
 P->>W: search Task
 W->>T: 재료 기준 후보 조회
 T-->>W: 후보 ID와 이름
 loop 최대 4개 후보
  P->>W: detail Task
  W->>T: 해당 ID의 재료·조리법
  W-->>L: 결과와 소요시간
  W-->>P: 성공 또는 실패 사유
  opt 재료 불일치 또는 상세 없음
   P-->>L: 기존 목록을 재사용한 재계획
  end
 end
 P-->>A: 추천·미확인 재료·상한 사유
 A->>D: 버전 확인과 요청 결과 원자 저장
 A-->>UI: 추천과 순서 있는 실행 이력
 UI-->>U: 재료·근거·다음 작업
~~~

## 판단과 메모리

- **재고**는 기한이 지난 포장을 제외한다. 같은 재료의 계량 중량을 합산하고 미계량은 ‘수량 확인’으로 보낸다. 1인분 필요량에 조리 인분을 곱한 뒤 기한이 빠른 포장부터 차감한다. 조리로 만든 분량을 실제로 먹을 때 영양을 기록한다.
- **식단**은 제외 재료·식물성·시간 조건으로 먼저 거른다. 다음으로 부족 재료 수, 먼저 먹고 싶은 재료, 가장 가까운 소비기한, 선택한 단백질 우선 기준을 비교한다. 영양 값이 없는 재료가 있으면 그 영양소의 합도 미확인으로 둔다. 1주 초안은 매일의 현재 재고를 기준으로 제안한다.
- **운동**은 목표, 부위, 경험, 기구, 실제 사용할 수 있는 분을 사용한다. 매 회차에는 준비·반복·휴식·마무리를 포함한다. 지난번 같은 부위가 어려웠으면 다음 루틴의 부담을 줄인다. 플랜핏에서 참고한 범위는 부위·기구·숙련도 선택과 피드백 흐름이다. 동작 안내와 화면은 이 프로젝트에서 작성했다.
- **대화**는 사용자가 바꾼 조건만 덮어쓴다. 가용 시간, 날짜·시각, 지역, 식단 목표, 개인 상한 예산, 최근 메뉴와 재료가 다음 요청에 이어진다. 외식은 해당 날짜의 조리를 건너뛰고 집밥으로 되돌릴 수 있다.
- **에이전트**는 명령·도메인 계산을 규칙으로 처리한다. Planner는 자유 입력에서 명시한 조건을 추출할 때 GMS를 쓴다. Worker는 정해진 Task를 실행하고 인자를 다듬을 수 있는 실패만 모델에 맡긴다. 같은 도구 1회 재시도만 허용하고 사용자가 고정한 인자는 보호한다. 조회 결과는 요청 단위로 재사용한다.
- **로깅**은 구독자가 실행 순서대로 저장한다. 중복 입력·비계획 호출·재계획 상한 초과를 코드로 판정한다. 근거가 없으면 ‘판정 불가’다. 경고가 있을 때만 선택적으로 모델이 별도 진단을 쓰며 Planner가 남은 작업을 정리한다.
- **저장**은 유료 API 호출 중에 SQLite 쓰기 잠금을 잡지 않는다. 완료 시점에 revision을 비교하고 재시도 식별자와 응답을 함께 커밋한다. 같은 식별자의 같은 입력은 이미 저장한 응답을 반환한다. 서버 배포 시에는 브라우저의 HttpOnly 쿠키에서 파생한 개인 저장 공간을 사용한다.

## V 모델과 일정

| 사용자 목표일 | 설계·개발 산출물 | 맞물리는 검증 |
|---|---|---|
| 11월 25일 | 도메인, 사용자, 재료 등록부터 섭취까지의 주 시나리오 | 빈 재고와 재고 보유자의 수용 시나리오 |
| 12월 4일 | 기획서, 요구사항 추적표, 외부 데이터 계약과 평가 지표 | 기준선·정답셋·누락값 처리 검토 |
| 12월 17일 | 시스템·아키텍처, ERD, 클래스·시퀀스, API와 앱 | 모델 단위 → SQLite·API 통합 → 화면 흐름 검증 |
| 12월 21일 | 실제 운영 서버·실기기 검증·Play 배포 목표 | 발급키, 권한, 후보 실패·재계획, 복구 및 삭제 확인 |
| 12월 23일 | 발표자료와 시연 | 등록→조리→섭취 흐름, 평가 전후, 운영상 미검증 항목 설명 |

일정은 사용자가 지정한 2026년 목표일이다. 실제 운영 배포일과 심사 완료일은 운영 계정 확인 후 기록한다.

## 메인 Agent 실행 그래프 (명세서 4.2)

`python workflow.py` 로 LangGraph 구조를 출력한다.

~~~mermaid
graph TD
  S([시작]) --> A[분석: 조건을 기준·선호·제약으로 정리]
  A --> P[계획: 규칙 핵심 작업 + 모델 보조 도구 Plan]
  P -. 작업 있음 .-> X[실행: Worker, 도구 호출]
  P -. 작업 없음 · 도구 불필요 .-> V[검증: 로깅 Agent 이벤트로 이상 징후]
  X --> J[판정: 재고·기한·부족 g·시간, 코드]
  J -. 다음 후보 · 재계획 최대 3회 .-> X
  J -. 완료 .-> V
  V --> R[응답: 확인된 값만으로 문장]
  R --> E([끝])
~~~

| 노드 | 입력 | 출력 | 모델 사용 |
| --- | --- | --- | --- |
| 분석 | 해석한 조건 | `conditions` 이벤트(기준·선호·제약, 도구 필요 여부) | 해석 단계에서만(키가 있을 때). 요청에 없던 조건은 채우지 않음 |
| 계획 | 명령·조건·재고 | Task 목록 | 자연어 요청이면 보조 도구 선택(Plan), 등록된 도구만 통과 |
| 실행 | Task | 도구 결과(ok/error/source) | 결과 없음일 때 Worker 가 인자 보정 1회 |
| 판정 | 도구 결과·재고 | 다음 Task 또는 완료 | 사용 안 함 |
| 검증 | 실행 이벤트 | 정상·이상·판정 불가 | 이상일 때만 원인 진단 |
| 응답 | 판정 결과 | 화면 결과 + 답변 문장 | 문장 생성만 |

## 그래프 밖에서 이어지는 기능

- **자동 진행**(`autopilot.py`): 상황 문장이면 그래프 결과 뒤에 후보 3개 · 메뉴 확정 · 부족 재료 담기 · 영상 찾기 · 조리 모드 준비를 실행하고, 실행한 일과 되돌리기 명령을 응답에 싣는다. 모델은 허용된 작업과 인분만 고른다.
- **조리 모드**(`cook_guide.py`, `media.py`, `video_guide.py`): 단계 카드, 사진 움직임, YouTube 챕터 매칭, Instagram 임베드.
- **사진 기록**(`photos.py`): 후보만 만들고 사용자가 확인해야 기록된다.
- **알림**(`reminders.py`): 물은 목표 진도, 영양제는 복용 여부로 보낼지 판정한다. 웹은 화면이 열려 있을 때, Android 는 AlarmManager 로 앱이 꺼져 있어도 알린다.
