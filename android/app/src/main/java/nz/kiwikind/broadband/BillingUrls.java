package nz.kiwikind.broadband;

import java.net.URI;

/** Keep test Checkout, real Checkout and card-management addresses separate. */
final class BillingUrls {
    private BillingUrls() { }
    private static boolean allowed(String value, String host, String prefix) {
        if(value==null||value.length()>4096||value.matches("(?s).*[\\s\\\\].*"))return false;
        try {
            URI uri=new URI(value);
            return "https".equals(uri.getScheme())&&host.equals(uri.getHost())&&uri.getUserInfo()==null
                &&(uri.getPort()==-1||uri.getPort()==443)&&uri.getPath()!=null&&uri.getPath().startsWith(prefix);
        } catch(Exception ignored){return false;}
    }
    static boolean isTestCheckout(String value){return allowed(value,"checkout.stripe.com","/c/pay/cs_test_");}
    static boolean isLiveCheckout(String value){return allowed(value,"checkout.stripe.com","/c/pay/cs_live_");}
    static boolean isLivePortal(String value){return allowed(value,"billing.stripe.com","/p/session/")&&!allowed(value,"billing.stripe.com","/p/session/test_");}
}
