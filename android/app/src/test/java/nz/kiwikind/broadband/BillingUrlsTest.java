package nz.kiwikind.broadband;
import org.junit.Test;
import static org.junit.Assert.*;
public class BillingUrlsTest {
    @Test public void liveCheckoutCannotOpenTestOrForeignAddresses(){
        assertTrue(BillingUrls.isLiveCheckout("https://checkout.stripe.com/c/pay/cs_live_synthetic"));
        assertFalse(BillingUrls.isLiveCheckout("https://checkout.stripe.com/c/pay/cs_test_synthetic"));
        assertFalse(BillingUrls.isLiveCheckout("https://checkout.stripe.com.evil.invalid/c/pay/cs_live_a"));
        assertFalse(BillingUrls.isLiveCheckout("https://evil@checkout.stripe.com/c/pay/cs_live_a"));
    }
    @Test public void acceptsOnlyExactTestCheckout(){
        assertTrue(BillingUrls.isTestCheckout("https://checkout.stripe.com/c/pay/cs_test_synthetic#test"));
        assertTrue(BillingUrls.isTestCheckout("https://checkout.stripe.com:443/c/pay/cs_test_synthetic"));
    }
    @Test public void rejectsLiveAndDeceptiveAddresses(){
        String[] bad={null,"", "http://checkout.stripe.com/c/pay/cs_test_a",
            "https://checkout.stripe.com/c/pay/cs_live_a", "https://checkout.stripe.com.evil.invalid/c/pay/cs_test_a",
            "https://user@checkout.stripe.com/c/pay/cs_test_a", "https://checkout.stripe.com:444/c/pay/cs_test_a",
            "javascript:alert(1)", "https://checkout.stripe.com/other", "https://checkout.stripe.com\n/c/pay/cs_test_a"};
        for(String value:bad)assertFalse(String.valueOf(value),BillingUrls.isTestCheckout(value));
    }
}
