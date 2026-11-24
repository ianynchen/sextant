from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.views import View
from django.views.generic import TemplateView

from shop.base import JsonView


class OrderDetail(View):
    def get(self, request, order_id):
        return HttpResponse(str(order_id))

    def delete(self, request, order_id):
        return HttpResponse(status=204)


class OrderItems(JsonView):
    pass


class MyOrders(LoginRequiredMixin, View):
    def get(self, request):
        return HttpResponse("mine")


class OrderHistory(View):
    def get(self, request):
        return HttpResponse("history")


class ArchivedItems(View):
    http_method_names = ["get"]  # noqa: RUF012  (Django's own spelling of the list)

    def get(self, request, order_id):
        return HttpResponse("archived")

    def post(self, request, order_id):
        return HttpResponse("restored")


class StatusProbe(View):
    def dispatch(self, request, *args, **kwargs):
        return HttpResponse("up")


class ShippingPage(TemplateView):
    template_name = "orders/shipping.html"
