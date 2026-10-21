package nz.kiwikind.broadband;

import android.app.Activity;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Button;
import android.widget.Toast;
import com.google.android.gms.ads.*;
import com.google.android.ump.*;
import java.util.Arrays;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Consented release banners; SDK-recognized test devices always retain test requests. */
final class BannerAds {
    private final Activity activity;
    private final ConsentInformation consent;
    private final Handler main=new Handler(Looper.getMainLooper());
    private final ExecutorService initialization=Executors.newSingleThreadExecutor();
    private ConsentRequestParameters parameters=new ConsentRequestParameters.Builder().build();
    private LinearLayout slot;
    private TextView status;
    private AdView banner;
    private boolean foreground,destroyed,consentPending,consentUpdated,initializing,formShowing;
    private boolean loaded;
    private int generation;

    BannerAds(Activity activity){
        this.activity=activity;consent=UserMessagingPlatform.getConsentInformation(activity);
        if(!BuildConfig.AD_TEST_DEVICE_IDS.isEmpty()){
            MobileAds.setRequestConfiguration(new RequestConfiguration.Builder()
                .setTestDeviceIds(Arrays.asList(BuildConfig.AD_TEST_DEVICE_IDS.split(","))).build());
        }
    }
    void show(LinearLayout target){
        leave();slot=target;final int token=generation;
        int gap=(int)(24*activity.getResources().getDisplayMetrics().density);
        target.setPadding(0,gap,0,gap);
        status=new TextView(activity);status.setText("Advertisement · Privacy choices apply.");target.addView(status);
        Button retry=new Button(activity);retry.setText("Retry advertisement");retry.setAllCaps(false);
        retry.setOnClickListener(v->{if(active(token)&&!consentPending&&!initializing&&banner==null)gatherConsent(token);});target.addView(retry);
        target.addOnAttachStateChangeListener(new View.OnAttachStateChangeListener(){
            public void onViewAttachedToWindow(View v){}
            public void onViewDetachedFromWindow(View v){if(slot==target)leave();}
        });
        target.post(()->{if(active(token))gatherConsent(token);});
    }
    private boolean active(int token){return !destroyed&&!activity.isFinishing()&&!activity.isDestroyed()
        &&foreground&&!formShowing&&token==generation&&slot!=null&&slot.isAttachedToWindow();}
    boolean testDevice(){return new AdRequest.Builder().build().isTestDevice(activity);}
    boolean liveAdsEnabled(){return BuildConfig.LIVE_ADS_ENABLED;}
    private void gatherConsent(int token){
        if(!active(token)||consentPending||initializing||banner!=null)return;
        if(!AdPolicy.canRequest(liveAdsEnabled(),testDevice())){
            status.setText("This development build requires an SDK test device for advertising.");return;
        }
        consentPending=true;consentUpdated=false;status.setText("Advertisement · Checking privacy choices…");
        consent.requestConsentInfoUpdate(activity,parameters,()->{
            consentPending=false;
            if(!active(token))return;
            formShowing=true;
            UserMessagingPlatform.loadAndShowConsentFormIfRequired(activity,error->{
                formShowing=false;
                if(!active(token))return;
                if(error!=null){status.setText("Advertising stayed off: privacy choices are unavailable. You can retry.");return;}
                consentUpdated=true;load(token);
            });
        },error->{consentPending=false;android.util.Log.w("KiwiKindAds","Consent update: "+error.getErrorCode()+" "+error.getMessage());if(active(token))status.setText("Advertising stayed off: consent service unavailable. You can retry.");});
    }
    private void load(int token){
        if(!active(token)||!consentUpdated||banner!=null||initializing)return;
        AdRequest request=new AdRequest.Builder().build();
        // The SDK preserves emulator/registered-device test status even in a live-capable release.
        if(!AdPolicy.canLoad(consent.canRequestAds(),request.isTestDevice(activity),foreground,slot.isAttachedToWindow(),liveAdsEnabled())){
            status.setText(consent.canRequestAds()?"This development build requires an SDK test device.":"Advertising stayed off: your privacy choices do not permit a request.");return;
        }
        initializing=true;
        initialization.execute(()->{try{MobileAds.initialize(activity.getApplicationContext(),result->main.post(()->{
            initializing=false;
            if(!active(token)||!consentUpdated||!consent.canRequestAds())return;
            AdRequest checkedRequest=new AdRequest.Builder().build();
            if(!AdPolicy.canRequest(liveAdsEnabled(),checkedRequest.isTestDevice(activity)))return;
            AdView view=new AdView(activity);banner=view;loaded=false;
            view.setAdUnitId(BuildConfig.ADMOB_BANNER_ID);
            int width=Math.max(1,(int)(slot.getWidth()/activity.getResources().getDisplayMetrics().density));
            view.setAdSize(AdSize.getCurrentOrientationAnchoredAdaptiveBannerAdSize(activity,width));
            view.setAdListener(new AdListener(){
                @Override public void onAdLoaded(){if(active(token)&&banner==view){loaded=true;status.setText(checkedRequest.isTestDevice(activity)?"Advertisement · Test ad · No advertising revenue is generated.":"Advertisement");}}
                @Override public void onAdFailedToLoad(LoadAdError error){if(active(token)&&banner==view){android.util.Log.w("KiwiKindAds","Banner load: "+error.getCode()+" "+error.getMessage());removeBanner();status.setText("Advertisement unavailable ("+error.getCode()+"). You can retry; account functions still work.");}}
            });
            LinearLayout.LayoutParams layout=new LinearLayout.LayoutParams(-1,-2);
            int gap=(int)(24*activity.getResources().getDisplayMetrics().density);
            layout.setMargins(0,gap,0,gap);slot.addView(view,layout);view.loadAd(checkedRequest);
        }));}catch(RuntimeException error){main.post(()->{
            initializing=false;
            if(active(token))status.setText("Advertising stayed off: SDK unavailable. You can retry.");
        });}});
    }
    void privacyChoices(){
        if(destroyed||activity.isFinishing()||formShowing||consentPending)return;
        removeBanner();consentUpdated=false;consentPending=true;
        consent.requestConsentInfoUpdate(activity,parameters,()->{
            consentPending=false;if(destroyed||activity.isFinishing()||activity.isDestroyed()||!foreground)return;
            if(consent.getPrivacyOptionsRequirementStatus()!=ConsentInformation.PrivacyOptionsRequirementStatus.REQUIRED){
                Toast.makeText(activity,"Google does not currently require an additional advertising privacy form for this device. Live ads remain disabled.",Toast.LENGTH_LONG).show();return;
            }
            formShowing=true;UserMessagingPlatform.showPrivacyOptionsForm(activity,error->{
                formShowing=false;consentUpdated=error==null;
                if(error!=null&&!destroyed)Toast.makeText(activity,"Privacy choices could not load. Ads remain off; retry when connected.",Toast.LENGTH_LONG).show();
                // No automatic ad reload after editing choices; explicit Home retry is required.
            });
        },error->{consentPending=false;if(!destroyed)Toast.makeText(activity,"Privacy choices could not load. Ads remain off; retry when connected.",Toast.LENGTH_LONG).show();});
    }
    void pause(){foreground=false;if(banner!=null)banner.pause();}
    void resume(){foreground=true;if(banner!=null)banner.resume();}
    private void removeBanner(){loaded=false;if(banner!=null){AdView old=banner;banner=null;if(old.getParent() instanceof LinearLayout)((LinearLayout)old.getParent()).removeView(old);old.destroy();}}
    private void leave(){generation++;removeBanner();slot=null;status=null;}
    void destroy(){destroyed=true;leave();initialization.shutdownNow();main.removeCallbacksAndMessages(null);}
}
