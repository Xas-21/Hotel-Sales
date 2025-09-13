"""
Configuration Dashboard Views

This module provides the Motion/Notion-style configuration dashboard
for managing all system sections and fields dynamically.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.contrib.admin.views.decorators import staff_member_required
from django.apps import apps
from django.core.exceptions import FieldDoesNotExist
import json

from .models import DynamicModel, DynamicField
from .services.existing_model_bridge import ExistingModelBridge
from .services.schema_manager import SchemaManager


def _get_or_create_extension_model(section_name):
    """Get or create an extension model for existing Django models"""
    model_extensions = {
        'requests.Request': ('RequestExtension', 'Request Extension Fields'),
        'agreements.Agreement': ('AgreementExtension', 'Agreement Extension Fields'),
        'sales_calls.SalesCall': ('SalesCallExtension', 'SalesCall Extension Fields'),
        'accounts.Company': ('CompanyExtension', 'Company Extension Fields'),
        'requests.RoomEntry': ('RoomEntryExtension', 'RoomEntry Extension Fields')
    }
    
    if section_name not in model_extensions:
        raise ValueError(f"Unknown section: {section_name}")
    
    extension_name, display_name = model_extensions[section_name]
    app_label = section_name.split('.')[0]
    
    # Get or create the extension model
    extension_model, created = DynamicModel.objects.get_or_create(
        name=extension_name,
        app_label=app_label,
        defaults={
            'display_name': display_name,
            'description': f'Dynamic fields for {section_name}',
            'is_active': True
        }
    )
    return extension_model


@staff_member_required
def configuration_dashboard(request):
    """Main configuration dashboard showing Core Sections and Custom Sections"""
    from requests.services.admin_model_detector import AdminModelDetector
    from requests.models import DynamicSection
    
    # Ensure core sections are created from existing admin models
    detector = AdminModelDetector()
    detector.sync_core_sections()
    
    # Get Core Sections (existing admin models)
    core_sections = []
    for section in DynamicSection.objects.filter(is_core_section=True).order_by('order', 'name'):
        core_fields = section.fields.filter(is_core_field=True)
        custom_fields = section.fields.filter(is_core_field=False)
        
        core_sections.append({
            'id': section.id,
            'name': section.name,
            'display_name': section.display_name,
            'description': section.description,
            'source_model': section.source_model,
            'core_field_count': core_fields.count(),
            'custom_field_count': custom_fields.count(),
            'total_fields': section.fields.count(),
            'is_core': True,
            'admin_url': f'/admin/{section.source_model.lower().replace(".", "/")}/' if section.source_model else None
        })
    
    # Get Custom Sections (user-created sections) 
    custom_sections = []
    for section in DynamicSection.objects.filter(is_core_section=False).order_by('order', 'name'):
        custom_sections.append({
            'id': section.id,
            'name': section.name,
            'display_name': section.display_name,
            'description': section.description,
            'field_count': section.fields.count(),
            'total_fields': section.fields.count(),
            'is_core': False,
            'admin_url': None  # Custom sections don't have admin URLs yet
        })
    
    # Legacy dynamic models support (for backward compatibility)
    dynamic_models = []
    for dm in DynamicModel.objects.filter(is_active=True):
        field_count = dm.fields.filter(is_active=True).count()
        dynamic_models.append({
            'id': dm.id,
            'name': f"{dm.app_label}.{dm.name}",
            'display_name': dm.display_name,
            'field_count': field_count,
            'is_core': False,
            'model': dm
        })
    
    context = {
        'core_sections': core_sections,
        'custom_sections': custom_sections,
        'dynamic_models': dynamic_models,  # Legacy support
        'total_core_sections': len(core_sections),
        'total_custom_sections': len(custom_sections),
        'total_sections': len(core_sections) + len(custom_sections) + len(dynamic_models)
    }
    
    return render(request, 'configuration/dashboard.html', context)


@staff_member_required
def section_fields(request, section_name):
    """Show and manage fields for a specific section"""
    is_dynamic = request.GET.get('dynamic') == 'true'
    
    if is_dynamic:
        # Handle dynamic model
        dynamic_model = get_object_or_404(DynamicModel, id=section_name)
        model_name = f"{dynamic_model.app_label}.{dynamic_model.name}"
        display_name = dynamic_model.display_name
        
        # Get dynamic fields
        fields = DynamicField.objects.filter(
            model=dynamic_model,
            is_active=True
        ).order_by('section', 'order')
        
        # Get model fields (always empty for dynamic models)
        model_fields = []
        
    else:
        # Handle existing Django model
        try:
            model = apps.get_model(section_name)
            model_name = section_name
            display_name = {
                'accounts.Company': 'Companies & Accounts',
                'requests.Request': 'Booking Requests', 
                'agreements.Agreement': 'Agreements & Contracts',
                'sales_calls.SalesCall': 'Sales Calls & Meetings',
                'requests.RoomEntry': 'Room Occupancies'
            }.get(section_name, section_name)
            
            # Get model fields
            model_fields = []
            for field in model._meta.fields:
                if field.name not in ['id', 'created_at', 'updated_at']:
                    model_fields.append({
                        'name': field.name,
                        'display_name': field.verbose_name or field.name.replace('_', ' ').title(),
                        'field_type': field.get_internal_type(),
                        'required': not field.null and not field.blank,
                        'is_model_field': True
                    })
            
            # Get dynamic fields through extension models
            from requests.services.existing_model_bridge import ExistingModelBridge
            fields = ExistingModelBridge.get_dynamic_fields_for_model(section_name)
            
        except Exception as e:
            messages.error(request, f"Error loading section: {e}")
            return redirect('configuration:dashboard')
    
    # Convert dynamic fields to dict format
    dynamic_fields = []
    for field in fields:
        dynamic_fields.append({
            'id': field.id,
            'name': field.name,
            'display_name': field.display_name,
            'field_type': field.field_type,
            'required': field.required,
            'section': field.section or 'Custom Fields',
            'order': field.order,
            'max_length': field.max_length,
            'choices': field.choices,
            'default_value': field.default_value,
            'is_model_field': False
        })
    
    # For dynamic models, use ID for URL building; for existing models, use the model name
    section_url_param = section_name if is_dynamic else model_name
    
    context = {
        'section_name': section_url_param,
        'display_name': display_name,
        'model_fields': model_fields,
        'dynamic_fields': dynamic_fields,
        'all_fields': model_fields + dynamic_fields,
        'is_dynamic': is_dynamic
    }
    
    return render(request, 'configuration/section_fields.html', context)


@staff_member_required
@require_POST
def add_field(request, section_name):
    """Add a new field to a section"""
    try:
        data = json.loads(request.body)
        is_dynamic = request.GET.get('dynamic') == 'true'
        
        # Create new dynamic field
        if is_dynamic:
            dynamic_model = get_object_or_404(DynamicModel, id=section_name)
            field = DynamicField.objects.create(
                model=dynamic_model,
                name=data['name'],
                display_name=data['display_name'],
                field_type=data['field_type'],
                required=data.get('required', False),
                section=data.get('section', 'Custom Fields'),
                max_length=data.get('max_length') or 255,
                choices=data.get('choices') or '{}',
                default_value=data.get('default_value') or '',
                order=data.get('order', 100)
            )
        else:
            # For existing models, get or create an extension model
            extension_model = _get_or_create_extension_model(section_name)
            field = DynamicField.objects.create(
                model=extension_model,
                name=data['name'],
                display_name=data['display_name'],
                field_type=data['field_type'],
                required=data.get('required', False),
                section=data.get('section', 'Custom Fields'),
                max_length=data.get('max_length') or 255,
                choices=data.get('choices') or '{}',
                default_value=data.get('default_value') or '',
                order=data.get('order', 100)
            )
        
        # Apply schema changes if needed
        if is_dynamic:
            schema_manager = SchemaManager()
            field_config = {
                'name': field.name,
                'field_type': field.field_type,
                'max_length': field.max_length,
                'required': field.required,
                'default_value': field.default_value
            }
            # Note: Schema changes for dynamic fields are handled by the model creation process
        
        return JsonResponse({
            'success': True,
            'field': {
                'id': field.id,
                'name': field.name,
                'display_name': field.display_name,
                'field_type': field.field_type,
                'required': field.required,
                'section': field.section
            }
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@staff_member_required
@require_POST
def update_field(request, field_id):
    """Update an existing field"""
    try:
        field = get_object_or_404(DynamicField, id=field_id)
        data = json.loads(request.body)
        
        # Update field properties
        field.display_name = data.get('display_name', field.display_name)
        field.required = data.get('required', field.required)
        field.section = data.get('section', field.section)
        field.order = data.get('order', field.order)
        field.max_length = data.get('max_length', field.max_length)
        field.choices = data.get('choices', field.choices)
        field.default_value = data.get('default_value', field.default_value)
        field.save()
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@staff_member_required
@require_POST
def delete_field(request, field_id):
    """Delete a field"""
    try:
        field = get_object_or_404(DynamicField, id=field_id)
        field.is_active = False
        field.save()
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@staff_member_required
@require_POST  
def create_section(request):
    """Create a new dynamic section/model"""
    try:
        data = json.loads(request.body)
        
        # Create new dynamic model with unique table name
        import uuid
        base_table_name = f"dynamic_{data['name']}"
        table_name = base_table_name
        counter = 1
        
        # Ensure unique table name
        while DynamicModel.objects.filter(table_name=table_name).exists():
            table_name = f"{base_table_name}_{counter}"
            counter += 1
        
        dynamic_model = DynamicModel.objects.create(
            name=data['name'],
            display_name=data['display_name'],
            app_label='dynamic',
            table_name=table_name,
            description=data.get('description', '')
        )
        
        # Create schema
        schema_manager = SchemaManager()
        model_config = {
            'table_name': f"dynamic_{dynamic_model.name}",
            'name': dynamic_model.name,
            'display_name': dynamic_model.display_name
        }
        schema_manager.create_dynamic_model_table(model_config)
        
        return JsonResponse({
            'success': True,
            'model': {
                'id': dynamic_model.id,
                'name': dynamic_model.name,
                'display_name': dynamic_model.display_name
            }
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@staff_member_required
@require_POST
def delete_section(request, section_id):
    """Delete a dynamic section"""
    try:
        dynamic_model = get_object_or_404(DynamicModel, id=section_id)
        dynamic_model.is_active = False
        dynamic_model.save()
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})