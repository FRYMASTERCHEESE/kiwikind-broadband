package nz.kiwikind.broadband;
import android.app.Activity;
import android.app.Instrumentation;
import android.content.Intent;
import android.os.Bundle;
import android.graphics.Bitmap;
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
            if(node.performAction(AccessibilityNodeInfo.ACTION_CLICK))return true;
            AccessibilityNodeInfo parent=node.getParent();return parent!=null&&parent.performAction(AccessibilityNodeInfo.ACTION_CLICK);
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
            runOnMainSync(()->{try{
                UserMessagingPlatform.getConsentInformation(activity).reset();
                BannerAds ads=(BannerAds)field(activity,"bannerAds");
                Field params=BannerAds.class.getDeclaredField("parameters");params.setAccessible(true);
                params.set(ads,new ConsentRequestParameters.Builder().setConsentDebugSettings(new ConsentDebugSettings.Builder(activity).setDebugGeography(ConsentDebugSettings.DebugGeography.DEBUG_GEOGRAPHY_EEA).build()).build());
                invoke("publicPage",String.class,"home");
            }catch(Exception e){throw new RuntimeException(e);}});
            boolean refused=false,loaded=false;
            for(int i=0;i<180;i++){
                waitForIdleSync();
                if(!refused){if(clickRefusal(getUiAutomation().getRootInActiveWindow())){refused=true;}}
                BannerAds ads=(BannerAds)field(activity,"bannerAds");
                if((Boolean)field(ads,"loaded")){loaded=true;break;}
                Thread.sleep(500);
            }
            capture("01-home-test-banner.png");
            require(refused,"EEA refusal control was not exercised; consent configuration is not verified");
            require(loaded,"Real KiwiKind test banner did not fill; inspect screenshot and SDK logs");
            runOnMainSync(()->{try{
                BannerAds ads=(BannerAds)field(activity,"bannerAds");
                require(field(ads,"banner")!=null,"Loaded banner missing");
                ads.pause();require(!(Boolean)field(ads,"foreground"),"Pause gate not closed");
                ads.resume();require((Boolean)field(ads,"foreground"),"Resume gate not reopened");
                invoke("auth",boolean.class,false);
                require(field(ads,"banner")==null&&field(ads,"slot")==null,"Banner survived sign-in navigation");
                invoke("policyScreen",String.class,"privacy");
                require(field(ads,"banner")==null,"Banner appeared on privacy screen");
            }catch(Exception e){throw new RuntimeException(e);}});
            waitForIdleSync();capture("02-privacy-no-banner.png");
            result.putString("stream","AD_PLACEMENT_PASS: Real KiwiKind App ID/banner unit; EEA refusal exercised; filled SDK test banner; pause/resume; navigation destruction; sign-in/privacy exclusion. Emulator only.");
            runOnMainSync(activity::finish);finish(Activity.RESULT_OK,result);
        }catch(Throwable error){
            try{if(evidence!=null)capture("failure.png");}catch(Exception ignored){}
            result.putString("stream","AD_PLACEMENT_FAIL: "+error);finish(Activity.RESULT_CANCELED,result);
        }
    }
}
