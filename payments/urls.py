from django.urls import path
from . import views, owner_qa, live_preflight, live_views
urlpatterns = [
    path('api/payments/summary', live_views.summary),
    path('api/payments/checkout', live_views.checkout),
    path('api/payments/cancel', live_views.cancel),
    path('api/payments/webhook', live_views.webhook),
    path('api/billing/summary', views.summary),
    path('api/billing/checkout', views.checkout),
    path('api/billing/cancel', views.cancel),
    path('api/billing/refund', views.refund),
    path('api/billing/webhook', views.webhook),
    path('admin/billing-readiness/', views.readiness),
    path('admin/billing-qa/', owner_qa.owner_qa),
    path('admin/live-stripe-readiness/', live_preflight.owner_live_status),
    path('billing/', views.page),
]
