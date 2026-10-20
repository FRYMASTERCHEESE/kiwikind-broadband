from django.urls import path
from . import views
urlpatterns = [
    path('api/billing/summary',views.summary),
    path('api/billing/checkout',views.checkout),
    path('api/billing/cancel',views.cancel),
    path('api/billing/refund',views.refund),
    path('api/billing/webhook',views.webhook),
    path('admin/billing-readiness/',views.readiness),
    path('billing/',views.page),
]
