from django.contrib import admin
from django.urls import path

from newsroom.admin_views import metrics_view

urlpatterns = [
    path("admin/metrics/", admin.site.admin_view(metrics_view), name="newsroom_metrics"),
    path("admin/", admin.site.urls),
]
