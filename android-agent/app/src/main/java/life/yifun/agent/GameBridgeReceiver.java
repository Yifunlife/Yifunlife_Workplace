package life.yifun.agent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import org.json.JSONObject;

/** Same-signature integration only. Other-signature games need a separately reviewed vendor bridge. */
public class GameBridgeReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context c,Intent intent){
        try{
            if(!Agent.bound(c)){setResultCode(403);setResultData("设备未绑定");return;}
            if("life.yifun.agent.GET_CONFIG".equals(intent.getAction())){
                JSONObject config=new JSONObject(Agent.prefs(c).getString("config","{}"));
                if(config.optDouble("offline_valid_until",0)*1000<System.currentTimeMillis()){setResultCode(403);setResultData("离线配置已到期，请联网同步");return;}
                setResultCode(200);setResultData(config.toString());return;
            }
            if(!"life.yifun.agent.REPORT_EVENT".equals(intent.getAction())){setResultCode(400);return;}
            String raw=intent.getStringExtra("payload");
            if(raw==null||raw.getBytes(java.nio.charset.StandardCharsets.UTF_8).length>8192){setResultCode(400);return;}
            JSONObject value=new JSONObject(raw);String type=value.optString("event","");String eventId=value.optString("event_id","");
            if(!eventId.matches("[A-Za-z0-9_.:-]{1,95}")){setResultCode(400);return;}
            if(!type.equals("game.session_started")&&!type.equals("game.level_scored")&&!type.equals("game.session_ended")){setResultCode(400);return;}
            try(Outbox outbox=new Outbox(c)){outbox.append("game",value,"game:"+eventId);}
            setResultCode(200);setResultData("已保存到本地队列；云端确认后清理");
        }catch(Exception e){setResultCode(503);setResultData("暂时无法接收，请保留事件并稍后重试");}
    }
}
