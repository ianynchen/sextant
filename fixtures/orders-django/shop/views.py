from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.views.decorators.http import (
    require_GET,
    require_http_methods,
    require_POST,
    require_safe,
)

from shop.integrations import audited


def health(request):
    return HttpResponse("ok")


def ping(request):
    return HttpResponse("pong")


def catalog(request):
    return HttpResponse("catalog")


@require_GET
def product(request, slug):
    return HttpResponse(slug)


@require_safe
def receipt(request, token):
    return HttpResponse(str(token))


@require_GET
def download(request, rest):
    return HttpResponse(rest)


@require_http_methods(["GET", "POST"])
def cart(request):
    return HttpResponse(request.GET.get("coupon", ""))


@require_POST
def stripe_webhook(request):
    return HttpResponse("accepted")


@login_required
def profile(request):
    return HttpResponse("profile")


@login_required
@require_POST
def change_password(request):
    return HttpResponse("changed")


def faq(request):
    return HttpResponse("faq")


@audited
def export_orders(request):
    return HttpResponse("export")


@login_required(login_url="/accounts/login/")
def wishlist(request):
    return HttpResponse("wishlist")


def promotions(request):
    return HttpResponse("promotions")


def debug_echo(request):
    return HttpResponse(request.GET.get("msg", ""))


def legacy_order(request, order_id):
    return HttpResponse(order_id)


@require_GET
def invoice(request, number):
    return HttpResponse(number)


def shelf(request, section):
    return HttpResponse(section)
