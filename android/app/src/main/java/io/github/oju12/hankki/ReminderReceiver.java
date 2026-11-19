package io.github.oju12.hankki;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.webkit.CookieManager;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import org.json.JSONArray;
import org.json.JSONObject;

/**
 * 알림 시각에 서버(/api/reminders/due)에 물어 '지금 보낼 알림인지' 확인한다.
 * 물을 진도만큼 마셨거나 영양제를 이미 먹었으면 조용히 넘어가고, 서버에 닿지 않으면 기본 문구로 알린다.
 * 외부 앱이 알림을 흉내 내지 못하도록 exported=false 로 두고, 재부팅 처리는 BootReceiver 가 맡는다.
 */
public class ReminderReceiver extends BroadcastReceiver {
    static final String CHANNEL = "hankki-reminders";

    @Override public void onReceive(Context context, Intent intent) {
        final PendingResult pending = goAsync();
        final Context app = context.getApplicationContext();
        new Thread(() -> {
            try {
                String id = intent.getStringExtra("id"), slot = intent.getStringExtra("slot"), kind = intent.getStringExtra("kind");
                ReminderScheduler.arm(app, intent.getIntExtra("code", 0), id, kind, intent.getStringExtra("title"), slot);
                String[] text = ask(app, id, slot);
                if (text == null) text = fallback(kind, intent.getStringExtra("title"));
                if (text.length == 2) show(app, intent.getIntExtra("code", 0), text[0], text[1]);
            } finally { pending.finish(); }
        }).start();
    }

    /** 서버 판단: 보낼 알림이면 {제목, 내용}, 보낼 필요 없으면 빈 배열, 연결 실패면 null. */
    private static String[] ask(Context c, String id, String slot) {
        String origin = c.getSharedPreferences(ReminderScheduler.PREFS, Context.MODE_PRIVATE).getString("origin", "");
        if (origin.isEmpty()) return null;
        HttpURLConnection con = null;
        try {
            con = (HttpURLConnection) new URL(origin + "/api/reminders/due?now=" + slot).openConnection();
            con.setConnectTimeout(6000); con.setReadTimeout(6000);
            String cookie = CookieManager.getInstance().getCookie(origin);
            if (cookie != null) con.setRequestProperty("Cookie", cookie);
            if (con.getResponseCode() != 200) return null;
            try (InputStream in = con.getInputStream()) {
                ByteArrayOutputStream body = new ByteArrayOutputStream();
                byte[] buffer = new byte[4096];
                int count;
                while ((count = in.read(buffer)) != -1) {
                    body.write(buffer, 0, count);
                }
                JSONArray due = new JSONObject(body.toString(StandardCharsets.UTF_8.name())).getJSONArray("due");
                for (int i = 0; i < due.length(); i++) {
                    JSONObject d = due.getJSONObject(i);
                    if (id.equals(d.optString("id"))) return new String[]{d.optString("title"), d.optString("body")};
                }
                return new String[0];
            }
        } catch (Exception e) {
            return null;
        } finally { if (con != null) con.disconnect(); }
    }

    private static String[] fallback(String kind, String title) {
        return "water".equals(kind)
                ? new String[]{"물 마실 시간이에요", "한 컵 마시고 한끼에 기록해 보세요."}
                : new String[]{title + " 드실 시간이에요", "복용량은 제품 표시나 전문가 안내를 따르세요."};
    }

    private static void show(Context c, int code, String title, String body) {
        NotificationManager nm = c.getSystemService(NotificationManager.class);
        if (nm == null || !nm.areNotificationsEnabled()) return;
        nm.createNotificationChannel(new NotificationChannel(CHANNEL, "물·영양제 알림", NotificationManager.IMPORTANCE_DEFAULT));
        PendingIntent open = PendingIntent.getActivity(c, 0, new Intent(c, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP),
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Notification n = new Notification.Builder(c, CHANNEL)
                .setSmallIcon(R.drawable.sprout).setContentTitle(title).setContentText(body)
                .setStyle(new Notification.BigTextStyle().bigText(body)).setContentIntent(open).setAutoCancel(true).build();
        nm.notify(code, n);
    }
}
