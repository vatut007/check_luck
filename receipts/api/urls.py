from django.urls import path

from receipts.api import views

app_name = "receipts_api"

urlpatterns = [
    path("receipts/", views.ReceiptListCreateView.as_view(), name="receipt-list-create"),
    path("promo/", views.PromoConfigView.as_view(), name="promo-config"),
]
