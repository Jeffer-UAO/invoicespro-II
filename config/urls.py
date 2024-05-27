
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include


from drf_yasg.views import get_schema_view
from drf_yasg import openapi

from config import settings
from core.dashboard.views import *

from core.pos.api.router import router_category, router_product, router_provider
from core.user.api.router import router_user


schema_view = get_schema_view(
    openapi.Info(
        title="Documentation supra_enterprise_back",
        default_version='v 1.0.1',
        description="API supraEnterprise",
        terms_of_service="https://www.google.com/policies/terms/",
        contact=openapi.Contact(email="jeffer443@gmail.com"),
        license=openapi.License(name="BSD License"),
    ),
    public=True,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('dashboard/', DashboardView.as_view(), name='dashboard'),

     path('docs/', schema_view.with_ui('swagger',
         cache_timeout=0), name='schema-swagger-ui'),
    path('redocs/', schema_view.with_ui('redoc',
         cache_timeout=0), name='schema-redoc'),

    path('login/', include('core.login.urls')),
    path('pos/', include('core.pos.urls')),
    path('reports/', include('core.reports.urls')),
    path('rrhh/', include('core.rrhh.urls')),
    path('security/', include('core.security.urls')),
    path('tenant/', include('core.tenant.urls')),
    path('user/', include('core.user.urls')),
    path('', DashboardView.as_view(), name='dashboard'),

    path('api/', include('core.user.api.router')),
    path('api/', include(router_category.urls)),
    path('api/', include(router_product.urls)),
    path('api/', include(router_user.urls)),
    path('api/', include(router_provider.urls)),

    

]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
