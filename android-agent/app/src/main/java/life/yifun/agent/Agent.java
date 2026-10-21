package life.yifun.agent;

import android.app.admin.DevicePolicyManager;
import android.app.job.JobInfo;
import android.app.job.JobScheduler;
import android.content.ComponentName;
import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.PackageInfo;
import android.os.Build;
import android.util.Base64;
import org.json.JSONObject;
import javax.net.ssl.HttpsURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.UUID;

public final class Agent {
    private Agent() {}
    static SharedPreferences prefs(Context c) { return c.getSharedPreferences("agent_private", Context.MODE_PRIVATE); }
    static String origin(Context c) { return prefs(c).getString("origin", "https://yifunlife-workplace.yifunlife.workers.dev"); }
    static synchronized void identity(Context c) {
        if (!prefs(c).contains("secret")) {
            byte[] bytes=new byte[32]; new SecureRandom().nextBytes(bytes);
            boolean saved=prefs(c).edit().putString("secret",Base64.encodeToString(bytes,Base64.URL_SAFE|Base64.NO_WRAP|Base64.NO_PADDING)).putString("installation_id",UUID.randomUUID().toString()).commit();
            if(!saved) throw new IllegalStateException("无法保存设备凭证，请检查存储空间");
        }
    }
    static boolean bound(Context c) { return prefs(c).contains("device_id"); }
    static JSONObject telemetry(Context c) throws Exception {
        JSONObject t=new JSONObject();
        t.put("manufacturer",Build.MANUFACTURER).put("model",Build.MODEL).put("android_version",Build.VERSION.RELEASE).put("sdk_int",Build.VERSION.SDK_INT).put("agent_version","0.1.0");
        DevicePolicyManager dm=(DevicePolicyManager)c.getSystemService(Context.DEVICE_POLICY_SERVICE);
        boolean owner=dm!=null && dm.isDeviceOwnerApp(c.getPackageName());
        t.put("device_owner",owner).put("managed_install",owner).put("reboot",owner);
        String pkg=prefs(c).getString("package_name","");
        if(!pkg.isEmpty()) {
            t.put("package_name",pkg);
            try { PackageInfo p=c.getPackageManager().getPackageInfo(pkg,0); t.put("app_version",p.versionName==null?"未知":p.versionName).put("app_version_code",Build.VERSION.SDK_INT>=28?p.getLongVersionCode():p.versionCode); }
            catch(android.content.pm.PackageManager.NameNotFoundException e){ t.put("app_version","未安装"); }
        }
        return t;
    }
    static JSONObject request(Context c,String route,JSONObject payload,boolean authenticated) throws Exception {
        HttpsURLConnection conn=(HttpsURLConnection)new URL(origin(c)+route).openConnection();
        try {
            conn.setInstanceFollowRedirects(false);conn.setConnectTimeout(15000);conn.setReadTimeout(20000);conn.setRequestMethod("POST");conn.setDoOutput(true);conn.setRequestProperty("Content-Type","application/json; charset=utf-8");
            if(authenticated)conn.setRequestProperty("Authorization","Bearer "+prefs(c).getString("secret",""));
            byte[] body=payload.toString().getBytes(StandardCharsets.UTF_8);conn.setFixedLengthStreamingMode(body.length);
            try(var out=conn.getOutputStream()){out.write(body);}
            int status=conn.getResponseCode();String raw;
            try(var stream=status>=400?conn.getErrorStream():conn.getInputStream()) {
                if(stream==null)throw new java.io.IOException("服务器响应异常："+status);
                java.io.ByteArrayOutputStream buffer=new java.io.ByteArrayOutputStream();byte[] chunk=new byte[4096];int n;
                while((n=stream.read(chunk))!=-1){if(buffer.size()+n>65536)throw new java.io.IOException("服务器响应过大");buffer.write(chunk,0,n);}raw=buffer.toString("UTF-8");
            }
            JSONObject result=new JSONObject(raw);
            if(status<200||status>=300)throw new java.io.IOException(result.optString("error","请求失败："+status));
            return result;
        } finally { conn.disconnect(); }
    }
    static void bind(Context c,String code) throws Exception {
        identity(c);JSONObject p=new JSONObject().put("code",code.trim()).put("installation_id",prefs(c).getString("installation_id","")).put("device_secret",prefs(c).getString("secret","")).put("telemetry",telemetry(c));
        JSONObject result=request(c,"/api/software/agent/bind",p,false);
        if(!prefs(c).edit().putString("device_id",result.getString("device_id")).putString("package_name",result.getString("package_name")).commit())throw new java.io.IOException("绑定信息保存失败，请重新绑定");
        schedule(c); heartbeat(c);
    }
    static void heartbeat(Context c) throws Exception {
        if(!bound(c))return;
        request(c,"/api/software/agent/heartbeat",new JSONObject().put("telemetry",telemetry(c)),true);
        prefs(c).edit().putLong("last_success",System.currentTimeMillis()).apply();
    }
    static void schedule(Context c) {
        if(!bound(c))return;
        JobInfo info=new JobInfo.Builder(26001,new ComponentName(c,HeartbeatJob.class)).setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY).setPersisted(true).setPeriodic(15*60*1000L).setBackoffCriteria(30000,JobInfo.BACKOFF_POLICY_EXPONENTIAL).build();
        ((JobScheduler)c.getSystemService(Context.JOB_SCHEDULER_SERVICE)).schedule(info);
    }
}
