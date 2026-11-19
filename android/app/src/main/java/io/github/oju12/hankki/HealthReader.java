package io.github.oju12.hankki;

import android.annotation.TargetApi;
import android.app.Activity;
import android.content.pm.PackageManager;
import android.health.connect.*;
import android.health.connect.datatypes.*;
import android.health.connect.datatypes.units.*;
import android.os.OutcomeReceiver;
import java.time.*;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;
import java.util.function.ToDoubleFunction;
import org.json.JSONObject;
import org.json.JSONException;

@TargetApi(34)
final class HealthReader {
    static final String[] PERMISSIONS={"android.permission.health.READ_HYDRATION","android.permission.health.READ_SLEEP",
        "android.permission.health.READ_NUTRITION","android.permission.health.READ_EXERCISE"};
    private static <T> void measure(Activity ctx,HealthConnectManager manager,TimeRangeFilter interval,
            AggregationType<T> type,String key,ToDoubleFunction<T> convert,JSONObject out,Runnable done) {
        AggregateRecordsRequest<T> req=new AggregateRecordsRequest.Builder<T>(interval).addAggregationType(type).build();
        try {
            manager.aggregate(req,ctx.getMainExecutor(),new OutcomeReceiver<AggregateRecordsResponse<T>,HealthConnectException>() {
                public void onResult(AggregateRecordsResponse<T> response) {
                    T value=response.get(type);
                    try {if(value!=null)out.put(key,Math.round(convert.applyAsDouble(value)*10.0)/10.0);}
                    catch(JSONException ignored){} finally{done.run();}
                }
                public void onError(HealthConnectException error){done.run();}
            });
        } catch(RuntimeException e){done.run();}
    }
    static void read(Activity ctx,Consumer<JSONObject> finish) {
        ZoneId zone=ZoneId.of("Asia/Seoul");
        LocalDate day=LocalDate.now(zone);
        JSONObject out=new JSONObject();
        try{out.put("day",day.toString());}catch(JSONException ignored){}
        HealthConnectManager manager=ctx.getSystemService(HealthConnectManager.class);
        if(manager==null){finish.accept(out);return;}
        TimeRangeFilter range=new TimeInstantRangeFilter.Builder()
            .setStartTime(day.atStartOfDay(zone).toInstant()).setEndTime(Instant.now()).build();
        List<Consumer<Runnable>> reads=new ArrayList<>();
        if(ctx.checkSelfPermission(PERMISSIONS[0])==PackageManager.PERMISSION_GRANTED)
            reads.add(done->measure(ctx,manager,range,HydrationRecord.VOLUME_TOTAL,"water_ml",v->v.getInLiters()*1000,out,done));
        if(ctx.checkSelfPermission(PERMISSIONS[1])==PackageManager.PERMISSION_GRANTED)
            reads.add(done->measure(ctx,manager,range,SleepSessionRecord.SLEEP_DURATION_TOTAL,"sleep_hours",v->v/3600000.0,out,done));
        if(ctx.checkSelfPermission(PERMISSIONS[2])==PackageManager.PERMISSION_GRANTED) {
            reads.add(done->measure(ctx,manager,range,NutritionRecord.PROTEIN_TOTAL,"protein_g",Mass::getInGrams,out,done));
            reads.add(done->measure(ctx,manager,range,NutritionRecord.ENERGY_TOTAL,"kcal",v->v.getInCalories()/1000.0,out,done));
        }
        if(ctx.checkSelfPermission(PERMISSIONS[3])==PackageManager.PERMISSION_GRANTED)
            reads.add(done->measure(ctx,manager,range,ExerciseSessionRecord.EXERCISE_DURATION_TOTAL,"exercise_minutes",v->v/60000.0,out,done));
        AtomicInteger remaining=new AtomicInteger(reads.size());
        if(reads.isEmpty()){finish.accept(out);return;}
        for(Consumer<Runnable> read:reads) read.accept(()->{if(remaining.decrementAndGet()==0)finish.accept(out);});
    }
    static String describe(JSONObject o) {
        StringBuilder text=new StringBuilder(o.optString("day"));
        String[][] labels={{"water_ml","물","mL"},{"sleep_hours","수면","시간"},{"protein_g","단백질","g"},{"kcal","섭취 에너지","kcal"},{"exercise_minutes","운동","분"}};
        for(String[] label:labels)if(o.has(label[0]))text.append("\n").append(label[1]).append(" · ").append(o.opt(label[0])).append(" ").append(label[2]);
        return text.toString();
    }
}
