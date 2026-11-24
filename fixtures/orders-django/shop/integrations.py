"""Project helpers: an audit decorator, a partner feed router, a pattern wrapper."""

import functools

from django.http import HttpResponse
from django.urls import path


def audited(view):
    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        return view(request, *args, **kwargs)

    return wrapper


def tracked(patterns):
    return list(patterns)


class PartnerFeeds:
    """Stands in for a third-party router that publishes its routes as `.urls`."""

    def feed(self, request):
        return HttpResponse("feed")

    @property
    def urls(self):
        return [path("feed/", self.feed)]


partner_feeds = PartnerFeeds()
