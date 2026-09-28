"""
Django settings for config project.
"""

import datetime as dt
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import environ
from django.core.exceptions import ImproperlyConfigured

from config.promo import PromoConfig

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
SECURE_COOKIES = env.bool("DJANGO_SECURE_COOKIES", default=False)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "receipts",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": env.db("DATABASE_URL"),
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- Промо-акция -------------------------------------------------------

PROMO_TIMEZONE = env("PROMO_TIMEZONE", default="Europe/Moscow")

try:
    PROMO = PromoConfig(
        start_date=dt.date.fromisoformat(env("PROMO_START")),
        end_date=dt.date.fromisoformat(env("PROMO_END")),
        timezone=ZoneInfo(PROMO_TIMEZONE),
        min_amount=Decimal(env("PROMO_MIN_AMOUNT", default="1000")),
        photo_max_mb=env.int("RECEIPT_PHOTO_MAX_MB", default=5),
    )
except ValueError as exc:
    raise ImproperlyConfigured(str(exc)) from exc

RECEIPT_PHOTO_MAX_MB = PROMO.photo_max_mb

# --- Интернационализация ------------------------------------------------

LANGUAGE_CODE = "ru"
TIME_ZONE = PROMO_TIMEZONE
USE_I18N = True
USE_TZ = True

# --- Статика и медиа ------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        # Хэшированный манифест — только в проде, где entrypoint.sh запускает
        # collectstatic. Локально/в тестах манифеста нет, и он не нужен.
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        ),
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Cookies и CSRF ---------------------------------------------------

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = SECURE_COOKIES

CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = SECURE_COOKIES

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "receipts:cabinet"
LOGOUT_REDIRECT_URL = "login"

# --- DRF и Swagger ---------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 10,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "receipts-write": "20/min",
    },
    "EXCEPTION_HANDLER": "receipts.api.exceptions.exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Чек на удачу — API",
    "DESCRIPTION": "API промо-акции «Чек на удачу».",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}
