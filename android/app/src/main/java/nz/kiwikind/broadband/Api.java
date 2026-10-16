package nz.kiwikind.broadband;
import org.json.JSONObject;
import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import java.util.Base64;
import java.net.HttpCookie;
import org.json.JSONArray;

import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.HttpURLConnection;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.io.InputStream;
import java.io.ByteArrayOutputStream;
import java.util.List;
import java.util.Map;

final class Api {
    static final class SessionExpiredException extends Exception { SessionExpiredException(){super("Please sign in again.");} }
    private final String origin;
    private final CookieManager cookies = new CookieManager(null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);
    private String csrf="";
    private final SharedPreferences prefs;
    private static final String KEY_ALIAS="kiwikind_session_aes_v1";
    Api(String origin, Context context) {
        this.origin=origin;
        prefs=context.getApplicationContext().getSharedPreferences("kiwikind_secure_session",Context.MODE_PRIVATE);
        restoreCookies();
    }
    private SecretKey secretKey() throws Exception {
        KeyStore store=KeyStore.getInstance("AndroidKeyStore");store.load(null);
        KeyStore.Entry entry=store.getEntry(KEY_ALIAS,null);
        if(entry instanceof KeyStore.SecretKeyEntry)return ((KeyStore.SecretKeyEntry)entry).getSecretKey();
        KeyGenerator generator=KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore");
        generator.init(new KeyGenParameterSpec.Builder(KEY_ALIAS,KeyProperties.PURPOSE_ENCRYPT|KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setKeySize(256).build());
        return generator.generateKey();
    }
    private void saveCookies() {
        try {
            JSONArray entries=new JSONArray();
            for(HttpCookie cookie:cookies.getCookieStore().getCookies()){
                if(!cookie.getSecure()||cookie.hasExpired())continue;
                entries.put(new JSONObject().put("name",cookie.getName()).put("value",cookie.getValue())
                    .put("path",cookie.getPath()).put("domain",cookie.getDomain()));
            }
            Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");cipher.init(Cipher.ENCRYPT_MODE,secretKey());
            byte[] encrypted=cipher.doFinal(entries.toString().getBytes(StandardCharsets.UTF_8));
            prefs.edit().putString("iv",Base64.getEncoder().encodeToString(cipher.getIV()))
                .putString("cookies",Base64.getEncoder().encodeToString(encrypted)).apply();
        }catch(Exception ignored){prefs.edit().clear().apply();}
    }
    private void restoreCookies() {
        try {
            String iv=prefs.getString("iv",null),stored=prefs.getString("cookies",null);
            if(iv==null||stored==null)return;
            Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE,secretKey(),new GCMParameterSpec(128,Base64.getDecoder().decode(iv)));
            JSONArray entries=new JSONArray(new String(cipher.doFinal(Base64.getDecoder().decode(stored)),StandardCharsets.UTF_8));
            URI uri=URI.create(origin);
            for(int i=0;i<entries.length();i++){
                JSONObject entry=entries.getJSONObject(i);
                HttpCookie cookie=new HttpCookie(entry.getString("name"),entry.getString("value"));
                cookie.setSecure(true);cookie.setHttpOnly(true);
                if(!entry.isNull("path"))cookie.setPath(entry.getString("path"));
                if(!entry.isNull("domain"))cookie.setDomain(entry.getString("domain"));
                cookies.getCookieStore().add(uri,cookie);
            }
        }catch(Exception ignored){cookies.getCookieStore().removeAll();prefs.edit().clear().apply();}
    }
    boolean configured() { return Endpoint.valid(origin); }
    void clear() { cookies.getCookieStore().removeAll(); csrf=""; prefs.edit().clear().apply(); }
    JSONObject call(String path, JSONObject data) throws Exception {
        if(!configured()) throw new Exception("Pre-launch build: customer backend is not configured.");
        if(data!=null && csrf.isEmpty()) call("csrf",null);
        URI uri=URI.create(origin+"/api/"+path);
        HttpURLConnection c=(HttpURLConnection)uri.toURL().openConnection();
        c.setInstanceFollowRedirects(false);c.setConnectTimeout(65000);c.setReadTimeout(65000);
        c.setRequestProperty("Accept","application/json");
        for(Map.Entry<String,List<String>> h:cookies.get(uri,java.util.Collections.emptyMap()).entrySet()) c.setRequestProperty(h.getKey(),String.join("; ",h.getValue()));
        try {
            if(data!=null){
                c.setRequestMethod("POST");c.setDoOutput(true);c.setRequestProperty("Content-Type","application/json");
                c.setRequestProperty("X-CSRFToken",csrf);c.setRequestProperty("Referer",origin+"/");c.setRequestProperty("Origin",origin);
                try(var out=c.getOutputStream()){out.write(data.toString().getBytes(StandardCharsets.UTF_8));}
            }
            int code=c.getResponseCode();cookies.put(uri,c.getHeaderFields());saveCookies();
            InputStream stream=code<400?c.getInputStream():c.getErrorStream();
            if(stream==null) throw new Exception("No server response. Please try again.");
            ByteArrayOutputStream out=new ByteArrayOutputStream();
            try(stream){byte[] buf=new byte[4096];int n;while((n=stream.read(buf))!=-1){out.write(buf,0,n);if(out.size()>2000000)throw new Exception("Server response too large.");}}
            JSONObject result;
            try{result=new JSONObject(out.toString(StandardCharsets.UTF_8.name()));}catch(Exception e){throw new Exception("The customer backend is unavailable. Please try again.");}
            if(code==401)throw new SessionExpiredException();
            if(code>=300)throw new Exception(result.optString("error","Request failed ("+code+")"));
            if(result.has("csrfToken"))csrf=result.getString("csrfToken");
            return result;
        } finally { c.disconnect(); }
    }
}
