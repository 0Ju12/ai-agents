# 한끼 실행·시연·스크린샷 가이드

2026-11-20에 코드 버전 `0d242a3`으로 전체 테스트 100건 통과, 실계정 4건 건너뜀을 확인했다. 임시 DB로 Chromium을 새로 열어 모바일 너비 390px와 데스크톱 너비 1440px에서 시연 흐름을 실행하고 화면 12장을 촬영했다. 아래 실기기·외부 계정 항목은 별도 실측 대상이다. [스크린샷 12장과 테스트 결과 ZIP](evidence/demo-screens.zip)

## 1. 처음 실행하기

Git과 Python 3.12를 설치한다. 저장소가 이미 있으면 해당 폴더에서 시작한다. 처음이면 다음을 실행한다.

```sh
git clone https://github.com/0Ju12/ai-agents.git
cd ai-agents
```

**Windows PowerShell**에서 저장소 루트를 열고 실행한다. 가상환경을 직접 호출하므로 활성화 정책 변경이 필요 없다.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip install tzdata
$env:FRIDGE_DEMO = "0"
$env:FRIDGE_DATA_DIR = Join-Path $env:TEMP ("hankki-demo-" + [guid]::NewGuid())
.\.venv\Scripts\python.exe fridge_agent/app.py
```

**macOS·Linux**에서는 다음을 실행한다.

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
export FRIDGE_DEMO=0
export FRIDGE_DATA_DIR="$(mktemp -d)"
python fridge_agent/app.py
```

