from django.urls import path

from receipts import views

app_name = "receipts"

urlpatterns = [
    path("", views.home, name="home"),
]
