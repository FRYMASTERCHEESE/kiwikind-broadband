package nz.kiwikind.broadband;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Intent;
import android.content.pm.ActivityInfo;
import android.graphics.Bitmap;
import android.graphics.Insets;
import android.os.Bundle;
import android.os.SystemClock;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowInsets;
import android.view.inputmethod.InputMethodManager;
import android.widget.EditText;
import java.io.File;
import java.io.FileOutputStream;

/** Black-box checks against the optimized signed release, no private reflection. */
public class LayoutVerification extends Instrumentation {
    private File evidence;
    @Override public void onCreate(Bundle args){super.onCreate(args);start();}
    private void require(boolean ok,String message){if(!ok)throw new IllegalStateException(message);}
    private EditText input(View view){
        if(view instanceof EditText)return (EditText)view;
        if(view instanceof ViewGroup){ViewGroup group=(ViewGroup)view;for(int i=0;i<group.getChildCount();i++){EditText found=input(group.getChildAt(i));if(found!=null)return found;}}
        return null;
    }
    private void verify(Activity activity,String name,boolean keyboard)throws Exception{
        waitForIdleSync();SystemClock.sleep(700);
        View root=((ViewGroup)activity.findViewById(android.R.id.content)).getChildAt(0);
        require(root.getWidth()>0&&root.getHeight()>0,"Empty layout");
        if(android.os.Build.VERSION.SDK_INT>=30){
            WindowInsets insets=root.getRootWindowInsets();require(insets!=null,"Missing window insets");
            Insets safe=insets.getInsets(WindowInsets.Type.systemBars()|WindowInsets.Type.displayCutout()|WindowInsets.Type.ime());
            require(root.getPaddingLeft()>=safe.left&&root.getPaddingTop()>=safe.top&&root.getPaddingRight()>=safe.right&&root.getPaddingBottom()>=safe.bottom,"Content overlaps system bars/cutout/keyboard: "+name);
            if(keyboard)require(insets.isVisible(WindowInsets.Type.ime()),"Keyboard did not open");
        }
        Bitmap shot=getUiAutomation().takeScreenshot();require(shot!=null,"Screenshot unavailable");
        try(FileOutputStream out=new FileOutputStream(new File(evidence,name+".png"))){shot.compress(Bitmap.CompressFormat.PNG,100,out);}
    }
    @Override public void onStart(){Bundle result=new Bundle();try{
        Activity activity=startActivitySync(new Intent(getTargetContext(),MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        evidence=new File(activity.getExternalFilesDir(null),"layout-v11");evidence.mkdirs();
        verify(activity,"portrait",false);
        EditText field=input(activity.findViewById(android.R.id.content));require(field!=null,"No sign-in input");
        final Activity portrait=activity;
        runOnMainSync(()->{field.requestFocus();((InputMethodManager)portrait.getSystemService(Activity.INPUT_METHOD_SERVICE)).showSoftInput(field,InputMethodManager.SHOW_IMPLICIT);});
        SystemClock.sleep(1800);verify(activity,"portrait-keyboard",true);
        runOnMainSync(()->((InputMethodManager)portrait.getSystemService(Activity.INPUT_METHOD_SERVICE)).hideSoftInputFromWindow(field.getWindowToken(),0));
        SystemClock.sleep(500);
        ActivityMonitor monitor=addMonitor(MainActivity.class.getName(),null,false);
        runOnMainSync(()->portrait.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE));
        Activity rotated=monitor.waitForActivityWithTimeout(12000);removeMonitor(monitor);require(rotated!=null,"Landscape activity did not recreate");
        verify(rotated,"landscape",false);
        result.putString("stream","SIGNED_LAYOUT_PASS: portrait, IME avoidance, landscape recreation; no customer data or authentication bypass");
        runOnMainSync(rotated::finish);finish(Activity.RESULT_OK,result);
    }catch(Throwable failure){result.putString("stream","SIGNED_LAYOUT_FAIL: "+failure);finish(Activity.RESULT_CANCELED,result);}}
}
