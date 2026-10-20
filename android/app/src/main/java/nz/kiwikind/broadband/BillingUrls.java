package nz.kiwikind.broadband;

import java.net.URI;

/** Only a server-created Stripe test Checkout may leave the native app. */
final class BillingUrls {
    private BillingUrls() { }
    static boolean isTestCheckout(String value) {
        if (value == null || value.length() > 4096 || value.matches("(?s).*[\\s\\\\].*")) return false;
        try {
            URI uri = new URI(value);
            return "https".equals(uri.getScheme()) && "checkout.stripe.com".equals(uri.getHost())
                && uri.getUserInfo() == null && (uri.getPort() == -1 || uri.getPort() == 443)
                && uri.getPath() != null && uri.getPath().startsWith("/c/pay/cs_test_");
        } catch (Exception ignored) { return false; }
    }
}
