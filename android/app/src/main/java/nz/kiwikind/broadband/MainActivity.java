package nz.kiwikind.broadband;

import android.app.Activity;
import androidx.core.graphics.Insets;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.credentials.CredentialManager;
import androidx.credentials.GetCredentialRequest;
import androidx.credentials.GetCredentialResponse;
import androidx.credentials.CustomCredential;
import androidx.credentials.exceptions.GetCredentialException;
import androidx.credentials.CredentialManagerCallback;
import com.google.android.libraries.identity.googleid.GetGoogleIdOption;
import com.google.android.libraries.identity.googleid.GetSignInWithGoogleOption;
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential;
import android.app.AlertDialog;
import android.os.Bundle;
import android.content.Intent;
import android.net.Uri;
import android.graphics.Color;
import android.text.InputType;
import android.widget.*;
import org.json.*;
import java.util.UUID;
import java.util.concurrent.Executors;
import java.util.concurrent.ExecutorService;

public class MainActivity extends Activity {
    private static final String CONSENT="prelaunch-2026-10-16";
    private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private Api api;
    private BannerAds bannerAds;
    private LinearLayout content;
    private TextView feedback;
    private ProgressBar operationProgress;
    private Button recoveryButton;
    private boolean intake=false, registrationEnabled=false, signedIn=false, busy=false;
    private String exportData=null;
    private String orderKey=null;
    private long lastResumeCheck=0L;
    private Runnable refreshScreen=null;
    interface Task { JSONObject run() throws Exception; }
    interface Done { void accept(JSONObject data) throws Exception; }
    @Override public void onCreate(Bundle state){
        super.onCreate(state);WindowCompat.enableEdgeToEdge(getWindow());bannerAds=new BannerAds(this);api=new Api(BuildConfig.API_ORIGIN,this);
        if(android.os.Build.VERSION.SDK_INT>=33)getOnBackInvokedDispatcher().registerOnBackInvokedCallback(android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT,this::backToAccount);
        LinearLayout root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setBackgroundColor(PAPER);
        ViewCompat.setOnApplyWindowInsetsListener(root,(v,insets)->{
            Insets safe=insets.getInsets(WindowInsetsCompat.Type.systemBars()
                |WindowInsetsCompat.Type.displayCutout()|WindowInsetsCompat.Type.ime());
            v.setPadding(safe.left,safe.top,safe.right,safe.bottom);
            return insets;
        });
        LinearLayout header=new LinearLayout(this);header.setGravity(android.view.Gravity.CENTER_VERTICAL);header.setBackgroundColor(FOREST);header.setPadding(dp(18),dp(12),dp(18),dp(12));
        ImageView mark=new ImageView(this);mark.setImageResource(R.drawable.ic_launcher);mark.setImportantForAccessibility(android.view.View.IMPORTANT_FOR_ACCESSIBILITY_NO);header.addView(mark,new LinearLayout.LayoutParams(dp(44),dp(44)));
        TextView brand=new TextView(this);brand.setText("KiwiKind Broadband");brand.setTextSize(22);brand.setTypeface(android.graphics.Typeface.DEFAULT,android.graphics.Typeface.BOLD);brand.setTextColor(Color.WHITE);brand.setPadding(dp(10),0,0,0);header.addView(brand,new LinearLayout.LayoutParams(0,-2,1));root.addView(header);
        Button menu=new Button(this);menu.setText("Menu");menu.setAllCaps(false);menu.setMinHeight(dp(48));menu.setContentDescription("KiwiKind navigation");header.addView(menu);menu.setOnClickListener(v->{
            PopupMenu pages=new PopupMenu(this,menu);
            String[] labels={"Broadband plans","My broadband requests","Payment offers","Support messages","Home","Our vision","My KiwiKind","Our journey","FAQs",signedIn?"My account":"Sign in","Sign up"};
            String[] ids={"plans","orders","payments","support","home","why","mykiwikind","progress","questions","account","signup"};
            for(int i=0;i<labels.length;i++)pages.getMenu().add(0,i,i,labels[i]);
            pages.setOnMenuItemClickListener(item->{if(busy)return true;String page=ids[item.getItemId()];if(page.equals("plans"))broadbandPlans();
                else if(page.equals("orders")){if(signedIn)orders();else auth(false);}
                else if(page.equals("payments")){if(signedIn)liveBillingScreen();else auth(false);}
                else if(page.equals("support")){if(signedIn)tickets();else auth(false);}
                else if(page.equals("account")){if(signedIn)home();else auth(false);}
                else if(page.equals("signup")){if(signedIn)home();else auth(true);}
                else publicPage(page);return true;});pages.show();
        });
        feedback=new TextView(this);feedback.setTextSize(13);feedback.setTextColor(FOREST);feedback.setBackgroundColor(MINT);feedback.setPadding(dp(22),dp(10),dp(22),dp(10));feedback.setAccessibilityLiveRegion(1);root.addView(feedback);
        operationProgress=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);operationProgress.setIndeterminate(true);operationProgress.setContentDescription("Connecting securely to KiwiKind");operationProgress.setVisibility(android.view.View.GONE);root.addView(operationProgress,new LinearLayout.LayoutParams(-1,dp(4)));
        recoveryButton=new Button(this);recoveryButton.setText("Reconnect / refresh safely");recoveryButton.setAllCaps(false);recoveryButton.setMinHeight(dp(48));recoveryButton.setVisibility(android.view.View.GONE);root.addView(recoveryButton);
        // Retry only a read. Never replay a possibly completed order, message or payment.
        recoveryButton.setOnClickListener(v->{if(!busy){if(signedIn){if(refreshScreen!=null)refreshScreen.run();else home();}else connectAccount();}});
        ScrollView scroll=new ScrollView(this){@Override protected void onSizeChanged(int w,int h,int oldw,int oldh){super.onSizeChanged(w,h,oldw,oldh);int side=Math.max(dp(22),(w-dp(680))/2);content.setPadding(side,dp(12),side,dp(24));}};scroll.setFillViewport(true);content=new LinearLayout(this);content.setOrientation(LinearLayout.VERTICAL);content.setPadding(dp(22),dp(12),dp(22),dp(24));scroll.addView(content);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));setContentView(root);
        root.post(()->{ViewCompat.requestApplyInsets(root);applySystemBarAppearance();});
        if(!api.configured()){message("The Android shell is ready for backend configuration. Customer intake is closed.");auth(false);}
        else if(api.hasSession())connectAccount();
        else {auth(false);message("Ready to sign in. The free server may need time to wake up when you connect.");}
    }
    private void applySystemBarAppearance(){
        androidx.core.view.WindowInsetsControllerCompat controller=
            WindowCompat.getInsetsController(getWindow(),getWindow().getDecorView());
        controller.setAppearanceLightStatusBars(true);
        controller.setAppearanceLightNavigationBars(true);
    }
    @Override public void onWindowFocusChanged(boolean hasFocus){super.onWindowFocusChanged(hasFocus);if(hasFocus)applySystemBarAppearance();}
    @Override protected void onResume(){
        super.onResume();
        if(bannerAds!=null)bannerAds.resume();
        // On returning from the browser, verify the saved session without interrupting active screens.
        long now=android.os.SystemClock.elapsedRealtime();
        if(api!=null && api.configured() && signedIn && !busy && now-lastResumeCheck>30000L){
            lastResumeCheck=now;
            // Account screen refreshes already authenticate their own request.
            // Avoid a serial /me request before fetching the same screen again.
            if(refreshScreen!=null)refreshScreen.run();
            else run(()->api.call("me",null),r->{
                signedIn=true;
                message("Account connected to KiwiKind server.");
            });
        }
    }
    private void connectAccount(){loadingAccount();restoreSession();}
    private void loadingAccount(){
        content.removeAllViews();
        title("Restoring your account…");
        paragraph("Connecting securely to KiwiKind. The free server may take a minute to wake up.");
        ProgressBar spinner=new ProgressBar(this);
        spinner.setIndeterminate(true);
        content.addView(spinner);
        button("Retry connection",this::connectAccount);
        message("Checking your saved session…");
    }
    private void restoreSession(){
        // A server-verified session, not a local flag, determines whether to show the account.
        run(()->{
            try { return api.call("bootstrap",null); }
            catch(Api.SessionExpiredException e) { api.clear();return new JSONObject().put("session_unavailable",true); }
            catch(Exception e) { return new JSONObject().put("connection_unavailable",true); }
        },r->{
            if(r.optBoolean("connection_unavailable")){
                signedIn=false;auth(false);
                message("Could not reach KiwiKind. Your saved login was kept; try reopening when connected.");
            }else if(r.optBoolean("session_unavailable")){
                signedIn=false;auth(false);
                message("Sign in to My KiwiKind. Customer intake remains closed.");
            }else if(r.isNull("account")){
                intake=r.optBoolean("intake_enabled");registrationEnabled=r.optBoolean("registration_enabled");api.clear();signedIn=false;auth(false);message("Sign in to My KiwiKind. Customer intake remains closed.");
            }else{
                intake=r.optBoolean("intake_enabled");registrationEnabled=r.optBoolean("registration_enabled");signedIn=true;accountHome(r.getJSONObject("account"));message("Account restored from KiwiKind server.");
            }
        });
    }
    private void message(String text){feedback.setText(text);}
    // Tokens taken from the approved public website, revision dda5601.
    private static final int FOREST=Color.rgb(16,62,52), INK=Color.rgb(22,59,49), PAPER=Color.rgb(246,248,243), MINT=Color.rgb(231,243,232);
    private int dp(float value){return Math.round(value*getResources().getDisplayMetrics().density);}
    private android.graphics.drawable.GradientDrawable shape(int color,int radius){
        android.graphics.drawable.GradientDrawable d=new android.graphics.drawable.GradientDrawable();d.setColor(color);d.setCornerRadius(dp(radius));d.setStroke(dp(1),Color.rgb(217,233,222));return d;
    }
    private LinearLayout.LayoutParams spaced(){LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.bottomMargin=dp(12);return lp;}
    private void title(String text){TextView t=new TextView(this);t.setText(text);t.setTextColor(INK);t.setTextSize(30);t.setTypeface(android.graphics.Typeface.DEFAULT,android.graphics.Typeface.BOLD);t.setPadding(0,dp(20),0,dp(16));if(android.os.Build.VERSION.SDK_INT>=28)t.setAccessibilityHeading(true);content.addView(t);content.post(()->{if(content.getParent() instanceof ScrollView)((ScrollView)content.getParent()).scrollTo(0,0);});}
    private void paragraph(String text){TextView t=new TextView(this);t.setText(text);t.setTextColor(INK);t.setTextSize(16);t.setLineSpacing(dp(3),1);t.setPadding(dp(20),dp(18),dp(20),dp(18));t.setBackground(shape(Color.WHITE,22));content.addView(t,spaced());}
    private EditText field(String label,int type){TextView l=new TextView(this);l.setText(label);l.setTextColor(INK);l.setTextSize(14);l.setPadding(0,dp(8),0,dp(6));content.addView(l);EditText input=new EditText(this);input.setId(android.view.View.generateViewId());l.setLabelFor(input.getId());input.setInputType(type);input.setContentDescription(label);input.setTextColor(INK);input.setTextSize(16);input.setSingleLine();input.setMinHeight(dp(56));input.setPadding(dp(16),dp(12),dp(16),dp(12));android.graphics.drawable.StateListDrawable states=new android.graphics.drawable.StateListDrawable();android.graphics.drawable.GradientDrawable focused=shape(Color.WHITE,12);focused.setStroke(dp(3),FOREST);states.addState(new int[]{android.R.attr.state_focused},focused);states.addState(new int[]{},shape(Color.WHITE,12));input.setBackground(states);content.addView(input,spaced());return input;}
    private Button button(String text,Runnable action){Button b=new Button(this);b.setText(text);b.setTextSize(16);b.setAllCaps(false);b.setMinHeight(dp(56));b.setGravity(android.view.Gravity.CENTER);b.setPadding(dp(18),dp(14),dp(18),dp(14));
        b.setTextColor(new android.content.res.ColorStateList(new int[][]{new int[]{-android.R.attr.state_enabled},new int[]{}},new int[]{Color.rgb(75,96,83),Color.WHITE}));
        android.graphics.drawable.StateListDrawable states=new android.graphics.drawable.StateListDrawable();states.addState(new int[]{-android.R.attr.state_enabled},shape(Color.rgb(223,232,222),14));states.addState(new int[]{android.R.attr.state_pressed},shape(Color.rgb(35,87,72),14));states.addState(new int[]{android.R.attr.state_focused},shape(Color.rgb(35,87,72),14));states.addState(new int[]{},shape(FOREST,14));b.setBackground(states);content.addView(b,spaced());b.setOnClickListener(v->{if(!busy)action.run();});return b;}
    private void landscape(){
        android.view.View art=new android.view.View(this){
            private final android.graphics.Paint paint=new android.graphics.Paint(3);
            private final android.graphics.Path clip=new android.graphics.Path();
            @Override protected void onDraw(android.graphics.Canvas canvas){
                super.onDraw(canvas);float w=getWidth(),h=getHeight();canvas.save();clip.reset();clip.addRoundRect(0,0,w,h,dp(28),dp(28),android.graphics.Path.Direction.CW);canvas.clipPath(clip);canvas.drawColor(Color.rgb(198,229,207));
                paint.setColor(Color.rgb(249,217,136));canvas.drawCircle(w*.76f,h*.32f,h*.22f,paint);
                paint.setColor(Color.rgb(49,137,102));canvas.drawOval(-w*.4f,h*.51f,w*1.05f,h*1.6f,paint);
                paint.setColor(Color.rgb(29,101,78));canvas.drawOval(w*.2f,h*.65f,w*1.5f,h*1.7f,paint);
                paint.setColor(Color.WHITE);paint.setTextSize(dp(24));paint.setTypeface(android.graphics.Typeface.create("sans-serif",android.graphics.Typeface.BOLD));canvas.drawText("Made for Kiwis.",dp(22),h-dp(24),paint);canvas.restore();
            }
        };art.setContentDescription("Illustration of green hills and sunshine. Made for Kiwis.");LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,dp(170));lp.topMargin=dp(6);lp.bottomMargin=dp(16);content.addView(art,lp);
    }
    private void accountCard(String label,String detail,Runnable action){
        Button card=button(label+"\n"+detail+"  ›",action);card.setGravity(android.view.Gravity.START|android.view.Gravity.CENTER_VERTICAL);card.setTextColor(INK);
        card.setBackground(new android.graphics.drawable.RippleDrawable(android.content.res.ColorStateList.valueOf(Color.rgb(198,229,207)),shape(Color.WHITE,22),null));
    }
    /** Bundled verbatim public copy; no scripts, web cookies or private data in the preview. */
    private void publicPage(String id){
        refreshScreen=null;content.removeAllViews();
        try(java.io.InputStream stream=getAssets().open("website-content.json")){
            java.io.ByteArrayOutputStream bytes=new java.io.ByteArrayOutputStream();byte[] buffer=new byte[4096];int count;
            while((count=stream.read(buffer))!=-1)bytes.write(buffer,0,count);
            JSONArray sections=new JSONObject(bytes.toString("UTF-8")).getJSONArray("sections");
            for(int i=0;i<sections.length();i++){
                JSONObject section=sections.getJSONObject(i);if(!id.equals(section.getString("id")))continue;
                if(id.equals("mykiwikind"))paragraph("Public website · Dashboard design preview only. This screen does not load account information. Use My account to view your records.");
                JSONArray blocks=section.getJSONArray("blocks");
                for(int j=0;j<blocks.length();j++){
                    JSONObject block=blocks.getJSONObject(j);String kind=block.getString("kind"),text=block.getString("text");
                    if(kind.equals("faq")){
                        LinearLayout answer=new LinearLayout(this);answer.setOrientation(LinearLayout.VERTICAL);answer.setVisibility(android.view.View.GONE);
                        Button question=button(text,()->{});question.setOnClickListener(v->{boolean open=answer.getVisibility()!=android.view.View.VISIBLE;answer.setVisibility(open?android.view.View.VISIBLE:android.view.View.GONE);question.setContentDescription(text+(open?", expanded":", collapsed"));});
                        TextView body=new TextView(this);body.setText(block.getString("answer"));body.setTextColor(INK);body.setTextSize(16);body.setPadding(dp(18),dp(12),dp(18),dp(18));answer.addView(body);content.addView(answer,spaced());
                    }else if(kind.equals("card")){
                        String heading=block.optString("icon")+" "+text;
                        android.text.SpannableString card=new android.text.SpannableString(heading+"\n\n"+block.getString("answer"));
                        card.setSpan(new android.text.style.StyleSpan(android.graphics.Typeface.BOLD),0,heading.length(),0);
                        TextView body=new TextView(this);body.setText(card);body.setTextColor(INK);body.setTextSize(16);body.setLineSpacing(dp(3),1);body.setPadding(dp(24),dp(24),dp(24),dp(24));body.setBackground(shape(Color.WHITE,22));content.addView(body,spaced());
                    }else if(kind.startsWith("h"))title(text);else paragraph(text);
                    if(id.equals("home")&&kind.equals("h1"))landscape();
                }
            }
            if(id.equals("home"))button("Choose your broadband plan",this::broadbandPlans);
            if(AdPolicy.publicPlacement(id)){
                LinearLayout adSlot=new LinearLayout(this);adSlot.setOrientation(LinearLayout.VERTICAL);
                content.addView(adSlot,spaced());bannerAds.show(adSlot);
                button("Advertising privacy choices",()->bannerAds.privacyChoices());
            }
            if(id.equals("why"))button("Meet My KiwiKind",()->publicPage("mykiwikind"));
            if(id.equals("mykiwikind"))button("What happens next?",()->publicPage("progress"));
            button(signedIn?"My account":"Sign in",()->{if(signedIn)home();else auth(false);});
            button("Our vision",()->publicPage("why"));button("FAQs",()->publicPage("questions"));
            button("Privacy notice",()->privacyPage("/privacy/"));button("Terms",()->legal("terms"));
            paragraph("KiwiKind Broadband Limited · Broadband orders are subject to address and connection confirmation. Pay only after confirmation.");
            message("KiwiKind Broadband · Public information");
        }catch(Exception e){paragraph("Website information could not load.");button("Back to My KiwiKind",()->{if(signedIn)home();else auth(false);});}
    }
    private void backToAccount(){if(busy)return;if(signedIn)home();else auth(false);}
    // API 26–32 fallback; newer Android uses the gesture callback registered in onCreate.
    @android.annotation.SuppressLint("GestureBackNavigation")
    @Override public void onBackPressed(){backToAccount();}
    private JSONObject data(Object... pairs){JSONObject d=new JSONObject();try{for(int i=0;i<pairs.length;i+=2)d.put((String)pairs[i],pairs[i+1]);}catch(JSONException ignored){}return d;}
    private void run(Task task,Done done){if(busy)return;busy=true;recoveryButton.setVisibility(android.view.View.GONE);operationProgress.setVisibility(android.view.View.VISIBLE);message("Connecting securely… The free server may take a minute to wake up.");worker.submit(()->{try{JSONObject result=task.run();runOnUiThread(()->{busy=false;operationProgress.setVisibility(android.view.View.GONE);if(isFinishing()||isDestroyed())return;message("Ready.");try{done.accept(result);}catch(Exception e){message("Could not display the result. Refresh and try again.");recoveryButton.setVisibility(android.view.View.VISIBLE);}});}catch(Exception e){runOnUiThread(()->{busy=false;operationProgress.setVisibility(android.view.View.GONE);if(!isFinishing()&&!isDestroyed()){
            if(e instanceof Api.SessionExpiredException){api.clear();signedIn=false;exportData=null;orderKey=null;auth(false);}
            message(e.getMessage()==null?"Connection failed. Try again.":e.getMessage());
            recoveryButton.setVisibility(android.view.View.VISIBLE);
        }});}});}
    private void legal(String hash){policyScreen(hash.equals("terms")?"terms":"privacy");}
    private void privacyPage(String path){
        policyScreen(path.contains("deletion")?"deletion":"privacy");
    }
    private void auth(boolean register){
        refreshScreen=null;
        content.removeAllViews();title(register?"Create your account":"A kinder connection.");landscape();paragraph("Create a free account or sign in to choose a broadband plan. We confirm your address and connection details before payment. Your account, orders and payment offers are shared with the website.");
        EditText email=field("Email",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS);
        EditText password=field("Password (at least 12 characters)",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);
        EditText referral=register?field("Referral code (optional; programme not open yet)",1):null;
        CheckBox consent=new CheckBox(this);consent.setText(R.string.account_consent);if(register)content.addView(consent);
        button(register?"Create account":"Sign in",()->{
            if(register&&!consent.isChecked()){message("Please read and accept the pre-launch terms.");return;}
            String e=email.getText().toString().trim(),p=password.getText().toString();password.setText("");
            run(()->api.call(register?"register":"login",data("email",e,"password",p,"consent_version",CONSENT,"referral_code",referral==null?"":referral.getText().toString().trim())),r->{if(register){message(r.optString("message"));}else{acceptLogin(r);}});
        }).setEnabled(api.configured()&&(!register||registrationEnabled));
        Button googleButton=button("Sign in with Google",this::googleSignIn);
        googleButton.setEnabled(api.configured());
        googleButton.setTextColor(Color.WHITE);
        googleButton.setBackgroundTintList(android.content.res.ColorStateList.valueOf(FOREST));
        googleButton.setAllCaps(false);
        googleButton.setMinHeight((int)(52*getResources().getDisplayMetrics().density));
        if(register&&!registrationEnabled)paragraph("Email registration remains closed during pre-launch.");
        button(register?"Back to sign in":"Create an account",()->auth(!register));
        button("Retry account connection",this::connectAccount).setEnabled(api.configured());
        button("Browse broadband plans",this::broadbandPlans);
        button("Discover our vision ↗",()->publicPage("home"));
        button("Open My KiwiKind website",()->startActivity(new Intent(Intent.ACTION_VIEW,
            Uri.parse("https://frymastercheese.github.io/kiwikind-broadband-website/account.html#portal"))));
        button("Reset password",()->{
            String address=email.getText().toString().trim();
            if(!android.util.Patterns.EMAIL_ADDRESS.matcher(address).matches()){email.setError("Enter a valid email address");email.requestFocus();return;}
            run(()->api.call("password-reset",data("email",address)),r->message(r.optString("message")+" Open the email link in your browser, then return here to sign in."));
        }).setEnabled(api.configured());
        button("Privacy policy",()->privacyPage("/privacy/"));button("Account deletion information",()->privacyPage("/account-deletion/"));button("Pre-launch terms",()->legal("terms"));
    }
    private void googleSignIn(){
        if(BuildConfig.GOOGLE_WEB_CLIENT_ID.trim().isEmpty()){message("Google sign-in is not configured in this Android build. Use the website while setup is completed.");return;}
        message("Opening Google account chooser…");
        GetGoogleIdOption option=new GetGoogleIdOption.Builder()
            .setServerClientId(BuildConfig.GOOGLE_WEB_CLIENT_ID)
            .setFilterByAuthorizedAccounts(false)
            .build();
        GetCredentialRequest request=new GetCredentialRequest.Builder().addCredentialOption(option).build();
        CredentialManager.create(this).getCredentialAsync(this,request,null,this::runOnUiThread,new CredentialManagerCallback<GetCredentialResponse,GetCredentialException>(){
            @Override public void onResult(GetCredentialResponse response){
                if(!(response.getCredential() instanceof CustomCredential)){message("Google did not return a supported account.");return;}
                CustomCredential credential=(CustomCredential)response.getCredential();
                if(!GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL.equals(credential.getType())){message("Google did not return an ID token.");return;}
                try{
                    String token=GoogleIdTokenCredential.createFrom(credential.getData()).getIdToken();
                    run(()->api.call("google-login",data("id_token",token)),r->{acceptLogin(r);message("Signed in with Google.");});
                }catch(Exception e){message("Could not verify the Google account. Try again.");}
            }
            @Override public void onError(GetCredentialException e){
                if(e instanceof androidx.credentials.exceptions.GetCredentialCancellationException)message("Google account selection was cancelled. Tap Sign in with Google to try again.");
                else if(e instanceof androidx.credentials.exceptions.NoCredentialException)retryGoogleWithExplicitButton();
                else message("Android Google sign-in could not start. Check the Android OAuth client package and signing SHA-1 in Google Cloud. Website sign-in is available below.");
            }
        });
    }
    // Some devices return NoCredentialException for the general account chooser even when
    // a Google account is installed. The explicit Google button is a separate supported flow.
    private void retryGoogleWithExplicitButton(){
        message("Trying the Google sign-in button instead…");
        GetSignInWithGoogleOption option=new GetSignInWithGoogleOption.Builder(BuildConfig.GOOGLE_WEB_CLIENT_ID).build();
        GetCredentialRequest request=new GetCredentialRequest.Builder().addCredentialOption(option).build();
        CredentialManager.create(this).getCredentialAsync(this,request,null,this::runOnUiThread,new CredentialManagerCallback<GetCredentialResponse,GetCredentialException>(){
            @Override public void onResult(GetCredentialResponse response){
                if(!(response.getCredential() instanceof CustomCredential)){
                    message("Google did not return an account. Your saved session has not been deleted.");return;
                }
                CustomCredential credential=(CustomCredential)response.getCredential();
                if(!GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL.equals(credential.getType())){
                    message("Google did not return a supported ID token.");return;
                }
                try{
                    String token=GoogleIdTokenCredential.createFrom(credential.getData()).getIdToken();
                    run(()->api.call("google-login",data("id_token",token)),r->{acceptLogin(r);message("Signed in with Google.");});
                }catch(Exception e){message("Google sign-in could not be completed. Your saved login was kept.");}
            }
            @Override public void onError(GetCredentialException e){
                if(e instanceof androidx.credentials.exceptions.GetCredentialCancellationException)
                    message("Google sign-in cancelled. Your saved login was kept.");
                else message("Google sign-in is unavailable. Check Google Play services and the app signing SHA-1; your saved login was kept.");
            }
        });
    }
    private void nav(){button("Back to account",this::home);}
    private void policyScreen(String key){
        refreshScreen=null;content.removeAllViews();
        try(java.io.InputStream stream=getAssets().open("policy-content.json")){
            java.io.ByteArrayOutputStream out=new java.io.ByteArrayOutputStream();byte[] buffer=new byte[4096];int n;while((n=stream.read(buffer))!=-1)out.write(buffer,0,n);
            JSONArray blocks=new JSONObject(out.toString("UTF-8")).getJSONArray(key);
            for(int i=0;i<blocks.length();i++){JSONObject block=blocks.getJSONObject(i);if(block.getString("kind").startsWith("h"))title(block.getString("text"));else paragraph(block.getString("text"));}
        }catch(Exception e){title("Privacy and account help");paragraph("Contact kiwikindbroadband@gmail.com. Do not send passwords, login codes or identity documents.");}
        if(key.equals("privacy"))button("Advertising privacy choices",()->bannerAds.privacyChoices());
        if(signedIn)button("Request access or account correction",this::correctionScreen);
        if(signedIn)nav();else button("Back to sign in",()->auth(false));
        message("KiwiKind Broadband · Public policy · Available offline");
    }
    private void correctionScreen(){
        refreshScreen=null;content.removeAllViews();title("Privacy & account correction");paragraph("Tell us which account information needs review. Changes are reviewed manually. Do not include passwords, identity documents or payment details.");
        EditText body=field("Your access or correction request",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_FLAG_MULTI_LINE);body.setSingleLine(false);body.setMinLines(4);
        button("Send private request",()->run(()->api.call("tickets",data("subject","Account access or correction","category","privacy","body",body.getText().toString())),r->{tickets();}));nav();
    }
    private void deletionScreen(boolean hasPassword){
        refreshScreen=null;content.removeAllViews();title("Request account deletion");paragraph("Request manual review of your account and associated data. No records are deleted immediately. Any lawful retention will be explained. You can also contact kiwikindbroadband@gmail.com without signing in.");
        EditText password=hasPassword?field("Current password",129):null;
        CheckBox confirm=new CheckBox(this);confirm.setText("I want my account and associated data reviewed for deletion.");content.addView(confirm);
        button("Submit deletion request",()->{if(!confirm.isChecked()){message("Confirm that you want deletion review.");return;}String value=password==null?"":password.getText().toString();if(password!=null)password.setText("");run(()->api.call("privacy/deletion",data("password",value,"confirm",true)),r->message(r.optString("message")));});
        button("Read deletion policy",()->policyScreen("deletion"));nav();
    }
    private void referralsScreen(){run(()->api.call("referrals",null),this::renderReferrals);}
    private void renderReferrals(JSONObject result) throws Exception {
        refreshScreen=this::referralsScreen;content.removeAllViews();title("Invite friends & whānau");paragraph("Referral programme preview. Registration remains closed. No rewards, discounts or free broadband are promised.");
        String code=result.optString("code","");if(code.isEmpty()||code.equals("null"))button("Create my referral code",()->run(()->api.call("referrals",data()),this::renderReferrals));
        else{paragraph("Your code: "+code);String url=result.getString("share_url");paragraph(url);button("Share my referral link",()->{Intent send=new Intent(Intent.ACTION_SEND);send.setType("text/plain");send.putExtra(Intent.EXTRA_TEXT,"KiwiKind Broadband · Pre-launch referral preview. Registration and rewards are not open. "+url);startActivity(Intent.createChooser(send,"Share KiwiKind"));});}
        JSONArray history=result.getJSONArray("history");if(history.length()==0)paragraph("No referrals recorded.");for(int i=0;i<history.length();i++){JSONObject item=history.getJSONObject(i);paragraph(item.getString("status")+" · "+item.getString("created_at"));}nav();
    }
    private void settingsScreen(){run(()->api.call("preferences",null),r->{refreshScreen=this::settingsScreen;content.removeAllViews();title("Account settings & notifications");paragraph("Preferences use your shared KiwiKind account. Notification delivery and marketing are disabled; saving this preference does not enable push messages or emails.");
        CheckBox choice=new CheckBox(this);choice.setText("Account update notifications, when delivery becomes available");choice.setChecked(r.optBoolean("account_notifications"));content.addView(choice);
        button("Save preference",()->run(()->api.call("preferences",data("account_notifications",choice.isChecked())),s->message("Preference saved to your KiwiKind account. Delivery remains disabled.")));button("Review account details or request correction",this::correctionScreen);nav();});}
    private void acceptLogin(JSONObject account){signedIn=true;intake=account.optBoolean("intake_enabled");registrationEnabled=account.optBoolean("registration_enabled");accountHome(account);}
    private void home(){
        if(api.configured()){run(()->api.call("me",null),this::accountHome);}else accountHome(new JSONObject());
    }
    private void accountHome(JSONObject account){
        refreshScreen=this::home;
        content.removeAllViews();title("My KiwiKind");landscape();paragraph("Kia ora, welcome home. 💚");
        if(account.has("email"))paragraph(account.optString("email"));
        paragraph("Your account, broadband orders, support conversations and payment offers are shared securely with the KiwiKind website. Choose a plan, then pay after your address and connection details are confirmed.");
        paragraph("Step 1: Choose a plan. Step 2: Pick options. Step 3: Send your address. Step 4: Pay only after KiwiKind confirms your service.");
        accountCard("1 · Browse broadband plans","Fibre, copper, rural, wireless and mobile options",this::broadbandPlans);
        accountCard("2 · My broadband requests","Check address review and connection progress",this::orders);
        accountCard("3 · Payment offers","Review confirmed GST-inclusive prices and pay securely",this::liveBillingScreen);
        accountCard("4 · Support & complaints","Ask questions or report a problem",this::tickets);
        accountCard("Connection preparation","Manual availability and installation updates",this::connectionPreparation);
        button("Refresh account from website",()->run(()->api.call("me",null),r->{signedIn=true;accountHome(r);message("Account refreshed from KiwiKind server.");}));
        button("Download my account data",()->run(()->api.call("privacy/export",null),r->{exportData=r.toString(2);Intent intent=new Intent(Intent.ACTION_CREATE_DOCUMENT);intent.setType("application/json");intent.addCategory(Intent.CATEGORY_OPENABLE);intent.putExtra(Intent.EXTRA_TITLE,"kiwikind-data.json");startActivityForResult(intent,10);message("Choose where to save your private account export.");}));
        button("Request account deletion",()->deletionScreen(account.optBoolean("has_password",true)));
        button("Privacy & account correction",()->policyScreen("privacy"));
        accountCard("Invite friends & whānau","Referral preview · Rewards disabled",this::referralsScreen);
        accountCard("Account settings","Shared notification preferences",this::settingsScreen);
        button("Sign out",()->run(()->api.call("logout",data()),r->{api.clear();signedIn=false;exportData=null;orderKey=null;auth(false);message("Signed out.");}));
        message("Account connected · Pay after connection confirmation");
    }

    private void liveBillingScreen(){run(()->api.call("payments/summary",null),r->{
        refreshScreen=this::liveBillingScreen;content.removeAllViews();title("Payments");
        if(!"live".equals(r.optString("mode"))){paragraph("Unexpected payment mode. Nothing was submitted.");nav();return;}
        paragraph("Only approved offers assigned to your account can be paid. All displayed amounts include GST. Payment does not automatically activate broadband.");
        JSONArray agreements=r.optJSONArray("agreements");
        if(agreements==null||agreements.length()==0)paragraph("No approved payment offer is assigned to your account.");
        else for(int i=0;i<agreements.length();i++){
            JSONObject a=agreements.getJSONObject(i);String id=a.getString("id"),version=a.getString("terms_version");
            long monthlyCents=a.getLong("monthly_cents"),setupCents=a.getLong("setup_cents");
            if(monthlyCents<0||setupCents<0||monthlyCents>1200000||setupCents>1200000)throw new IllegalStateException("Invalid payment amount");
            String monthly=billingMoney(monthlyCents),setup=billingMoney(setupCents),status=a.getString("status");
            String terms=a.getString("service_terms");
            paragraph(a.getString("label")+"\n"+monthly+" per month plus "+setup+" setup once. First payment: "+billingMoney(monthlyCents+setupCents)+". GST included.\nThe totals already include exactly $3 monthly and $10 setup once, both including GST.\n"+terms+"\nPayment start: "+a.optString("bill_from")+". Status: "+status+(a.optBoolean("cancel_at_period_end")?" · cancellation requested":""));
            if(r.optBoolean("live_payments_enabled")&&a.optBoolean("ready_to_pay")&&"pending".equals(status))button("Continue to secure Stripe checkout",()->{
                new AlertDialog.Builder(this).setTitle("Confirm recurring payment")
                    .setMessage("I accept the displayed terms and authorise "+monthly+" each month plus "+setup+" once, including GST. My account email and agreement reference will be sent to Stripe. Payment does not automatically activate broadband.\n\n"+terms)
                    .setNegativeButton("Back",null).setPositiveButton("Agree and continue",(dialog,which)->run(
                        ()->api.call("payments/checkout",data("agreement_id",id,"terms_version",version,"accept_live_recurring",true)),reply->{
                            String url=reply.optString("url");
                            if(!reply.optBoolean("livemode")||!BillingUrls.isLiveCheckout(url)){message("Unrecognised payment destination. Nothing opened.");return;}
                            startActivity(new Intent(Intent.ACTION_VIEW,Uri.parse(url)));
                            message("Stripe checkout opened. Refresh after returning; a return page is not proof of payment.");
                        })).show();
            });
            if(a.optBoolean("can_manage")&&!a.optBoolean("cancel_at_period_end")&&!java.util.Arrays.asList("pending","canceled","incomplete_expired").contains(status))button("Stop future subscription payments",()->{
                new AlertDialog.Builder(this).setTitle("Stop future payments?")
                    .setMessage("Request cancellation at the current period end. Contact KiwiKind separately about broadband cancellation and contractual obligations.")
                    .setNegativeButton("Back",null).setPositiveButton("Stop future payments",(dialog,which)->run(
                        ()->api.call("payments/cancel",data("agreement_id",id,"accept_live_cancel",true)),reply->{message(reply.optString("message"));liveBillingScreen();})).show();
            });
            JSONArray invoices=a.optJSONArray("invoices");
            if(invoices!=null)for(int j=0;j<invoices.length();j++){
                JSONObject invoice=invoices.getJSONObject(j);
                paragraph("Invoice: "+billingMoney(invoice.getLong("amount_cents"))+" · "+invoice.getString("status")+" · refunded "+billingMoney(invoice.getLong("refunded_cents"))+(invoice.optString("dispute_status").isEmpty()?"":" · dispute "+invoice.optString("dispute_status")));
            }
        }
        if(!r.optBoolean("live_payments_enabled"))paragraph("New payments are paused. Existing payment records remain available.");
        button("Refresh payments",this::liveBillingScreen);button("Private sandbox testing",this::billingScreen);nav();
    });}

    private String billingMoney(long cents){return "NZ$"+java.math.BigDecimal.valueOf(cents,2).toPlainString();}
    private void billingScreen(){run(()->api.call("billing/summary",null),r->{
        refreshScreen=this::billingScreen;content.removeAllViews();title("Billing status");
        paragraph("TEST ONLY. This screen uses separate test billing and does not create a broadband order. Use only Stripe test payment details. Your account email, test reference and agreed amounts are sent to Stripe only after confirmation. A successful test does not connect broadband.");
        if(!"sandbox_only".equals(r.optString("mode"))||r.optBoolean("live_payments_enabled",true)){
            paragraph("Unexpected billing mode. Nothing was submitted.");nav();return;
        }
        JSONArray agreements=r.optJSONArray("agreements");
        if(agreements==null||agreements.length()==0)paragraph("No reviewed test agreements are assigned to this account.");
        else for(int i=0;i<agreements.length();i++){
            JSONObject a=agreements.getJSONObject(i);String id=a.getString("id"),version=a.getString("terms_version");
            String monthly=billingMoney(a.getLong("monthly_cents")),setup=billingMoney(a.getLong("setup_cents"));
            String total=billingMoney(a.getLong("monthly_cents")+a.getLong("setup_cents"));
            String status=a.getString("status");
            paragraph(a.getString("label")+"\n"+monthly+" per month, plus "+setup+" once. Initial test total: "+total+".\nTest status: "+status+(a.optBoolean("cancel_at_period_end")?" (cancellation at period end requested)":""));
            if(r.optBoolean("test_enabled")&&"pending".equals(status))button("Open Stripe test checkout",()->{
                new AlertDialog.Builder(this).setTitle("Confirm test recurring billing")
                    .setMessage("I agree to test "+monthly+" each month plus "+setup+" once, using test payment details only. No actual broadband service is ordered.")
                    .setNegativeButton("Back",null).setPositiveButton("Agree and test",(dialog,which)->run(
                        ()->api.call("billing/checkout",data("agreement_id",id,"terms_version",version,"accept_test_recurring",true)),reply->{
                            String url=reply.optString("url");
                            if(!reply.optBoolean("test_only")||!BillingUrls.isTestCheckout(url)){message("Unrecognised test checkout address. Nothing opened.");return;}
                            startActivity(new Intent(Intent.ACTION_VIEW,Uri.parse(url)));
                            message("Stripe test checkout opened. Refresh billing after returning; returning alone is not proof of payment.");
                        })).show();
            });
            if(r.optBoolean("test_enabled")&&!a.optBoolean("cancel_at_period_end")&&!java.util.Arrays.asList("pending","canceled","incomplete_expired").contains(status))button("Cancel test subscription",()->{
                new AlertDialog.Builder(this).setTitle("Cancel test subscription?")
                    .setMessage("Request cancellation at the current period end. This does not cancel any actual broadband service.")
                    .setNegativeButton("Keep test",null).setPositiveButton("Cancel test",(dialog,which)->run(
                        ()->api.call("billing/cancel",data("agreement_id",id,"accept_test_cancel",true)),reply->{message(reply.optString("message"));billingScreen();})).show();
            });
            JSONArray invoices=a.optJSONArray("invoices");
            if(invoices!=null)for(int j=0;j<invoices.length();j++){
                JSONObject invoice=invoices.getJSONObject(j);
                paragraph(BillingDisplay.invoiceLabel(invoice.getString("status"),
                    invoice.getLong("amount_cents"),invoice.getLong("refunded_cents"),
                    invoice.optString("dispute_status")));
            }
        }
        if(!r.optBoolean("test_enabled"))paragraph("Payment testing is not enabled for this account. No payment is due here.");
        button("Refresh billing status",this::billingScreen);nav();
    });}
    private void connectionPreparation(){run(()->api.call("connection-progress",null),r->{
        refreshScreen=this::connectionPreparation;content.removeAllViews();title("Connection preparation");
        paragraph("Your broadband order is reviewed before payment. Confirmed offers appear under Billing. Payment does not automatically activate the connection.");
        int count=0;
        for(String group:new String[]{"orders","faults"}){
            JSONArray records=r.optJSONArray(group);if(records==null)continue;
            for(int i=0;i<records.length();i++){JSONObject item=records.getJSONObject(i);count++;
                paragraph(PreparationStatus.label(item.optString("stage"))+"\n"+item.optString(group.equals("orders")?"request_id":"ticket_id")+"\nUpdated "+item.optString("updated_at"));
            }
        }
        if(count==0)paragraph("No preparation updates yet.");
        button("Refresh preparation",this::connectionPreparation);nav();
    });}
    private void orders(){run(()->api.call("orders",null),r->{
        refreshScreen=this::orders;content.removeAllViews();title("Broadband orders");JSONArray a=r.getJSONArray("orders");if(a.length()==0)paragraph("No orders yet.");
        for(int i=0;i<a.length();i++){
            JSONObject o=a.getJSONObject(i);paragraph(o.getString("address")+"\n"+o.getString("status")+"\n"+o.getString("id"));
            if(o.has("broadband")){showBroadbandQuote(o.getJSONObject("broadband"));if(!o.getString("status").equals("cancelled"))paragraph(o.optBoolean("payment_offer_available")?"Your final offer is available under Billing. Review it before payment.":"Awaiting address and connection confirmation. No payment is due yet.");}
            if(!o.getString("status").equals("cancelled")&&o.optBoolean("can_cancel_request",true))button("Cancel this request",()->new AlertDialog.Builder(this).setMessage("Cancel this pending request?").setPositiveButton("Cancel request",(d,w)->run(()->api.call("orders/"+o.optString("id")+"/cancel",data()),x->orders())).setNegativeButton("Keep request",null).show());
        }
        button("Choose a broadband plan",this::broadbandPlans);button("View confirmed payment offers",this::liveBillingScreen);nav();message("Your broadband orders");
    });}
    private void broadbandPlans(){run(()->api.call("broadband/catalogue",null),r->{
        refreshScreen=this::broadbandPlans;content.removeAllViews();title("Broadband plans");
        paragraph("Step 1 of 4: choose a type of broadband. Next pick your speed and extras, send an address, and pay only after owner confirmation. Prices include GST and the $3 monthly plus $10 setup additions exactly once.");
        if(signedIn)button("Track my existing requests",this::orders);
        JSONArray products=r.getJSONArray("products");String consent=r.getString("consent_version");
        if(products.length()==0)paragraph("Broadband plans are temporarily unavailable. Contact KiwiKind.");
        EditText search=field("Find broadband by type (fibre, rural, wireless or mobile)",
            InputType.TYPE_CLASS_TEXT);
        java.util.ArrayList<String> searchTexts=new java.util.ArrayList<>();
        java.util.ArrayList<android.view.View[]> productViews=new java.util.ArrayList<>();
        for(int i=0;i<products.length();i++){
            JSONObject p=products.getJSONObject(i);
            int before=content.getChildCount();
            title(p.getString("name"));
            paragraph("Starting from "+billingMoney(p.getLong("headline_monthly_cents"))+" per month, including GST.\n"+p.optString("headline_note")+"\n"+p.getString("description"));
            button("Choose options",()->configureBroadband(p,consent));
            int after=content.getChildCount();
            android.view.View[] group=new android.view.View[after-before];
            for(int j=0;j<group.length;j++)group[j]=content.getChildAt(before+j);
            productViews.add(group);
            searchTexts.add((p.getString("name")+" "+p.getString("description")).toLowerCase(java.util.Locale.ROOT));
        }
        search.addTextChangedListener(new android.text.TextWatcher(){
            @Override public void beforeTextChanged(CharSequence s,int start,int count,int after){}
            @Override public void onTextChanged(CharSequence s,int start,int before,int count){
                String query=s.toString().trim().toLowerCase(java.util.Locale.ROOT);
                for(int i=0;i<productViews.size();i++){
                    int visibility=searchTexts.get(i).contains(query)?android.view.View.VISIBLE:android.view.View.GONE;
                    for(android.view.View view:productViews.get(i))view.setVisibility(visibility);
                }
            }
            @Override public void afterTextChanged(android.text.Editable e){}
        });
        if(signedIn)nav();else button("Sign in",()->auth(false));
    });}
    private void configureBroadband(JSONObject product,String consent){
        refreshScreen=null;content.removeAllViews();title(product.optString("name"));
        paragraph("Step 2 of 4: choose your options, then review your exact GST-inclusive price. You will not be charged here.");
        paragraph(product.optString("description"));
        JSONArray groups=product.optJSONArray("groups");if(groups==null)return;
        Spinner[] choices=new Spinner[groups.length()];
        try{
            for(int i=0;i<groups.length();i++){
                JSONObject group=groups.getJSONObject(i);paragraph(group.getString("label"));
                JSONArray options=group.getJSONArray("options");String[] labels=new String[options.length()];
                for(int j=0;j<options.length();j++)labels[j]=options.getJSONObject(j).getString("name");
                Spinner select=new Spinner(this);select.setContentDescription(group.getString("label"));select.setMinimumHeight(dp(56));
                select.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,labels));content.addView(select,spaced());choices[i]=select;
            }
            button("Review price and order",()->{
                java.util.ArrayList<String> values=new java.util.ArrayList<>();
                try{for(int i=0;i<choices.length;i++)values.add(groups.getJSONObject(i).getJSONArray("options").getJSONObject(choices[i].getSelectedItemPosition()).getString("id"));}
                catch(JSONException e){message("Choose each option again.");return;}
                String query="broadband/quote?product="+Uri.encode(product.optString("id"))+"&options="+Uri.encode(String.join(",",values));
                run(()->api.call(query,null),q->broadbandOrderForm(q,consent,product));
            });
            button("Back to plans",this::broadbandPlans);
        }catch(JSONException e){message("The plan could not load. Refresh the catalogue.");}
    }
    private void showBroadbandQuote(JSONObject q) throws JSONException {
        StringBuilder text=new StringBuilder(q.getString("name"));JSONArray options=q.getJSONArray("options");
        for(int i=0;i<options.length();i++){JSONObject o=options.getJSONObject(i);text.append("\n").append(o.getString("group")).append(": ").append(o.getString("name"));}
        text.append("\n\n").append(billingMoney(q.getLong("monthly_cents"))).append(" per month, including GST.\nSetup once: ")
            .append(q.isNull("setup_cents")?"to confirm":billingMoney(q.getLong("setup_cents")))
            .append("\nFirst month + setup: ").append(q.isNull("first_invoice_cents")?"to confirm":billingMoney(q.getLong("first_invoice_cents")))
            .append("\nThe totals include exactly $3 monthly and $10 setup once, both including GST.");
        JSONArray usage=q.getJSONArray("usage");for(int i=0;i<usage.length();i++)text.append("\n").append(usage.getString(i));
        paragraph(text.toString());
    }
    private void broadbandOrderForm(JSONObject q,String consent,JSONObject product) throws JSONException {
        refreshScreen=null;content.removeAllViews();title("Review your broadband order");
        paragraph("Step 3 of 4: send your NZ service address. Step 4 is payment only after we confirm availability, setup fees, and final terms.");
        showBroadbandQuote(q);
        paragraph("Nothing is charged now. We confirm your address and connection details, then your final offer appears under Billing for acceptance and secure Stripe payment.");
        if(!signedIn){paragraph("Sign in to submit your order. You can return to the same plan in My KiwiKind after sign-in.");
            button("Sign in to order",()->auth(false));button("Back to plans",this::broadbandPlans);return;}
        EditText name=field("Contact name",InputType.TYPE_CLASS_TEXT),address=field("Full NZ service address",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_POSTAL_ADDRESS),postcode=field("Four-digit postcode",InputType.TYPE_CLASS_NUMBER),phone=field("Phone (optional)",InputType.TYPE_CLASS_PHONE);
        CheckBox accept=new CheckBox(this);accept.setText("I understand availability and connection details must be confirmed before payment. I have read the order terms and privacy notice. This submission does not activate service.");content.addView(accept,spaced());
        String key=UUID.randomUUID().toString();JSONObject[] pending={null};
        button("Submit order for confirmation",()->{
            if(!accept.isChecked()){message("Read and accept the order review information first.");return;}
            if(pending[0]==null){
                String contact=name.getText().toString().trim(),street=address.getText().toString().trim(),number=phone.getText().toString().trim();
                if(contact.isEmpty()||contact.length()>100||street.length()<8||street.length()>300||!postcode.getText().toString().matches("[0-9]{4}")||(!number.isEmpty()&&!number.matches("[+0-9 ()-]{6,25}"))){message("Enter a contact name, full address, four-digit postcode and valid phone number (or leave phone blank).");return;}
                pending[0]=data("product_id",q.optString("product_id"),"selections",q.optJSONArray("selections"),"quote_version",q.optString("quote_version"),"consent_version",consent,"accept_review",true,"idempotency_key",key,"contact_name",name.getText().toString().trim(),"address",address.getText().toString().trim(),"postcode",postcode.getText().toString(),"phone",phone.getText().toString().trim());
                for(EditText field:new EditText[]{name,address,postcode,phone})field.setEnabled(false);accept.setEnabled(false);
            }
            run(()->api.call("broadband/orders",pending[0]),r->{content.removeAllViews();title("Order received");paragraph(r.getString("message"));paragraph("Order reference: "+r.getString("id"));button("View my broadband orders",this::orders);nav();});
        });
        button("Order terms",()->startActivity(new Intent(Intent.ACTION_VIEW,Uri.parse("https://frymastercheese.github.io/kiwikind-broadband-website/terms.html"))));
        button("Privacy notice",()->startActivity(new Intent(Intent.ACTION_VIEW,Uri.parse("https://frymastercheese.github.io/kiwikind-broadband-website/privacy.html"))));
        button("View existing orders before retrying",this::orders);
        button("Change plan options",()->configureBroadband(product,consent));
    }
    private void newOrder(){
        refreshScreen=null;
        content.removeAllViews();title("Request a connection");paragraph("No supplier order, price, installation date or payment is authorised. Do not cancel your current broadband.");
        EditText name=field("Contact name",1),address=field("Full NZ service address",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_POSTAL_ADDRESS),postcode=field("Four-digit postcode",2),phone=field("Phone (optional)",3);
        CheckBox c=new CheckBox(this);c.setText(R.string.request_consent);content.addView(c);
        orderKey=UUID.randomUUID().toString();
        button("Send request",()->{if(!c.isChecked()){message("Please accept the request terms.");return;}JSONObject d=data("contact_name",name.getText().toString(),"address",address.getText().toString(),"postcode",postcode.getText().toString(),"phone",phone.getText().toString(),"consent_version",CONSENT,"idempotency_key",orderKey);run(()->api.call("orders",d),r->{orderKey=null;orders();});});button("Read request terms",()->legal("terms"));nav();
    }
    private void tickets(){run(()->api.call("tickets",null),r->{
        refreshScreen=this::tickets;content.removeAllViews();title("Support & complaints");paragraph("No response time is promised during pre-launch. This is not an emergency service.");JSONArray a=r.getJSONArray("tickets");if(a.length()==0)paragraph("No conversations yet.");
        for(int i=0;i<a.length();i++){JSONObject t=a.getJSONObject(i);button(t.getString("subject")+" · "+t.getString("status"),()->conversation(t.optString("id")));}
        button("Start a conversation",this::newTicket);nav();message("Your conversations");
    });}
    private void newTicket(){refreshScreen=null;content.removeAllViews();title("How can we help?");paragraph("Do not include payment card details, identity documents or health information.");EditText subject=field("Subject",1);Spinner category=new Spinner(this);category.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,new String[]{"support","complaint","privacy"}));category.setContentDescription("Topic");content.addView(category);EditText body=field("Message",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_FLAG_MULTI_LINE);body.setSingleLine(false);body.setMinLines(4);button("Send message",()->run(()->api.call("tickets",data("subject",subject.getText().toString(),"category",category.getSelectedItem().toString(),"body",body.getText().toString())),r->tickets()));nav();}
    private void conversation(String id){run(()->api.call("tickets/"+id+"/messages",null),r->{refreshScreen=null;content.removeAllViews();title("Conversation");JSONArray a=r.getJSONArray("messages");for(int i=0;i<a.length();i++){JSONObject m=a.getJSONObject(i);paragraph((m.optBoolean("from_support")?"Support: ":"You: ")+m.getString("body"));}EditText reply=field("Your reply",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_FLAG_MULTI_LINE);reply.setSingleLine(false);button("Refresh conversation",()->conversation(id));button("Send reply",()->run(()->api.call("tickets/"+id+"/messages",data("body",reply.getText().toString())),x->conversation(id)));nav();message("Your conversation");});}
    @Override protected void onActivityResult(int request,int result,Intent intent){super.onActivityResult(request,result,intent);if(request==10){if(result==RESULT_OK&&intent!=null&&intent.getData()!=null&&exportData!=null){try(var out=getContentResolver().openOutputStream(intent.getData())){if(out!=null){out.write(exportData.getBytes(java.nio.charset.StandardCharsets.UTF_8));message("Export saved.");}}catch(Exception e){message("Could not save export.");}}exportData=null;}}
    @Override protected void onPause(){if(bannerAds!=null)bannerAds.pause();super.onPause();}
    @Override protected void onDestroy(){if(bannerAds!=null)bannerAds.destroy();worker.shutdownNow();exportData=null;super.onDestroy();}
}
