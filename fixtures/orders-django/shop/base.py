from django.http import HttpResponse
from django.views import View


class JsonView(View):
    """The project's base for its JSON resources: list with GET, create with POST."""

    def get(self, request, *args, **kwargs):
        return HttpResponse("[]")

    def post(self, request, *args, **kwargs):
        return HttpResponse("{}", status=201)
