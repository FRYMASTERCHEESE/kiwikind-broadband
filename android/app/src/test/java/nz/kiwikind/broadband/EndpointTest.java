package nz.kiwikind.broadband;
import org.junit.Test;
import static org.junit.Assert.*;
public class EndpointTest {
    @Test public void requiresHttpsOrigin(){assertTrue(Endpoint.valid("https://portal.example.invalid"));assertFalse(Endpoint.valid("http://portal.example.invalid"));assertFalse(Endpoint.valid(""));assertFalse(Endpoint.valid("https://user:pass@example.invalid"));assertFalse(Endpoint.valid("https://example.invalid/api"));assertFalse(Endpoint.valid("https://example.invalid?secret=x"));}
}
