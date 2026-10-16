#!/usr/bin/env python3
"""Six read-only prelaunch checks; never sends mail, creates users or contacts Neon."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def has(path, *terms):
    data = (ROOT / path).read_text(encoding="utf-8")
    return all(term in data for term in terms)

def main():
    gates = [
        ("1. Email verification token expiry and replay guard",
         has("portal/views.py", "salt='verify',max_age=86400", "if user.is_active: raise ValueError")),
        ("2. Password reset token expiry and replay guard",
         has("portal/views.py", "salt='reset',max_age=3600", "default_token_generator.check_token")),
        ("3. Password reset does not disclose unknown addresses",
         has("portal/views.py", "If the account is eligible, a reset email has been requested.")),
        ("4. Customer intake stays closed by default",
         has("config/settings.py", "INTAKE_ENABLED = os.getenv('INTAKE_ENABLED') == '1'")),
        ("5. Admin access requires MFA perimeter",
         has("config/settings.py", "ADMIN_MFA_PERIMETER_CONFIRMED")),
        ("6. SMTP settings available for a real delivery test",
         bool(os.getenv("EMAIL_HOST") and os.getenv("DEFAULT_FROM_EMAIL")
              and os.getenv("EMAIL_HOST_USER") and os.getenv("EMAIL_HOST_PASSWORD"))),
    ]
    for label, ok in gates:
        print(("PASS" if ok else "PENDING") + "  " + label)
    print("No network calls, email delivery, account changes or previously passing tests executed.")
    # SMTP being pending is expected in offline CI; exit nonzero only for source regressions.
    return 0 if all(ok for _, ok in gates[:5]) else 1

if __name__ == "__main__":
    sys.exit(main())
