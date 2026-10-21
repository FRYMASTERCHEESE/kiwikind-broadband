package nz.kiwikind.broadband.preview;

import android.app.Activity;
import android.os.Bundle;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.WebResourceRequest;
import android.widget.TextView;
import androidx.core.view.WindowCompat;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.core.graphics.Insets;
import java.nio.charset.StandardCharsets;

/** Offline design review only. No network permission, backend, accounts, ads or ordering. */
public class PreviewActivity extends Activity {
    WebView preview;
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        WindowCompat.enableEdgeToEdge(getWindow());
        preview = new WebView(this);
        preview.getSettings().setJavaScriptEnabled(true);
        preview.getSettings().setDomStorageEnabled(false);
        preview.getSettings().setAllowFileAccess(false);
        preview.getSettings().setAllowContentAccess(false);
        preview.getSettings().setBlockNetworkLoads(true);
        preview.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) { return true; }
        });
        ViewCompat.setOnApplyWindowInsetsListener(preview,(view,insets)->{
            Insets safe=insets.getInsets(WindowInsetsCompat.Type.systemBars()|WindowInsetsCompat.Type.displayCutout()|WindowInsetsCompat.Type.ime());
            view.setPadding(safe.left,safe.top,safe.right,safe.bottom);return insets;
        });
        setContentView(preview);
        try (java.io.InputStream stream=getAssets().open("catalogue.html")) {
            java.io.ByteArrayOutputStream bytes=new java.io.ByteArrayOutputStream();
            byte[] buffer=new byte[4096];int count;
            while((count=stream.read(buffer))!=-1)bytes.write(buffer,0,count);
            preview.loadDataWithBaseURL("https://preview.invalid/",new String(bytes.toByteArray(),StandardCharsets.UTF_8),"text/html","UTF-8",null);
        } catch (java.io.IOException error) {
            TextView message=new TextView(this);message.setText("Private preview data was not supplied. No customer services are available in this preview.");setContentView(message);
        }
    }
    @Override protected void onDestroy(){if(preview!=null){preview.destroy();preview=null;}super.onDestroy();}
}
