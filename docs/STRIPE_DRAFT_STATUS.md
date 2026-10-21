# STOP: incomplete, untested Stripe work — do not merge or deploy

This branch preserves work requested by the owner. It is not a working release.
The attempted write of payments/test_live.py was blocked by the tool safety
system. That write has not been retried or routed through a different channel.
No new release has been deployed and no payment flags have been enabled.

The modules in this branch are proposed live-billing model, gateway, API, admin
and customer-page implementations. They are NOT registered with the existing
application yet. In particular, payments/live_service.py and the additive
migration are not generated; Android MainActivity navigation and the public
website are not changed. The preparatory script records exact intended edits
for later review, but it has NOT run. Its automatic workflow was removed from
this draft so no background code-writing job will be started.

The existing CI may still pass the unchanged current application; that must NOT
be represented as validation of these proposed new modules. Successful provider
transactions, current private environment configuration and the signed Android
release have not been verified. There is no connected Stripe tool in this
conversation, and no secret keys were requested or included.

Remaining prerequisites: resolve the blocked test-write action with appropriate
approval; finish and review the integration glue/migration; run all new and
regression tests; verify provider sandbox flows; retain a recovery checkpoint;
review signed Android and browser flows; configure live secrets privately; then
obtain explicit live release approval. Keep all live payments, supplier orders
and unapproved plan publication disabled. Do not use this draft as a workaround
for the blocked test write or enable it in production.
