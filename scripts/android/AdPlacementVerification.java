package nz.kiwikind.broadband;
import android.app.Activity;
import android.app.Instrumentation;
import android.content.Intent;
import android.os.Bundle;
import android.graphics.Bitmap;
import android.graphics.Rect;
import android.view.MotionEvent;
import android.os.SystemClock;
import android.widget.ScrollView;
import android.widget.LinearLayout;
import android.view.accessibility.AccessibilityNodeInfo;
import java.io.File;
import java.io.FileOutputStream;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import com.google.android.ump.*;

/** Fresh API36 emulator only. Real KiwiKind identifiers, SDK test device, no customer accounts. */
public class AdPlacementVerification extends Instrumentation {
    private Activity activity;
    private File evidence;
    @Override public void onCreate(Bundle args){super.onCreate(args);start();}
    private void require(boolean ok,String text){if(!ok)throw new IllegalStateException(text);}
    private Object field(Object object,String key)throws Exception{Field f=object.getClass().getDeclaredField(key);f.setAccessible(true);return f.get(object);}
    private void invoke(String key,Class<?> type,Object value)throws Exception{Method m=MainActivity.class.getDeclaredMethod(key,type);m.setAccessible(true);m.invoke(activity,value);}
    private boolean clickRefusal(AccessibilityNodeInfo node){
        if(node==null)return false;
        String text=node.getText()==null?"":node.getText().toString().trim();
        if(text.equalsIgnoreCase("Do not consent")||text.equalsIgnoreCase("Do not agree")){
            Rect bounds=new Rect();node.getBoundsInScreen(bounds);
            if(!node.isVisibleToUser()||bounds.isEmpty())return false;
            long now=SystemClock.uptimeMillis();
            MotionEvent down=MotionEvent.obtain(now,now,MotionEvent.ACTION_DOWN,bounds.centerX(),bounds.centerY(),0);
            MotionEvent up=MotionEvent.obtain(now,now+100,MotionEvent.ACTION_UP,bounds.centerX(),bounds.centerY(),0);
            down.setSource(android.view.InputDevice.SOURCE_TOUCHSCREEN);up.setSource(android.view.InputDevice.SOURCE_TOUCHSCREEN);
            try{return getUiAutomation().injectInputEvent(down,true)&&getUiAutomation().injectInputEvent(up,true);}
            finally{down.recycle();up.recycle();}
        }
        for(int i=0;i<node.getChildCount();i++)if(clickRefusal(node.getChild(i)))return true;
        return false;
    }
    private void capture(String name)throws Exception{
        Bitmap bitmap=getUiAutomation().takeScreenshot();
        if(bitmap!=null)try(FileOutputStream out=new FileOutputStream(new File(evidence,name))){bitmap.compress(Bitmap.CompressFormat.PNG,100,out);}
    }
    @Override public void onStart(){
        Bundle result=new Bundle();
        try{
            activity=startActivitySync(new Intent(getTargetContext(),MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            evidence=new File(activity.getExternalFilesDir(null),"advertising-v8");evidence.mkdirs();
            waitForIdleSync();
            Method testDevice=BannerAds.class.getDeclaredMethod("testDevice");testDevice.setAccessible(true);
            require((Boolean)testDevice.invoke(field(activity,"bannerAds")),"Automated consent/ad checks require an SDK-recognized TEST device");
            Method liveEnabled=BannerAds.class.getDeclaredMethod("liveAdsEnabled");liveEnabled.setAccessible(true);
            require((Boolean)liveEnabled.invoke(field(activity,"bannerAds")),"Signed V12 release must permit consented live requests on ordinary devices");
            runOnMainSync(()->{try{
                UserMessagingPlatform.getConsentInformation(activity).reset();
                BannerAds ads=(BannerAds)field(activity,"bannerAds");
                Field params=BannerAds.class.getDeclaredField("parameters");params.setAccessible(true);
                params.set(ads,new ConsentRequestParameters.Builder().setConsentDebugSettings(new ConsentDebugSettings.Builder(activity).setDebugGeography(ConsentDebugSettings.DebugGeography.DEBUG_GEOGRAPHY_EEA).build()).build());
                invoke("publicPage",String.class,"home");
            }catch(Exception e){throw new RuntimeException(e);}});
            boolean refused=false,loaded=false;int taps=0;
            long deadline=SystemClock.elapsedRealtime()+120000;
            while(SystemClock.elapsedRealtime()<deadline){
                waitForIdleSync();
                BannerAds ads=(BannerAds)field(activity,"bannerAds");
                if((Boolean)field(ads,"formShowing")){
                    if(taps==0)capture("00-eea-consent.png");
                    if(clickRefusal(getUiAutomation().getRootInActiveWindow()))taps++;
                }
                refused=taps>0&&(Boolean)field(ads,"consentUpdated")&&!(Boolean)field(ads,"formShowing");
                if((Boolean)field(ads,"loaded")){loaded=true;break;}
                Thread.sleep(1000);
            }
            require(refused,"EEA refusal was not completed; consent configuration is not verified");
            require(loaded,"KiwiKind test banner did not fill: "+((android.widget.TextView)field(field(activity,"bannerAds"),"status")).getText());
            runOnMainSync(()->{try{
                LinearLayout slot=(LinearLayout)field(field(activity,"bannerAds"),"slot");
                LinearLayout content=(LinearLayout)field(activity,"content");
                ((ScrollView)content.getParent()).scrollTo(0,slot.getTop());
            }catch(Exception e){throw new RuntimeException(e);}});
            Thread.sleep(500);capture("01-home-test-banner.png");
            runOnMainSync(()->{try{
                BannerAds ads=(BannerAds)field(activity,"bannerAds");ads.privacyChoices();
                require(field(ads,"banner")==null,"Privacy choices did not remove banner");
            }catch(Exception e){throw new RuntimeException(e);}});
            boolean reopened=false,closed=false;deadline=SystemClock.elapsedRealtime()+60000;
            while(SystemClock.elapsedRealtime()<deadline){
                waitForIdleSync();BannerAds ads=(BannerAds)field(activity,"bannerAds");
                if((Boolean)field(ads,"formShowing")){
                    if(!reopened)capture("02-privacy-options.png");reopened=true;
                    clickRefusal(getUiAutomation().getRootInActiveWindow());
                }
                if(reopened&&!(Boolean)field(ads,"formShowing")&&(Boolean)field(ads,"consentUpdated")){closed=true;break;}
                Thread.sleep(1000);
            }
            require(reopened&&closed,"Privacy choices did not reopen and close successfully");
            require(field(field(activity,"bannerAds"),"banner")==null,"Ad automatically reloaded after privacy changes");
            runOnMainSync(()->{try{
                BannerAds ads=(BannerAds)field(activity,"bannerAds");
                require(field(ads,"banner")==null,"Privacy choice dismissal reloaded a banner");
                ads.pause();require(!(Boolean)field(ads,"foreground"),"Pause gate not closed");
                ads.resume();require((Boolean)field(ads,"foreground"),"Resume gate not reopened");
                invoke("auth",boolean.class,false);
                require(field(ads,"banner")==null&&field(ads,"slot")==null,"Banner survived sign-in navigation");
                invoke("policyScreen",String.class,"privacy");
                require(field(ads,"banner")==null,"Banner appeared on privacy screen");
            }catch(Exception e){throw new RuntimeException(e);}});
            waitForIdleSync();capture("03-privacy-no-banner.png");
            result.putString("stream","AD_PLACEMENT_PASS: Real KiwiKind App ID/banner unit; EEA refusal exercised; filled SDK test banner; reopened/refused privacy choices with no automatic reload; pause/resume; navigation destruction; sign-in/privacy exclusion. Emulator only.");
            runOnMainSync(activity::finish);finish(Activity.RESULT_OK,result);
        }catch(Throwable error){
            try{if(evidence!=null)capture("failure.png");}catch(Exception ignored){}
            result.putString("stream","AD_PLACEMENT_FAIL: "+error);finish(Activity.RESULT_CANCELED,result);
        }
    }
}
