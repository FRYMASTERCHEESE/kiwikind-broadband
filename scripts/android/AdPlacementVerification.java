package nz.kiwikind.broadband;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Intent;
import android.os.Bundle;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

/** Fresh emulator, official sample IDs only. Verifies lifecycle, not filled inventory. */
public class AdPlacementVerification extends Instrumentation {
    @Override public void onCreate(Bundle args){super.onCreate(args);start();}
    private void require(boolean ok,String message){if(!ok)throw new IllegalStateException(message);}
    private void invoke(Activity activity,String name,Class<?> type,Object value)throws Exception{
        Method m=MainActivity.class.getDeclaredMethod(name,type);m.setAccessible(true);m.invoke(activity,value);
    }
    @Override public void onStart(){
        Bundle result=new Bundle();
        try{
            Activity activity=startActivitySync(new Intent(getTargetContext(),MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            waitForIdleSync();
            runOnMainSync(()->{try{
                Class<?> preview=Class.forName("nz.kiwikind.broadband.AdPreview");
                Method active=preview.getDeclaredMethod("active",Activity.class,LinearLayout.class);active.setAccessible(true);
                Method show=preview.getMethod("show",Activity.class,LinearLayout.class);
                invoke(activity,"publicPage",String.class,"home");
                Field f=MainActivity.class.getDeclaredField("content");f.setAccessible(true);
                LinearLayout content=(LinearLayout)f.get(activity),slot=null;
                Button trigger=null;
                for(int i=0;i<content.getChildCount();i++){
                    View child=content.getChildAt(i);
                    if(child instanceof Button&&((Button)child).getText().toString().equals("Internal test ad preview")){
                        trigger=(Button)child;slot=(LinearLayout)content.getChildAt(i+1);break;
                    }
                }
                require(trigger!=null&&slot!=null,"Public Home test placement missing");
                require((Boolean)active.invoke(null,activity,slot),"Visible Home slot not active");
                trigger.performClick();int children=slot.getChildCount();trigger.performClick();
                require(children==1&&slot.getChildCount()==children,"Duplicate preview request accepted");
                invoke(activity,"auth",boolean.class,false);
                require(!(Boolean)active.invoke(null,activity,slot),"Stale Home slot active on sign-in");
                int before=slot.getChildCount();show.invoke(null,activity,slot);
                require(slot.getChildCount()==before,"Detached request changed stale slot");
                for(int i=0;i<content.getChildCount();i++)require(!content.getChildAt(i).getClass().getName().contains("AdView"),"Ad on sign-in");
                invoke(activity,"policyScreen",String.class,"privacy");
                require(!(Boolean)active.invoke(null,activity,slot),"Stale Home slot active on privacy");
            }catch(Exception e){throw new RuntimeException(e);}});
            waitForIdleSync();
            result.putString("stream","AD_PLACEMENT_PASS: Home placement, duplicate guard, navigation invalidation, sign-in/privacy exclusion. No filled-ad claim.");
            runOnMainSync(activity::finish);finish(Activity.RESULT_OK,result);
        }catch(Throwable e){result.putString("stream","AD_PLACEMENT_FAIL: "+e);finish(Activity.RESULT_CANCELED,result);}
    }
}
