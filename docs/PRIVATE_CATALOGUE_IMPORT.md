# Private wholesale CSV import (owner only)

The public GitHub Pages site remains the public website. Render remains the
API/backend and the owner MFA-only admin. No live orders or payments are enabled.

The importer lives at /admin/catalogue/import/. A verified owner Google
session and authenticator MFA are mandatory. CSV upload requires CSRF and an
explicit draft-only checkbox. The input never enters GitHub, the public
website, logs or a stored raw upload.

Download the blank CSV header template from the private admin screen.
Rows can contain name, download_mbps, upload_mbps, network,
wholesale_ex_gst, setup_ex_gst, retail_ex_gst, retail_setup_ex_gst,
source_reference. The five mandatory columns are name, both speeds,
wholesale_ex_gst and source_reference. The operator must use only actual
authorised quote facts; **no sample supplier prices are published**.

Each imported row is:
- review_status='draft'; address_specific=True; never auto-approved
- not marked verified; no fabricated valid-until date
- limited to server-calculated 15% NZ GST illustrations
- imported transactionally, all-or-nothing, with immutable audit record
- not an address check, an API call, a supplier order or a customer bill
- rejected if its name collides with an edited/approved/conflicting row
- repeat safe when the same private draft already exists

A signed master framework agreement alone does not establish any individual
Product Terms, completed wholesale onboarding, API access or accepted order.
Only quote entries with the current authorised source, correct tax treatment,
network, speeds, scope, validity, owner approval and separate release approval
may ever become public; the existing public projection independently enforces
its publication gate. No source contract terms or signed contracts belong in
the public repository. Supplier/API integration remains unavailable until
the provider delivers authenticated official integration documentation.
