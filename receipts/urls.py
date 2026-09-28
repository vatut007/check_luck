from django.urls import path

from receipts import views

app_name = "receipts"

urlpatterns = [
    path("", views.home, name="home"),
    path("receipts/new/", views.receipt_form, name="receipt-form"),
]
