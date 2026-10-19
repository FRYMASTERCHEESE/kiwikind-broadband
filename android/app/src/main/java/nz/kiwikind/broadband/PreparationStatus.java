package nz.kiwikind.broadband;

/** Customer-safe labels. Unknown states never claim an active service. */
final class PreparationStatus {
    private PreparationStatus() {}
    static String label(String stage) {
        if (stage == null) return "Awaiting an update from KiwiKind";
        switch (stage) {
            case "draft": return "Preparation started";
            case "availability_review": return "Availability evidence under review";
            case "quote_review": return "Draft quote under review";
            case "ready": return "Prepared — awaiting launch approval";
            case "cancelled": return "Request cancelled";
            case "triage": return "KiwiKind reviewing support";
            case "resolved": return "Support review resolved";
            case "closed": return "Review closed";
            default: return "Awaiting an update from KiwiKind";
        }
    }
}
