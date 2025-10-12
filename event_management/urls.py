from django.urls import path
from . import views

app_name = 'event_management'

urlpatterns = [
    path('', views.event_management_dashboard, name='dashboard'),
    path('create/', views.create_event, name='create_event'),
    path('api/check-availability/', views.check_availability, name='check_availability'),
    path('api/metrics/', views.event_metrics_api, name='event_metrics_api'),
    path('api/calendar-events/', views.calendar_events_api, name='calendar_events_api'),
    path('api/room-availability/', views.room_availability_api, name='room_availability_api'),
    path('api/create-account/', views.create_account_api, name='create_account_api'),
    path('api/event-account-performance/', views.api_event_account_performance, name='api_event_account_performance'),
    path('api/recent-event-requests/', views.api_recent_event_requests, name='api_recent_event_requests'),
    path('api/update-request-status/', views.update_request_status, name='update_request_status'),
]
