# Shared referral preview

Codes are created only by an authenticated, CSRF-protected, throttled POST. GET
does not issue a code. A server-generated 144-bit random code has a database
uniqueness constraint; each account has one code. Share links lead to the same
secure portal and prefill an optional registration field. No invite email is sent.

`REFERRALS_ENABLED` defaults false. `INTAKE_ENABLED` remains false in production.
Code preview/history is available to existing accounts; referral registration is
not accepting signups. Enabling it later requires BOTH gates, approved programme
terms and consent version, and explicit operator approval. Rewards are hard-coded
off: no credits, discounts, free broadband, payments or supplier orders exist.

For future permitted email registration, the relationship is created atomically
with a new inactive account. Pending becomes email-verified only after the actual
verification token is accepted. An existing account cannot change attribution;
one invitee can have only one referrer; the database rejects self-referral. Code
validation behaves the same for existing and unknown email addresses.

Referrer history returns random record IDs/status/timestamps, never an invitee's
email or name. Account export includes only the requesting account's referral
metadata and preferences. Ordinary account/session isolation applies on both
platforms. Deletion processing must include these relationships and recovery
snapshots under the retention procedure; PROTECT prevents silently discarding
referrer records during a naive user delete.

Google Sign-In remains unchanged: a first Google login does not apply a pending
referral code. This is a known extension needed before a future programme accepts
Google-registration attribution; do not promise coverage that is not implemented.
The current closed prelaunch does not accept attribution through either path.

These controls limit casual abuse, not prove a human has only one email/account.
Before financial rewards: approved eligibility, anti-fraud review, account/service
qualification and settlement/chargeback rules, lawful retention, and appeal/support
procedures. Email verification alone must never qualify someone for money.
