package nz.kiwikind.broadband;

import android.app.Activity;
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
    private LinearLayout content;
    private TextView feedback;
    private ProgressBar operationProgress;
    private boolean intake=false, signedIn=false, busy=false;
    private String exportData=null;
    private String orderKey=null;
    private long lastResumeCheck=0L;
    private Runnable refreshScreen=null;
    interface Task { JSONObject run() throws Exception; }
    interface Done { void accept(JSONObject data) throws Exception; }
    @Override public void onCreate(Bundle state){
        super.onCreate(state);api=new Api(BuildConfig.API_ORIGIN,this);
        if(android.os.Build.VERSION.SDK_INT>=33)getOnBackInvokedDispatcher().registerOnBackInvokedCallback(android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT,this::backToAccount);
        getWindow().getDecorView().setSystemUiVisibility(android.view.View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR|(android.os.Build.VERSION.SDK_INT>=27?android.view.View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR:0));
        LinearLayout root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setBackgroundColor(PAPER);
        root.setOnApplyWindowInsetsListener((v,insets)->{v.setPadding(insets.getSystemWindowInsetLeft(),insets.getSystemWindowInsetTop(),insets.getSystemWindowInsetRight(),insets.getSystemWindowInsetBottom());return insets;});
        LinearLayout header=new LinearLayout(this);header.setGravity(android.view.Gravity.CENTER_VERTICAL);header.setBackgroundColor(FOREST);header.setPadding(dp(18),dp(12),dp(18),dp(12));
        ImageView mark=new ImageView(this);mark.setImageResource(R.drawable.ic_launcher);mark.setImportantForAccessibility(android.view.View.IMPORTANT_FOR_ACCESSIBILITY_NO);header.addView(mark,new LinearLayout.LayoutParams(dp(44),dp(44)));
        TextView brand=new TextView(this);brand.setText("KiwiKind Broadband");brand.setTextSize(22);brand.setTypeface(android.graphics.Typeface.DEFAULT,android.graphics.Typeface.BOLD);brand.setTextColor(Color.WHITE);brand.setPadding(dp(10),0,0,0);header.addView(brand,new LinearLayout.LayoutParams(0,-2,1));root.addView(header);
        Button menu=new Button(this);menu.setText("Menu");menu.setAllCaps(false);menu.setMinHeight(dp(48));menu.setContentDescription("KiwiKind navigation");header.addView(menu);menu.setOnClickListener(v->{
            PopupMenu pages=new PopupMenu(this,menu);
            String[] labels={"Home","Our vision","My KiwiKind","Our journey","FAQs",signedIn?"My account":"Sign in","Sign up"};
            String[] ids={"home","why","mykiwikind","progress","questions","account","signup"};
            for(int i=0;i<labels.length;i++)pages.getMenu().add(0,i,i,labels[i]);
            pages.setOnMenuItemClickListener(item->{if(busy)return true;String page=ids[item.getItemId()];if(page.equals("account")){if(signedIn)home();else auth(false);}else if(page.equals("signup")){if(signedIn)home();else auth(true);}else publicPage(page);return true;});pages.show();
        });
        feedback=new TextView(this);feedback.setTextSize(13);feedback.setTextColor(FOREST);feedback.setBackgroundColor(MINT);feedback.setPadding(dp(22),dp(10),dp(22),dp(10));feedback.setAccessibilityLiveRegion(1);root.addView(feedback);
        operationProgress=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);operationProgress.setIndeterminate(true);operationProgress.setContentDescription("Connecting securely to KiwiKind");operationProgress.setVisibility(android.view.View.GONE);root.addView(operationProgress,new LinearLayout.LayoutParams(-1,dp(4)));
        ScrollView scroll=new ScrollView(this){@Override protected void onSizeChanged(int w,int h,int oldw,int oldh){super.onSizeChanged(w,h,oldw,oldh);int side=Math.max(dp(22),(w-dp(680))/2);content.setPadding(side,dp(12),side,dp(24));}};scroll.setFillViewport(true);content=new LinearLayout(this);content.setOrientation(LinearLayout.VERTICAL);content.setPadding(dp(22),dp(12),dp(22),dp(24));scroll.addView(content);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));setContentView(root);
        root.post(this::applySystemBarAppearance);
        if(!api.configured()){message("The Android shell is ready for backend configuration. Customer intake is closed.");auth(false);}
        else if(api.hasSession())connectAccount();
        else {auth(false);message("Ready to sign in. The free server may need time to wake up when you connect.");}
    }
    private void applySystemBarAppearance(){
        if(android.os.Build.VERSION.SDK_INT>=30){
            android.view.WindowInsetsController controller=getWindow().getInsetsController();
            if(controller!=null){int light=android.view.WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS|android.view.WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS;controller.setSystemBarsAppearance(light,light);}
        }
    }
    @Override public void onWindowFocusChanged(boolean hasFocus){super.onWindowFocusChanged(hasFocus);if(hasFocus)applySystemBarAppearance();}
    @Override protected void onResume(){
        super.onResume();
        // On returning from the browser, verify the saved session without interrupting active screens.
        long now=android.os.SystemClock.elapsedRealtime();
        if(api!=null && api.configured() && signedIn && !busy && now-lastResumeCheck>30000L){
            lastResumeCheck=now;
            run(()->api.call("me",null),r->{
                signedIn=true;
                if(refreshScreen!=null)refreshScreen.run();
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
                intake=r.optBoolean("intake_enabled");api.clear();signedIn=false;auth(false);message("Sign in to My KiwiKind. Customer intake remains closed.");
            }else{
                intake=r.optBoolean("intake_enabled");signedIn=true;accountHome(r.getJSONObject("account"));message("Account restored from KiwiKind server.");
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
            if(id.equals("home"))button("Discover our vision ↗",()->publicPage("why"));
            if(id.equals("home")&&BuildConfig.DEBUG&&BuildConfig.TEST_ADS){
                // A dedicated child detaches on navigation, invalidating delayed consent callbacks.
                LinearLayout adSlot=new LinearLayout(this);adSlot.setOrientation(LinearLayout.VERTICAL);
                button("Internal test ad preview",()->{try{Class.forName("nz.kiwikind.broadband.AdPreview").getMethod("show",Activity.class,LinearLayout.class).invoke(null,this,adSlot);}catch(Exception e){message("Test ad preview unavailable. Live ads remain off.");}});
                content.addView(adSlot,spaced());
            }
            if(id.equals("why"))button("Meet My KiwiKind",()->publicPage("mykiwikind"));
            if(id.equals("mykiwikind"))button("What happens next?",()->publicPage("progress"));
            button(signedIn?"My account":"Sign in",()->{if(signedIn)home();else auth(false);});
            button("Our vision",()->publicPage("why"));button("FAQs",()->publicPage("questions"));
            button("Privacy notice",()->privacyPage("/privacy/"));button("Terms",()->legal("terms"));
            paragraph("A kinder connection. In the making. 🇳🇿\n© 2026 KiwiKind Broadband · Pre-launch project · No broadband services currently offered.");
            message("KiwiKind Broadband · Public information · Pre-launch");
        }catch(Exception e){paragraph("Website information could not load.");button("Back to My KiwiKind",()->{if(signedIn)home();else auth(false);});}
    }
    private void backToAccount(){if(busy)return;if(signedIn)home();else auth(false);}
    // API 26–32 fallback; newer Android uses the gesture callback registered in onCreate.
    @android.annotation.SuppressLint("GestureBackNavigation")
    @Override public void onBackPressed(){backToAccount();}
    private JSONObject data(Object... pairs){JSONObject d=new JSONObject();try{for(int i=0;i<pairs.length;i+=2)d.put((String)pairs[i],pairs[i+1]);}catch(JSONException ignored){}return d;}
    private void run(Task task,Done done){if(busy)return;busy=true;operationProgress.setVisibility(android.view.View.VISIBLE);message("Connecting securely… The free server may take a minute to wake up.");worker.submit(()->{try{JSONObject result=task.run();runOnUiThread(()->{busy=false;operationProgress.setVisibility(android.view.View.GONE);if(isFinishing()||isDestroyed())return;message("Ready.");try{done.accept(result);}catch(Exception e){message("Could not display the result. Refresh and try again.");}});}catch(Exception e){runOnUiThread(()->{busy=false;operationProgress.setVisibility(android.view.View.GONE);if(!isFinishing()&&!isDestroyed()){
            if(e instanceof Api.SessionExpiredException){api.clear();signedIn=false;exportData=null;orderKey=null;auth(false);}
            message(e.getMessage()==null?"Connection failed. Try again.":e.getMessage());
        }});}});}
    private void legal(String hash){policyScreen(hash.equals("terms")?"terms":"privacy");}
    private void privacyPage(String path){
        policyScreen(path.contains("deletion")?"deletion":"privacy");
    }
    private void auth(boolean register){
        refreshScreen=null;
        content.removeAllViews();title(register?"Create your account":"A kinder connection.");landscape();paragraph("My KiwiKind · Pre-launch\nSign in to your existing account. Broadband requests and payments remain closed.");
        EditText email=field("Email",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS);
        EditText password=field("Password (at least 12 characters)",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);
        EditText referral=register?field("Referral code (optional; programme not open yet)",1):null;
        CheckBox consent=new CheckBox(this);consent.setText(R.string.account_consent);if(register)content.addView(consent);
        button(register?"Create account":"Sign in",()->{
            if(register&&!consent.isChecked()){message("Please read and accept the pre-launch terms.");return;}
            String e=email.getText().toString().trim(),p=password.getText().toString();password.setText("");
            run(()->api.call(register?"register":"login",data("email",e,"password",p,"consent_version",CONSENT,"referral_code",referral==null?"":referral.getText().toString().trim())),r->{if(register){message(r.optString("message"));}else{acceptLogin(r);}});
        }).setEnabled(api.configured()&&(!register||intake));
        Button googleButton=button("Sign in with Google",this::googleSignIn);
        googleButton.setEnabled(api.configured());
        googleButton.setTextColor(Color.WHITE);
        googleButton.setBackgroundTintList(android.content.res.ColorStateList.valueOf(FOREST));
        googleButton.setAllCaps(false);
        googleButton.setMinHeight((int)(52*getResources().getDisplayMetrics().density));
        if(register&&!intake)paragraph("Email registration remains closed during pre-launch.");
        button(register?"Back to sign in":"Create an account",()->auth(!register));
        button("Retry account connection",this::connectAccount).setEnabled(api.configured());
        button("Discover our vision ↗",()->publicPage("home"));
        button("Open My KiwiKind website",()->startActivity(new Intent(Intent.ACTION_VIEW,Uri.parse(BuildConfig.API_ORIGIN+"/#portal")))).setEnabled(api.configured());
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
                String kind=e.getClass().getSimpleName();
                if("GetCredentialCancellationException".equals(kind))message("Google account selection was cancelled. Tap Sign in with Google to try again.");
                else if("NoCredentialException".equals(kind))retryGoogleWithExplicitButton();
                else message("Android Google sign-in could not start ("+kind+"). Check the Android OAuth client package and signing SHA-1 in Google Cloud. Website sign-in is available below.");
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
                if("GetCredentialCancellationException".equals(e.getClass().getSimpleName()))
                    message("Google sign-in cancelled. Your saved login was kept.");
                else message("Google sign-in is unavailable ("+e.getClass().getSimpleName()+"). Check Google Play services and the app signing SHA-1; your saved login was kept.");
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
    private void acceptLogin(JSONObject account){signedIn=true;intake=account.optBoolean("intake_enabled");accountHome(account);}
    private void home(){
        if(api.configured()){run(()->api.call("me",null),this::accountHome);}else accountHome(new JSONObject());
    }
    private void accountHome(JSONObject account){
        refreshScreen=this::home;
        content.removeAllViews();title("My KiwiKind");landscape();paragraph("Kia ora, welcome home. 💚");
        if(account.has("email"))paragraph(account.optString("email"));
        paragraph("Your account, requests, support conversations and preferences are shared securely with the KiwiKind website. Email registration remains closed during pre-launch.");
        accountCard("My connection","No active service · View requests",this::orders);accountCard("My support","Support & complaints",this::tickets);accountCard("Billing","Payments disabled",()->run(()->api.call("invoices",null),r->{refreshScreen=null;content.removeAllViews();title("Billing");paragraph("Payments are disabled. No charges are being taken.");JSONArray a=r.optJSONArray("invoices");if(a==null||a.length()==0)paragraph("No invoices.");else for(int i=0;i<a.length();i++)paragraph(a.getJSONObject(i).toString());nav();}));
        button("Refresh account from website",()->run(()->api.call("me",null),r->{signedIn=true;accountHome(r);message("Account refreshed from KiwiKind server.");}));
        button("Download my account data",()->run(()->api.call("privacy/export",null),r->{exportData=r.toString(2);Intent intent=new Intent(Intent.ACTION_CREATE_DOCUMENT);intent.setType("application/json");intent.addCategory(Intent.CATEGORY_OPENABLE);intent.putExtra(Intent.EXTRA_TITLE,"kiwikind-data.json");startActivityForResult(intent,10);message("Choose where to save your private account export.");}));
        button("Request account deletion",()->deletionScreen(account.optBoolean("has_password",true)));
        button("Privacy & account correction",()->policyScreen("privacy"));
        accountCard("Invite friends & whānau","Referral preview · Rewards disabled",this::referralsScreen);
        accountCard("Account settings","Shared notification preferences",this::settingsScreen);
        button("Sign out",()->run(()->api.call("logout",data()),r->{api.clear();signedIn=false;exportData=null;orderKey=null;auth(false);message("Signed out.");}));
        message("Account connected · Pre-launch only");
    }
    private void orders(){run(()->api.call("orders",null),r->{
        refreshScreen=this::orders;content.removeAllViews();title("Broadband requests");JSONArray a=r.getJSONArray("orders");if(a.length()==0)paragraph("No requests yet.");
        for(int i=0;i<a.length();i++){JSONObject o=a.getJSONObject(i);paragraph(o.getString("address")+"\n"+o.getString("status")+"\n"+o.getString("id"));if(!o.getString("status").equals("cancelled"))button("Cancel this request",()->new AlertDialog.Builder(this).setMessage("Cancel this pending request?").setPositiveButton("Cancel request",(d,w)->run(()->api.call("orders/"+o.optString("id")+"/cancel",data()),x->orders())).setNegativeButton("Keep request",null).show());}
        button("New connection request",this::newOrder).setEnabled(intake);nav();message("Availability has not been checked.");
    });}
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
    @Override protected void onDestroy(){worker.shutdownNow();exportData=null;super.onDestroy();}
}
