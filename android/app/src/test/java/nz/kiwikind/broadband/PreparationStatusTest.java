package nz.kiwikind.broadband;
import org.junit.Test;
import static org.junit.Assert.*;

public class PreparationStatusTest {
    @Test public void knownPreparationIsNotAnActiveService() {
        assertEquals("Prepared — awaiting launch approval", PreparationStatus.label("ready"));
        assertEquals("Request cancelled", PreparationStatus.label("cancelled"));
    }
    @Test public void unexpectedOrPracticeStatusesCannotClaimService() {
        for (String state : new String[]{null,"", "active", "submitted", "<script>"})
            assertEquals("Awaiting an update from KiwiKind", PreparationStatus.label(state));
    }
}
