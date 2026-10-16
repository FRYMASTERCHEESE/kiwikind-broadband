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
    interface Task { JSONObject run() throws Exception; }
    interface Done { void accept(JSONObject data) throws Exception; }
    @Override public void onCreate(Bundle state){
        super.onCreate(state);api=new Api(BuildConfig.API_ORIGIN,this);
        LinearLayout root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setBackgroundColor(Color.rgb(244,242,233));
        root.setOnApplyWindowInsetsListener((v,insets)->{v.setPadding(22,insets.getSystemWindowInsetTop()+12,22,insets.getSystemWindowInsetBottom()+12);return insets;});
        TextView brand=new TextView(this);brand.setText(R.string.app_name);brand.setTextSize(25);brand.setTextColor(Color.rgb(18,63,50));root.addView(brand);
        TextView label=new TextView(this);label.setText(R.string.prelaunch);root.addView(label);
        feedback=new TextView(this);feedback.setTextSize(14);feedback.setPadding(0,16,0,16);feedback.setAccessibilityLiveRegion(1);root.addView(feedback);
        ScrollView scroll=new ScrollView(this);content=new LinearLayout(this);content.setOrientation(LinearLayout.VERTICAL);scroll.addView(content);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));setContentView(root);
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
    private void title(String text){TextView t=new TextView(this);t.setText(text);t.setTextSize(23);t.setPadding(0,22,0,14);content.addView(t);}
    private void paragraph(String text){TextView t=new TextView(this);t.setText(text);t.setTextSize(15);t.setPadding(0,10,0,16);content.addView(t);}
    private EditText field(String label,int type){TextView l=new TextView(this);l.setText(label);content.addView(l);EditText input=new EditText(this);input.setInputType(type);input.setContentDescription(label);input.setSingleLine();content.addView(input);return input;}
    private Button button(String text,Runnable action){Button b=new Button(this);b.setText(text);b.setAllCaps(false);content.addView(b);b.setOnClickListener(v->{if(!busy)action.run();});return b;}
    private JSONObject data(Object... pairs){JSONObject d=new JSONObject();try{for(int i=0;i<pairs.length;i+=2)d.put((String)pairs[i],pairs[i+1]);}catch(JSONException ignored){}return d;}
    private void run(Task task,Done done){if(busy)return;busy=true;message("Working…");worker.submit(()->{try{JSONObject result=task.run();runOnUiThread(()->{busy=false;if(isFinishing()||isDestroyed())return;try{done.accept(result);}catch(Exception e){message("Could not display the result. Refresh and try again.");}});}catch(Exception e){runOnUiThread(()->{busy=false;if(!isFinishing()&&!isDestroyed()){
            if(e instanceof Api.SessionExpiredException){api.clear();signedIn=false;auth(false);}
            message(e.getMessage()==null?"Connection failed. Try again.":e.getMessage());
        }});}});}
    private void legal(String hash){if(api.configured())startActivity(new Intent(Intent.ACTION_VIEW,Uri.parse(BuildConfig.API_ORIGIN+"/#"+hash)));else message("Read the privacy notice and terms in the website preview. No data is collected by this unconfigured build.");}
    private void auth(boolean register){
        content.removeAllViews();title(register?"Create your account":"A kinder connection.");paragraph("A request is not a broadband contract. Verify your email on the website before signing in here.");
        EditText email=field("Email",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS);
        EditText password=field("Password (at least 12 characters)",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);
        CheckBox consent=new CheckBox(this);consent.setText(R.string.account_consent);if(register)content.addView(consent);
        button(register?"Create account":"Sign in",()->{
            if(register&&!consent.isChecked()){message("Please read and accept the pre-launch terms.");return;}
            String e=email.getText().toString(),p=password.getText().toString();password.setText("");
            run(()->api.call(register?"register":"login",data("email",e,"password",p,"consent_version",CONSENT)),r->{if(register){message(r.optString("message"));}else{signedIn=true;home();}});
        }).setEnabled(api.configured()&&(!register||intake));
        Button googleButton=button("Sign in with Google",this::googleSignIn);
        googleButton.setEnabled(api.configured());
        googleButton.setTextColor(Color.WHITE);
        googleButton.setBackgroundTintList(android.content.res.ColorStateList.valueOf(Color.rgb(25,25,25)));
        googleButton.setAllCaps(false);
        googleButton.setMinHeight((int)(52*getResources().getDisplayMetrics().density));
        button(register?"Back to sign in":"Create an account",()->auth(!register));
        button("Open My KiwiKind website",()->startActivity(new Intent(Intent.ACTION_VIEW,Uri.parse(BuildConfig.API_ORIGIN+"/#portal")))).setEnabled(api.configured());
        button("Reset password",()->run(()->api.call("password-reset",data("email",email.getText().toString())),r->message(r.optString("message")))).setEnabled(api.configured());
        button("Privacy notice",()->legal("privacy"));button("Pre-launch terms",()->legal("terms"));
    }
    private void googleSignIn(){
        if(BuildConfig.GOOGLE_WEB_CLIENT_ID.trim().isEmpty()){message("Google sign-in is not configured in this Android build. Use the website while setup is completed.");return;}
        message("Opening Google account chooser…");
        GetGoogleIdOption option=new GetGoogleIdOption.Builder()
            .setServerClientId(BuildConfig.GOOGLE_WEB_CLIENT_ID)
            .setFilterByAuthorizedAccounts(false)
            .build();
        GetCredentialRequest request=new GetCredentialRequest.Builder().addCredentialOption(option).build();
        CredentialManager.create(this).getCredentialAsync(this,request,null,getMainExecutor(),new CredentialManagerCallback<GetCredentialResponse,GetCredentialException>(){
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
        CredentialManager.create(this).getCredentialAsync(this,request,null,getMainExecutor(),new CredentialManagerCallback<GetCredentialResponse,GetCredentialException>(){
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
        content.removeAllViews();title("My KiwiKind");paragraph("No active broadband service. Your website and app use the same customer backend.");
        button("Refresh account from website",()->run(()->api.call("me",null),r->{signedIn=true;home();message("Account refreshed from KiwiKind server.");}));
        button("My broadband requests",this::orders);button("Support & complaints",this::tickets);button("Billing",()->run(()->api.call("invoices",null),r->{content.removeAllViews();title("Billing");paragraph("Payments are disabled. No charges are being taken.");JSONArray a=r.optJSONArray("invoices");if(a==null||a.length()==0)paragraph("No invoices.");else for(int i=0;i<a.length();i++)paragraph(a.getJSONObject(i).toString());nav();}));
        button("Download my account data",()->run(()->api.call("privacy/export",null),r->{exportData=r.toString(2);Intent intent=new Intent(Intent.ACTION_CREATE_DOCUMENT);intent.setType("application/json");intent.addCategory(Intent.CATEGORY_OPENABLE);intent.putExtra(Intent.EXTRA_TITLE,"kiwikind-data.json");startActivityForResult(intent,10);message("Choose where to save your private account export.");}));
        button("Request account deletion",()->{content.removeAllViews();title("Request deletion");paragraph("We will review lawful retention needs. This is not instant deletion. Request corrections using a privacy support ticket.");EditText p=field("Current password",129);button("Submit deletion request",()->{String password=p.getText().toString();p.setText("");run(()->api.call("privacy/deletion",data("password",password)),r->message(r.optString("message")));});nav();});
        button("Privacy & account correction",()->legal("privacy"));
        button("Sign out",()->run(()->api.call("logout",data()),r->{api.clear();signedIn=false;orderKey=null;auth(false);message("Signed out.");}));
        message("Account connected · Pre-launch only");
    }
    private void orders(){run(()->api.call("orders",null),r->{
        content.removeAllViews();title("Broadband requests");JSONArray a=r.getJSONArray("orders");if(a.length()==0)paragraph("No requests yet.");
        for(int i=0;i<a.length();i++){JSONObject o=a.getJSONObject(i);paragraph(o.getString("address")+"\n"+o.getString("status")+"\n"+o.getString("id"));if(!o.getString("status").equals("cancelled"))button("Cancel this request",()->new AlertDialog.Builder(this).setMessage("Cancel this pending request?").setPositiveButton("Cancel request",(d,w)->run(()->api.call("orders/"+o.optString("id")+"/cancel",data()),x->orders())).setNegativeButton("Keep request",null).show());}
        button("New connection request",this::newOrder).setEnabled(intake);nav();message("Availability has not been checked.");
    });}
    private void newOrder(){
        content.removeAllViews();title("Request a connection");paragraph("No supplier order, price, installation date or payment is authorised. Do not cancel your current broadband.");
        EditText name=field("Contact name",1),address=field("Full NZ service address",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_POSTAL_ADDRESS),postcode=field("Four-digit postcode",2),phone=field("Phone (optional)",3);
        CheckBox c=new CheckBox(this);c.setText(R.string.request_consent);content.addView(c);
        orderKey=UUID.randomUUID().toString();
        button("Send request",()->{if(!c.isChecked()){message("Please accept the request terms.");return;}JSONObject d=data("contact_name",name.getText().toString(),"address",address.getText().toString(),"postcode",postcode.getText().toString(),"phone",phone.getText().toString(),"consent_version",CONSENT,"idempotency_key",orderKey);run(()->api.call("orders",d),r->{orderKey=null;orders();});});button("Read request terms",()->legal("terms"));nav();
    }
    private void tickets(){run(()->api.call("tickets",null),r->{
        content.removeAllViews();title("Support & complaints");paragraph("No response time is promised during pre-launch. This is not an emergency service.");JSONArray a=r.getJSONArray("tickets");if(a.length()==0)paragraph("No conversations yet.");
        for(int i=0;i<a.length();i++){JSONObject t=a.getJSONObject(i);button(t.getString("subject")+" · "+t.getString("status"),()->conversation(t.optString("id")));}
        button("Start a conversation",this::newTicket);nav();message("Your conversations");
    });}
    private void newTicket(){content.removeAllViews();title("How can we help?");paragraph("Do not include payment card details, identity documents or health information.");EditText subject=field("Subject",1);Spinner category=new Spinner(this);category.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,new String[]{"support","complaint","privacy"}));category.setContentDescription("Topic");content.addView(category);EditText body=field("Message",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_FLAG_MULTI_LINE);body.setSingleLine(false);body.setMinLines(4);button("Send message",()->run(()->api.call("tickets",data("subject",subject.getText().toString(),"category",category.getSelectedItem().toString(),"body",body.getText().toString())),r->tickets()));nav();}
    private void conversation(String id){run(()->api.call("tickets/"+id+"/messages",null),r->{content.removeAllViews();title("Conversation");JSONArray a=r.getJSONArray("messages");for(int i=0;i<a.length();i++){JSONObject m=a.getJSONObject(i);paragraph((m.optBoolean("from_support")?"Support: ":"You: ")+m.getString("body"));}EditText reply=field("Your reply",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_FLAG_MULTI_LINE);reply.setSingleLine(false);button("Send reply",()->run(()->api.call("tickets/"+id+"/messages",data("body",reply.getText().toString())),x->conversation(id)));nav();message("Your conversation");});}
    @Override protected void onActivityResult(int request,int result,Intent intent){super.onActivityResult(request,result,intent);if(request==10){if(result==RESULT_OK&&intent!=null&&intent.getData()!=null&&exportData!=null){try(var out=getContentResolver().openOutputStream(intent.getData())){if(out!=null){out.write(exportData.getBytes(java.nio.charset.StandardCharsets.UTF_8));message("Export saved.");}}catch(Exception e){message("Could not save export.");}}exportData=null;}}
    @Override protected void onDestroy(){worker.shutdownNow();exportData=null;super.onDestroy();}
}
