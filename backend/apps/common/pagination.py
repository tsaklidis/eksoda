from rest_framework import pagination


class PageNumberPagination(pagination.PageNumberPagination):
    """``?page=&page_size=`` pagination; responses are ``{count, next, previous, results}``."""

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100
