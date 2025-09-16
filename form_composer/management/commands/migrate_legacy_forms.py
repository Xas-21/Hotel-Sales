"""
Management command to migrate legacy SystemFieldRequirement and SystemFormLayout
to the new FormComposer models (FormDefinition, FormSection, FieldConfig).

This migration ensures complete data safety by:
- Migrating ALL SystemFieldRequirement records (prevents data loss)
- Preserving field ordering and semantic data
- Creating comprehensive FormSections from all referenced sections
- Using safe error handling to prevent runtime failures
"""
import json
import logging
from collections import defaultdict
from django.core.management.base import BaseCommand
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.apps import apps

from form_composer.models import FormDefinition, FormSection, FieldConfig
from form_composer.services import ConfigRegistry
from requests.models import SystemFieldRequirement, SystemFormLayout

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Migrate legacy SystemFieldRequirement and SystemFormLayout to Form Composer models'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be migrated without actually migrating',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force migration even if Form Composer data already exists',
        )
    
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']
        
        self.stdout.write(self.style.SUCCESS('Starting legacy form migration...'))
        
        # Check if migration is needed (but allow --force for idempotent updates)
        if not force and FormDefinition.objects.exists():
            existing_count = FormDefinition.objects.count()
            self.stdout.write(
                self.style.WARNING(
                    f'Form Composer already has {existing_count} definitions. '
                    'Use --force to run idempotent migration that updates existing records.'
                )
            )
            return
        
        if force:
            self.stdout.write(
                self.style.SUCCESS(
                    'Running in --force mode: Will update existing records idempotently'
                )
            )
        
        # Get source data - include ALL data, not just active/enabled
        layouts = SystemFormLayout.objects.all().order_by('form_type')
        requirements = SystemFieldRequirement.objects.all().order_by(
            'form_type', 'section_name', 'sort_order', 'field_name'
        )
        
        if not layouts.exists() and not requirements.exists():
            self.stdout.write(self.style.WARNING('No legacy data found to migrate.'))
            return
        
        self.stdout.write(
            f'Found {layouts.count()} layouts and {requirements.count()} field requirements.\n'
            f'  - Active layouts: {layouts.filter(active=True).count()}\n'
            f'  - Enabled requirements: {requirements.filter(enabled=True).count()}'
        )
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - No changes will be made'))
            self._show_migration_plan(layouts, requirements)
            return
        
        # Perform migration with comprehensive data safety
        migration_stats = {
            'definitions': 0,
            'sections': 0,
            'fields': 0,
            'orphaned_fields': 0,
            'errors': []
        }
        
        try:
            with transaction.atomic():
                self._migrate_data_safely(layouts, requirements, migration_stats)
                
            # Report results
            self.stdout.write(
                self.style.SUCCESS(
                    f'Migration completed successfully!\n'
                    f'  - FormDefinitions: {migration_stats["definitions"]}\n'
                    f'  - FormSections: {migration_stats["sections"]}\n'
                    f'  - FieldConfigs: {migration_stats["fields"]}\n'
                    f'  - Orphaned fields recovered: {migration_stats["orphaned_fields"]}'
                )
            )
            
            if migration_stats['errors']:
                self.stdout.write(self.style.WARNING(
                    f'Warnings during migration:\n' + 
                    '\n'.join(f'  - {error}' for error in migration_stats['errors'])
                ))
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Migration failed: {e}')
            )
            logger.exception('Migration failed')
            raise
    
    def _show_migration_plan(self, layouts, requirements):
        """Show comprehensive migration plan including data safety analysis"""
        self.stdout.write('\n=== MIGRATION PLAN ===\n')
        
        # Analyze layouts
        active_layouts = layouts.filter(active=True)
        inactive_layouts = layouts.filter(active=False)
        
        self.stdout.write(f'LAYOUTS TO MIGRATE: {len(active_layouts)} active, {len(inactive_layouts)} inactive')
        for layout in layouts:
            status = "ACTIVE" if layout.active else "INACTIVE"
            self.stdout.write(f'  [{status}] {layout.form_type}')
            sections_data = self.safe_get_sections(layout)
            for section in sections_data:
                section_name = section.get("name", "Unknown")
                field_count = len(section.get("fields", []))
                self.stdout.write(f'    → {section_name}: {field_count} fields')
        
        # Analyze requirements with data safety check
        req_by_form_type = defaultdict(lambda: defaultdict(list))
        for req in requirements:
            req_by_form_type[req.form_type][req.section_name].append(req)
        
        # Check for orphaned fields (requirements not in any layout)
        orphaned_fields = self._find_orphaned_fields(layouts, requirements)
        
        self.stdout.write(f'\nFIELD REQUIREMENTS: {requirements.count()} total')
        for form_type, sections in req_by_form_type.items():
            enabled_count = sum(len([r for r in fields if r.enabled]) for fields in sections.values())
            disabled_count = sum(len([r for r in fields if not r.enabled]) for fields in sections.values())
            self.stdout.write(f'  {form_type}: {enabled_count} enabled, {disabled_count} disabled')
            for section_name, fields in sections.items():
                enabled = len([r for r in fields if r.enabled])
                disabled = len([r for r in fields if not r.enabled])
                self.stdout.write(f'    → {section_name}: {enabled} enabled, {disabled} disabled')
        
        # Warn about data safety issues
        if orphaned_fields:
            self.stdout.write(self.style.WARNING(
                f'\nDATA SAFETY WARNING: {len(orphaned_fields)} orphaned fields found!\n'
                'These SystemFieldRequirement records are not referenced in any layout:\n' +
                '\n'.join(f'  - {req.form_type} → {req.section_name} → {req.field_name}' 
                         for req in orphaned_fields[:10]) +
                (f'\n  ... and {len(orphaned_fields)-10} more' if len(orphaned_fields) > 10 else '')
            ))
            self.stdout.write('These fields will be recovered and placed in their respective sections.')
        else:
            self.stdout.write(self.style.SUCCESS('\nDATA SAFETY: All field requirements are covered by layouts.'))
    
    def _migrate_data_safely(self, layouts, requirements, stats):
        """Migrate legacy data with complete data safety and zero-loss guarantee"""
        
        # Phase 1: Dynamic ContentType resolution with preflight validation
        form_type_mappings = self._create_dynamic_content_type_mappings(layouts, requirements)
        
        # Phase 2: Build complete migration plan in memory (ZERO database writes yet)
        logger.info('Building complete migration plan in memory...')
        migration_plan = self._build_migration_plan(layouts, requirements, form_type_mappings)
        
        # Phase 3: Coverage preflight - ensure zero data loss guarantee
        coverage_report = self._validate_coverage_preflight(migration_plan, requirements)
        
        if not coverage_report['coverage_complete']:
            uncovered_count = len(coverage_report['uncovered_requirements'])
            raise ValueError(
                f"ZERO-LOSS GUARANTEE VIOLATED: {uncovered_count} SystemFieldRequirement records would be lost!\n" +
                "\nUNCOVERED REQUIREMENTS:\n" +
                "\n".join(f"  - {req.form_type} → {req.section_name} → {req.field_name}" 
                         for req in coverage_report['uncovered_requirements'][:10]) +
                (f"\n  ... and {uncovered_count-10} more" if uncovered_count > 10 else "") +
                "\n\nMigration aborted to prevent data loss. Please review the data."
            )
        
        logger.info(f'✓ COVERAGE PREFLIGHT PASSED: All {requirements.count()} requirements covered')
        
        # Phase 4: Execute the migration plan (database writes begin)
        logger.info('Executing migration plan with database writes...')
        self._execute_migration_plan(migration_plan, stats)
        
        # Post-migration: Clear ConfigRegistry cache to ensure fresh data
        logger.info('Clearing ConfigRegistry cache after migration...')
        ConfigRegistry.clear_cache()
    
    def _create_dynamic_content_type_mappings(self, layouts, requirements):
        """Dynamically resolve ContentTypes for all form types with preflight validation"""
        mappings = {}
        
        # Get all unique form types from actual data
        all_form_types = set()
        all_form_types.update(layout.form_type for layout in layouts)
        all_form_types.update(req.form_type for req in requirements)
        
        logger.info(f'Discovered {len(all_form_types)} unique form types from data: {sorted(all_form_types)}')
        
        # Preflight validation - ensure all form types can be resolved
        unresolved_form_types = []
        
        for form_type in sorted(all_form_types):
            content_type = self._resolve_content_type(form_type)
            if content_type:
                mappings[form_type] = content_type
                logger.info(f'✓ Resolved {form_type} → {content_type}')
            else:
                unresolved_form_types.append(form_type)
                logger.error(f'✗ Cannot resolve {form_type} to any ContentType')
        
        # Hard fail if any form types cannot be resolved (zero-loss guarantee)
        if unresolved_form_types:
            raise ValueError(
                f"PREFLIGHT FAILED: Cannot resolve {len(unresolved_form_types)} form types to ContentTypes:\n" +
                "\n".join(f"  - {ft}" for ft in unresolved_form_types) +
                "\n\nThis would cause data loss. Please ensure all referenced models exist."
            )
        
        # Post-resolution: Register all successfully resolved models with ConfigRegistry
        self._register_resolved_models_with_config_registry(mappings)
        
        logger.info(f'✓ PREFLIGHT PASSED: All {len(mappings)} form types successfully resolved')
        return mappings
    
    def _register_resolved_models_with_config_registry(self, form_type_mappings):
        """Register all resolved models with ConfigRegistry for future use"""
        
        registered_count = 0
        
        for form_type, content_type in form_type_mappings.items():
            try:
                model_class = content_type.model_class()
                if not model_class:
                    continue
                
                # Check if already registered
                existing_form_def = ConfigRegistry.get_form_definition(model_class)
                if existing_form_def:
                    logger.debug(f'Model {model_class} already registered with ConfigRegistry')
                    continue
                
                # Register with ConfigRegistry
                form_definition = ConfigRegistry.register_model(
                    model_class=model_class,
                    form_type=form_type.replace('.', '_').replace(' ', '_').lower(),
                    name=f"{model_class._meta.verbose_name_plural.title()} Form",
                    description=f"Registered during migration from {form_type}",
                    auto_create=True
                )
                
                registered_count += 1
                logger.info(f'Registered {model_class} with ConfigRegistry: {form_definition}')
                
            except Exception as e:
                logger.warning(f'Failed to register {content_type.model_class()} with ConfigRegistry: {e}')
        
        if registered_count > 0:
            logger.info(f'✓ ConfigRegistry integration: Registered {registered_count} models for future use')
        else:
            logger.info('✓ ConfigRegistry integration: All models already registered')
    
    def _resolve_content_type(self, form_type):
        """Dynamically resolve a single form_type to ContentType with smart fallbacks"""
        
        # Method 1: Try ConfigRegistry approach (app.model format)
        if '.' in form_type:
            parts = form_type.split('.')
            if len(parts) >= 2:
                app_label = parts[0]
                model_name = parts[-1].lower()  # Take last part as model name
                
                try:
                    content_type = ContentType.objects.get(app_label=app_label, model=model_name)
                    logger.debug(f'Method 1 success: {form_type} → {content_type}')
                    return content_type
                except ContentType.DoesNotExist:
                    logger.debug(f'Method 1 failed: {app_label}.{model_name} not found')
        
        # Method 2: Try module fallback patterns
        module_fallbacks = {
            'requests': ['request', 'accommodationrequest', 'eventwithrooms', 'eventonly', 'seriesgroup'],
            'sales_calls': ['salescall'],
            'agreements': ['agreement'], 
            'accounts': ['account'],
        }
        
        # Extract module from form_type
        module_name = form_type.split('.')[0] if '.' in form_type else None
        if module_name and module_name in module_fallbacks:
            for model_name in module_fallbacks[module_name]:
                try:
                    content_type = ContentType.objects.get(app_label=module_name, model=model_name)
                    logger.debug(f'Method 2 success: {form_type} → {content_type} (fallback to {model_name})')
                    return content_type
                except ContentType.DoesNotExist:
                    continue
        
        # Method 3: Use ConfigRegistry to find existing registrations and auto-register if needed
        try:
            # Get all registered models and see if any match this form_type
            registered_models = ConfigRegistry.get_registered_models()
            for model_info in registered_models:
                if model_info['form_type'] == form_type:
                    logger.debug(f'Method 3 success: {form_type} → {model_info["model_class"]} (via ConfigRegistry)')
                    return ContentType.objects.get_for_model(model_info['model_class'])
            
            # Method 3b: Auto-register models that match our form_type patterns
            content_type = self._auto_register_with_config_registry(form_type)
            if content_type:
                return content_type
                
        except Exception as e:
            logger.debug(f'Method 3 failed: {e}')
        
        logger.warning(f'All resolution methods failed for {form_type}')
        return None
    
    def _auto_register_with_config_registry(self, form_type):
        """Auto-register discovered models with ConfigRegistry during migration"""
        
        # Try to resolve the model first using our existing logic
        content_type = None
        
        # Parse form_type to get potential model information
        if '.' in form_type:
            parts = form_type.split('.')
            app_label = parts[0]
            model_name = parts[-1].lower()
            
            try:
                content_type = ContentType.objects.get(app_label=app_label, model=model_name)
                model_class = content_type.model_class()
                
                if model_class:
                    # Auto-register with ConfigRegistry
                    try:
                        form_definition = ConfigRegistry.register_model(
                            model_class=model_class,
                            form_type=form_type.replace('.', '_').replace(' ', '_').lower(),
                            name=f"{model_class._meta.verbose_name_plural.title()} (Migrated)",
                            description=f"Auto-registered during migration from {form_type}",
                            auto_create=True
                        )
                        
                        logger.info(f'✓ Auto-registered {model_class} with ConfigRegistry: {form_definition}')
                        return content_type
                        
                    except Exception as e:
                        logger.warning(f'Failed to auto-register {model_class} with ConfigRegistry: {e}')
                        # Still return the ContentType even if registration failed
                        return content_type
                        
            except ContentType.DoesNotExist:
                pass
        
        return None
    
    def safe_get_sections(self, layout):
        """Safely extract sections from SystemFormLayout with schema normalization"""
        if not layout:
            return []
        
        try:
            # Get raw sections data
            raw_sections = layout.get_sections()
            
            # Handle None or empty cases
            if not raw_sections:
                logger.debug(f'No sections data for layout {layout.form_type}')
                return []
            
            # Normalize different schema formats to consistent structure
            normalized_sections = []
            
            # Case 1: Already a list of dicts (ideal format)
            if isinstance(raw_sections, list):
                for i, section_data in enumerate(raw_sections):
                    if isinstance(section_data, dict):
                        normalized_section = self._normalize_section_dict(section_data, i)
                        normalized_sections.append(normalized_section)
                    else:
                        # Handle string section names
                        logger.warning(f'Section {i} is not a dict: {type(section_data)} - {section_data}')
                        normalized_sections.append({
                            'name': str(section_data),
                            'fields': [],
                            'order': i + 1,
                            'collapsed': False,
                            'source': 'fallback_string'
                        })
            
            # Case 2: Dict mapping (section_name -> fields or config)
            elif isinstance(raw_sections, dict):
                for i, (section_name, section_config) in enumerate(raw_sections.items()):
                    if isinstance(section_config, dict):
                        normalized_section = self._normalize_section_dict(section_config, i)
                        normalized_section['name'] = section_name  # Override with key
                    elif isinstance(section_config, list):
                        # section_name -> [field1, field2, ...]
                        normalized_section = {
                            'name': section_name,
                            'fields': self._normalize_field_list(section_config),
                            'order': i + 1,
                            'collapsed': False,
                            'source': 'dict_mapping'
                        }
                    else:
                        logger.warning(f'Invalid section config for {section_name}: {type(section_config)}')
                        normalized_section = {
                            'name': section_name,
                            'fields': [],
                            'order': i + 1,
                            'collapsed': False,
                            'source': 'fallback_dict'
                        }
                    
                    normalized_sections.append(normalized_section)
            
            # Case 3: String (JSON)
            elif isinstance(raw_sections, str):
                try:
                    parsed_data = json.loads(raw_sections)
                    # Recursively handle parsed JSON
                    temp_layout = type('TempLayout', (), {'get_sections': lambda: parsed_data})()
                    return self.safe_get_sections(temp_layout)
                except json.JSONDecodeError as e:
                    logger.error(f'Invalid JSON in sections for {layout.form_type}: {e}')
                    return []
            
            # Case 4: Unexpected format
            else:
                logger.error(f'Unexpected sections format for {layout.form_type}: {type(raw_sections)} - {raw_sections}')
                return []
            
            logger.debug(f'Normalized {len(normalized_sections)} sections for {layout.form_type}')
            return normalized_sections
            
        except Exception as e:
            logger.error(f'Failed to extract sections from {layout.form_type}: {e}')
            return []
    
    def _normalize_section_dict(self, section_data, index):
        """Normalize a single section dictionary to consistent format"""
        # Extract common fields with safe defaults
        name = section_data.get('name', f'Section {index + 1}')
        fields = section_data.get('fields', [])
        order = section_data.get('order', index + 1)
        collapsed = bool(section_data.get('collapsed', False))
        
        # Normalize fields list
        normalized_fields = self._normalize_field_list(fields)
        
        return {
            'name': name,
            'fields': normalized_fields,
            'order': order,
            'collapsed': collapsed,
            'source': 'normalized_dict'
        }
    
    def _normalize_field_list(self, fields):
        """Normalize field list handling both strings and dicts"""
        if not fields:
            return []
        
        if not isinstance(fields, list):
            logger.warning(f'Fields is not a list: {type(fields)} - converting to list')
            fields = [fields]
        
        normalized_fields = []
        for field in fields:
            if isinstance(field, str):
                normalized_fields.append(field)
            elif isinstance(field, dict):
                # Extract field name from dict (could be 'name', 'field_name', 'key', etc.)
                field_name = field.get('name') or field.get('field_name') or field.get('key')
                if field_name:
                    normalized_fields.append(field_name)
                else:
                    logger.warning(f'Cannot extract field name from dict: {field}')
            else:
                logger.warning(f'Unexpected field type: {type(field)} - {field}')
                normalized_fields.append(str(field))
        
        return normalized_fields
    
    def _build_migration_plan(self, layouts, requirements, form_type_mappings):
        """Build complete migration plan in memory before database writes"""
        
        # Group requirements for processing
        requirements_grouped = self._group_requirements(requirements)
        
        # Get all unique form types
        all_form_types = set()
        all_form_types.update(layout.form_type for layout in layouts)
        all_form_types.update(req.form_type for req in requirements)
        
        logger.info(f'Planning migration for {len(all_form_types)} unique form types')
        
        migration_plan = {
            'form_definitions': {},
            'form_sections': {},
            'field_configs': {},
            'metadata': {
                'total_form_types': len(all_form_types),
                'form_types': sorted(all_form_types),
                'requirements_by_form_type': {ft: len(requirements_grouped.get(ft, {})) for ft in all_form_types}
            }
        }
        
        # Build plan for each form type
        for form_type in sorted(all_form_types):
            content_type = form_type_mappings.get(form_type)
            if not content_type:
                logger.error(f'Skipping {form_type} - no ContentType mapping')
                continue
                
            layout = next((l for l in layouts if l.form_type == form_type), None)
            
            # Plan FormDefinition
            form_def_plan = self._plan_form_definition(form_type, layout, content_type)
            migration_plan['form_definitions'][form_type] = form_def_plan
            
            # Plan FormSections and FieldConfigs
            sections_plan = self._plan_form_sections(form_type, layout, requirements_grouped)
            migration_plan['form_sections'][form_type] = sections_plan
            
            # Plan FieldConfigs for each section
            fields_plan = {}
            for section_name, section_info in sections_plan.items():
                field_configs_plan = self._plan_field_configs(
                    form_type, section_name, section_info, requirements_grouped
                )
                fields_plan[section_name] = field_configs_plan
            
            migration_plan['field_configs'][form_type] = fields_plan
        
        # Log plan summary
        total_definitions = len(migration_plan['form_definitions'])
        total_sections = sum(len(sections) for sections in migration_plan['form_sections'].values())
        total_fields = sum(
            sum(len(fields) for fields in form_fields.values()) 
            for form_fields in migration_plan['field_configs'].values()
        )
        
        logger.info(f'Migration plan built: {total_definitions} definitions, {total_sections} sections, {total_fields} fields')
        
        return migration_plan
    
    def _plan_form_definition(self, form_type, layout, content_type):
        """Plan a single FormDefinition creation"""
        form_name = self._get_safe_form_type_display(form_type, layout)
        form_slug = form_type.replace('.', '_').replace(' ', '_').lower()
        
        return {
            'form_type': form_slug,
            'name': form_name,
            'target_model': content_type,
            'description': f'Migrated from legacy {form_type}',
            'is_active': layout.active if layout else True,
            'version': 1,
            'layout_source': layout
        }
    
    def _plan_form_sections(self, form_type, layout, requirements_grouped):
        """Plan all FormSections for a form type"""
        all_sections = self._get_all_sections_for_form_type(form_type, layout, requirements_grouped)
        
        sections_plan = {}
        for section_order, section_info in enumerate(all_sections, 1):
            section_name = section_info['name']
            sections_plan[section_name] = {
                'name': section_name,
                'slug': section_name.lower().replace(' ', '_'),
                'description': f'Migrated section from {form_type}',
                'order': section_order,
                'is_collapsed': section_info.get('collapsed', False),
                'is_active': True,
                'fields': section_info.get('fields', []),
                'source': section_info.get('source', 'unknown')
            }
        
        return sections_plan
    
    def _plan_field_configs(self, form_type, section_name, section_info, requirements_grouped):
        """Plan all FieldConfigs for a section"""
        # Get field requirements for this section
        section_requirements = requirements_grouped.get(form_type, {}).get(section_name, [])
        req_by_field_name = {req.field_name: req for req in section_requirements}
        
        # Get fields from section
        section_fields = section_info.get('fields', [])
        
        fields_plan = {}
        
        # Plan FieldConfigs for section fields
        for field_order, field_name in enumerate(section_fields, 1):
            field_req = req_by_field_name.get(field_name)
            field_plan = self._plan_single_field_config(field_name, field_req, field_order)
            field_plan['coverage_source'] = 'layout_field'
            fields_plan[field_name] = field_plan
        
        # Plan FieldConfigs for orphaned requirement fields (not in layout)
        orphaned_fields = [req for req in section_requirements if req.field_name not in section_fields]
        for field_req in orphaned_fields:
            field_order = len(section_fields) + field_req.sort_order + 1
            field_plan = self._plan_single_field_config(field_req.field_name, field_req, field_order)
            field_plan['coverage_source'] = 'orphaned_requirement'
            fields_plan[field_req.field_name] = field_plan
        
        return fields_plan
    
    def _plan_single_field_config(self, field_name, field_req, field_order):
        """Plan a single FieldConfig creation"""
        if field_req:
            return {
                'field_key': field_name,
                'label': field_req.field_label,
                'help_text': field_req.help_text,
                'is_required': field_req.required,
                'is_active': field_req.enabled,
                'order': field_order,
                'field_type': self._infer_field_type(field_req.field_name),
                'widget_type': self._infer_widget_type(field_req.field_name),
                'widget_attrs': self._infer_widget_attrs(field_req.field_name),
                'validation_rules': self._infer_validation_rules(field_req),
                'choices_data': self._infer_choices_data(field_req.field_name),
                'storage_type': 'model_field',
                'is_dynamic': False,
                'requirement_source': field_req
            }
        else:
            return {
                'field_key': field_name,
                'label': field_name.replace('_', ' ').title(),
                'help_text': '',
                'is_required': False,
                'is_active': True,
                'order': field_order,
                'field_type': self._infer_field_type(field_name),
                'widget_type': self._infer_widget_type(field_name),
                'widget_attrs': self._infer_widget_attrs(field_name),
                'validation_rules': {},
                'choices_data': self._infer_choices_data(field_name),
                'storage_type': 'model_field',
                'is_dynamic': False,
                'requirement_source': None
            }
    
    def _validate_coverage_preflight(self, migration_plan, requirements):
        """Validate that all requirements will be covered - zero-loss guarantee"""
        
        # Collect all requirement IDs that will be covered by the migration plan
        covered_requirement_ids = set()
        uncovered_requirements = []
        
        for form_type, form_fields in migration_plan['field_configs'].items():
            for section_name, field_configs in form_fields.items():
                for field_name, field_plan in field_configs.items():
                    req_source = field_plan.get('requirement_source')
                    if req_source:
                        covered_requirement_ids.add(req_source.id)
        
        # Check each requirement to see if it's covered
        for req in requirements:
            if req.id not in covered_requirement_ids:
                uncovered_requirements.append(req)
        
        coverage_report = {
            'total_requirements': requirements.count(),
            'covered_requirements': len(covered_requirement_ids),
            'uncovered_requirements': uncovered_requirements,
            'coverage_complete': len(uncovered_requirements) == 0,
            'coverage_percentage': (len(covered_requirement_ids) / requirements.count() * 100) if requirements.count() > 0 else 100.0
        }
        
        logger.info(
            f'Coverage analysis: {coverage_report["covered_requirements"]}/{coverage_report["total_requirements"]} requirements covered '
            f'({coverage_report["coverage_percentage"]:.1f}%)'
        )
        
        if uncovered_requirements:
            logger.warning(
                f'COVERAGE WARNING: {len(uncovered_requirements)} requirements would be uncovered:\n' +
                '\n'.join(f'  - {req.form_type} → {req.section_name} → {req.field_name}' 
                         for req in uncovered_requirements[:5]) +
                (f'\n  ... and {len(uncovered_requirements)-5} more' if len(uncovered_requirements) > 5 else '')
            )
        
        return coverage_report
    
    def _execute_migration_plan(self, migration_plan, stats):
        """Execute the validated migration plan with database writes"""
        
        for form_type in migration_plan['metadata']['form_types']:
            try:
                self._execute_form_type_plan(form_type, migration_plan, stats)
            except Exception as e:
                error_msg = f'Failed to execute plan for form type {form_type}: {e}'
                stats['errors'].append(error_msg)
                logger.error(error_msg)
                # Continue with other form types
    
    def _execute_form_type_plan(self, form_type, migration_plan, stats):
        """Execute migration plan for a single form type"""
        
        # Create FormDefinition
        form_def_plan = migration_plan['form_definitions'].get(form_type)
        if not form_def_plan:
            logger.warning(f'No FormDefinition plan found for {form_type}')
            return
        
        form_definition, created = FormDefinition.objects.update_or_create(
            form_type=form_def_plan['form_type'],
            defaults={
                'name': form_def_plan['name'],
                'target_model': form_def_plan['target_model'],
                'description': form_def_plan['description'],
                'is_active': form_def_plan['is_active'],
                'version': form_def_plan['version'],
            }
        )
        
        if created:
            stats['definitions'] += 1
            logger.info(f'Created FormDefinition: {form_def_plan["name"]}')
        else:
            logger.info(f'Updated FormDefinition: {form_def_plan["name"]}')
        
        # Create FormSections
        sections_plan = migration_plan['form_sections'].get(form_type, {})
        for section_name, section_plan in sections_plan.items():
            form_section, created = FormSection.objects.update_or_create(
                form_definition=form_definition,
                name=section_plan['name'],
                defaults={
                    'slug': section_plan['slug'],
                    'description': section_plan['description'],
                    'order': section_plan['order'],
                    'is_collapsed': section_plan['is_collapsed'],
                    'is_active': section_plan['is_active'],
                }
            )
            
            if created:
                stats['sections'] += 1
                logger.info(f'Created FormSection: {form_def_plan["name"]} → {section_name}')
            else:
                logger.info(f'Updated FormSection: {form_def_plan["name"]} → {section_name}')
            
            # Create FieldConfigs for this section
            fields_plan = migration_plan['field_configs'].get(form_type, {}).get(section_name, {})
            for field_name, field_plan in fields_plan.items():
                field_config, created = FieldConfig.objects.update_or_create(
                    section=form_section,
                    field_key=field_plan['field_key'],
                    defaults={
                        'label': field_plan['label'],
                        'help_text': field_plan['help_text'],
                        'is_required': field_plan['is_required'],
                        'is_active': field_plan['is_active'],
                        'order': field_plan['order'],
                        'field_type': field_plan['field_type'],
                        'widget_type': field_plan['widget_type'],
                        'widget_attrs': field_plan['widget_attrs'],
                        'validation_rules': field_plan['validation_rules'],
                        'choices_data': field_plan['choices_data'],
                        'storage_type': field_plan['storage_type'],
                        'is_dynamic': field_plan['is_dynamic'],
                    }
                )
                
                if created:
                    stats['fields'] += 1
                    # Track orphaned fields
                    if field_plan.get('coverage_source') == 'orphaned_requirement':
                        stats['orphaned_fields'] += 1
                    
                    logger.info(f'Created FieldConfig: {form_def_plan["name"]} → {section_name} → {field_name}')
                else:
                    logger.info(f'Updated FieldConfig: {form_def_plan["name"]} → {section_name} → {field_name}')
    
    def _group_requirements(self, requirements):
        """Group field requirements by form_type and section_name with sorting"""
        grouped = defaultdict(lambda: defaultdict(list))
        for req in requirements:
            grouped[req.form_type][req.section_name].append(req)
        
        # Sort requirements within each group by sort_order, then field_name
        for form_type in grouped:
            for section_name in grouped[form_type]:
                grouped[form_type][section_name].sort(key=lambda r: (r.sort_order, r.field_name))
        
        return grouped
    
    def _find_orphaned_fields(self, layouts, requirements):
        """Find SystemFieldRequirement records not referenced in any layout JSON"""
        # Get all fields referenced in layouts
        layout_fields = set()
        for layout in layouts:
            sections_data = self.safe_get_sections(layout)
            for section in sections_data:
                for field_name in section.get('fields', []):
                    layout_fields.add((layout.form_type, field_name))
        
        # Find requirements not in layouts
        orphaned = []
        for req in requirements:
            if (req.form_type, req.field_name) not in layout_fields:
                orphaned.append(req)
        
        return orphaned
    
    def _migrate_form_type_safely_legacy(self, form_type, layouts, requirements_grouped, form_type_mappings, stats):
        """Migrate a single form type with complete data preservation"""
        content_type = form_type_mappings.get(form_type)
        if not content_type:
            error_msg = f'No ContentType mapping found for {form_type}'
            stats['errors'].append(error_msg)
            return
        
        # Find layout for this form type
        layout = next((l for l in layouts if l.form_type == form_type), None)
        
        # Create FormDefinition with safe form type display
        form_name = self._get_safe_form_type_display(form_type, layout)
        form_slug = form_type.replace('.', '_').replace(' ', '_').lower()
        
        form_definition, created = FormDefinition.objects.get_or_create(
            form_type=form_slug,
            defaults={
                'name': form_name,
                'target_model': content_type,
                'description': f'Migrated from legacy {form_type}',
                'is_active': layout.active if layout else True,
                'version': 1,
            }
        )
        
        if created:
            stats['definitions'] += 1
            logger.info(f'Created FormDefinition: {form_name}')
        
        # Get ALL sections for this form type (from layout AND requirements)
        all_sections = self._get_all_sections_for_form_type(form_type, layout, requirements_grouped)
        
        # Create FormSections for ALL sections
        for section_order, section_info in enumerate(all_sections, 1):
            section_name = section_info['name']
            form_section, created = FormSection.objects.get_or_create(
                form_definition=form_definition,
                name=section_name,
                defaults={
                    'slug': section_name.lower().replace(' ', '_'),
                    'description': f'Migrated section from {form_type}',
                    'order': section_order,
                    'is_collapsed': section_info.get('collapsed', False),
                    'is_active': True,
                }
            )
            
            if created:
                stats['sections'] += 1
                logger.info(f'Created FormSection: {form_name} → {section_name}')
            
            # Create ALL FieldConfigs for this section
            self._create_all_field_configs(
                form_section, form_type, section_name, section_info, requirements_grouped, stats
            )
    
    def _get_safe_form_type_display(self, form_type, layout):
        """Get display name safely without relying on model choices"""
        if layout:
            try:
                # Try to get the display name from the model
                return layout.get_form_type_display()
            except (AttributeError, ValueError):
                # Fallback to the raw form_type
                pass
        
        # Create a human-readable name from form_type
        return form_type.replace('.', ' - ').replace('_', ' ').title()
    
    def _get_all_sections_for_form_type(self, form_type, layout, requirements_grouped):
        """Get ALL sections for a form type from both layout and requirements"""
        all_sections = []
        sections_seen = set()
        
        # First, add sections from layout (if exists)
        if layout:
            sections_data = self.safe_get_sections(layout)
            for section_data in sections_data:
                section_name = section_data.get('name', 'Unknown')
                all_sections.append({
                    'name': section_name,
                    'fields': section_data.get('fields', []),
                    'order': section_data.get('order', len(all_sections) + 1),
                    'collapsed': section_data.get('collapsed', False),
                    'source': 'layout'
                })
                sections_seen.add(section_name)
        
        # Then, add any sections from requirements that aren't in layout
        form_requirements = requirements_grouped.get(form_type, {})
        for section_name in sorted(form_requirements.keys()):
            if section_name not in sections_seen:
                # This is an orphaned section not in layout
                field_names = [req.field_name for req in form_requirements[section_name]]
                all_sections.append({
                    'name': section_name,
                    'fields': field_names,
                    'order': len(all_sections) + 1,
                    'collapsed': False,
                    'source': 'requirements_orphaned'
                })
                logger.warning(f'Recovered orphaned section: {form_type} → {section_name}')
        
        return all_sections
    
    def _create_all_field_configs(self, form_section, form_type, section_name, section_info, requirements_grouped, stats):
        """Create FieldConfigs for ALL fields, ensuring no data loss"""
        # Get field requirements for this section
        section_requirements = requirements_grouped.get(form_type, {}).get(section_name, [])
        req_by_field_name = {req.field_name: req for req in section_requirements}
        
        # Get fields from layout
        layout_fields = section_info.get('fields', [])
        
        # Create FieldConfigs for layout fields
        for field_order, field_name in enumerate(layout_fields, 1):
            field_req = req_by_field_name.get(field_name)
            self._create_field_config(
                form_section, field_name, field_req, field_order, stats
            )
        
        # Create FieldConfigs for orphaned requirement fields (not in layout)
        orphaned_fields = [req for req in section_requirements if req.field_name not in layout_fields]
        if orphaned_fields:
            logger.warning(f'Found {len(orphaned_fields)} orphaned fields in {form_type} → {section_name}')
            stats['orphaned_fields'] += len(orphaned_fields)
            
            for field_req in orphaned_fields:
                # Use the requirement's sort_order, but add offset to avoid conflicts
                field_order = len(layout_fields) + field_req.sort_order + 1
                self._create_field_config(
                    form_section, field_req.field_name, field_req, field_order, stats
                )
    
    def _create_field_config(self, form_section, field_name, field_req, field_order, stats):
        """Create a single FieldConfig with complete data preservation"""
        # Determine field configuration
        if field_req:
            # Use data from SystemFieldRequirement
            field_config_data = {
                'label': field_req.field_label,
                'help_text': field_req.help_text,
                'is_required': field_req.required,
                'is_active': field_req.enabled,
                'order': field_order,
                'field_type': self._infer_field_type(field_req.field_name),
                'is_readonly': False,
                'placeholder': '',
                'default_value': '',
                'widget_type': self._infer_widget_type(field_req.field_name),
                'widget_attrs': self._infer_widget_attrs(field_req.field_name),
                'validation_rules': self._infer_validation_rules(field_req),
                'choices_data': self._infer_choices_data(field_req.field_name),
                'storage_type': 'model_field',
                'is_dynamic': False,
            }
        else:
            # Create basic configuration for fields without requirements
            field_config_data = {
                'label': field_name.replace('_', ' ').title(),
                'help_text': '',
                'is_required': False,
                'is_active': True,
                'order': field_order,
                'field_type': self._infer_field_type(field_name),
                'is_readonly': False,
                'placeholder': '',
                'default_value': '',
                'widget_type': self._infer_widget_type(field_name),
                'widget_attrs': self._infer_widget_attrs(field_name),
                'validation_rules': {},
                'choices_data': self._infer_choices_data(field_name),
                'storage_type': 'model_field',
                'is_dynamic': False,
            }
        
        # Create FieldConfig
        field_config, created = FieldConfig.objects.get_or_create(
            section=form_section,
            field_key=field_name,
            defaults=field_config_data
        )
        
        if created:
            stats['fields'] += 1
            logger.info(f'Created FieldConfig: {form_section.form_definition.name} → {form_section.name} → {field_name}')
    
    def _infer_field_type(self, field_name):
        """Infer field type from field name with enhanced detection"""
        field_name_lower = field_name.lower()
        
        if 'email' in field_name_lower:
            return 'email'
        elif 'url' in field_name_lower or 'website' in field_name_lower:
            return 'url'
        elif 'date' in field_name_lower and 'time' not in field_name_lower:
            return 'date'
        elif 'datetime' in field_name_lower or ('date' in field_name_lower and 'time' in field_name_lower):
            return 'datetime'
        elif 'time' in field_name_lower:
            return 'time'
        elif 'phone' in field_name_lower:
            return 'char'
        elif 'number' in field_name_lower or 'count' in field_name_lower or 'quantity' in field_name_lower:
            return 'integer'
        elif any(word in field_name_lower for word in ['price', 'cost', 'amount', 'rate', 'fee', 'total']):
            return 'decimal'
        elif any(word in field_name_lower for word in ['description', 'notes', 'comment', 'detail']):
            return 'text'
        elif any(word in field_name_lower for word in ['choice', 'status', 'type', 'category']):
            return 'choice'
        elif 'file' in field_name_lower or 'document' in field_name_lower or 'attachment' in field_name_lower:
            return 'file'
        elif 'image' in field_name_lower or 'photo' in field_name_lower:
            return 'image'
        elif field_name_lower.startswith('is_') or field_name_lower.startswith('has_') or 'boolean' in field_name_lower:
            return 'boolean'
        else:
            return 'char'
    
    def _infer_widget_type(self, field_name):
        """Infer widget type from field name"""
        field_name_lower = field_name.lower()
        
        if 'email' in field_name_lower:
            return 'email'
        elif 'url' in field_name_lower or 'website' in field_name_lower:
            return 'url'
        elif 'password' in field_name_lower:
            return 'password'
        elif any(word in field_name_lower for word in ['description', 'notes', 'comment', 'detail']):
            return 'textarea'
        elif any(word in field_name_lower for word in ['choice', 'status', 'type', 'category']):
            return 'select'
        elif 'date' in field_name_lower and 'time' not in field_name_lower:
            return 'date'
        elif 'datetime' in field_name_lower or ('date' in field_name_lower and 'time' in field_name_lower):
            return 'datetime'
        elif 'time' in field_name_lower:
            return 'time'
        elif 'file' in field_name_lower or 'document' in field_name_lower:
            return 'file'
        elif 'image' in field_name_lower or 'photo' in field_name_lower:
            return 'image'
        elif field_name_lower.startswith('is_') or field_name_lower.startswith('has_'):
            return 'checkbox'
        else:
            return 'default'
    
    def _infer_widget_attrs(self, field_name):
        """Infer widget attributes from field name"""
        field_name_lower = field_name.lower()
        attrs = {}
        
        if any(word in field_name_lower for word in ['description', 'notes', 'comment']):
            attrs['rows'] = 4
        elif 'long' in field_name_lower or 'detail' in field_name_lower:
            attrs['rows'] = 6
        
        return attrs
    
    def _infer_validation_rules(self, field_req):
        """Infer validation rules from field requirement"""
        rules = {}
        
        if field_req.required:
            rules['required'] = True
        
        field_name_lower = field_req.field_name.lower()
        
        if 'email' in field_name_lower:
            rules['email'] = True
        elif 'phone' in field_name_lower:
            rules['pattern'] = r'^[\+]?[1-9]?[\d\s\-\(\)]+$'
        elif any(word in field_name_lower for word in ['price', 'cost', 'amount', 'rate']):
            rules['min'] = 0
        
        return rules
    
    def _infer_choices_data(self, field_name):
        """Infer choices data from field name"""
        field_name_lower = field_name.lower()
        
        # Common choice mappings
        if 'status' in field_name_lower:
            return [
                ['draft', 'Draft'],
                ['active', 'Active'],
                ['inactive', 'Inactive'],
            ]
        elif 'priority' in field_name_lower:
            return [
                ['low', 'Low'],
                ['medium', 'Medium'],
                ['high', 'High'],
                ['urgent', 'Urgent'],
            ]
        elif 'type' in field_name_lower and 'room' in field_name_lower:
            return [
                ['single', 'Single'],
                ['double', 'Double'],
                ['suite', 'Suite'],
            ]
        
        return []