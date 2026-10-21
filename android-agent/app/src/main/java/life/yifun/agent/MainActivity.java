package life.yifun.agent;

import android.app.Activity;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.view.View;
import android.widget.*;
import java.util.concurrent.Executors;
import java.util.concurrent.ExecutorService;

public class MainActivity extends Activity {
    private final ExecutorService io=Executors.newSingleThreadExecutor();
    private final Handler ui=new Handler(Looper.getMainLooper());
    private TextView status;private EditText code;private Button bind,send;private boolean running=false,active=false;
    private final Runnable tick=new Runnable(){public void run(){if(!active)return;if(Agent.bound(MainActivity.this))perform(false);ui.postDelayed(this,60000);}};
    @Override public void onCreate(Bundle b){super.onCreate(b);
        LinearLayout layout=new LinearLayout(this);layout.setOrientation(LinearLayout.VERTICAL);int pad=(int)(24*getResources().getDisplayMetrics().density);layout.setPadding(pad,pad,pad,pad);
        TextView title=new TextView(this);title.setText("亦玩 · 安卓设备管理");title.setTextSize(24);layout.addView(title);
        TextView hint=new TextView(this);hint.setText("将本机绑定到软件中心，自动上报系统与游戏版本。\n"+Agent.origin(this)+"\n");layout.addView(hint);
        code=new EditText(this);code.setHint("输入管理员签发的 AND- 绑定码");code.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);code.setSingleLine(true);layout.addView(code);
        bind=new Button(this);bind.setText("绑定本机");layout.addView(bind);bind.setOnClickListener(v->perform(true));
        send=new Button(this);send.setText("立即同步状态");layout.addView(send);send.setOnClickListener(v->perform(false));
        status=new TextView(this);status.setPadding(0,pad,0,0);layout.addView(status);
        TextView note=new TextView(this);note.setText("\n前台每 60 秒同步；后台由安卓系统调度，可能延迟。\n本版本不执行安装、重启或远程控制。\n绑定凭证保存在应用私有空间，卸载或清除数据后需重新绑定。");layout.addView(note);
        ScrollView scroll=new ScrollView(this);scroll.addView(layout);setContentView(scroll);refresh();Agent.schedule(this);
    }
    private void refresh(){boolean b=Agent.bound(this);code.setVisibility(b?View.GONE:View.VISIBLE);bind.setVisibility(b?View.GONE:View.VISIBLE);send.setEnabled(b&&!running);long last=Agent.prefs(this).getLong("last_success",0);status.setText(b?"已绑定设备："+Agent.prefs(this).getString("device_id","")+"\n游戏包名："+Agent.prefs(this).getString("package_name","")+"\n最近同步："+(last==0?"等待首次上报":java.text.DateFormat.getDateTimeInstance().format(new java.util.Date(last))):"尚未绑定。请先在软件中心登记产品并签发绑定码。");}
    private void perform(boolean enroll){if(running||isFinishing())return;String raw=code.getText().toString();if(enroll&&raw.trim().isEmpty()){code.setError("请输入绑定码");return;}running=true;bind.setEnabled(false);send.setEnabled(false);status.setText("正在同步…");io.execute(()->{String error=null;try{if(enroll)Agent.bind(getApplicationContext(),raw);else Agent.heartbeat(getApplicationContext());}catch(Exception e){error=e.getMessage()==null?"连接失败，请检查网络":e.getMessage();}final String result=error;ui.post(()->{if(isFinishing()||isDestroyed())return;running=false;bind.setEnabled(true);refresh();if(result!=null)status.append("\n同步失败："+result);});});}
    @Override protected void onResume(){super.onResume();active=true;ui.post(tick);}
    @Override protected void onPause(){active=false;ui.removeCallbacks(tick);super.onPause();}
    @Override protected void onDestroy(){ui.removeCallbacksAndMessages(null);io.shutdownNow();super.onDestroy();}
}
