import pytest
from django.urls import reverse

from receipts.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

HOME_URL = "/"


class TestHomeRedirect:
    def test_authenticated_user_is_redirected_to_cabinet(self, client):
        user = UserFactory()
        client.force_login(user)

        response = client.get(HOME_URL)

        assert response.status_code == 302
        assert response.url == reverse("receipts:cabinet")

    def test_anonymous_user_ends_up_at_login(self, client):
        response = client.get(HOME_URL, follow=True)

        assert response.redirect_chain
        assert response.request["PATH_INFO"] == reverse("login")
