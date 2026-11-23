from django.conf import settings
from django.urls import include, path, re_path
from django.views.decorators.cache import cache_page
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView

from shop import api_urls, views
from shop.integrations import partner_feeds, tracked

account_patterns = [
    path("profile/", views.profile),
    path("password/", views.change_password),
    path("wishlist/", views.wishlist),
]
help_patterns = [
    path("faq/", views.faq),
]
promo_patterns = [
    path("current/", views.promotions),
]

urlpatterns = [
    path("health/", views.health),
    path("catalog/", cache_page(60)(views.catalog)),
    path("products/<slug:slug>/", views.product),
    path("receipts/<uuid:token>/", views.receipt),
    path("files/<path:rest>", views.download),
    path("orders/", include("shop.orders.urls", namespace="shop-orders")),
    path("api/", include(api_urls)),
    path("account/", include(account_patterns)),
    path("help/", include((help_patterns, "help"))),
    path("support/", include(help_patterns)),
    path("webhooks/stripe/", csrf_exempt(views.stripe_webhook)),
    path("about/", TemplateView.as_view(template_name="about.html")),
    re_path(r"^legacy/", include("shop.legacy_urls")),
    path("partners/", include(partner_feeds.urls)),
    path("promo/", include(tracked(promo_patterns))),
]
urlpatterns += [
    path("ping/", views.ping),
]
urlpatterns.extend([path("exports/orders/", views.export_orders)])

if settings.DEBUG:
    urlpatterns += [path("debug/echo/", views.debug_echo)]
