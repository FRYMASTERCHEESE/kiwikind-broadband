from django.contrib.admin.apps import AdminConfig

class OwnerAdminConfig(AdminConfig):
    default_site = 'portal.admin_site.OwnerAdminSite'
