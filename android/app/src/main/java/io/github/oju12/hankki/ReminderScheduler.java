package io.github.oju12.hankki;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import java.util.Calendar;
import org.json.JSONArray;
import org.json.JSONObject;

/** 서버의 /api/reminders 일정으로 하루 반복 알림을 예약한다 (앱이 꺼져 있어도 울린다). */
final class ReminderScheduler {
    static final String PREFS = "reminders";
    private ReminderScheduler() {}

    static void save(Context c, String origin, String json) {
        c.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putString("items", json).putString("origin", origin).apply();
    }

    /** 저장된 일정으로 다시 예약한다. 예전 예약은 모두 취소한다. */
    static void rescheduleAll(Context c) {
        SharedPreferences p = c.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        AlarmManager am = c.getSystemService(AlarmManager.class);
        JSONArray old;
        try { old = new JSONArray(p.getString("codes", "[]")); } catch (Exception e) { old = new JSONArray(); }
        for (int i = 0; i < old.length(); i++) {
            PendingIntent pi = PendingIntent.getBroadcast(c, old.optInt(i), new Intent(c, ReminderReceiver.class),
                    PendingIntent.FLAG_NO_CREATE | PendingIntent.FLAG_IMMUTABLE);
            if (pi != null) { am.cancel(pi); pi.cancel(); }
        }
        JSONArray codes = new JSONArray();
        try {
            JSONArray items = new JSONArray(p.getString("items", "[]"));
            for (int i = 0; i < items.length() && i < 20; i++) {
                JSONObject r = items.getJSONObject(i);
                if (!r.optBoolean("enabled", true)) continue;
                JSONArray slots = r.getJSONArray("slots");
                for (int j = 0; j < slots.length() && j < 30; j++) {
                    String slot = slots.getString(j);
                    int code = (r.getString("id") + slot).hashCode();
                    arm(c, code, r.getString("id"), r.optString("kind"), r.optString("title"), slot);
                    codes.put(code);
                }
            }
        } catch (Exception ignored) { }
        p.edit().putString("codes", codes.toString()).apply();
    }

    /** slot(HH:MM) 의 다음 시각에 한 번 울리도록 예약한다. 울린 뒤 수신기가 다음 날로 다시 예약한다. */
    static void arm(Context c, int code, String id, String kind, String title, String slot) {
        String[] hm = slot.split(":");
        Calendar t = Calendar.getInstance();
        t.set(Calendar.HOUR_OF_DAY, Integer.parseInt(hm[0]));
        t.set(Calendar.MINUTE, Integer.parseInt(hm[1]));
        t.set(Calendar.SECOND, 0);
        t.set(Calendar.MILLISECOND, 0);
        if (t.getTimeInMillis() <= System.currentTimeMillis() + 30_000) t.add(Calendar.DAY_OF_YEAR, 1);
        Intent i = new Intent(c, ReminderReceiver.class)
                .putExtra("code", code).putExtra("id", id).putExtra("kind", kind).putExtra("title", title).putExtra("slot", slot);
        PendingIntent pi = PendingIntent.getBroadcast(c, code, i, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        // 정확한 알람 권한 없이 쓰는 방식: 절전 중에도 울리되 몇 분 늦을 수 있다.
        c.getSystemService(AlarmManager.class).setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, t.getTimeInMillis(), pi);
    }
}
