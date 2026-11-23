from django.contrib.auth.decorators import login_required
from django.urls import include, path

from shop.orders.views import MyOrders, OrderDetail, OrderHistory, ShippingPage, StatusProbe

app_name = "orders"

urlpatterns = [
    path("<int:order_id>/", OrderDetail.as_view()),
    path("<int:order_id>/items/", include("shop.orders.item_urls")),
    path("mine/", MyOrders.as_view()),
    path("history/", login_required(OrderHistory.as_view())),
    path("status/", StatusProbe.as_view()),
    path("shipping/", ShippingPage.as_view()),
]
