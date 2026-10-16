package nz.kiwikind.broadband;
import java.net.URI;

public final class Endpoint {
    private Endpoint() {}
    public static boolean valid(String value) {
        try {
            URI uri = URI.create(value);
            return "https".equals(uri.getScheme()) && uri.getHost()!=null && uri.getUserInfo()==null
                && (uri.getRawPath()==null || uri.getRawPath().isEmpty()) && uri.getQuery()==null && uri.getFragment()==null;
        } catch (IllegalArgumentException ex) { return false; }
    }
}
