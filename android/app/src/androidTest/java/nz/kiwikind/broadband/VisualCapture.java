package nz.kiwikind.broadband;

import android.app.Instrumentation;
import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.graphics.Bitmap;
import java.io.File;
import java.io.FileOutputStream;

/** Isolated emulator fixture: no login, account mutations or live customer data. */
public class VisualCapture extends Instrumentation {
    @Override public void onCreate(Bundle arguments){super.onCreate(arguments);start();}
    @Override public void onStart(){
        Bundle result=new Bundle();
        try {
            Activity activity=startActivitySync(new Intent(getTargetContext(),MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            capture(activity,"auth","01-sign-in.png");
            capture(activity,"home","02-dashboard-fixture.png");
            result.putString("stream","Native sign-in and dashboard fixture captured successfully.");finish(-1,result);
        } catch(Exception e){result.putString("stream",e.toString());finish(Activity.RESULT_CANCELED,result);}
    }
    private void capture(Activity activity,String screen,String filename) throws Exception {
        runOnMainSync(()->{try {
            java.lang.reflect.Method method=MainActivity.class.getDeclaredMethod(screen,screen.equals("auth")?new Class<?>[]{boolean.class}:new Class<?>[]{});
            method.setAccessible(true);method.invoke(activity,screen.equals("auth")?new Object[]{false}:new Object[]{});
        }catch(Exception e){throw new RuntimeException(e);}});
        waitForIdleSync();Thread.sleep(1200);
        runOnMainSync(()->{
            if(android.os.Build.VERSION.SDK_INT>=30){android.view.WindowInsetsController bars=activity.getWindow().getInsetsController();if(bars==null||(bars.getSystemBarsAppearance()&android.view.WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS)==0)throw new IllegalStateException("Status bar contrast not configured");}
        });
        runOnMainSync(()->checkLayout(activity.getWindow().getDecorView()));
        save(filename);
        runOnMainSync(()->scrollToBottom(activity));
        waitForIdleSync();Thread.sleep(300);
        runOnMainSync(()->scrollToBottom(activity));
        waitForIdleSync();Thread.sleep(300);save(filename.replace(".png","-controls.png"));
    }
    private void scrollToBottom(Activity activity){
        android.widget.ScrollView scroll=findScroll(activity.getWindow().getDecorView());
        if(scroll==null)throw new IllegalStateException("Scrollable content missing");
        scroll.clearFocus();scroll.scrollTo(0,scroll.getChildAt(0).getHeight());
        int bottom=scroll.getChildAt(0).getBottom();
        if(bottom>scroll.getScrollY()+scroll.getHeight()+2)throw new IllegalStateException("Bottom controls not reachable");
    }
    private android.widget.ScrollView findScroll(android.view.View view){
        if(view instanceof android.widget.ScrollView)return (android.widget.ScrollView)view;
        if(view instanceof android.view.ViewGroup){android.view.ViewGroup group=(android.view.ViewGroup)view;for(int i=0;i<group.getChildCount();i++){android.widget.ScrollView found=findScroll(group.getChildAt(i));if(found!=null)return found;}}
        return null;
    }
    private void checkLayout(android.view.View view){
        if(view instanceof android.widget.Button && view.getHeight()<48*getTargetContext().getResources().getDisplayMetrics().density)throw new IllegalStateException("Touch target below 48dp");
        if(view instanceof android.view.ViewGroup){android.view.ViewGroup group=(android.view.ViewGroup)view;for(int i=0;i<group.getChildCount();i++){android.view.View child=group.getChildAt(i);if(child.getVisibility()==android.view.View.VISIBLE && child.getRight()>group.getWidth())throw new IllegalStateException("Horizontal overflow");checkLayout(child);}}
    }
    private void save(String filename) throws Exception {
        Bitmap bitmap=getUiAutomation().takeScreenshot();
        if(bitmap==null)throw new IllegalStateException("Screenshot unavailable");
        File dir=new File(getTargetContext().getExternalFilesDir(null),"visual-evidence");dir.mkdirs();
        try(FileOutputStream out=new FileOutputStream(new File(dir,filename))){bitmap.compress(Bitmap.CompressFormat.PNG,100,out);}bitmap.recycle();
    }
}
