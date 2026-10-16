from django.contrib import admin
from django.urls import path
from portal import views

urlpatterns = [path('', views.home), path('styles.css', views.styles), path('app.js', views.script), path('api/csrf', views.csrf), path('api/status', views.status),
 path('api/register', views.register), path('api/verify', views.verify), path('api/login', views.signin), path('api/google-login', views.google_signin), path('api/google-link', views.google_link),
 path('api/logout', views.signout), path('api/password-reset', views.reset_start),
 path('api/password-reset/confirm', views.reset_confirm), path('api/me', views.me),
 path('api/orders', views.orders), path('api/orders/<uuid:pk>/cancel', views.cancel_order),
 path('api/tickets', views.tickets), path('api/tickets/<uuid:pk>/messages', views.messages),
 path('api/invoices', views.invoices), path('api/privacy/export', views.export),
 path('api/privacy/deletion', views.deletion), path('healthz', views.health), path('admin/', admin.site.urls)]
