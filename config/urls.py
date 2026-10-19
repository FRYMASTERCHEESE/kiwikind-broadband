from django.contrib import admin
from django.urls import path
from portal import views
from portal import owner_admin
from portal import wholesale_admin, wholesale_views

# Shared native/web account APIs; all account-specific routes enforce sessions.

urlpatterns = [path('api/connection-progress', wholesale_views.connection_progress),
 path('admin/wholesale/', admin.site.admin_view(wholesale_admin.dashboard), name='wholesale-dashboard'),
 path('privacy/', views.privacy_policy), path('account-deletion/', views.account_deletion_info), path('', views.home), path('styles.css', views.styles), path('app.js', views.script), path('api/csrf', views.csrf), path('api/status', views.status),
 path('app-ads.txt', views.advertising_sellers), path('ads.txt', views.advertising_sellers),
 path('readiness.js',views.readiness_script), path('api/bootstrap',views.bootstrap), path('api/referrals',views.referrals), path('api/preferences',views.preferences),
 path('api/register', views.register), path('api/verify', views.verify), path('api/login', views.signin), path('api/google-login', views.google_signin), path('api/google-callback', views.google_callback), path('api/google-link', views.google_link),
 path('api/logout', views.signout), path('api/password-reset', views.reset_start),
 path('api/password-reset/confirm', views.reset_confirm), path('api/me', views.me),
 path('api/orders', views.orders), path('api/orders/<uuid:pk>/cancel', views.cancel_order),
 path('api/tickets', views.tickets), path('api/tickets/<uuid:pk>/messages', views.messages),
 path('api/invoices', views.invoices), path('api/privacy/export', views.export),
 path('api/privacy/deletion', views.deletion), path('healthz', views.health),
 path('admin/owner-signin/', owner_admin.owner_signin),
 path('admin/owner.js', owner_admin.owner_script), path('admin/', admin.site.urls)]
