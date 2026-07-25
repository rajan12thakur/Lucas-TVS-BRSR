"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('apps.accounts.urls')),
    path('companies/',include('apps.companies.urls')),
    path('notifications/', include('apps.notifications.urls')),
    path('brsr/', include('apps.brsr.urls')),
    path('organizations/', include('apps.organizations.urls')),
    path('email_master/', include('apps.email_master.urls')),
    # path('api/', include('apps.calculator.urls')),  # For /api/get-conversion/
    path('calculator/', include('apps.calculator.urls')),  # For /calculator/api/get-conversion
    path("emission/", include('apps.emission.urls')),
    path("goals/", include("apps.goals.urls")),
    path("report/", include("apps.report.urls")),
]


if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )
