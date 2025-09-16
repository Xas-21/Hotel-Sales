"""
Form Composer URLs

URL patterns for the Form Composer interface
"""

from django.urls import path
from . import views

app_name = 'form_composer'

urlpatterns = [
    # Main interface
    path('', views.form_composer_index, name='index'),
    path('editor/<int:form_definition_id>/', views.form_composer_editor, name='editor'),
    
    # Section management
    path('form/<int:form_definition_id>/add-section/', views.add_section, name='add_section'),
    path('section/<int:section_id>/add-field/', views.add_field_to_section, name='add_field_to_section'),
    path('section/<int:section_id>/properties/', views.section_properties, name='section_properties'),
    path('section/<int:section_id>/update/', views.update_section, name='update_section'),
    path('section/<int:section_id>/toggle/', views.toggle_section, name='toggle_section'),
    path('section/<int:section_id>/delete/', views.delete_section, name='delete_section'),
    path('section/<int:section_id>/update-field-order/', views.update_field_order, name='update_field_order'),
    
    # Field management
    path('field/<int:field_id>/properties/', views.field_properties, name='field_properties'),
    path('field/<int:field_id>/update/', views.update_field, name='update_field'),
    path('field/<int:field_id>/delete/', views.delete_field, name='delete_field'),
    path('section/<int:section_id>/move-field/', views.move_field_to_section, name='move_field_to_section'),
    
    # Ordering
    path('update-section-order/', views.update_section_order, name='update_section_order'),
]