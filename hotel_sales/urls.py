from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView
from dashboard.views import (
    dashboard_view, api_request_chart_data, api_status_chart_data, 
    health_check, api_health_check, calendar_view, api_calendar_events
)

# Configure admin site headers
admin.site.site_header = "Hotel Sales Request Management System"
admin.site.site_title = "Hotel Sales Admin"
admin.site.index_title = "Welcome to Hotel Sales Management"

urlpatterns = [
    path('', RedirectView.as_view(url='/dashboard/', permanent=False), name='home'),
    path('health/', health_check, name='health_check'),
    path('api', api_health_check, name='api_health_check_no_slash'),
    path('api/', api_health_check, name='api_health_check'),
    path('api/health/', api_health_check, name='api_health_check_alt'),
    path('dashboard/', dashboard_view, name='dashboard'),
    path('calendar/', calendar_view, name='calendar'),
    path('api/request-chart-data/', api_request_chart_data, name='api_request_chart_data'),
    path('api/status-chart-data/', api_status_chart_data, name='api_status_chart_data'),
    path('api/calendar/events/', api_calendar_events, name='api_calendar_events'),
    path('admin/', admin.site.urls),
]

# Serve media files during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