서버 터미널을 열어 둔 채 브라우저에서 [한끼](http://127.0.0.1:8000)를 연다. 첫 안내가 보이면 닫는다. 이 명령은 예시 재료가 없는 새 시연 공간을 만든다. 이어서 촬영할 때는 같은 서버를 사용한다. 시연 후 서버는 Ctrl+C로 종료한다. 데모 재고 21종으로 자연어 추천을 시연하려면 별도 시연 공간에서 냉장고의 **예시 재료로 채우기**를 누른다.

GMS와 식품·영상 API를 시험할 때는 `fridge_agent/.env.example`을 같은 폴더의 `.env`로 복사하고 발급받은 값과 허용된 모델명을 입력한 뒤 서버를 다시 켠다. 환경변수로 직접 지정해도 된다. API 키, 토큰, 개인 건강 기록이 보이는 설정 화면은 제출 캡처에서 제외한다.

## 2. 화면별 시연 순서

빈 냉장고에서 ①~④를 순서대로 진행하면 아래 수량을 그대로 비교할 수 있다. 파일명은 ZIP 안의 실제 화면이다. 직접 촬영 항목은 해당 기기에서 결과가 보이는 순간에 촬영한다.

| 기능 | 조작 | 합격 기준과 촬영 시점 |
|---|---|---|
| ① 시작 | 모바일 너비로 오늘 탭을 열고 데스크톱 너비에서도 다시 열기 | 제목과 하단 또는 측면 메뉴가 보인다. 첫 화면은 today-mobile.webp, 데스크톱 예시는 today-desktop.webp |
| ② 냉장고 | 재료 추가 → 두부 300g, 달걀 3개를 각각 입력하고 서로 다른 미래 소비기한을 지정 → 냉장고에 넣기 | 냉장고 목록에서 이름·남은 양·기한이 보인다. 분량을 입력하지 않은 재료도 따로 추가해 분량 확인 상태를 확인한다. pantry-mobile.webp |
| ③ 추천과 영양 | 식단 확인 → 두부 달걀찜의 1인분 재료 보기 | 두부 100g·달걀 50g과 메뉴를 함께 찍는다. 기준 영양은 약 148kcal·단백질 14.4g이다. meal-mobile.webp |
| ④ 조리·섭취 | 조리 기록 → 만든 분량 2, 실제 조리시간 14 → 조리 완료 → 1인분 섭취 | 두부는 100g, 달걀은 약 50g 남고 만든 음식은 1인분 남는다. 섭취는 1인분만 하루 합계에 반영된다. 냉장고와 기록의 변경 후 모습을 나란히 찍는다. |
| ⑤ 장보기 | 레시피에서 김치볶음밥 선택 → 부족분 장바구니에 담기 → 장바구니에 담기 → 냉장고 | 부족한 품목과 구입 후 입고 버튼이 보인다. 한 품목을 실제 입고 처리한 뒤 장바구니 잔량과 냉장고 증가량도 비교한다. shopping-desktop.webp |
| ⑥ 인분·찜·타이머 | 양배추를 이름만 추가 → 레시피에서 양배추 두부덮밥 찜 → 새로고침 후 찜한 레시피 → 조리 모드 → 2인분 → 분량 입력 140g | 필요량 200g과 부족량 60g이 한 화면에 보인다. 부족분 담기 후 장바구니도 60g이어야 한다. 타이머는 사과 아몬드 오트죽 3단계에서 시작 → 종료 → 다시 시작 시 06:00을 확인한다. recipe-portions-mobile.webp |
| ⑦ 코치 역할 | 코치에 차례로 ‘안녕’, ‘어깨 운동 30분 하고 싶어’, ‘두부로 저녁 추천해줘’ 입력 | 각각 로봇 AI, 흰 셔츠 트레이너, 자주색 재킷 셰프가 답한다. 질문과 답변자를 함께 찍는다. coach-mobile.webp, trainer-mobile.webp, chef-mobile.webp |
| ⑧ 운동 | 운동 탭에서 부위·숙련도·가용 시간을 변경하고 운동 모드 열기 | 선택 조건과 동작·세트·휴식이 함께 보이는 화면을 찍는다. 내 루틴 저장 후 다시 열어 같은 동작인지 확인한다. workout-mobile.webp는 운동 탭 예시다. |
| ⑨ 생활 기록 | 기록 → 물 더하기 또는 코치에 ‘물 250’, ‘수면 7.5’ → 새로고침 | 물이 직전보다 250mL 증가하고 수면이 해당 날짜에 기록된다. 조리한 식사의 단백질과 함께 하루 합계를 찍는다. journal-mobile.webp |
| ⑩ 일정·충돌 | 기록 → 계획과 일정 → 같은 날짜에 18:15~19:00 일정 저장 → 18:20~18:40 일정 추가 | 두 번째 일정의 겹침 안내를 찍는다. 시간을 바꿔 겹침이 사라지는지 확인하고 테스트용 일정만 삭제한다. |
| ⑪ 도구·실행 로그 | 코치에 ‘레시피 두부구이’ → 결과 자세히 보기 → 이번 실행 과정. 이어서 /docs에서 GET /api/tools 및 GET /api/logs 실행 | 어떤 도구를 왜 호출했고 결과나 오류가 무엇인지 확인한다. 키가 없으면 키 누락 상태가 기대 결과다. trace-mobile.webp |
| ⑫ 추천 이유·출처·개인화 | 예시 재고로 ‘20분 안에 단백질 위주로 먹고 싶어’ → ‘다른 추천후보 알려줘’. 이어서 ‘단백질 하루 권장량이 얼마야?’ | 후보의 시간·재고·영양 근거와 후속 후보를 비교한다. 지식 질문은 답과 근거 문서·출처를 함께 찍는다. 식단 제한 설정 후에는 제한에 맞는 후보만 남는지 확인한다. |

## 3. 외부 기능과 실기기 촬영

| 항목 | 확인 방법 | 통과로 기록할 증거 |
|---|---|---|
| 국내 레시피·영양 | 식품안전나라 및 식품영양성분 키 설정 후 ‘레시피 달걀찜’, ‘식품영양 두부’ | 제공처 이름과 실제 조리 순서 또는 기준량·영양 수치 |
| 장보기·레시피 영상·헬스장 | 해당 키로 ‘쇼핑 두부’, ‘영상 두부구이’, ‘헬스장 강남역’ 실행 | 네이버·쿠팡 상품, YouTube·Instagram 게시물, 카카오 장소를 제공처별로 확인한다. 검색 링크만 보이면 ‘검색 이동 확인’으로 기록한다. |
| GMS 모델 | ‘김치찌개 먹고 싶은데 뭐 사야 해?’ 실행 후 실행 과정 펼치기 | 모델 계획, 재료 조회 결과, 부족 재료, 마지막 답변을 함께 확인한다. 모델 경로와 규칙 경로는 로그로 구분한다. |
| 사진·바코드 | 식사 사진을 올리고 후보·분량을 수정한 뒤 저장. 알려진 식품 바코드 조회 | 인식 후보와 사용자 확인 후 식사 기록, 바코드 제품명과 영양 출처를 각각 촬영한다. 사진 실측에는 비전 지원 모델이 필요하다. |
| Google Calendar | 테스트 계정 연결 → 저장한 계획을 일정에 등록 → 앱에서 재조회 | Google Calendar와 앱 양쪽에 같은 날짜·시작·종료 시간이 보인다. 로컬 일정 캡처와 따로 보관한다. |
| Android·헬스·알림 | Android 14 이상 실기기에서 HTTPS 서버에 연결 → Health Connect에서 일부 권한 허용 → 오늘 합계 가져오기. 물·영양제 알림을 곧 도달할 시각으로 등록 | 동기화 전후 값과 출처, 같은 날 재동기화해도 중복되지 않는 합계, 실제 알림 수신을 찍는다. 삼성/Google 원본 앱이 Health Connect에 기록한 데이터가 필요하다. |
| 배포 | 테스트 APK 설치와 Play 배포를 각각 확인 | 설치는 앱 실행 화면, Play 배포는 실제 트랙·배포 상태가 보이는 Play Console 화면으로 확인한다. |

## 4. 스크린샷과 테스트 결과를 다시 만들기

저장소 루트의 새 터미널에서 같은 가상환경을 사용한다. 아래 `python`은 Windows에서 `.\.venv\Scripts\python.exe`로 바꾸면 된다. Linux·macOS는 먼저 `source .venv/bin/activate`를 실행한다.

```sh
python -m pytest -rs --junitxml=hankki-tests.xml
python -m pip install playwright pillow
python -m playwright install chromium
python fridge_agent/system_check.py --screens my-screens
```

Linux에 시스템 Chromium이 이미 있으면 마지막 명령에 `--chromium /usr/bin/chromium`을 붙일 수 있다. 자동 촬영은 자체 임시 서버·DB를 사용한다. 완료 기준은 터미널의 PASS와 출력 폴더의 WebP 14장이다. 캡처를 열어 글자, 재료 수량, 답변 주체가 읽히는지 확인한다.

화면에서 재현이 어려운 ‘같은 도구 연속 실패’와 ‘재계획 3회 도달’은 다음 명령의 테스트 이름과 PASSED가 함께 보이게 찍는다. 실계정 점검 4건의 실행 조건은 [2·3일차 점검표](course-check.md)에 있다.

```sh
python -m pytest -v fridge_agent/test_agent.py::test_graph_scenarios fridge_agent/test_final.py::test_consecutive_tool_failures fridge_agent/test_final.py::test_replan_warning_boundary fridge_agent/test_final.py::test_log_http_contract_and_detached_agent
```

제출할 때 각 캡처 아래에 **입력 / 기대 결과 / 관찰 결과 / 통과·실패·미확인 / 사용 환경**을 한 줄씩 적는다. 예를 들어 “양배추 140g, 2인분 선택 / 60g 부족 예상 / 화면에 60g 부족 표시 / 통과 / Chromium 모바일 너비”처럼 쓴다. 개인정보나 계정 설정이 필요한 기능에는 시험한 계정의 종류와 기기 버전만 적는다.

현재 버전에서는 [양배추 썰기](../screens/cabbage-chopping-mobile.webp)와 [날짜별 대화 관리](../screens/coach-history-mobile.webp)도 자동 촬영한다. 코치에서 이전 날짜를 선택해 문구를 수정하고 해당 날짜만 지운 뒤 오늘 대화가 유지되는지 확인한다. 전체 대화 초기화 후에는 오늘 대화도 비워지고 물 섭취량은 그대로여야 한다.
