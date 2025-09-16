"""
Form Composer Views

Django views for the modern form configuration interface.
Provides drag-and-drop form building with HTMX-powered updates.
"""

from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db import models
import json
import logging

from .models import FormDefinition, FormSection, FieldConfig, DynamicFieldValue
from .services import ConfigRegistry, ConfigEnforcementV2
from django.contrib.contenttypes.models import ContentType

logger = logging.getLogger(__name__)

def is_staff(user):
    """Check if user is staff"""
    return user.is_staff

@login_required
@user_passes_test(is_staff)
def form_composer_index(request):
    """
    Main Form Composer index page showing all form definitions
    """
    form_definitions = FormDefinition.objects.filter(is_active=True).select_related('target_model')
    
    context = {
        'form_definitions': form_definitions,
        'registered_models': ConfigRegistry.get_registered_models(),
    }
    
    return render(request, 'form_composer/index.html', context)

@login_required
@user_passes_test(is_staff)
def form_composer_editor(request, form_definition_id):
    """
    Main Form Composer editor interface
    """
    form_definition = get_object_or_404(FormDefinition, id=form_definition_id, is_active=True)
    sections = form_definition.get_sections_ordered()
    
    # Get model fields for the palette
    model_fields = []
    try:
        model_class = form_definition.get_model_class()
        if model_class:
            model_fields = ConfigRegistry.get_model_fields(model_class)
    except Exception as e:
        logger.error(f"Error getting model fields for {form_definition}: {e}")
        messages.warning(request, "Could not load model fields for this form.")
    
    context = {
        'form_definition': form_definition,
        'sections': sections,
        'model_fields': model_fields,
    }
    
    return render(request, 'form_composer/form_composer.html', context)

@login_required
@user_passes_test(is_staff)
@require_POST
def add_section(request, form_definition_id):
    """
    Add a new section to the form
    """
    form_definition = get_object_or_404(FormDefinition, id=form_definition_id, is_active=True)
    
    try:
        # Get the next order number
        max_order = FormSection.objects.filter(form_definition=form_definition).aggregate(
            max_order=models.Max('order')
        )['max_order'] or 0
        
        section = FormSection.objects.create(
            form_definition=form_definition,
            name=request.POST.get('name', 'New Section'),
            slug=request.POST.get('slug') or None,  # Auto-generated in model
            order=max_order + 1,
            description=request.POST.get('description', ''),
            is_active=True,
            is_collapsed=False,
        )
        
        if request.headers.get('HX-Request'):
            # Return HTML fragment for HTMX
            return render(request, 'form_composer/partials/section.html', {
                'section': section,
                'form_definition': form_definition,
            })
        else:
            return JsonResponse({
                'success': True,
                'section_id': section.id,
                'section_name': section.name,
            })
            
    except Exception as e:
        logger.error(f"Error adding section to {form_definition}: {e}")
        if request.headers.get('HX-Request'):
            return HttpResponse('<div class="alert alert-danger">Error adding section</div>')
        else:
            return JsonResponse({'success': False, 'error': str(e)})

@login_required
@user_passes_test(is_staff)
@require_POST
def add_field_to_section(request, section_id):
    """
    Add a field to a section
    """
    section = get_object_or_404(FormSection, id=section_id, is_active=True)
    
    try:
        # Get the next order number for this section
        max_order = FieldConfig.objects.filter(section=section).aggregate(
            max_order=models.Max('order')
        )['max_order'] or 0
        
        field_config = FieldConfig.objects.create(
            section=section,
            field_key=request.POST.get('field_key', f'field_{section.id}_{max_order + 1}'),
            label=request.POST.get('label', 'New Field'),
            field_type=request.POST.get('field_type', 'text'),
            order=max_order + 1,
            is_active=True,
            is_required=request.POST.get('is_required') == 'true',
            is_readonly=request.POST.get('is_readonly') == 'true',
            is_dynamic=request.POST.get('is_dynamic') == 'true',
            help_text=request.POST.get('help_text', ''),
            placeholder=request.POST.get('placeholder', ''),
            widget_type=request.POST.get('widget_type', 'default'),
        )
        
        return JsonResponse({
            'success': True,
            'field_id': field_config.id,
            'field_key': field_config.field_key,
            'field_label': field_config.label,
        })
        
    except Exception as e:
        logger.error(f"Error adding field to section {section_id}: {e}")
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@user_passes_test(is_staff)
@require_POST
def update_section_order(request):
    """
    Update section order after drag and drop
    """
    try:
        data = json.loads(request.body)
        sections_data = data.get('sections', [])
        
        with transaction.atomic():
            for section_data in sections_data:
                FormSection.objects.filter(id=section_data['id']).update(
                    order=section_data['order']
                )
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        logger.error(f"Error updating section order: {e}")
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@user_passes_test(is_staff)
@require_POST
def update_field_order(request, section_id):
    """
    Update field order within a section after drag and drop
    """
    section = get_object_or_404(FormSection, id=section_id, is_active=True)
    
    try:
        data = json.loads(request.body)
        fields_data = data.get('fields', [])
        
        with transaction.atomic():
            for field_data in fields_data:
                FieldConfig.objects.filter(
                    id=field_data['id'],
                    section=section
                ).update(order=field_data['order'])
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        logger.error(f"Error updating field order for section {section_id}: {e}")
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@user_passes_test(is_staff)
def section_properties(request, section_id):
    """
    Load section properties panel
    """
    section = get_object_or_404(FormSection, id=section_id, is_active=True)
    
    context = {
        'section': section,
        'form_definition': section.form_definition,
    }
    
    return render(request, 'form_composer/partials/section_properties.html', context)

