# 한끼 Android

Android 8(API 26) 이상에서 HTTPS 서버에 연결합니다. 앱 안에서 재료를 등록하고 식사와 운동을 기록합니다. Android 14(API 34) 이상에서 Health Connect 권한을 선택하면 물·수면·단백질·열량·운동시간 중 허용한 오늘의 합계를 미리 본 뒤 서버에 보낼 수 있습니다. 서울 시간대를 사용합니다. 사용자가 같은 날짜를 다시 가져오면 최신 합계로 대체합니다.

## 빌드

JDK 17과 Android SDK 플랫폼 36, Build Tools 35.0.0을 설치하고 android 폴더에서 실행하세요.

~~~bash
./gradlew assembleDebug bundleRelease
~~~

에뮬레이터의 개발 서버는 디버그 앱에서만 http://10.0.2.2:8000 을 사용할 수 있습니다. 실제 연결할 호스트는 첫 실행 시 지정합니다. 운영 서버를 지정하려면 빌드 시 `-PhankkiOrigin=https://your-domain.example` 를 전달하세요. 서버 설정은 앱의 기록 화면에서 변경할 수 있습니다. 같은 휴대폰에서 서버를 실행하지 않는 한 휴대폰의 localhost는 PC를 가리키지 않습니다.

## Play 배포

1. 실제 HTTPS 서버를 배포하고 접근 가능한 개인정보 처리방침, 운영자 연락처와 보관 정책을 등록합니다.
2. 본인 소유 Play Console 계정에서 앱 ID `io.github.oju12.hankki`를 확인합니다. 건강 앱 선언, 데이터 보안, Health Connect 이용 목적 및 권한 범위를 작성합니다. 표시는 Android 앱에서 실제로 전송하는 필드와 일치해야 합니다.
3. 서버 외부의 보안 저장소에서 업로드 키를 준비하고 `HANKKI_KEYSTORE` (절대 경로), `HANKKI_STORE_PASSWORD`, `HANKKI_KEY_ALIAS`, `HANKKI_KEY_PASSWORD`를 설정합니다. 버전 코드와 표시명을 확인하고 bundleRelease를 다시 실행합니다.
4. 내부 테스트 트랙에서 로그인·동의·부분 권한·권한 철회·기기 재연결과 데이터 삭제를 검사합니다. Samsung Health 또는 Google Fit이 Health Connect에 쓰는 데이터 종류는 기기와 원본 앱 설정에 따라 다릅니다.
5. 최종 서명한 `app/build/outputs/bundle/release/app-release.aab`를 업로드합니다. 심사 및 계정별 테스트 요건은 Play Console에서 확인합니다.

테스트 APK와 미서명 AAB는 [빌드 산출물](artifacts)에서 받을 수 있습니다. 디버그 APK는 소유자의 Play 업로드 키와 별개인 디버그 서명을 사용합니다. 실기기의 권한 및 동기화 상태는 사용자 기기로 검증할 항목입니다.

[Health Connect 개발 문서](https://developer.android.com/health-and-fitness/guides/health-connect) · [Google Play 건강 앱 정책](https://support.google.com/googleplay/android-developer/answer/14738291)
