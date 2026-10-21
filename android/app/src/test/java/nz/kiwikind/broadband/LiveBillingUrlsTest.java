package nz.kiwikind.broadband;
import org.junit.Test;
import static org.junit.Assert.*;
public class LiveBillingUrlsTest {
    @Test public void onlyLiveCheckoutAccepted(){
        assertTrue(BillingUrls.isLiveCheckout("https://checkout.stripe.com/c/pay/cs_live_synthetic"));
        assertFalse(BillingUrls.isLiveCheckout("https://checkout.stripe.com/c/pay/cs_test_synthetic"));
        assertFalse(BillingUrls.isTestCheckout("https://checkout.stripe.com/c/pay/cs_live_synthetic"));
    }
    @Test public void hostileHostsAndSchemesBlocked(){
        for(String url:new String[]{"http://checkout.stripe.com/c/pay/cs_live_fake","https://checkout.stripe.com.attacker.invalid/c/pay/cs_live_fake","https://attacker@checkout.stripe.com/c/pay/cs_live_fake","https://checkout.stripe.com:444/c/pay/cs_live_fake","javascript:alert(1)","https://checkout.stripe.com\\@evil.invalid/c/pay/cs_live_fake"})assertFalse(url,BillingUrls.isLiveCheckout(url));
    }
    @Test public void portalModeIsSeparate(){
        assertTrue(BillingUrls.isLivePortal("https://billing.stripe.com/p/session/synthetic"));
        assertFalse(BillingUrls.isLivePortal("https://billing.stripe.com/p/session/test_synthetic"));
        assertFalse(BillingUrls.isLivePortal("https://evil.invalid/p/session/synthetic"));
        assertFalse(BillingUrls.isLivePortal(null));
    }
}
