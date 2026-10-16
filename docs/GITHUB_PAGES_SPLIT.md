# GitHub-first public website split

The owner made `kiwikind-broadband` public. GitHub remains the primary source platform for the website, backend and Android app. This change does not alter repository visibility, authentication, hosting or working features. Credentials, signing material and account data must stay outside Git, including its history.

The separate public repository already exists: [FRYMASTERCHEESE/kiwikind-broadband-website](https://github.com/FRYMASTERCHEESE/kiwikind-broadband-website). Reuse it; no additional repository is needed.

Its Pages address is [KiwiKind Broadband](https://frymastercheese.github.io/kiwikind-broadband-website/). GitHub records a successful deployment of commit `114b1d9637434b53cb3b7c3b45dd28c6be361a88` in [run 38875629416](https://github.com/FRYMASTERCHEESE/kiwikind-broadband-website/actions/runs/38875629416). Verify live rendering separately; deployment success alone is not a browser check.

`public-site/index.html` in this private branch is a minimal informational preview. Do not overwrite the public repository's existing design with it. The optional manual packaging workflow exports that preview only and does not deploy it.

The website repository should deploy an explicit allowlist of reviewed static assets. Its current page is self-contained, so only `index.html` and a generated `.nojekyll` are needed. Do not include `.env`, signing files, `config/`, `portal/`, databases, CI files or the application checkout/history in the Pages artifact. Backend and Android source belong in the main repository; they are not static website assets. Review any additional assets before publication.

The Django-served `site/dist` client uses same-origin API, CSRF and session behavior. Moving that application onto github.io requires a separate authentication design review. Preserve the current backend, Android and Google sign-in integration. Public sign-up/login remain unavailable on the informational Pages site.

Retain the existing Render/Neon/email setup without a hosting migration or paid upgrade. Current free-plan status and quotas require independent confirmation. Keep customer intake, administration, billing and provisioning disabled until their respective approvals and verification are complete.
