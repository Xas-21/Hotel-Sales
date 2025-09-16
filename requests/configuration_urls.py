"""
Configuration URLs

URL patterns for the Motion/Notion-style configuration dashboard.
"""

from django.urls import path
from . import configuration_views

app_name = 'configuration'

urlpatterns = [
    # Main configuration dashboard
    path('', configuration_views.configuration_dashboard, name='dashboard'),
    
    # Section field management
    path('section/<int:section_id>/', configuration_views.section_fields, name='section_fields'),
    
    # Field operations
    path('section/<int:section_id>/add-field/', configuration_views.add_field, name='add_field'),
    path('field/<int:field_id>/update/', configuration_views.update_field, name='update_field'),
    path('field/<int:field_id>/delete/', configuration_views.delete_field, name='delete_field'),
    
    # Section operations
    path('create-section/', configuration_views.create_section, name='create_section'),
    path('section/<int:section_id>/delete/', configuration_views.delete_section, name='delete_section'),
]