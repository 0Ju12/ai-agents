package io.github.oju12.hankki;
import android.app.Activity;
import android.os.Bundle;
import android.widget.TextView;
public class PrivacyActivity extends Activity {
    @Override public void onCreate(Bundle state){
        super.onCreate(state);TextView text=new TextView(this);text.setPadding(40,110,40,40);text.setTextSize(18);
        text.setText("냉장고 한 끼 · 건강 데이터 사용\n\nHealth Connect 접근은 선택 사항입니다. 허용한 항목의 오늘 합계만 읽습니다. 가져올 내용을 확인하고 저장을 선택한 경우에만 사용자가 설정한 한 끼 서버로 전송합니다. 앱은 Health Connect에 기록을 쓰지 않습니다.\n\nHealth Connect 설정에서 언제든 권한을 철회할 수 있습니다. 서버에 저장한 자료는 앱의 기록 탭에서 삭제할 수 있습니다.");
        setContentView(text);
    }
}
