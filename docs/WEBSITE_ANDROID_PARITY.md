# Approved website and Android parity

Reference: `FRYMASTERCHEESE/kiwikind-broadband-website` revision
`dda56013be4bfaac94eea15877da8c47ffbcae8c`.

The public website stays the source of approved informational copy. The native
Home, Our vision, My KiwiKind preview, Our journey and FAQs pages render bundled
text with Android widgets. No WebView or website scripts are embedded.

Regenerate the native bundle after reviewing an approved website change:

```sh
python scripts/sync_website_content.py /path/to/kiwikind-broadband-website/index.html
```

The JSON records the source URL and SHA-256. Public copy updates ship with an app
release; this is not automatic remote content delivery. The secure portal's public
HTML sections use the same approved copy and styling. Review those sections when
the reference changes, retaining account IDs, legal sections and app.js handlers.

The static dashboard preview is labelled as a demonstration. It never receives
account records. The authenticated dashboard, requests, support messages, invoices,
exports and deletion requests continue using the existing HTTPS Django API and
Neon database. Each device keeps its own secure session; shared records do not
mean shared browser cookies. Existing refresh-on-return behaviour remains, and
conversation views have an explicit refresh to avoid erasing an unsent reply.

`portal.test_shared_account` exercises two independent CSRF-protected sessions,
cross-session support history, logout independence, and closed intake/billing
gates. Tests use disposable databases, never production customer records.

Native visual verification captures normal and narrow screens at 130% text size,
the sign-in and dashboard fixtures, all public pages and expanded FAQs. Web visual
verification uses disconnected API fixtures at desktop and phone sizes. These
checks do not establish Google sign-in on a Play-installed build, real mail
delivery, every device's accessibility, or production cross-device login.

PR #24 was already merged and version 5 already uploaded before this continuation.
This candidate is version 6 / 0.2.4-prelaunch. It must use the existing protected
signing workflow on `feature/neon-postgres-config`; never overwrite version 5,
rotate keys, weaken branch protection or change the existing tester audience.
No new service, payment, wholesale integration or registration gate is enabled.
