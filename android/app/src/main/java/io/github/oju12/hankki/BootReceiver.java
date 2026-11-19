package io.github.oju12.hankki;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** 기기 재부팅·앱 업데이트 뒤 저장된 물·영양제 알림을 다시 예약한다. */
public class BootReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent intent) {
        String a = intent.getAction();
        if (Intent.ACTION_BOOT_COMPLETED.equals(a) || Intent.ACTION_MY_PACKAGE_REPLACED.equals(a))
            ReminderScheduler.rescheduleAll(context);
    }
}
