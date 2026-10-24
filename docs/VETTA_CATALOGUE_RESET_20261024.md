# KiwiKind Broadband — Vetta catalogue hard reset (24 October 2026)

Owner instruction: remove all prior supplier plan entries, prices, download/upload speed selections and allowances. Start a NEW verification process using the authenticated Vetta wholesale portal. Do not recover or publish the former eight-product catalogue or the older unverified drafts.

## Verified production state after reset

- Neon primary database, `public.portal_privatecataloguerelease`: **0 records**.
- `public.portal_draftplan`: **0 records**.
- `public.portal_verifiedsupplieroption`: **0 records**.
- The public `/api/broadband/catalogue` and compatibility `/api/plans` both respond with empty product/plan arrays. Catalogue orders and supplier orders are disabled.
- One existing customer broadband request is preserved as historical customer data. Accounts, support, audit history and payment configuration were not reset.
- To prevent a concurrent old import from resurrecting offers, the primary database now has validated constraint `kiwikind_vetta_reset_freeze CHECK (false)` on `portal_privatecataloguerelease`. **No new catalogue release/draft payload can be inserted or updated until the owner explicitly authorises unlocking it.**
- Historic Neon snapshots, Git history and prior Work output may retain old data but are not live authoritative prices. Never deploy or re-import those figures as if current Vetta prices.

## Website and app source cleanup

- Website main branch removes hard-coded fibre speed suggestions, outdated setup prices and the old Vetta-derived test fixture. No static price, download/upload speed or data allowance is shown as an active offer.
- Android source branch `feature/neon-postgres-config` removes the hard-coded default 500/100 speed picker, and displays an empty-catalogue notice. Existing installed Play builds read the same live API; source changes require a separate signed Android release before they appear in the installed binary.
- Site and Android should accept plan data only from the shared backend when it has been populated from fresh, verified wholesale evidence, and never fall back to example pricing.

## Restart procedure (ONLY on new explicit owner instruction)

1. Obtain fresh Vetta portal/service evidence with product names, exact download and upload speeds, data allowance and excess usage policy, monthly component prices, once-only fees, equipment charges, network and GST basis.
2. Compare private source evidence against each proposed complete retail service configuration. Never substitute public retail prices, past screenshots, old commits, generic ISP assumptions or incomplete supplier components.
3. Before new deliberate imports, remove the freeze in the **correct primary Neon database** with the narrowly scoped statement: `ALTER TABLE public.portal_privatecataloguerelease DROP CONSTRAINT kiwikind_vetta_reset_freeze;`. Do not do this automatically or for an old Work task. Owner permission and fresh evidence are required.
4. Populate private drafts and verify all tax and price calculations, including the previously requested NZ$4 monthly retail adjustment on the correct verified basis. Keep wholesale details private.
5. Separately approve release for publication only after source-by-source review. Do not collect customer payments, place supplier orders or claim service availability without explicit release and operational approval.

Last verified: public APIs empty and the database freeze validated. This note records a reset, **not** supplier integration or readiness for broadband sales.
