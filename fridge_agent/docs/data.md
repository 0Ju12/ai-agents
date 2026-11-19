# 데이터와 외부 연동

## 도메인 데이터

| 자료 | 저장 방법과 표시 기준 |
|---|---|
| USDA SR Legacy | 공개 CSV ZIP의 25개 FDC ID를 골라 100g당 열량, 단백질, 탄수화물, 지방, 식이섬유, 나트륨을 가져왔다. 한국어 재료별 영문 기준 식품과 ID를 보관한다. 같은 재료라도 품종·수분·가공 상태에 따라 다르다. |
| 한끼 레시피 | 1인분 재료 g, 예상 분, 순서를 작성한 기본 메뉴 16개. 재료 원문과 기준 인분이 불명확한 외부 메뉴는 자동 계량하지 않는다. 국내 검색 결과의 원문을 확인한 사용자가 분량과 시간을 지정하면 개인 레시피 DB에 저장한다. |
| wger | 공개 API에서 운동 참조 8개를 가져왔다. 원문명·기구·근육·원문 링크·저자·각 항목의 라이선스를 유지했다. 한국어 루틴과 난이도 규칙은 별도로 작성했다. |
| 생활 기록 | 사용자 입력과 동의한 Health Connect 오늘 합계를 분리 저장한다. 기록 전 값은 미확인으로 표시한다. 같은 날 기기 값은 대체하며 수기 값과 합산하지 않는다. |
| 시각 자료 | 식탁 사진은 이 프로젝트용 생성 이미지다. 상품·사용자 냉장고 실사진으로 사용하지 않는다. 아이콘은 Lucide ISC/MIT 라이선스이며 static/lucide-LICENSE.txt에 포함했다. |

USDA ZIP을 받아 `python assets/import_usda.py <zip경로>`로 재생성할 수 있다. `python assets/import_wger.py`는 참조 운동을 다시 가져온다. 앱을 처음 실행하면 JSON을 SQLite 카탈로그에 적재한다. 한국 식품 검색 결과는 별도 테이블에 24시간 캐시한다. [USDA 원본 자료](https://fdc.nal.usda.gov/download-datasets/) · [wger API](https://wger.de/en/software/api) · [운동별 출처와 저자](../assets/training.json)

## 연동 설정

| 기능 | 환경 변수 | 데이터와 이용 조건 |
|---|---|---|
| 한국 조리식품 | FOODSAFETY_API_KEY | COOKRCP01 메뉴·순서·재료 원문. 식품안전나라 발급량과 제공 조건 적용. [제공처](https://www.foodsafetykorea.go.kr/api/openApiInfo.do?svc_no=COOKRCP01) |
| 한국 식품영양 | DATA_GO_KR_SERVICE_KEY | 식약처 식품영양성분DB정보02. 기준량과 단위를 함께 표시한다. 포털 활용신청·허용 트래픽 적용. [제공처](https://www.data.go.kr/) |
| 해외 후보와 상세 | MEALDB_API_KEY | 교육용 키 1로 검증했다. 앱스토어 공개 시 지원자 키와 배포 조건을 적용한다. [이용 조건](https://www.themealdb.com/api.php) |
| 제품 바코드 | 없음 | Open Food Facts의 사용자 기여 자료. ODbL 등 라이선스와 엔드포인트별 호출 한도 적용. [제공처](https://openfoodfacts.github.io/openfoodfacts-server/api/) |
| 식품 영양 원자료 | USDA_API_KEY | 개발용 DEMO_KEY 또는 본인 키. 영문명·FDC ID로 USDA 원본을 확인할 수 있다. [제공처](https://fdc.nal.usda.gov/api-guide/) |
| 운동 원자료 | 없음 | wger의 운동별 Creative Commons 조건. [제공처](https://wger.de/api/v2/) |
| 네이버 쇼핑 | NAVER_CLIENT_ID, NAVER_CLIENT_SECRET | 상품명·몰·표시 최저가·상품 링크. 제공 결과의 포장 표기가 명확할 때만 100g 가격을 계산한다. [개발 문서](https://developers.naver.com/docs/serviceapi/search/shopping/shopping.md) |
| 쿠팡 파트너스 | COUPANG_ACCESS_KEY, COUPANG_SECRET_KEY | 승인된 파트너스 상품 검색과 제휴 표시. 실결제·배송료는 판매처에서 확인한다. [제공처](https://partners.coupang.com/) |
| 유튜브 | YOUTUBE_API_KEY | 최근 30일 후보의 게시 시각과 조회수를 확인해 일평균 조회수로 정렬한다. 검색 표본과 쿼터를 반영한다. [문서](https://developers.google.com/youtube/v3/docs/search/list) |
| 인스타그램 | IG_USER_ID, IG_ACCESS_TOKEN, META_GRAPH_VERSION | 권한 있는 비즈니스 계정의 해시태그 최근 미디어를 공개 반응 수로 정렬한다. 공개 지표가 없으면 미확인이다. 계정 승인·해시태그 수 제한을 적용한다. [문서](https://developers.facebook.com/docs/instagram-platform/) |
| 헬스장 | KAKAO_REST_API_KEY | 지역·역 키워드로 장소명과 도로명 주소·지도 링크를 조회한다. [문서](https://developers.kakao.com/docs/latest/ko/local/dev-guide) |
| GMS | GMS_KEY, GMS_BASE_URL, GMS_MODEL | 서버에서만 사용한다. 교육 계정에 허용된 채팅 모델을 지정한다. |
| 캘린더 | GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI | Google의 웹 OAuth 앱에 정확히 같은 callback URL을 등록한다. scope는 calendar.events다. 사용자가 승인하면 로컬 대신 자신의 Google 기본 캘린더를 쓴다. [문서](https://developers.google.com/workspace/calendar/api/guides/overview) |

보유 키가 없는 쇼핑·영상·지도 화면은 직접 검색을 제공한다. 검색 링크 자체를 확인된 상품이나 인기 콘텐츠로 집계하지 않는다. 공개 API의 응답과 지연 시간은 시점별로 달라진다. [실제 호출 기록](evidence/live-apis.json)

## 기획 참고

잔여 재료 우선 활용과 단계별 조리 안내가 식재료 등록에서 조리 완료까지 이어지도록 구성했다. 운동 화면은 부위·숙련도 선택과 운동 후 피드백을 반영한다. [오늘의 스토리](https://picks.my/ko_v2s/s/detail/36808/content.html) · [냉픽](https://frescioai.com/) · [플랜핏](https://planfit.ai/)
