import os

SECRET_KEY = "orders-django-fixture"
DEBUG = os.environ.get("SHOP_DEBUG") == "1"
ROOT_URLCONF = "shop.urls"
ALLOWED_HOSTS = ["*"]
INSTALLED_APPS = ["django.contrib.contenttypes", "django.contrib.auth"]
USE_TZ = True
