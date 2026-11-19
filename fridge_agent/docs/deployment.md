# 배포와 기록 보관

## 서버

Python 3.12와 쓰기 가능한 영구 디스크가 있는 서버에서 FastAPI를 실행한다. 운영 예시는 프록시가 HTTPS 인증서를 관리하고 Docker 컨테이너의 8000 포트로 요청을 전달하는 구성이다. 요청 경로는 /, /static, /api, /privacy를 포함한다. 내부 프록시만 신뢰하도록 포워딩 헤더를 설정한다.

~~~bash
docker build -f fridge_agent/Dockerfile -t hankki:1 .
docker volume create hankki-data
docker run --name hankki --restart unless-stopped -d \
  --env-file fridge_agent/.env -e FRIDGE_MODE=server -e FRIDGE_HTTPS=1 \
  -e FRIDGE_DATA_DIR=/var/lib/hankki -v hankki-data:/var/lib/hankki \
  -p 127.0.0.1:8000:8000 hankki:1
~~~

운영 비밀은 호스트의 비공개 환경파일이나 배포 플랫폼의 Secret에 보관한다. 서버 모드는 Secure·HttpOnly 쿠키를 사용한다. HTTP로만 실행하는 로컬 데모는 `python app.py`의 local 모드로 열거나 격리 테스트에 한해 `FRIDGE_HTTPS=0`을 설정한다. 요금이 발생하는 개인 키로 공개 베타를 운영할 때는 호스팅 계층의 사용자 접근 제한과 API 쿼터를 적용한다. 보유 도메인·운영 계정과 TLS가 준비되면 해당 주소를 APK의 설정 또는 빌드 기본 URL로 지정한다.

## SQLite와 백업

food_catalog.sqlite3은 공용 검색 캐시와 출처가 있는 식품·운동 데이터다. server 모드에서 homes 아래 각 기기 디렉터리에 냉장고·하루 기록, 계획과 실행 로그, 캘린더가 나뉜다. local 모드는 FRIDGE_DATA_DIR 바로 아래에 보관한다. 같은 데이터 폴더를 여러 서버 인스턴스가 네트워크 파일시스템으로 공유하는 배포는 피한다.

개인 포트폴리오의 작은 데이터셋에는 영구 디스크와 SQLite로 충분하다. Drive는 사용자가 선택할 수 있는 비공개 백업 위치다. 동작 중인 SQLite 파일을 동기화 폴더에서 직접 열지 않는다. 운영자가 쓰기 중인 DB는 다음처럼 SQLite 백업 API로 일관된 사본을 만든 후 암호화된 비공개 백업 저장소에 보관한다.

~~~python
import sqlite3
with sqlite3.connect("fridge.sqlite3") as src, sqlite3.connect("fridge-backup.sqlite3") as dst:
    src.backup(dst)
~~~

여러 DB를 같은 시점으로 복구해야 할 때는 새 요청을 잠시 멈춘 상태에서 각 파일을 백업한다. 개인 JSON은 ‘기록 → 내 데이터’에서 내려받는다. 이 기기의 데이터 삭제는 해당 개인 공간에서만 실행된다. 쿠키를 잃으면 새 기기처럼 인식한다. 백업에 실제 건강 데이터 또는 OAuth 토큰이 있으면 접근 권한과 삭제 요청에 대응할 보관 기간을 별도로 정한다.

## Google Calendar와 2회차 색인

Google Cloud에서 Calendar API와 OAuth 웹 앱을 활성화하고 `GOOGLE_REDIRECT_URI=https://운영도메인/api/calendar/callback`을 정확히 등록한다. 계획 화면에서 연결을 누르면 승인 후 개인 저장소에 갱신 토큰이 저장된다. OAuth state와 PKCE는 한 번만 사용할 수 있다. 등록은 서버에 저장된 계획 ID 하나로 수행하고 같은 계획은 같은 이벤트 ID를 써서 중복을 막는다. 일정 조회에 실패하면 일정 충족 여부를 미확인으로 표시한다. 로컬 캘린더와 Google 일정은 서로 자동 이관되지 않는다.

`HERITAGE_RAG_DIR`를 2회차 프로젝트의 루트로 설정한다. 그 아래 `data/chroma/chroma.sqlite3`와 `heritage_docs` 컬렉션, 같은 임베딩 모델의 GMS 접근 권한이 필요하다. 국가유산 해설에 쓰는 자료는 식단 영양 근거와 분리한다. [원본 프로젝트](https://github.com/0Ju12/heritage-rag-guide)

## Play 출시

운영 URL, 운영자 개인정보 처리방침·연락처, 업로드 서명키, Play Console 계정, Android 14 이상 실기기에서의 Health Connect 검증이 남는다. 공개용 AAB는 운영자가 소유한 키로 서명한다. 이 저장소의 AAB는 미서명 빌드다. [Android 빌드 및 업로드 절차](../../android/README.md)
