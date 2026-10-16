# NZ business and service launch gates

As of 16 October 2026 the owner confirms no registered operating business/NZBN and no wholesale agreement. KiwiKind Broadband is a working brand, not evidence of company incorporation. Company versus sole-trader structure needs an owner decision; this build does not register either.

## Before public customer intake

- Decide legal operating structure; obtain applicable registrations/NZBN and business contact details. Review tax/GST obligations with an adviser. IRD's GST guidance covers the $60,000 threshold and other triggers: https://www.ird.govt.nz/gst/registering-for-gst
- Clear the brand using IPONZ Trade Mark Check (including similar marks, relevant class 38 telecom services and any other relevant classes), Companies Register/ONECheck and domain registry/registrar checks. A company name, domain or search-engine absence does not clear a trademark. Use https://www.iponz.govt.nz/get-ip/trade-marks/search/ and https://dnc.org.nz/tools-and-services/how-do-i-2/domain-availability/
- Approve actual privacy notice, hosting subprocessors, privacy officer/contact, overseas arrangements, security and retention schedule. Current site copy is a draft, not a representation that compliance is complete.
- Provide support access without sign-in, assign responsible operators and response processes. Test password reset, support and privacy requests end to end using real authorised mail infrastructure.
- Apply production deployment gates and staging acceptance tests. Keep `INTAKE_ENABLED=0` until approved.

## Before selling broadband

- Sign a real wholesale/reseller agreement, confirm network/region rights, rates and minimum commitments; obtain the supplier's actual API documentation and sandbox. No invented commercial offers are in the project.
- Decide whether to use a managed wholesale/reseller service or operate more network functions. Confirm address qualification, access technology, CPE ownership/returns, installation/consents, backhaul/transit responsibilities, authentication, addressing, faults, switching, cancellations and supplier SLAs.
- Add a verified supplier catalog and quote validity, total NZD pricing/GST/setup/equipment/termination terms, speed and traffic-management disclosures and separate customer acceptance. Follow Commerce Commission retail service quality/product disclosure requirements: https://www.comcom.govt.nz/regulated-industries/telecommunications/projects/retail-service-quality/
- Assess applicable Telecommunications Act, Fair Trading Act, Consumer Guarantees Act, lawful assistance/interception/network-security requirements and any registrations/levies/reporting. Scope these with qualified NZ advisers and supplier; software alone does not resolve them.
- Establish complaints escalation and assess TDR membership/obligations; do not claim membership before confirmation. Confirm the applicable 111 Contact Code duties, including disclosures for future naked broadband offers and any residential voice service. The current app provides no voice service. https://www.comcom.govt.nz/regulated-industries/telecommunications/telecommunications-for-consumers/commission-111-contact-code/
- Validate provisioning sandbox then controlled live pilot; match supplier events to customer consent and audit records. Add HMAC/mTLS verification, event timestamps, unique event IDs, replay rejection, retry/dead-letter handling, reconciliation and manual failure recovery.
- Implement proper billing schedules, pro-rating/tax documents, consented payment methods, provider-hosted card collection, signed payment webhooks, idempotency, disputes, refunds and reconciliation. This build has none of these live integrations.

## Privacy operating foundations

Direct collection covers the current forms. Assess IPP3A when suppliers or others provide information indirectly (in force from 1 May 2026). Review all privacy principles and overseas arrangements: https://www.privacy.org.nz/privacy-principles/ and https://www.privacy.org.nz/responsibilities/disclosing-personal-information-outside-new-zealand/decision-tree-page/

Proposed retention for approval, **not automated**: unverified accounts 7 days; withdrawn/unconverted enquiries 90 days; support 12 months after closure; pseudonymous security events 90 days; accounting records according to confirmed statutory retention duties once billing exists. Backups have a bounded expiry. Add and test approved purge jobs before real intake. Database session/rate-bucket cleanup also needs scheduled maintenance. Current deletion requests are queued for a human; marking a request completed in admin does not delete its underlying records.

Privacy access/correction requests must be tracked and answered within applicable statutory timeframes (normally 20 working days, subject to permitted extensions). Publish the real privacy contact before intake. Verify requesters without collecting unnecessary ID. Export downloads contain personal information; keep them private.

Incident runbook: contain access, disable intake if needed, preserve limited evidence, assess harm, notify OPC and affected people as soon as practicable for notifiable breaches; OPC expects notification ideally within 72 hours of awareness. Record decisions and follow up as facts become clear. Source: https://www.privacy.org.nz/responsibilities/privacy-breaches/notify-us/
