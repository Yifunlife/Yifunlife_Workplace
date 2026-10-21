package life.yifun.agent;
import android.app.job.JobParameters;
import android.app.job.JobService;
public class HeartbeatJob extends JobService {
    private volatile Thread worker;
    @Override public boolean onStartJob(JobParameters p){worker=new Thread(()->{boolean retry=false;try{Agent.heartbeat(getApplicationContext());}catch(Exception e){retry=true;}if(!Thread.currentThread().isInterrupted())jobFinished(p,retry);});worker.start();return true;}
    @Override public boolean onStopJob(JobParameters p){Thread w=worker;if(w!=null)w.interrupt();return true;}
}
