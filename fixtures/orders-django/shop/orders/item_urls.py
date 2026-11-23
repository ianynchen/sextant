from django.urls import path

from shop.orders.views import ArchivedItems, OrderItems

urlpatterns = [
    path("", OrderItems.as_view()),
    path("archived/", ArchivedItems.as_view()),
]
