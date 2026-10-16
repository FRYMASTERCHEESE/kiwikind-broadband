# GitHub-first public website split

This branch adds an **informational, public-safe landing page** in `public-site/index.html`. It is not a deployed GitHub Pages site and does not contain private backend/Android source.

Why the existing `site/dist` cannot simply be copied to GitHub Pages: it currently assumes same-origin Django API, CSRF and session cookies. On a separate github.io origin, these flows require deliberate cookie, CSRF, CORS and Google OAuth security design. Until reviewed, public visitors are sent to the existing secure Render portal for test-account sign-in.

## Owner action to finish GitHub Pages

1. Create a separate **public** repository named `kiwikind-broadband-site` under FRYMASTERCHEESE. Never make the existing `kiwikind-broadband` repository public.
2. Copy only the files inside `public-site/` to the new repository's root. Do not copy `.env`, Android signing files, `config/`, `portal/` or private CI files.
3. In the public repository, Settings → Pages → Deploy from a branch → `main` / root. Its address should then be `https://frymastercheese.github.io/kiwikind-broadband-site/` after publication.
4. Keep Render Free for authenticated API/portal, Neon for data and Brevo for mail. Do not enable customer intake or claim live ISP service.

The optional `Prepare public Pages files` workflow packages just the allowlisted landing page as a downloadable artifact. It does not deploy, require a paid account or rerun previous suites.