@login_required
@user_passes_test(is_staff)
def field_properties(request, field_id):
    """
    Load field properties panel
    """
    field = get_object_or_404(FieldConfig, id=field_id, is_active=True)
    
    # Get widget type choices
    widget_choices = [
        ('default', 'Default'),
        ('text', 'Text Input'),
        ('textarea', 'Textarea'),
        ('number', 'Number Input'),
        ('email', 'Email Input'),
        ('url', 'URL Input'),
        ('password', 'Password Input'),
        ('checkbox', 'Checkbox'),
        ('radio', 'Radio Select'),
        ('select', 'Select'),
        ('multiselect', 'Multiple Select'),
        ('date', 'Date Input'),
        ('datetime', 'DateTime Input'),
        ('time', 'Time Input'),
        ('file', 'File Input'),
        ('image', 'Image Input'),
        ('hidden', 'Hidden Input'),
    ]
    
    context = {
        'field': field,
        'section': field.section,
        'form_definition': field.section.form_definition,
        'widget_choices': widget_choices,
    }
    
    return render(request, 'form_composer/partials/field_properties.html', context)

# Additional view stubs for completeness
@login_required
@user_passes_test(is_staff)
@require_POST
def update_section(request, section_id):
    """Update section properties"""
    section = get_object_or_404(FormSection, id=section_id, is_active=True)
    
    try:
        # Update section fields
        section.name = request.POST.get('name', section.name)
        section.description = request.POST.get('description', section.description)
        section.is_collapsed = request.POST.get('is_collapsed') == 'on'
        section.css_classes = request.POST.get('css_classes', section.css_classes)
        
        # Handle conditional logic as JSON
        conditional_logic = request.POST.get('conditional_logic', '{}')
        try:
            section.conditional_logic = json.loads(conditional_logic) if conditional_logic else {}
        except json.JSONDecodeError:
            pass  # Keep existing conditional logic if invalid JSON
        
        section.save()
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        logger.error(f"Error updating section {section_id}: {e}")
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@user_passes_test(is_staff)
@require_POST
def update_field(request, field_id):
    """Update field properties"""
    field = get_object_or_404(FieldConfig, id=field_id, is_active=True)
    
    try:
        # Update field properties
        field.field_key = request.POST.get('field_key', field.field_key)
        field.label = request.POST.get('label', field.label)
        field.help_text = request.POST.get('help_text', field.help_text)
        field.placeholder = request.POST.get('placeholder', field.placeholder)
        field.is_required = request.POST.get('is_required') == 'on'
        field.is_readonly = request.POST.get('is_readonly') == 'on'
        field.widget_type = request.POST.get('widget_type', field.widget_type)
        field.css_classes = request.POST.get('css_classes', field.css_classes)
        field.default_value = request.POST.get('default_value', field.default_value)
        
        # Handle widget attributes as JSON
        widget_attrs = request.POST.get('widget_attrs', '{}')
        try:
            field.widget_attrs = json.loads(widget_attrs) if widget_attrs else {}
        except json.JSONDecodeError:
            pass  # Keep existing widget attrs if invalid JSON
        
        # Handle validation rules as JSON
        validation_rules = request.POST.get('validation_rules', '{}')
        try:
            field.validation_rules = json.loads(validation_rules) if validation_rules else {}
        except json.JSONDecodeError:
            pass  # Keep existing validation rules if invalid JSON
        
        # Handle choices data as JSON
        choices_data = request.POST.get('choices_data', '[]')
        try:
            field.choices_data = json.loads(choices_data) if choices_data else []
        except json.JSONDecodeError:
            pass  # Keep existing choices if invalid JSON
        
        field.save()
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        logger.error(f"Error updating field {field_id}: {e}")
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@user_passes_test(is_staff)
@require_POST  
def toggle_section(request, section_id):
    """Toggle section collapsed state"""
    # Implementation would toggle collapse state
    return JsonResponse({'success': True})

