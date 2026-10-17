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
    private boolean intake=false, signedIn=false, busy=false;
    private String exportData=null;
    private String orderKey=null;
    private long lastResumeCheck=0L;
    private Runnable refreshScreen=null;
    interface Task { JSONObject run() throws Exception; }
    interface Done { void accept(JSONObject data) throws Exception; }
    @Override public void onCreate(Bundle state){
        super.onCreate(state);api=new Api(BuildConfig.API_ORIGIN,this);
        getWindow().getDecorView().setSystemUiVisibility(android.view.View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR|(android.os.Build.VERSION.SDK_INT>=27?android.view.View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR:0));
        LinearLayout root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setBackgroundColor(PAPER);
        root.setOnApplyWindowInsetsListener((v,insets)->{v.setPadding(insets.getSystemWindowInsetLeft(),insets.getSystemWindowInsetTop(),insets.getSystemWindowInsetRight(),insets.getSystemWindowInsetBottom());return insets;});
        LinearLayout header=new LinearLayout(this);header.setGravity(android.view.Gravity.CENTER_VERTICAL);header.setBackgroundColor(FOREST);header.setPadding(dp(18),dp(12),dp(18),dp(12));
        ImageView mark=new ImageView(this);mark.setImageResource(R.drawable.ic_launcher);mark.setImportantForAccessibility(android.view.View.IMPORTANT_FOR_ACCESSIBILITY_NO);header.addView(mark,new LinearLayout.LayoutParams(dp(44),dp(44)));
        TextView brand=new TextView(this);brand.setText("KiwiKind Broadband");brand.setTextSize(22);brand.setTypeface(android.graphics.Typeface.DEFAULT,android.graphics.Typeface.BOLD);brand.setTextColor(Color.WHITE);brand.setPadding(dp(10),0,0,0);header.addView(brand,new LinearLayout.LayoutParams(0,-2,1));root.addView(header);
        feedback=new TextView(this);feedback.setTextSize(13);feedback.setTextColor(FOREST);feedback.setBackgroundColor(MINT);feedback.setPadding(dp(22),dp(10),dp(22),dp(10));feedback.setAccessibilityLiveRegion(1);root.addView(feedback);
        ScrollView scroll=new ScrollView(this){@Override protected void onSizeChanged(int w,int h,int oldw,int oldh){super.onSizeChanged(w,h,oldw,oldh);int side=Math.max(dp(22),(w-dp(680))/2);content.setPadding(side,dp(12),side,dp(24));}};scroll.setFillViewport(true);content=new LinearLayout(this);content.setOrientation(LinearLayout.VERTICAL);content.setPadding(dp(22),dp(12),dp(22),dp(24));scroll.addView(content);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));setContentView(root);
        if(!api.configured()){message("The Android shell is ready for backend configuration. Customer intake is closed.");auth(false);}
        else connectAccount();
    }
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
    private void connectAccount(){loadingAccount();run(()->api.call("status",null),s->{intake=s.optBoolean("intake_enabled");restoreSession();});}
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
            try { return api.call("me",null); }
            catch(Api.SessionExpiredException e) { api.clear();return new JSONObject().put("session_unavailable",true); }
            catch(Exception e) { return new JSONObject().put("connection_unavailable",true); }
        },r->{
            if(r.optBoolean("connection_unavailable")){
                signedIn=false;auth(false);
                message("Could not reach KiwiKind. Your saved login was kept; try reopening when connected.");
            }else if(r.optBoolean("session_unavailable")){
                signedIn=false;auth(false);
                message("Sign in to My KiwiKind. Customer intake remains closed.");
            }else{
                signedIn=true;home();message("Account restored from KiwiKind server.");
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
    private JSONObject data(Object... pairs){JSONObject d=new JSONObject();try{for(int i=0;i<pairs.length;i+=2)d.put((String)pairs[i],pairs[i+1]);}catch(JSONException ignored){}return d;}
    private void run(Task task,Done done){if(busy)return;busy=true;message("Working…");worker.submit(()->{try{JSONObject result=task.run();runOnUiThread(()->{busy=false;if(isFinishing()||isDestroyed())return;try{done.accept(result);}catch(Exception e){message("Could not display the result. Refresh and try again.");}});}catch(Exception e){runOnUiThread(()->{busy=false;if(!isFinishing()&&!isDestroyed()){
            if(e instanceof Api.SessionExpiredException){api.clear();signedIn=false;exportData=null;orderKey=null;auth(false);}
            message(e.getMessage()==null?"Connection failed. Try again.":e.getMessage());
        }});}});}
    private void legal(String hash){if(api.configured())startActivity(new Intent(Intent.ACTION_VIEW,Uri.parse(BuildConfig.API_ORIGIN+"/#"+hash)));else message("Read the privacy notice and terms in the website preview. No data is collected by this unconfigured build.");}
    private void privacyPage(String path){
        if(!api.configured()){message("Contact kiwikindbroadband@gmail.com for privacy or account deletion.");return;}
        try{startActivity(new Intent(Intent.ACTION_VIEW,Uri.parse(BuildConfig.API_ORIGIN+path)));}
        catch(android.content.ActivityNotFoundException e){message("Open "+BuildConfig.API_ORIGIN+path+" in a browser, or email kiwikindbroadband@gmail.com. Do not send your password.");}
    }
    private void auth(boolean register){
        refreshScreen=null;
        content.removeAllViews();title(register?"Create your account":"A kinder connection.");landscape();paragraph("My KiwiKind · Pre-launch\nSign in to your existing account. Broadband requests and payments remain closed.");
        EditText email=field("Email",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS);
        EditText password=field("Password (at least 12 characters)",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);
        CheckBox consent=new CheckBox(this);consent.setText(R.string.account_consent);if(register)content.addView(consent);
        button(register?"Create account":"Sign in",()->{
            if(register&&!consent.isChecked()){message("Please read and accept the pre-launch terms.");return;}
            String e=email.getText().toString().trim(),p=password.getText().toString();password.setText("");
            run(()->api.call(register?"register":"login",data("email",e,"password",p,"consent_version",CONSENT)),r->{if(register){message(r.optString("message"));}else{signedIn=true;home();}});
        }).setEnabled(api.configured()&&(!register||intake));
        Button googleButton=button("Sign in with Google",this::googleSignIn);
        googleButton.setEnabled(api.configured());
        googleButton.setTextColor(Color.WHITE);
        googleButton.setBackgroundTintList(android.content.res.ColorStateList.valueOf(FOREST));
        googleButton.setAllCaps(false);
        googleButton.setMinHeight((int)(52*getResources().getDisplayMetrics().density));
        button(register?"Back to sign in":"Create an account",()->auth(!register)).setEnabled(register||intake);
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
                    run(()->api.call("google-login",data("id_token",token)),r->{signedIn=true;home();message("Signed in with Google.");});
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
                    run(()->api.call("google-login",data("id_token",token)),r->{signedIn=true;home();message("Signed in with Google.");});
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
    private void home(){
        refreshScreen=this::home;
        content.removeAllViews();title("My KiwiKind");landscape();paragraph("Kia ora, welcome home.\nOne KiwiKind account, on your website and app.");
        accountCard("My connection","No active service · View requests",this::orders);accountCard("My support","Support & complaints",this::tickets);accountCard("Billing","Payments disabled",()->run(()->api.call("invoices",null),r->{refreshScreen=null;content.removeAllViews();title("Billing");paragraph("Payments are disabled. No charges are being taken.");JSONArray a=r.optJSONArray("invoices");if(a==null||a.length()==0)paragraph("No invoices.");else for(int i=0;i<a.length();i++)paragraph(a.getJSONObject(i).toString());nav();}));
        button("Refresh account from website",()->run(()->api.call("me",null),r->{signedIn=true;home();message("Account refreshed from KiwiKind server.");}));
        button("Download my account data",()->run(()->api.call("privacy/export",null),r->{exportData=r.toString(2);Intent intent=new Intent(Intent.ACTION_CREATE_DOCUMENT);intent.setType("application/json");intent.addCategory(Intent.CATEGORY_OPENABLE);intent.putExtra(Intent.EXTRA_TITLE,"kiwikind-data.json");startActivityForResult(intent,10);message("Choose where to save your private account export.");}));
        button("Request account deletion",()->{refreshScreen=null;content.removeAllViews();title("Request deletion");paragraph("This is a request for manual review, not instant deletion. Google-only users can request deletion without a password using the web/email option below.");button("Request without a password (Google accounts)",()->privacyPage("/account-deletion/"));EditText p=field("Current password",129);button("Submit deletion request",()->{String password=p.getText().toString();p.setText("");run(()->api.call("privacy/deletion",data("password",password)),r->message(r.optString("message")));});nav();});
        button("Privacy & account correction",()->privacyPage("/privacy/"));
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
    private void conversation(String id){run(()->api.call("tickets/"+id+"/messages",null),r->{refreshScreen=null;content.removeAllViews();title("Conversation");JSONArray a=r.getJSONArray("messages");for(int i=0;i<a.length();i++){JSONObject m=a.getJSONObject(i);paragraph((m.optBoolean("from_support")?"Support: ":"You: ")+m.getString("body"));}EditText reply=field("Your reply",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_FLAG_MULTI_LINE);reply.setSingleLine(false);button("Send reply",()->run(()->api.call("tickets/"+id+"/messages",data("body",reply.getText().toString())),x->conversation(id)));nav();message("Your conversation");});}
    @Override protected void onActivityResult(int request,int result,Intent intent){super.onActivityResult(request,result,intent);if(request==10){if(result==RESULT_OK&&intent!=null&&intent.getData()!=null&&exportData!=null){try(var out=getContentResolver().openOutputStream(intent.getData())){if(out!=null){out.write(exportData.getBytes(java.nio.charset.StandardCharsets.UTF_8));message("Export saved.");}}catch(Exception e){message("Could not save export.");}}exportData=null;}}
    @Override protected void onDestroy(){worker.shutdownNow();exportData=null;super.onDestroy();}
}
