from django.urls import path, re_path

from shop import views

v1_patterns = [
    path("v1/cart/", views.cart),
    re_path(r"^v1/status/$", views.health),
]
v2_patterns = [
    path("v2/cart/", views.cart),
]

urlpatterns = v1_patterns + v2_patterns
