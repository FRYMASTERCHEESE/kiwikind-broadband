package nz.kiwikind.broadband;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Intent;
import android.os.Bundle;
import android.content.Context;
import android.content.SharedPreferences;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.net.CookieManager;
import java.net.HttpCookie;
import java.net.URI;

/** Fresh emulator only: synthetic cookies, refused local network, no Google login. */
public class RecoveryVerification extends Instrumentation {
    @Override public void onCreate(Bundle args){super.onCreate(args);start();}
    private Object field(Object object,String name) throws Exception {Field f=object.getClass().getDeclaredField(name);f.setAccessible(true);return f.get(object);}
    private void set(Object object,String name,Object value) throws Exception {Field f=object.getClass().getDeclaredField(name);f.setAccessible(true);f.set(object,value);}
    private void require(boolean ok,String message){if(!ok)throw new IllegalStateException(message);}
    private void invoke(Object object,String name) throws Exception {Method m=object.getClass().getDeclaredMethod(name);m.setAccessible(true);m.invoke(object);}
    private void idle(Activity activity) throws Exception {
        for(int i=0;i<150;i++){waitForIdleSync();if(!(Boolean)field(activity,"busy"))return;Thread.sleep(100);}
        throw new IllegalStateException("UI operation did not finish");
    }
    @Override public void onStart(){
        Bundle result=new Bundle();
        try {
            Context context=getTargetContext();
            SharedPreferences prefs=context.getSharedPreferences("kiwikind_secure_session",Context.MODE_PRIVATE);
            prefs.edit().clear().commit();
            Api api=new Api("https://127.0.0.1:1",context);
            CookieManager manager=(CookieManager)field(api,"cookies");
            HttpCookie cookie=new HttpCookie("sessionid","synthetic-emulator-session-only");cookie.setSecure(true);cookie.setPath("/");
            manager.getCookieStore().add(URI.create("https://127.0.0.1:1"),cookie);
            invoke(api,"saveCookies");
            require(!prefs.getString("cookies","").contains("synthetic-emulator-session-only"),"Session persisted in plaintext");
            Api reopened=new Api("https://127.0.0.1:1",context);
            require(((CookieManager)field(reopened,"cookies")).getCookieStore().getCookies().size()==1,"Encrypted session did not restore");
            try{reopened.call("status",null);throw new IllegalStateException("Refused connection succeeded");}catch(java.io.IOException expected){}
            require(((CookieManager)field(reopened,"cookies")).getCookieStore().getCookies().size()==1,"Network failure discarded saved login");
            prefs.edit().putString("cookies","corrupt-fixture").commit();
            Api corrupted=new Api("https://127.0.0.1:1",context);
            require(((CookieManager)field(corrupted,"cookies")).getCookieStore().getCookies().isEmpty(),"Corrupt session was accepted");
            require(prefs.getAll().isEmpty(),"Corrupt storage was not cleared");
            result.putString("storage","PASS encrypted reopen; offline preserves session; corruption clears safely");

            Activity activity=startActivitySync(new Intent(context,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            runOnMainSync(()->{try{set(activity,"api",new Api("https://127.0.0.1:1",context));invoke(activity,"connectAccount");}catch(Exception e){throw new RuntimeException(e);}});
            idle(activity);
            require(!(Boolean)field(activity,"signedIn"),"Offline startup displayed authenticated state");
            runOnMainSync(()->{try{invoke(activity,"connectAccount");}catch(Exception e){throw new RuntimeException(e);}});
            idle(activity);
            result.putString("offline_ui","PASS refused connection and retry return without stuck busy state");

            runOnMainSync(()->{try{
                set(activity,"signedIn",true);set(activity,"exportData","synthetic-private-export");set(activity,"orderKey","synthetic-order-key");
                Method run=MainActivity.class.getDeclaredMethod("run",MainActivity.Task.class,MainActivity.Done.class);run.setAccessible(true);
                run.invoke(activity,(MainActivity.Task)()->{throw new Api.SessionExpiredException();},(MainActivity.Done)data->{throw new IllegalStateException("Expired operation reported success");});
            }catch(Exception e){throw new RuntimeException(e);}});
            idle(activity);
            require(!(Boolean)field(activity,"signedIn"),"Expired session stayed signed in");
            require(field(activity,"exportData")==null && field(activity,"orderKey")==null,"Expired session retained private screen data");
            require(prefs.getAll().isEmpty(),"Expired session storage not cleared");
            result.putString("expired_ui","PASS expiry returns to authentication and clears private state");
            result.putString("stream","EXTENDED_RECOVERY_PASS: emulator only; no physical-device or real OAuth claim");
            finish(-1,result);
        }catch(Throwable e){result.putString("stream",e.toString());finish(Activity.RESULT_CANCELED,result);}
    }
}
