package nz.kiwikind.broadband;
import android.app.Activity;
import android.widget.LinearLayout;
import android.widget.TextView;
import com.google.android.gms.ads.*;
import com.google.android.ump.*;

/** Included only with -PKIWIKIND_TEST_ADS=true in an internal debug build. */
public final class AdPreview {
    public static void show(Activity activity,LinearLayout container){
        if(container.getTag()!=null)return;
        container.setTag("test-ad-requested");
        TextView status=new TextView(activity);status.setText("Internal test advertising · Checking consent…");container.addView(status);
        ConsentInformation consent=UserMessagingPlatform.getConsentInformation(activity);
        consent.requestConsentInfoUpdate(activity,new ConsentRequestParameters.Builder().build(),()->{
            if(!active(activity,container))return;
            UserMessagingPlatform.loadAndShowConsentFormIfRequired(activity,error->{
                if(!active(activity,container))return;
                if(error!=null||!consent.canRequestAds()){status.setText("Test advertising stayed off: consent configuration is not ready.");return;}
                MobileAds.initialize(activity,initialization->activity.runOnUiThread(()->{
                    if(!active(activity,container))return;
                    AdView ad=new AdView(activity);ad.setAdUnitId("ca-app-pub-3940256099942544/9214589741");
                    int width=Math.max(200,(int)(container.getWidth()/activity.getResources().getDisplayMetrics().density));
                    ad.setAdSize(AdSize.getCurrentOrientationAnchoredAdaptiveBannerAdSize(activity,width));
                    container.addView(ad);status.setText("Advertisement · Official Google test unit");
                    ad.addOnAttachStateChangeListener(new android.view.View.OnAttachStateChangeListener(){public void onViewAttachedToWindow(android.view.View v){}public void onViewDetachedFromWindow(android.view.View v){ad.destroy();}});
                    ad.loadAd(new AdRequest.Builder().build());
                }));
            });},error->{if(active(activity,container))status.setText("Test advertising stayed off: consent service unavailable.");});
    }
    private static boolean active(Activity activity,LinearLayout container){
        return !activity.isFinishing()&&!activity.isDestroyed()&&container.isAttachedToWindow();
    }
}
