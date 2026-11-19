package io.github.oju12.hankki;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceError;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.*;
import java.util.Set;
import org.json.JSONObject;

public class MainActivity extends Activity {
    private WebView web;
    private String origin;
    private static final int READ_HEALTH = 42;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        origin = getPreferences(MODE_PRIVATE).getString("origin", BuildConfig.DEFAULT_ORIGIN);
        if (origin.isEmpty()) setup(); else openHome();
    }

    private void setup() {
        if (web != null) { web.destroy(); web = null; }
        LinearLayout panel = new LinearLayout(this);
        panel.setOrientation(LinearLayout.VERTICAL);
        int pad = (int)(26 * getResources().getDisplayMetrics().density);
        panel.setPadding(pad, pad * 3, pad, pad);
        panel.setBackgroundColor(0xfff7f6ef);
        TextView title = new TextView(this);
        title.setText("냉장고 한 끼"); title.setTextSize(32);
        title.setTextColor(0xff234932); panel.addView(title);
        TextView help = new TextView(this);
        help.setText("사용할 한 끼 서버의 HTTPS 주소를 입력하세요. 이 주소에 식단과 생활 기록을 보관합니다.");
        panel.addView(help);
        EditText address = new EditText(this);
        address.setSingleLine(); address.setHint("https://");
        address.setText(origin.isEmpty() && BuildConfig.DEBUG ? "http://127.0.0.1:8000" : origin);
        panel.addView(address);
        Button connect = new Button(this); connect.setText("연결하기"); panel.addView(connect);
        connect.setOnClickListener(v -> {
            Uri u = Uri.parse(address.getText().toString().trim()).normalizeScheme();
            boolean debugLocal = BuildConfig.DEBUG && "http".equals(u.getScheme()) &&
                    java.util.Arrays.asList("10.0.2.2","127.0.0.1","localhost").contains(u.getHost());
            if (u.getHost()==null || u.getUserInfo()!=null || u.getQuery()!=null || u.getFragment()!=null ||
                    (!u.getPath().isEmpty() && !"/".equals(u.getPath())) || (!"https".equals(u.getScheme()) && !debugLocal)) {
                address.setError("HTTPS 서버 주소를 확인하세요."); return;
            }
            origin = u.getScheme()+"://"+u.getEncodedAuthority();
            getPreferences(MODE_PRIVATE).edit().putString("origin",origin).apply();
            openHome();
        });
        setContentView(panel);
    }

    private boolean sameOrigin(Uri uri) {
        if (uri==null) return false;
        Uri trusted=Uri.parse(origin);
        return trusted.getScheme().equals(uri.getScheme()) && trusted.getEncodedAuthority().equals(uri.getEncodedAuthority());
    }

    private void openHome() {
        web=new WebView(this);
        web.getSettings().setJavaScriptEnabled(true);
        web.getSettings().setDomStorageEnabled(true);
        web.getSettings().setAllowFileAccess(false);
        web.getSettings().setAllowContentAccess(false);
        web.getSettings().setMixedContentMode(android.webkit.WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web,false);
        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest req) {
                Uri target=req.getUrl();
                if (sameOrigin(target)) return false;
                if (!req.isForMainFrame() || !req.hasGesture()) return true;
                if ("hankki".equals(target.getScheme()) && sameOrigin(Uri.parse(view.getUrl()))) {
                    if ("health".equals(target.getHost())) startHealth();
                    if ("settings".equals(target.getHost())) setup();
                } else if ("https".equals(target.getScheme())) {
                    try {startActivity(new Intent(Intent.ACTION_VIEW,target));}
                    catch(ActivityNotFoundException e){show("링크를 열 브라우저가 없습니다.");}
                }
                return true;
            }
            @Override public void onReceivedError(WebView view,WebResourceRequest req,WebResourceError error) {
                if(req.isForMainFrame()) new AlertDialog.Builder(MainActivity.this).setMessage("서버 연결을 확인하세요.")
                        .setPositiveButton("재시도",(d,w)->view.reload())
                        .setNegativeButton("서버 설정",(d,w)->setup()).show();
            }
        });
        web.setOnApplyWindowInsetsListener((v,insets)->{
            if(Build.VERSION.SDK_INT>=30) {
                android.graphics.Insets bars=insets.getInsets(android.view.WindowInsets.Type.systemBars() | android.view.WindowInsets.Type.displayCutout());
                v.setPadding(bars.left,bars.top,bars.right,bars.bottom);
            }
            return insets;
        });
        setContentView(web); web.loadUrl(origin);
    }

    private void show(String message) {Toast.makeText(this,message,Toast.LENGTH_LONG).show();}
    private void startHealth() {
        if(Build.VERSION.SDK_INT<34) {show("이 앱의 Health Connect 가져오기는 Android 14 이상에서 지원합니다. 생활 기록은 직접 입력할 수 있습니다.");return;}
        new AlertDialog.Builder(this).setTitle("오늘의 건강 기록 읽기")
            .setMessage("Health Connect에서 물·수면·섭취 영양·운동 시간의 오늘 합계를 읽습니다. 다음 화면에서 전송할 값을 미리 확인합니다.")
            .setNegativeButton("취소",null)
            .setPositiveButton("권한 확인",(d,w)->requestPermissions(HealthReader.PERMISSIONS,READ_HEALTH)).show();
    }

    @Override public void onRequestPermissionsResult(int code,String[] permissions,int[] results) {
        super.onRequestPermissionsResult(code,permissions,results);
        if (code!=READ_HEALTH || Build.VERSION.SDK_INT<34 || web==null) return;
        final String requestedOrigin=origin;
        HealthReader.read(this, data->{
            if(isFinishing() || web==null || !origin.equals(requestedOrigin) || !sameOrigin(Uri.parse(web.getUrl())))return;
            if(data.length()<=1){show("읽을 수 있는 오늘의 기록이 없습니다. 권한과 원본 앱의 동기화를 확인하세요.");return;}
            new AlertDialog.Builder(this).setTitle("가져올 기록 확인")
                .setMessage(HealthReader.describe(data)+"\n\n저장할 서버: "+origin)
                .setNegativeButton("취소",null)
                .setPositiveButton("이 서버에 저장",(d,w)->{
                    if(web!=null && origin.equals(requestedOrigin) && sameOrigin(Uri.parse(web.getUrl())))
                        web.evaluateJavascript("window.importHealth("+data.toString()+")",null);
                }).show();
        });
    }
    @Override public void onBackPressed(){if(web!=null && web.canGoBack()) web.goBack(); else super.onBackPressed();}
}
