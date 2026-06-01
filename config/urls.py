from django.contrib import admin
from django.urls import path
from django.views.decorators.csrf import csrf_exempt

from api.schema import schema
from api.views import JWTGraphQLView

urlpatterns = [
    path('admin/', admin.site.urls),
    # CSRF-exempt: authentication is via the Authorization bearer header,
    # not session cookies, so CSRF protection does not apply.
    path('graphql/', csrf_exempt(JWTGraphQLView.as_view(schema=schema))),
]
