package nz.kiwikind.broadband;

import org.junit.Test;
import static org.junit.Assert.*;

public class BillingDisplayTest {
    @Test public void completedTestRefundIsUnmistakable() {
        assertEquals("TEST invoice NZ$1.00 · paid · fully refunded NZ$1.00",
            BillingDisplay.invoiceLabel("paid",100,100,""));
    }
    @Test public void paidButNotRefundedIsDistinct() {
        assertEquals("TEST invoice NZ$1.00 · paid · refunded NZ$0.00",
            BillingDisplay.invoiceLabel("paid",100,0,""));
    }
    @Test public void partialRefundDoesNotSayFullyRefunded() {
        assertEquals("TEST invoice NZ$10.00 · paid · refunded NZ$2.00",
            BillingDisplay.invoiceLabel("paid",1000,200,""));
    }
    @Test public void failedOrOpenInvoiceIsNotPaid() {
        assertEquals("TEST invoice NZ$1.00 · open · refunded NZ$0.00",
            BillingDisplay.invoiceLabel("open",100,0,""));
    }
    @Test public void disputeStatusIsKeptVisible() {
        assertTrue(BillingDisplay.invoiceLabel("paid",100,0,"needs_response")
            .contains("dispute needs_response"));
    }
}
