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
def section_fields(request, section_id):
    """Show and manage fields for a specific section (DynamicSection or legacy DynamicModel)"""
    from requests.models import DynamicSection
    
    is_legacy_dynamic = request.GET.get('dynamic') == 'true'
    
    if is_legacy_dynamic:
        # Handle legacy dynamic model for backward compatibility
        dynamic_model = get_object_or_404(DynamicModel, id=section_id)
        model_name = f"{dynamic_model.app_label}.{dynamic_model.name}"
        display_name = dynamic_model.display_name
        
        # Get legacy dynamic fields
        fields = DynamicField.objects.filter(
            model=dynamic_model,
            is_active=True
        ).order_by('section_name', 'order')
        
        section_type = 'legacy'
        model_fields = []  # Legacy models don't have core model fields
        
    else:
        # Handle DynamicSection (Core or Custom)
        section = get_object_or_404(DynamicSection, id=section_id)
        model_name = section.name
        display_name = section.display_name
        section_type = 'core' if section.is_core_section else 'custom'
        
        # Get all fields for this section
        fields = section.fields.filter(is_active=True).order_by('order')
        
        # For Core sections, separate core fields from custom fields
        if section.is_core_section:
            model_fields = []
            core_fields = fields.filter(is_core_field=True)
            
            for field in core_fields:
                # Parse choices for core fields 
                choices_obj = {}
                try:
                    if field.choices and field.choices != '{}':
                        # Handle both dict and JSON string formats
                        if isinstance(field.choices, dict):
                            choices_obj = field.choices
                        else:
                            choices_obj = json.loads(field.choices)
                except (json.JSONDecodeError, ValueError):
                    choices_obj = {}
                    
                model_fields.append({
                    'id': field.id,
                    'name': field.name,
                    'display_name': field.display_name,
                    'field_type': field.field_type,
                    'required': field.required,
                    'is_model_field': True,
                    'is_core_field': True,
                    'choices': choices_obj,  # Pass Python dict for json_script filter
                    'choices_script_id': f'choices-{field.id}'  # Pre-computed script ID
                })
        else:
            model_fields = []
    
    # Convert fields to dict format for template
    dynamic_fields = []
    for field in fields:
        # Skip core fields for core sections (already handled above)
        if section_type == 'core' and field.is_core_field:
            continue
            
        # Parse choices for dynamic fields
        choices_obj = {}
        try:
            if field.choices and field.choices != '{}':
                # Handle both dict and JSON string formats
                if isinstance(field.choices, dict):
                    choices_obj = field.choices
                else:
                    choices_obj = json.loads(field.choices)
        except (json.JSONDecodeError, ValueError):
            choices_obj = {}
            
        dynamic_fields.append({
            'id': field.id,
            'name': field.name,
            'display_name': field.display_name,
            'field_type': field.field_type,
            'required': field.required,
            'section_name': field.section_name if hasattr(field, 'section_name') else 'Custom Fields',
            'order': field.order,
            'max_length': field.max_length,
            'choices': choices_obj,  # Pass Python dict for json_script filter
            'choices_script_id': f'choices-{field.id}',  # Pre-computed script ID
            'default_value': field.default_value,
            'is_model_field': False,
            'is_core_field': getattr(field, 'is_core_field', False)
        })
    
    context = {
        'section_id': section_id,
        'section_name': model_name,
        'display_name': display_name,
        'section_type': section_type,
        'source_model': getattr(section, 'source_model', '') if not is_legacy_dynamic else '',
        'model_fields': model_fields,
        'dynamic_fields': dynamic_fields,
        'all_fields': model_fields + dynamic_fields,
        'is_legacy_dynamic': is_legacy_dynamic,
        'is_core_section': section_type == 'core',
        'is_custom_section': section_type == 'custom'
    }
    
    return render(request, 'configuration/section_fields.html', context)


