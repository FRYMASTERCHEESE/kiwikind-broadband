package nz.kiwikind.broadband;
import org.junit.Test;
import static org.junit.Assert.*;

public class RecoveryMessageTest {
    @Test public void uncertainWritePromptsRefreshInsteadOfBlindResubmit() {
        assertTrue(RecoveryMessage.interrupted(true).contains("may have reached KiwiKind"));
        assertTrue(RecoveryMessage.interrupted(true).contains("Refresh your account before sending again"));
    }
    @Test public void readFailureDoesNotTellCustomerToClearLogin() {
        assertTrue(RecoveryMessage.interrupted(false).contains("saved login is kept"));
    }
}
