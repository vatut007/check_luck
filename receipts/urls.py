from django.urls import path

from receipts import views

app_name = "receipts"

urlpatterns = [
    path("", views.home, name="home"),
    path("cabinet/", views.cabinet, name="cabinet"),
    path("receipts/new/", views.receipt_form, name="receipt-form"),
    path("receipts/<int:pk>/photo/", views.receipt_photo, name="receipt-photo"),
]
