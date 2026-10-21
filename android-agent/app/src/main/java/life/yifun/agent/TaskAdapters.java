package life.yifun.agent;
import android.content.Context;
import android.os.Build;
import org.json.JSONObject;

/** Vendor-specific actions must be explicitly implemented and advertised before the server can dispatch them. */
public final class TaskAdapters {
    private TaskAdapters(){}
    static void execute(Context c,Outbox outbox,JSONObject task) throws Exception {
        String id=task.getString("id"),lease=task.getString("lease"),kind=task.getString("kind");
        JSONObject previous=outbox.prior(id);
        if(previous!=null){outbox.complete(id,lease,previous.getString("state"),previous.getJSONObject("result"));return;}
        String state="succeeded";JSONObject result=new JSONObject();
        if("sync_config".equals(kind)){
            String config=Agent.prefs(c).getString("config","");
            if(config.isEmpty())throw new IllegalStateException("尚未收到配置");
            result.put("revision",new JSONObject(config).getString("revision")).put("enforcement","配置已缓存，游戏应用执行待适配");
        }else if("collect_agent_logs".equals(kind)){
            outbox.append("diagnostic",new JSONObject().put("task_id",id).put("message","Agent 诊断快照；不包含其他应用日志或凭证").put("agent_version","0.2.0").put("android_version",Build.VERSION.RELEASE).put("model",Build.MODEL),"task-log:"+id);
            result.put("diagnostic","已加入持久队列，将在下一次同步确认后入库");
        }else{
            state="unsupported";result.put("error","执行适配器未接入："+kind).put("adapter_required",true);
        }
        outbox.complete(id,lease,state,result);
    }
}
