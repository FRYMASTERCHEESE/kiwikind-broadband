package nz.kiwikind.broadband;
import android.app.*;
import android.content.*;
import android.os.Bundle;
import android.graphics.Bitmap;
import org.json.*;
import java.io.*;
import java.lang.reflect.*;

/** Synthetic backend latency and native screen evidence; no real account/OAuth. */
public class ReadinessCapture extends Instrumentation {
    @Override public void onCreate(Bundle args){super.onCreate(args);start();}
    static class FixtureApi extends Api {
        int calls=0;
        FixtureApi(Context context){super("https://fixture.example.invalid",context);}
        @Override boolean configured(){return true;}
        @Override JSONObject call(String path,JSONObject data)throws Exception{
            calls++;Thread.sleep(250);
            JSONObject account=new JSONObject().put("email","synthetic@example.invalid").put("has_password",false);
            switch(path){
                case "bootstrap":return new JSONObject().put("account",account).put("intake_enabled",false);
                case "status":return new JSONObject().put("intake_enabled",false);
                case "me":case "login":return account;
                case "preferences":return new JSONObject().put("account_notifications",true);
                case "referrals":return new JSONObject().put("code","SYNTHETIC-PREVIEW-CODE").put("share_url","https://example.invalid/?ref=synthetic#signup").put("history",new JSONArray());
                case "orders":return new JSONObject().put("orders",new JSONArray());
                case "tickets":return new JSONObject().put("tickets",new JSONArray());
                default:return new JSONObject();
            }
        }
    }
    Object field(Object o,String name)throws Exception{Field f=o.getClass().getDeclaredField(name);f.setAccessible(true);return f.get(o);}
    void set(Object o,String name,Object value)throws Exception{Field f=o.getClass().getDeclaredField(name);f.setAccessible(true);f.set(o,value);}
    void invoke(Object o,String name,Class<?>[]types,Object...args)throws Exception{Method m=o.getClass().getDeclaredMethod(name,types);m.setAccessible(true);m.invoke(o,args);}
    void main(Action action){runOnMainSync(()->{try{action.run();}catch(Exception e){throw new RuntimeException(e);}});}
    interface Action{void run()throws Exception;}
    void idle(Activity activity)throws Exception{for(int i=0;i<100;i++){waitForIdleSync();Thread.sleep(40);if(!(Boolean)field(activity,"busy")){waitForIdleSync();return;}}throw new Exception("Operation stuck busy");}
    void save(String name)throws Exception{waitForIdleSync();Thread.sleep(120);Bitmap b=getUiAutomation().takeScreenshot();File dir=new File(getTargetContext().getExternalFilesDir(null),"readiness");dir.mkdirs();try(FileOutputStream out=new FileOutputStream(new File(dir,name))){b.compress(Bitmap.CompressFormat.PNG,100,out);}b.recycle();}
    @Override public void onStart(){Bundle result=new Bundle();try{
        long start=android.os.SystemClock.elapsedRealtime();
        Activity activity=startActivitySync(new Intent(getTargetContext(),MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));waitForIdleSync();
        long local=android.os.SystemClock.elapsedRealtime()-start;
        FixtureApi api=new FixtureApi(getTargetContext());main(()->set(activity,"api",api));
        long restoreStart=android.os.SystemClock.elapsedRealtime();main(()->invoke(activity,"connectAccount",new Class<?>[]{}));idle(activity);
        long restore=android.os.SystemClock.elapsedRealtime()-restoreStart;int restoreCalls=api.calls;
        api.calls=0;long loginStart=android.os.SystemClock.elapsedRealtime();
        main(()->invoke(activity,"run",new Class<?>[]{MainActivity.Task.class,MainActivity.Done.class},
            (MainActivity.Task)()->api.call("login",new JSONObject()),(MainActivity.Done)account->{
                try{invoke(activity,"acceptLogin",new Class<?>[]{JSONObject.class},account);}catch(NoSuchMethodException old){set(activity,"signedIn",true);invoke(activity,"home",new Class<?>[]{});}
            }));idle(activity);
        String timing="local_launch_ms="+local+" restore_ms="+restore+" restore_calls="+restoreCalls+" login_ms="+(android.os.SystemClock.elapsedRealtime()-loginStart)+" login_calls="+api.calls+" per_request_fixture_ms=250";
        System.out.println("TIMING "+timing);save("01-account.png");
        boolean modern;
        try{MainActivity.class.getDeclaredMethod("policyScreen",String.class);modern=true;}catch(NoSuchMethodException old){modern=false;}
        if(modern){
            if(restoreCalls!=1||api.calls!=1)throw new Exception("Duplicate restore/login requests");
            main(()->invoke(activity,"policyScreen",new Class<?>[]{String.class},"privacy"));save("02-native-privacy.png");
            main(()->invoke(activity,"correctionScreen",new Class<?>[]{}));save("03-native-correction.png");
            main(()->invoke(activity,"deletionScreen",new Class<?>[]{boolean.class},false));save("04-native-google-deletion.png");
            main(()->invoke(activity,"referralsScreen",new Class<?>[]{}));idle(activity);save("05-native-referrals.png");
            main(()->invoke(activity,"settingsScreen",new Class<?>[]{}));idle(activity);save("06-native-settings.png");
            main(()->invoke(activity,"orders",new Class<?>[]{}));idle(activity);save("07-native-requests.png");
            main(()->invoke(activity,"tickets",new Class<?>[]{}));idle(activity);save("08-native-support.png");
        }
        File dir=new File(getTargetContext().getExternalFilesDir(null),"readiness");try(FileWriter out=new FileWriter(new File(dir,"timing.txt"))){out.write(timing+"\nSynthetic 250ms backend fixture; not real login, cold-start or phone evidence.\n");}
        result.putString("stream","READINESS_PASS "+timing);finish(-1,result);
    }catch(Throwable e){result.putString("stream",e.toString());finish(Activity.RESULT_CANCELED,result);}}
}
