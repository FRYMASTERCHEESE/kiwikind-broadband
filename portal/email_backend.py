"""Backend-only Brevo HTTPS delivery. No SMTP fallback or automatic retries."""
from email.utils import parseaddr

import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail.backends.base import BaseEmailBackend
from django.core.validators import validate_email
from django.views.decorators.debug import sensitive_variables


class MailDeliveryError(OSError):
    """Safe to log: never contains a provider response, address, token or key."""


class BrevoEmailBackend(BaseEmailBackend):
    # Fixed origin prevents credentials being sent to an arbitrary configured URL.
    origin = 'https://api.brevo.com/v3'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.session = None
        self.sender = None

    @staticmethod
    def address(value):
        name, address = parseaddr(value)
        try:
            validate_email(address)
        except ValidationError:
            raise MailDeliveryError('Email sender configuration is invalid') from None
        return {'name': name or 'KiwiKind Broadband', 'email': address}

    @sensitive_variables()
    def _request(self, method, path, expected, **kwargs):
        try:
            with self.session.request(
                method, self.origin + path, timeout=(3, 7),
                allow_redirects=False, **kwargs,
            ) as response:
                if response.status_code != expected:
                    # Do not include response text: it can contain recipient or key data.
                    raise MailDeliveryError('HTTPS email provider unavailable')
                result = response.json()
        except (requests.RequestException, ValueError):
            raise MailDeliveryError('HTTPS email provider unavailable') from None
        if not isinstance(result, dict):
            raise MailDeliveryError('HTTPS email provider returned an invalid response')
        return result

    @sensitive_variables()
    def open(self):
        if self.session is not None:
            return False
        key = settings.BREVO_API_KEY.strip()
        if not key:
            raise MailDeliveryError('HTTPS email provider is not configured')
        self.sender = self.address(settings.DEFAULT_FROM_EMAIL)
        self.reply_to = self.address(settings.EMAIL_REPLY_TO)
        self.session = requests.Session()
        self.session.headers.update({'api-key': key, 'Accept': 'application/json'})
        try:
            account = self._request('GET', '/account', 200)
            plans = account.get('plan', [])
            relay = account.get('relay')
            # SMS is an independent allowance. Paid/unknown email plans fail closed.
            if (not isinstance(plans, list) or not plans
                or any(not isinstance(p, dict) or p.get('type') not in ('free', 'sms') for p in plans)
                or not any(p.get('type') == 'free' and isinstance(p.get('credits'), (int, float))
                           and p['credits'] > 0 for p in plans)
                or not isinstance(relay, dict) or relay.get('enabled') is not True):
                raise MailDeliveryError('Free transactional email allowance unavailable')
            senders = self._request('GET', '/senders', 200).get('senders', [])
            if not isinstance(senders, list) or not any(
                isinstance(s, dict) and s.get('active') is True
                and str(s.get('email', '')).lower() == self.sender['email'].lower()
                for s in senders
            ):
                raise MailDeliveryError('HTTPS email sender is not verified')
        except Exception:
            self.close()
            raise
        return True

    def close(self):
        if self.session is not None:
            self.session.headers.clear()
            self.session.close()
            self.session = None

    @sensitive_variables()
    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        opened = False
        count = 0
        try:
            opened = self.open()
            for message in email_messages:
                if not message.recipients():
                    continue
                # Only the configured, verified sender and plain-text account mail
                # are supported. Do not forward arbitrary headers or attachments.
                if self.address(message.from_email)['email'].lower() != self.sender['email'].lower():
                    raise MailDeliveryError('Email sender does not match configuration')
                if message.cc or message.bcc or message.attachments or getattr(message, 'alternatives', None):
                    raise MailDeliveryError('Unsupported transactional email format')
                result = self._request('POST', '/smtp/email', 201, json={
                    'sender': self.sender,
                    'replyTo': self.reply_to,
                    'to': [{'email': address} for address in message.to],
                    'subject': message.subject,
                    'textContent': message.body,
                })
                if not isinstance(result.get('messageId'), str) or not result['messageId']:
                    raise MailDeliveryError('HTTPS email provider did not accept the message')
                count += 1
        except MailDeliveryError:
            if not self.fail_silently:
                raise
        finally:
            if opened:
                self.close()
        return count
