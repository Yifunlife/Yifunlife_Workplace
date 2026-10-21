package life.yifun.agent;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.UUID;

/** Private persistent outbound events and execution receipts; no bearer tokens enter this database. */
public class Outbox extends SQLiteOpenHelper {
    public Outbox(Context c){super(c,"outbox.db",null,1);}
    @Override public void onCreate(SQLiteDatabase db){
        db.execSQL("CREATE TABLE events(id TEXT PRIMARY KEY,category TEXT NOT NULL,data TEXT NOT NULL,created_at INTEGER NOT NULL)");
        db.execSQL("CREATE TABLE execution(task_id TEXT PRIMARY KEY,lease TEXT NOT NULL,state TEXT NOT NULL,result TEXT NOT NULL,acked INTEGER NOT NULL DEFAULT 0)");
    }
    @Override public void onUpgrade(SQLiteDatabase db,int a,int b){throw new IllegalStateException("Unsupported database migration");}
    public synchronized void append(String category,JSONObject data){append(category,data,UUID.randomUUID().toString());}
    public synchronized void append(String category,JSONObject data,String eventId){
        SQLiteDatabase db=getWritableDatabase();db.beginTransaction();
        try{
            try(Cursor existing=db.rawQuery("SELECT category,data FROM events WHERE id=?",new String[]{eventId})){
                if(existing.moveToFirst()){
                    if(!category.equals(existing.getString(0))||!data.toString().equals(existing.getString(1)))throw new IllegalStateException("事件编号已被其他内容使用");
                    db.setTransactionSuccessful();return;
                }
            }
            try(Cursor count=db.rawQuery("SELECT COUNT(*) FROM events",null)){count.moveToFirst();if(count.getInt(0)>=1000)throw new IllegalStateException("离线队列已满，请联网同步后重试");}
            db.execSQL("INSERT INTO events VALUES(?,?,?,?)",new Object[]{eventId,category,data.toString(),System.currentTimeMillis()});db.setTransactionSuccessful();
        }finally{db.endTransaction();}
    }
    public synchronized JSONArray events() throws Exception {
        JSONArray result=new JSONArray();
        try(Cursor c=getReadableDatabase().rawQuery("SELECT id,category,data FROM events ORDER BY created_at,id LIMIT 20",null)){
            while(c.moveToNext())result.put(new JSONObject().put("event_id",c.getString(0)).put("category",c.getString(1)).put("data",new JSONObject(c.getString(2))));
        }return result;
    }
    public synchronized void acknowledge(JSONArray ids){SQLiteDatabase db=getWritableDatabase();db.beginTransaction();try{for(int i=0;i<ids.length();i++)db.execSQL("DELETE FROM events WHERE id=?",new Object[]{ids.optString(i)});db.setTransactionSuccessful();}finally{db.endTransaction();}}
    public synchronized JSONObject receipt() throws Exception {
        try(Cursor c=getReadableDatabase().rawQuery("SELECT task_id,lease,state,result FROM execution WHERE acked=0 ORDER BY rowid LIMIT 1",null)){
            if(c.moveToFirst())return new JSONObject().put("task_id",c.getString(0)).put("lease",c.getString(1)).put("state",c.getString(2)).put("result",new JSONObject(c.getString(3)));
        }return null;
    }
    public synchronized JSONObject prior(String id) throws Exception {
        try(Cursor c=getReadableDatabase().rawQuery("SELECT state,result FROM execution WHERE task_id=?",new String[]{id})){
            if(c.moveToFirst())return new JSONObject().put("state",c.getString(0)).put("result",new JSONObject(c.getString(1)));
        }return null;
    }
    public synchronized void complete(String id,String lease,String state,JSONObject result){getWritableDatabase().execSQL("INSERT OR REPLACE INTO execution VALUES(?,?,?,?,0)",new Object[]{id,lease,state,result.toString()});}
    public synchronized void acknowledgedTask(String id){if(id!=null&&!id.isEmpty())getWritableDatabase().execSQL("UPDATE execution SET acked=1 WHERE task_id=?",new Object[]{id});}
}
