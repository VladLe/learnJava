from django.contrib import admin
from django.shortcuts import render

from .metrics import compute_metrics


def metrics_view(request):
    context = {
        **admin.site.each_context(request),
        "title": "Метрики конвейера",
        "metrics": compute_metrics(),
    }
    return render(request, "admin/newsroom/metrics.html", context)
