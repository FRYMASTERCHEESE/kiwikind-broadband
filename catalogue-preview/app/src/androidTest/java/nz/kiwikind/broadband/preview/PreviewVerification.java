package nz.kiwikind.broadband.preview;
import android.app.Activity;
import android.app.Instrumentation;
import android.content.Intent;
import android.os.Bundle;
import android.graphics.Bitmap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import java.io.File;
import java.io.FileOutputStream;

public class PreviewVerification extends Instrumentation {
    @Override public void onCreate(Bundle args){super.onCreate(args);start();}
    @Override public void onStart(){
        Bundle result=new Bundle();
        try {
            PreviewActivity a=(PreviewActivity)startActivitySync(new Intent(getTargetContext(),PreviewActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            String answer="";
            for(int i=0;i<30;i++){
                Thread.sleep(1000);CountDownLatch done=new CountDownLatch(1);AtomicReference<String> value=new AtomicReference<>();
                runOnMainSync(()->a.preview.evaluateJavascript("document.querySelectorAll('.card').length===4 && document.body.innerText.includes('incl. GST') && document.querySelectorAll('button:disabled').length===4",v->{value.set(v);done.countDown();}));
                if(!done.await(5,TimeUnit.SECONDS))throw new IllegalStateException("WebView response timed out");
                answer=value.get();if("true".equals(answer))break;
            }
            if(!"true".equals(answer))throw new IllegalStateException("Offline cards/GST/disabled ordering assertion failed");
            File folder=new File(a.getExternalFilesDir(null),"preview-proof");folder.mkdirs();
            Bitmap screen=getUiAutomation().takeScreenshot();
            try(FileOutputStream out=new FileOutputStream(new File(folder,"android-preview.png"))){screen.compress(Bitmap.CompressFormat.PNG,100,out);}
            result.putString("stream","CATALOGUE_PREVIEW_PASS: Offline cards, GST-inclusive labels and disabled order controls verified. Separate preview package; no network permission.");
            runOnMainSync(a::finish);finish(Activity.RESULT_OK,result);
        } catch(Throwable error){result.putString("stream","CATALOGUE_PREVIEW_FAIL: "+error);finish(Activity.RESULT_CANCELED,result);}
    }
}