def _normalize_choices_data(choices):
    """Helper function to normalize choice data to JSON string format"""
    if isinstance(choices, (dict, list)):
        return json.dumps(choices)
    elif isinstance(choices, str):
        # Validate and re-save existing JSON string
        try:
            parsed = json.loads(choices)
            return json.dumps(parsed)  # Normalize formatting
        except (json.JSONDecodeError, ValueError):
            return '{}'  # Fallback for invalid JSON
    else:
        return '{}'  # Empty JSON object as string


@staff_member_required
@require_POST
def add_field(request, section_id):
    """Add a new field to a section"""
    from requests.models import DynamicSection
    
    try:
        data = json.loads(request.body)
        is_legacy_dynamic = request.GET.get('dynamic') == 'true'
        
        # Create new dynamic field
        if is_legacy_dynamic:
            # Handle legacy dynamic model
            dynamic_model = get_object_or_404(DynamicModel, id=section_id)
            field = DynamicField.objects.create(
                model=dynamic_model,
                name=data['name'],
                display_name=data['display_name'],
                field_type=data['field_type'],
                required=data.get('required', False),
                section=data.get('section', 'Custom Fields'),
                max_length=data.get('max_length') or 255,
                choices=_normalize_choices_data(data.get('choices') or {}),
                default_value=data.get('default_value') or '',
                order=data.get('order', 100)
            )
        else:
            # Handle DynamicSection (Core or Custom)
            section = get_object_or_404(DynamicSection, id=section_id)
            
            # Determine if this is a core field and what mode
            core_mode = data.get('core_mode', 'custom')  # 'override', 'create', or 'custom'
            is_core_field = core_mode in ['override', 'create']
            
            # Validate core mode for core sections
            if section.is_core_section and core_mode in ['override', 'create']:
                # This is a core field - either override existing or create new
                if core_mode == 'override':
                    # Override mode requires model_field_name
                    model_field_name = data.get('model_field_name', '')
                    if not model_field_name:
                        return JsonResponse({
                            'success': False, 
                            'error': 'Override mode requires specifying the model field name to override.'
                        })
                    
                    # Verify the model field actually exists on the target model
                    if section.source_model:
                        app_label, model_name = section.source_model.split('.')
                        try:
                            from django.apps import apps
                            model_class = apps.get_model(app_label, model_name)
                            try:
                                model_class._meta.get_field(model_field_name)
                            except FieldDoesNotExist:
                                return JsonResponse({
                                    'success': False,
                                    'error': f'Model field "{model_field_name}" does not exist on {section.source_model}.'
                                })
                        except LookupError:
                            return JsonResponse({
                                'success': False,
                                'error': f'Model {section.source_model} not found.'
                            })
                    
                    # Check for duplicate overrides within this section
                    existing_override = DynamicField.objects.filter(
                        section=section,
                        is_core_field=True,
                        core_mode='override',
                        model_field_name=model_field_name,
                        is_active=True
                    ).first()
                    
                    if existing_override:
                        return JsonResponse({
                            'success': False,
                            'error': f'Model field "{model_field_name}" is already overridden by field "{existing_override.name}".'
                        })
                        
                elif core_mode == 'create':
                    # Create mode should not have model_field_name
                    if data.get('model_field_name'):
                        return JsonResponse({
                            'success': False, 
                            'error': 'Create mode should not specify a model field name.'
                        })
                    
                    # Check for name collision with existing model fields
                    from django.apps import apps
                    if section.source_model:
                        app_label, model_name = section.source_model.split('.')
                        try:
                            model_class = apps.get_model(app_label, model_name)
                            existing_field_names = [f.name for f in model_class._meta.get_fields()]
                            if data['name'] in existing_field_names:
                                return JsonResponse({
                                    'success': False,
                                    'error': f'Field name "{data["name"]}" conflicts with existing model field. Choose a different name.'
                                })
                        except LookupError:
                            pass  # Model not found, proceed
                    
                    # Check for collisions with existing DynamicField names in this section
                    existing_field = DynamicField.objects.filter(
                        section=section,
                        name=data['name'],
                        is_active=True
                    ).first()
                    
                    if existing_field:
                        return JsonResponse({
                            'success': False,
                            'error': f'Field name "{data["name"]}" already exists in this section.'
                        })
            else:
                # Regular custom field
                is_core_field = False
                core_mode = 'custom'
            
            # Determine storage type based on core_mode
            if is_core_field and core_mode == 'override':
                storage_type = 'model_field'
            else:
                storage_type = 'value_store'
            
            field = DynamicField.objects.create(
                section=section,  # Link to DynamicSection instead of DynamicModel
                name=data['name'],
                display_name=data['display_name'],
                field_type=data['field_type'],
                required=data.get('required', False),
                section_name=data.get('section_name', 'Core Fields' if is_core_field else 'Custom Fields'),
                max_length=data.get('max_length') or 255,
                choices=_normalize_choices_data(data.get('choices') or {}),
                default_value=data.get('default_value') or '',
                order=data.get('order', 100),
                is_core_field=is_core_field,
                # Fixed core field creation logic
                core_mode=core_mode if is_core_field else 'custom',  # Fixed: 'custom' for non-core fields
                model_field_name=data.get('model_field_name', '') if core_mode == 'override' else '',
                storage=storage_type  # Fixed: core overrides use 'model_field', others use 'value_store'
            )
        
        # Apply schema changes if needed (for legacy dynamic models only)
        if is_legacy_dynamic:
            # Note: Schema changes for legacy dynamic fields are handled by the model creation process
            pass
        
        return JsonResponse({
            'success': True,
            'field': {
                'id': field.id,
                'name': field.name,
                'display_name': field.display_name,
                'field_type': field.field_type,
                'required': field.required,
                'section_name': getattr(field, 'section_name', 'Custom Fields'),
                'is_core_field': getattr(field, 'is_core_field', False),
                'core_mode': getattr(field, 'core_mode', 'override'),
                'model_field_name': getattr(field, 'model_field_name', ''),
                'storage': getattr(field, 'storage', 'value_store')
            }
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@staff_member_required
@require_POST
def update_field(request, field_id):
    """Update an existing field (both core and custom fields)"""
    try:
        field = get_object_or_404(DynamicField, id=field_id)
        data = json.loads(request.body)
        
        # Update field properties
        field.display_name = data.get('display_name', field.display_name)
        field.field_type = data.get('field_type', field.field_type)
        field.required = data.get('required', field.required)
        
        # Handle choices properly for choice fields
        if 'choices' in data:
            # Normalize field type for comparison (handle case variations)
            normalized_type = field.field_type.lower()
            if normalized_type in ['choicefield', 'choice', 'multiple_choice']:
                # Use helper function for consistent normalization
                field.choices = _normalize_choices_data(data.get('choices', {}))
            else:
                # Clear choices for non-choice fields
                field.choices = '{}'  # Empty JSON object as string
        
        # For custom fields, update additional properties
        if not field.is_core_field:
            field.section = data.get('section', field.section)
            field.order = data.get('order', field.order)
            field.max_length = data.get('max_length', field.max_length)
            field.default_value = data.get('default_value', field.default_value)
        
        field.save()
        
        # Log the update for debugging
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Updated field {field.name} (id={field_id}, is_core={field.is_core_field}): choices={field.choices}")
        
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
    """Delete a dynamic section (handles both DynamicSection and legacy DynamicModel)"""
    from requests.models import DynamicSection
    
    try:
        is_legacy_dynamic = request.GET.get('dynamic') == 'true'
        
        if is_legacy_dynamic:
            # Handle legacy dynamic model deletion
            dynamic_model = get_object_or_404(DynamicModel, id=section_id)
            dynamic_model.is_active = False
            dynamic_model.save()
        else:
            # Handle DynamicSection deletion
            section = get_object_or_404(DynamicSection, id=section_id)
            
            # Core sections cannot be deleted (they represent existing admin models)
            if section.is_core_section:
                return JsonResponse({
                    'success': False, 
                    'error': 'Core sections cannot be deleted as they represent existing admin models.'
                })
            
            # Actually delete custom sections (DynamicSection doesn't have is_active field)
            section.delete()
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})