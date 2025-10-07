from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView
from dashboard.views import (
    dashboard_view, api_request_chart_data, api_status_chart_data, 
    health_check, api_health_check, calendar_view, api_calendar_events,
    api_update_request_status, api_update_agreement_status, logout_view,
    api_deadline_alerts, api_generate_notifications, api_property_performance
)
from dashboard.api_views import (
    get_notifications, get_unread_count, mark_notification_read, 
    mark_all_read, clear_all_notifications, generate_notifications
)
from hotel_sales.currency_views import toggle_currency, get_currency_status
from hotel_sales.timezone_views import detect_timezone, get_current_timezone, set_timezone

# Configure admin site headers
admin.site.site_header = "Hotel Sales Management System"
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
    path('api/property-performance/', api_property_performance, name='api_property_performance'),
    path('api/calendar/events/', api_calendar_events, name='api_calendar_events'),
    path('api/update-request-status/', api_update_request_status, name='api_update_request_status'),
    path('api/update-agreement-status/', api_update_agreement_status, name='api_update_agreement_status'),
    path('api/deadline-alerts/', api_deadline_alerts, name='api_deadline_alerts'),
    path('api/generate-notifications/', api_generate_notifications, name='api_generate_notifications'),
    
    # Notification API endpoints
    path('api/notifications/', get_notifications, name='api_notifications'),
    path('api/notifications/unread-count/', get_unread_count, name='api_notifications_unread_count'),
    path('api/notifications/<int:notification_id>/mark-read/', mark_notification_read, name='api_notification_mark_read'),
    path('api/notifications/mark-all-read/', mark_all_read, name='api_notifications_mark_all_read'),
    path('api/notifications/clear-all/', clear_all_notifications, name='api_notifications_clear_all'),
    path('api/notifications/generate/', generate_notifications, name='api_notifications_generate'),
    
    # Currency toggle endpoints
    path('api/currency/toggle/', toggle_currency, name='api_currency_toggle'),
    path('api/currency/status/', get_currency_status, name='api_currency_status'),
    
    # Timezone detection endpoints
    path('api/timezone/detect/', detect_timezone, name='api_timezone_detect'),
    path('api/timezone/current/', get_current_timezone, name='api_timezone_current'),
    path('api/timezone/set/', set_timezone, name='api_timezone_set'),
    
    path('logout/', logout_view, name='logout'),
    path('configuration/', include('requests.configuration_urls')),
    path('event-management/', include('event_management.urls')),
    path('admin/', admin.site.urls),
]

# Serve media files during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
