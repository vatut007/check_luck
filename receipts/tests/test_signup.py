import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

pytestmark = pytest.mark.django_db

SIGNUP_URL = "/accounts/signup/"


class TestSignupView:
    def test_get_renders_form(self, client):
        response = client.get(SIGNUP_URL)

        assert response.status_code == 200
        assert b'name="username"' in response.content

    def test_valid_post_creates_user_logs_in_and_redirects_to_cabinet(self, client):
        response = client.post(
            SIGNUP_URL,
            data={
                "username": "newparticipant",
                "password1": "a-very-strong-pass123",
                "password2": "a-very-strong-pass123",
            },
        )

        assert response.status_code == 302
        assert response.url == reverse("receipts:cabinet")
        assert get_user_model().objects.filter(username="newparticipant").exists()
        follow = client.get(reverse("receipts:cabinet"))
        assert follow.status_code == 200

    def test_password_mismatch_rerenders_form_with_error(self, client):
        response = client.post(
            SIGNUP_URL,
            data={
                "username": "newparticipant",
                "password1": "a-very-strong-pass123",
                "password2": "does-not-match",
            },
        )

        assert response.status_code == 200
        assert not get_user_model().objects.filter(username="newparticipant").exists()

    def test_duplicate_username_rerenders_form_with_error(self, client):
        get_user_model().objects.create_user(username="taken", password="whatever123")

        response = client.post(
            SIGNUP_URL,
            data={
                "username": "taken",
                "password1": "a-very-strong-pass123",
                "password2": "a-very-strong-pass123",
            },
        )

        assert response.status_code == 200
        assert get_user_model().objects.filter(username="taken").count() == 1

    def test_login_page_links_to_signup(self, client):
        response = client.get(reverse("login"))

        assert response.status_code == 200
        assert reverse("signup").encode() in response.content
