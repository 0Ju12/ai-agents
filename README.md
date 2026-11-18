# 종합 여행 플래너 Agent

국보·보물, 관광지, 음식점, 카페를 한 일정에 묶고, 사용자가 고른 이동 수단으로 **어디서 무엇을 타고 몇 시에 도착하는지**까지 안내하는 LangGraph Agent 입니다. 장소마다 YouTube 영상과 Instagram 해시태그를 붙이고, 국가유산 해설은 2회차 국보 RAG([heritage-rag-guide](https://github.com/0Ju12/heritage-rag-guide))를 Tool 로 재사용합니다.

> SSAFY AI 코어 프로젝트 3회차 (개인). 현재는 **뼈대 단계**입니다 — 공통 계층과 테스트는 동작하고, 외부 API 응답 매핑과 LLM 연결은 1~2일차에 채웁니다.

```
나  : 토요일 서울에서 KTX로 경주 당일치기. 국보 2곳, 관광지 1곳, 점심은 한식, 오후에 카페, 밤 9시 전 서울 도착.
Agent: 08:00 서울역 KTX → 10:05 신경주
       10:55 석굴암 · 12:10 불국사 · 13:00 점심 · 14:00 황리단길 · 15:30 카페
       18:30 신경주 KTX → 20:40 서울   (곳당 최대 체류시간 역산, 제외한 장소와 사유 표시)
```
(예시 화면이며 실제 시각은 API 로 확인합니다.)

## 구조

```
backend/
  config.py            키는 .env 에서만 읽음 (NF3001)
  tools/               Tool 11개 + 공통 계약(base.py) + 외부 호출(http.py)
  domain/              통합 장소 형식(place.py) · 판정 엔진(constraints.py, 코드로 판정)
  agent/               LangGraph 상태·노드·그래프·실행기
  events/bus.py        실행 이벤트 발행 (구독자에 의존하지 않음)
  logging_agent/       이벤트 구독 → 실행 로그 저장 (LLM 미사용)
  store/db.py          SQLite: 여행 계획 · 실행 로그 (로그 수정 함수 없음)
  api/                 FastAPI: /api/chat · /api/plans · /api/logs · /api/status
frontend/index.html    대화 화면 + 계획 관리 화면
docs/                  요구사항 정의서 · Agent 설계 · Tool 정의서(자동 생성)
tests/                 외부 API 없이 도는 테스트
```

## 실행

```bash
python -m venv .venv
```
```bash
source .venv/bin/activate
```
```bash
pip install -r requirements-dev.txt
```
```bash
cp .env.example .env
```
```bash
uvicorn backend.api.main:app --reload
```
http://localhost:8000 에서 화면을 엽니다. 키가 없어도 서버는 뜨고, 화면 상단에 설정되지 않은 키가 표시됩니다.

```bash
python -m pytest
```
```bash
python scripts/gen_tool_spec.py
```
```bash
python -m backend.agent.graph
```
(테스트 / Tool 정의서 생성 / 그래프 구조 출력)

## API 키 발급

| 키 | 어디서 | 쓰는 곳 |
| --- | --- | --- |
| `DATA_GO_KR_SERVICE_KEY` | 공공데이터포털 회원가입 후 API 마다 활용신청 | TourAPI, TAGO, 기상청, 특일, 관광지 집중률 |
| `KAKAO_REST_API_KEY` | Kakao Developers 앱 생성 | 카카오 로컬(카페·음식점), 모빌리티 길찾기 |
| `YOUTUBE_API_KEY` | Google Cloud 프로젝트에서 YouTube Data API v3 사용 설정 | 장소별 영상 |
| `ODSAY_API_KEY` (선택) | ODsay LAB | 현지 대중교통 상세 |
| `OPENAI_API_KEY` | OpenAI | LLM |

## 사용한 외부 API (출처와 이용 조건, NF3007)

| API | 제공 | 이용 조건 · 한도 |
| --- | --- | --- |
| [국가유산 검색 오픈API](https://www.khs.go.kr) | 국가유산청 | 키 불필요 |
| [국문 관광정보 서비스](https://www.data.go.kr/data/15101578/openapi.do) | 한국관광공사 | 공공데이터포털 이용허락범위 |
| [TAGO 고속버스](https://www.data.go.kr/data/15098522/openapi.do) · [시외버스](https://www.data.go.kr/data/15098541/openapi.do) · [열차](https://www.data.go.kr/data/15098552/openapi.do) | 국토교통부 | 잔여석 정보 없음 |
| [단기예보](https://www.data.go.kr/data/15084084/openapi.do) · [중기예보](https://www.data.go.kr/data/15059468/openapi.do) | 기상청 | |
| [특일 정보](https://www.data.go.kr/data/15012690/openapi.do) | 한국천문연구원 | |
| [관광지 집중률 예측](https://www.data.go.kr/data/15128555/openapi.do) | 한국관광공사 | |
| [카카오 로컬](https://developers.kakao.com/docs/latest/ko/local/dev-guide) · [카카오모빌리티](https://developers.kakaomobility.com) | 카카오 | 영업시간·평점 미제공 |
| [YouTube Data API v3](https://developers.google.com/youtube/v3/determine_quota_cost) | Google | 하루 10,000 단위, 검색 1회 100 단위 → 캐시 사용 |
| Instagram | Meta | 3회차는 해시태그 탐색 링크만(수집 안 함). Graph API 는 비즈니스 계정·앱 등록·7일 30개 해시태그 제한 |

영상과 해시태그는 참고 콘텐츠이며, 운영시간·관람시간 같은 판단 근거는 공공 API 값만 씁니다.

## 진행 상황

[docs/requirements.md](docs/requirements.md) 의 상태 열을 보세요. 1일차 할 일:

- [ ] 공공데이터포털 활용신청 후 TourAPI 경로·소개정보 필드, TAGO 기능명·응답 필드 확인
- [ ] 카카오·YouTube 키로 실제 호출 확인
- [ ] 16시 전 도메인 확정 (명세서 1.2절)
