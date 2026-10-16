package nz.kiwikind.broadband;
import org.json.JSONObject;
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
    private final String origin;
    private final CookieManager cookies = new CookieManager(null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);
    private String csrf="";
    Api(String origin) { this.origin=origin; }
    boolean configured() { return Endpoint.valid(origin); }
    void clear() { cookies.getCookieStore().removeAll(); csrf=""; }
    JSONObject call(String path, JSONObject data) throws Exception {
        if(!configured()) throw new Exception("Pre-launch build: customer backend is not configured.");
        if(data!=null && csrf.isEmpty()) call("csrf",null);
        URI uri=URI.create(origin+"/api/"+path);
        HttpURLConnection c=(HttpURLConnection)uri.toURL().openConnection();
        c.setInstanceFollowRedirects(false);c.setConnectTimeout(15000);c.setReadTimeout(15000);
        c.setRequestProperty("Accept","application/json");
        for(Map.Entry<String,List<String>> h:cookies.get(uri,Map.of()).entrySet()) c.setRequestProperty(h.getKey(),String.join("; ",h.getValue()));
        try {
            if(data!=null){
                c.setRequestMethod("POST");c.setDoOutput(true);c.setRequestProperty("Content-Type","application/json");
                c.setRequestProperty("X-CSRFToken",csrf);c.setRequestProperty("Referer",origin+"/");c.setRequestProperty("Origin",origin);
                try(var out=c.getOutputStream()){out.write(data.toString().getBytes(StandardCharsets.UTF_8));}
            }
            int code=c.getResponseCode();cookies.put(uri,c.getHeaderFields());
            InputStream stream=code<400?c.getInputStream():c.getErrorStream();
            if(stream==null) throw new Exception("No server response. Please try again.");
            ByteArrayOutputStream out=new ByteArrayOutputStream();
            try(stream){byte[] buf=new byte[4096];int n;while((n=stream.read(buf))!=-1){out.write(buf,0,n);if(out.size()>2000000)throw new Exception("Server response too large.");}}
            JSONObject result;
            try{result=new JSONObject(out.toString(StandardCharsets.UTF_8.name()));}catch(Exception e){throw new Exception("The customer backend is unavailable. Please try again.");}
            if(code>=300)throw new Exception(result.optString("error","Request failed ("+code+")"));
            if(result.has("csrfToken"))csrf=result.getString("csrfToken");
            return result;
        } finally { c.disconnect(); }
    }
}
