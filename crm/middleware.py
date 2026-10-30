class HtmxAuthenticationMiddleware:
    """Turn HTMX login redirects into a full navigation instead of a partial swap."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.headers.get("HX-Request") and response.status_code == 302:
            location = response.get("Location", "")
            if location.startswith("/login/"):
                response.status_code = 401
                response["HX-Redirect"] = location
                response["Cache-Control"] = "no-store"
        return response

