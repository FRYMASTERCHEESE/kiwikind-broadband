package nz.kiwikind.broadband;

final class RecoveryMessage {
    private RecoveryMessage() {}
    static String interrupted(boolean write) {
        return write
            ? "The response was interrupted. Your request may have reached KiwiKind. Refresh your account before sending again."
            : "Could not reach KiwiKind. Your saved login is kept. Check your connection and refresh; the server may be waking up.";
    }
}