@login_required
@user_passes_test(is_staff)
@require_http_methods(["DELETE"])
def delete_section(request, section_id):
    """Delete a section and all its fields"""
    section = get_object_or_404(FormSection, id=section_id, is_active=True)
    
    try:
        with transaction.atomic():
            # Mark section and all fields as inactive instead of deleting
            section.is_active = False
            section.save()
            
            FieldConfig.objects.filter(section=section).update(is_active=False)
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        logger.error(f"Error deleting section {section_id}: {e}")
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@user_passes_test(is_staff)
@require_http_methods(["DELETE"]) 
def delete_field(request, field_id):
    """Delete a field"""
    field = get_object_or_404(FieldConfig, id=field_id, is_active=True)
    
    try:
        field.is_active = False
        field.save()
        return JsonResponse({'success': True})
    except Exception as e:
        logger.error(f"Error deleting field {field_id}: {e}")
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@user_passes_test(is_staff)
@require_POST
def move_field_to_section(request, section_id):
    """Move a field to a different section"""
    target_section = get_object_or_404(FormSection, id=section_id, is_active=True)
    
    try:
        data = json.loads(request.body)
        field_id = data.get('field_id')
        new_order = data.get('order', 999)
        
        field = get_object_or_404(FieldConfig, id=field_id, is_active=True)
        
        with transaction.atomic():
            # Move field to new section
            field.section = target_section
            field.order = new_order
            field.save()
            
            # Reorder other fields in target section
            other_fields = FieldConfig.objects.filter(
                section=target_section,
                is_active=True
            ).exclude(id=field_id).order_by('order')
            
            order = 1
            for other_field in other_fields:
                if order == new_order:
                    order += 1
                other_field.order = order
                other_field.save()
                order += 1
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        logger.error(f"Error moving field to section {section_id}: {e}")
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@user_passes_test(is_staff)
def preview_form(request, form_definition_id=None):
    """Live preview of the form configuration"""
    if form_definition_id:
        form_definition = get_object_or_404(FormDefinition, id=form_definition_id, is_active=True)
    else:
        form_definition = FormDefinition.objects.filter(is_active=True).first()
        if not form_definition:
            return render(request, 'form_composer/preview_empty.html')
    
    # Get the complete configuration
    config = ConfigEnforcementV2.get_form_config(form_definition.get_model_class())
    
    # Create a demo form instance
    model_class = form_definition.get_model_class()
    if model_class:
        from django import forms
        
        class DemoForm(forms.ModelForm):
            class Meta:
                model = model_class
                fields = '__all__'
        
        demo_form = DemoForm()
        applied_config = ConfigEnforcementV2.apply_to_form(demo_form, model_class)
        
        context = {
            'form_definition': form_definition,
            'config': config,
            'demo_form': demo_form,
            'applied_config': applied_config,
            'sections': config['sections'] if config else [],
        }
    else:
        context = {
            'form_definition': form_definition,
            'error': 'Could not load model class',
        }
    
    return render(request, 'form_composer/preview.html', context)

@login_required
@user_passes_test(is_staff)
def api_preview_form(request, form_definition_id):
    """API endpoint for live preview updates"""
    form_definition = get_object_or_404(FormDefinition, id=form_definition_id, is_active=True)
    
    try:
        # Clear cache with proper signature - pass None to clear all or specific ID
        ConfigEnforcementV2.clear_cache(form_definition.id)
        config = ConfigEnforcementV2.get_form_config(form_definition.get_model_class())
        
        context = {
            'form_definition': form_definition,
            'config': config,
            'sections': config['sections'] if config else [],
        }
        
        return render(request, 'form_composer/partials/form_preview.html', context)
        
    except Exception as e:
        logger.error(f"Error generating preview for {form_definition_id}: {e}")
        return HttpResponse(f'<div class="alert alert-danger">Preview Error: {e}</div>')
