from django.conf import settings
from django_otp.admin import OTPAdminSite, OTPAdminAuthenticationForm

OWNER_EMAIL = 'kiwikindbroadband@gmail.com'

def is_owner(user):
    if not user.is_authenticated or not user.is_active or not user.is_staff:
        return False
    if str(user.pk) != str(settings.OWNER_USER_ID) or user.email != OWNER_EMAIL or user.username != OWNER_EMAIL:
        return False
    from .models import EmailVerification
    return EmailVerification.objects.filter(user=user, email=OWNER_EMAIL).exists()

class OwnerAuthenticationForm(OTPAdminAuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not is_owner(user):
            from django.core.exceptions import ValidationError
            raise ValidationError('Unable to sign in.', code='invalid_login')

class OwnerAdminSite(OTPAdminSite):
    login_form = OwnerAuthenticationForm

    def has_permission(self, request):
        return settings.ADMIN_ENABLED and is_owner(request.user) and super().has_permission(request)

