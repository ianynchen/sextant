"""The URLs of the old shop, kept so bookmarks and partner links still work."""

from django.urls import re_path

from shop import views

urlpatterns = [
    re_path(r"^orders/(?P<order_id>\d+)/$", views.legacy_order),
    re_path(r"^track/?$", views.ping),
    re_path(r"^invoices/(?P<number>\d+)(\.pdf)?$", views.invoice),
    re_path(r"^(shelf|books)/$", views.shelf),
]
