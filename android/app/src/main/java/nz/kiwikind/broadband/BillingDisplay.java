package nz.kiwikind.broadband;

import java.math.BigDecimal;

/** Test-billing amounts originate only from the authenticated server ledger. */
final class BillingDisplay {
    private BillingDisplay() { }

    static String money(long cents) {
        return "NZ$" + BigDecimal.valueOf(cents, 2).toPlainString();
    }

    static String invoiceLabel(String status, long amountCents, long refundedCents,
                               String disputeStatus) {
        boolean fullyRefunded = "paid".equals(status) && amountCents > 0
            && refundedCents == amountCents;
        String label = "TEST invoice " + money(amountCents) + " · " + status
            + (fullyRefunded ? " · fully refunded " : " · refunded ")
            + money(refundedCents);
        if (disputeStatus != null && !disputeStatus.isEmpty()) {
            label += " · dispute " + disputeStatus;
        }
        return label;
    }
}
