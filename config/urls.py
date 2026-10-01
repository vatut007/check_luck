from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from receipts.views import signup

# /media/ не раздаётся напрямую (ни в DEBUG, ни в проде) — фото чека отдаёт
# только receipts:receipt-photo, с проверкой владельца.
urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/signup/", signup, name="signup"),
    path("accounts/", include("django.contrib.auth.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="api-docs"),
    path("api/", include("receipts.api.urls")),
    path("", include("receipts.urls")),
]
