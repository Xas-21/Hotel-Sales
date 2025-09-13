"""
Dynamic Schema Management Service

This service handles runtime database schema changes for dynamic models and fields.
It provides safe operations for creating/modifying database tables and columns using
Django's schema_editor API for cross-database compatibility.
"""

from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.state import ModelState
from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.backends.utils import truncate_name
import logging
import time
import uuid
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class SchemaManager:
    """
    Service for managing dynamic database schema changes using Django's schema_editor API.
    
    This class provides cross-database compatible operations for creating and modifying
    database tables and columns without using raw SQL.
    """
    
    @classmethod
    def create_dynamic_model_table(cls, model_config: Dict[str, Any]) -> bool:
        """
        Create a new database table for a dynamic model using Django's schema_editor.
        
        Args:
            model_config: Dictionary containing model configuration
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            table_name = model_config['table_name']
            
            # Check if table already exists
            if cls._table_exists(table_name):
                logger.warning(f"Table {table_name} already exists")
                return False
            
            # Create a temporary model class for schema operations with unique name
            temp_model_name = f'TempModel_{int(time.time())}_{uuid.uuid4().hex[:8]}'
            
            temp_model_attrs = {
                'id': models.AutoField(primary_key=True),
                'created_at': models.DateTimeField(auto_now_add=True),
                'updated_at': models.DateTimeField(auto_now=True),
                '__module__': 'requests.services.schema_manager',
                'Meta': type('Meta', (), {
                    'db_table': table_name,
                    'app_label': 'requests'
                })
            }
            
            TempModel = type(temp_model_name, (models.Model,), temp_model_attrs)
            
            # Use schema editor with SQLite foreign key constraints disabled
            cls._execute_with_schema_editor(lambda editor: editor.create_model(TempModel))
            
            logger.info(f"Created table {table_name}")
            return True
                
        except Exception as e:
            logger.error(f"Failed to create table {table_name}: {e}")
            return False
    
    @classmethod
    def add_dynamic_field(cls, table_name: str, field_config: Dict[str, Any]) -> bool:
        """
        Add a new column to an existing table using Django's schema_editor.
        
        Args:
            table_name: Name of the table
            field_config: Dictionary containing field configuration
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            field_name = field_config['name']
            field_type = field_config['field_type']
            
            # Check if column already exists
            if cls._column_exists(table_name, field_name):
                logger.warning(f"Column {field_name} already exists in {table_name}")
                return False
            
            # Create Django field object
            field = cls._create_django_field(field_type, field_config)
            if not field:
                logger.error(f"Failed to create Django field for type {field_type}")
                return False
            
            field.set_attributes_from_name(field_name)
            
            # Create a temporary model class for schema operations with unique name
            temp_model_name = f'TempModel_{int(time.time())}_{uuid.uuid4().hex[:8]}'
            
            temp_model_attrs = {
                '__module__': 'requests.services.schema_manager',
                'Meta': type('Meta', (), {
                    'db_table': table_name,
                    'app_label': 'requests'
                })
            }
            
            TempModel = type(temp_model_name, (models.Model,), temp_model_attrs)
            
            # Use schema editor to add field
            cls._execute_with_schema_editor(lambda editor: editor.add_field(TempModel, field))
            
            logger.info(f"Added column {field_name} to {table_name}")
            return True
                
        except Exception as e:
            logger.error(f"Failed to add column {field_name} to {table_name}: {e}")
            return False
    
    @classmethod
    def remove_dynamic_field(cls, table_name: str, field_name: str) -> bool:
        """
        Remove a column from a table using Django's schema_editor.
        
        Args:
            table_name: Name of the table
            field_name: Name of the field to remove
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Check if column exists
                if not cls._column_exists(table_name, field_name):
                    logger.warning(f"Column {field_name} does not exist in {table_name}")
                    return False
                
                # Create a generic field for removal (type doesn't matter for removal)
                field = models.CharField(max_length=100)
                field.set_attributes_from_name(field_name)
                
                # Create a temporary model class for schema operations with unique name
                temp_model_name = f'TempModel_{int(time.time())}_{uuid.uuid4().hex[:8]}'
                
                temp_model_attrs = {
                    '__module__': 'requests.services.schema_manager',
                    'Meta': type('Meta', (), {
                        'db_table': table_name,
                        'app_label': 'requests'
                    })
                }
                
                TempModel = type(temp_model_name, (models.Model,), temp_model_attrs)
                
                # Use schema editor to remove field
                cls._execute_with_schema_editor(lambda editor: editor.remove_field(TempModel, field))
                
                logger.info(f"Removed column {field_name} from {table_name}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to remove column {field_name} from {table_name}: {e}")
            return False
    
    @classmethod
    def alter_dynamic_field(cls, table_name: str, field_name: str, old_config: Dict, new_config: Dict) -> bool:
        """
        Modify an existing column in a table using Django's schema_editor.
        
        Args:
            table_name: Name of the table
            field_name: Name of the field to alter
            old_config: Previous field configuration
            new_config: New field configuration
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Create Django field objects for old and new configurations
                old_field = cls._create_django_field(old_config['field_type'], old_config)
                new_field = cls._create_django_field(new_config['field_type'], new_config)
                
                if not old_field or not new_field:
                    logger.error("Failed to create Django field objects for alteration")
                    return False
                
                old_field.set_attributes_from_name(old_config['name'])
                new_field.set_attributes_from_name(new_config['name'])
                
                # Create a temporary model class for schema operations with unique name
                temp_model_name = f'TempModel_{int(time.time())}_{uuid.uuid4().hex[:8]}'
                
                temp_model_attrs = {
                    '__module__': 'requests.services.schema_manager',
                    'Meta': type('Meta', (), {
                        'db_table': table_name,
                        'app_label': 'requests'
                    })
                }
                
                TempModel = type(temp_model_name, (models.Model,), temp_model_attrs)
                
                # Use schema editor to alter field
                cls._execute_with_schema_editor(lambda editor: editor.alter_field(TempModel, old_field, new_field))
                
                logger.info(f"Altered column {field_name} in {table_name}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to alter column {field_name} in {table_name}: {e}")
            return False
    
    @classmethod
    def drop_dynamic_model_table(cls, table_name: str) -> bool:
        """
        Drop a table completely using Django's schema_editor.
        
        Args:
            table_name: Name of the table to drop
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not cls._table_exists(table_name):
                logger.warning(f"Table {table_name} does not exist")
                return False
            
            # Create a temporary model class for schema operations with unique name
            temp_model_name = f'TempModel_{int(time.time())}_{uuid.uuid4().hex[:8]}'
            
            temp_model_attrs = {
                '__module__': 'requests.services.schema_manager',
                'Meta': type('Meta', (), {
                    'db_table': table_name,
                    'app_label': 'requests'
                })
            }
            
            TempModel = type(temp_model_name, (models.Model,), temp_model_attrs)
            
            # Use schema editor to delete table
            cls._execute_with_schema_editor(lambda editor: editor.delete_model(TempModel))
            
            logger.info(f"Dropped table {table_name}")
            return True
                
        except Exception as e:
            logger.error(f"Failed to drop table {table_name}: {e}")
            return False
    
    @classmethod
    def _table_exists(cls, table_name: str) -> bool:
        """
        Check if a table exists using Django's database introspection.
        
        Args:
            table_name: Name of the table to check
            
        Returns:
            bool: True if table exists, False otherwise
        """
        try:
            introspection = connection.introspection
            table_names = introspection.table_names(connection.cursor())
            return table_name in table_names
        except Exception as e:
            logger.error(f"Failed to check table existence for {table_name}: {e}")
            return False
    
    @classmethod
    def _column_exists(cls, table_name: str, column_name: str) -> bool:
        """
        Check if a column exists in a table using Django's database introspection.
        
        Args:
            table_name: Name of the table
            column_name: Name of the column to check
            
        Returns:
            bool: True if column exists, False otherwise
        """
        try:
            if not cls._table_exists(table_name):
                return False
            
            introspection = connection.introspection
            with connection.cursor() as cursor:
                table_description = introspection.get_table_description(cursor, table_name)
                column_names = [row.name for row in table_description]
                return column_name in column_names
        except Exception as e:
            logger.error(f"Failed to check column existence for {table_name}.{column_name}: {e}")
            return False
    
    @classmethod
    def _create_django_field(cls, field_type: str, field_config: Dict[str, Any]) -> Optional[models.Field]:
        """
        Create a Django field object from field type and configuration.
        
        Args:
            field_type: String identifier of field type
            field_config: Configuration dictionary for the field
            
        Returns:
            Django field instance or None if type is not supported
        """
        # Common field parameters
        null = not field_config.get('required', False)
        blank = not field_config.get('required', False)
        default = field_config.get('default_value')
        help_text = field_config.get('help_text', '')
        
        # Map field types to Django field classes
        field_mapping = {
            'char': lambda: models.CharField(
                max_length=field_config.get('max_length', 255),
                null=null,
                blank=blank,
                default=default,
                help_text=help_text
            ),
            'text': lambda: models.TextField(
                null=null,
                blank=blank,
                default=default,
                help_text=help_text
            ),
            'email': lambda: models.EmailField(
                null=null,
                blank=blank,
                default=default,
                help_text=help_text
            ),
            'url': lambda: models.URLField(
                null=null,
                blank=blank,
                default=default,
                help_text=help_text
            ),
            'slug': lambda: models.SlugField(
                max_length=field_config.get('max_length', 50),
                null=null,
                blank=blank,
                default=default,
                help_text=help_text
            ),
            'integer': lambda: models.IntegerField(
                null=null,
                blank=blank,
                default=default,
                help_text=help_text
            ),
            'decimal': lambda: models.DecimalField(
                max_digits=field_config.get('max_digits', 10),
                decimal_places=field_config.get('decimal_places', 2),
                null=null,
                blank=blank,
                default=default,
                help_text=help_text
            ),
            'float': lambda: models.FloatField(
                null=null,
                blank=blank,
                default=default,
                help_text=help_text
            ),
            'date': lambda: models.DateField(
                null=null,
                blank=blank,
                default=default,
                help_text=help_text
            ),
            'datetime': lambda: models.DateTimeField(
                null=null,
                blank=blank,
                default=default,
                help_text=help_text
            ),
            'time': lambda: models.TimeField(
                null=null,
                blank=blank,
                default=default,
                help_text=help_text
            ),
            'boolean': lambda: models.BooleanField(
                default=bool(default) if default is not None else False,
                help_text=help_text
            ),
            'choice': lambda: models.CharField(
                max_length=field_config.get('max_length', 100),
                choices=field_config.get('choices', []),
                null=null,
                blank=blank,
                default=default,
                help_text=help_text
            ),
            'multiple_choice': lambda: models.TextField(
                null=null,
                blank=blank,
                default=default,
                help_text=help_text + ' (JSON format)'
            ),
            'file': lambda: models.FileField(
                upload_to=field_config.get('upload_to', 'dynamic_files/'),
                null=null,
                blank=blank,
                help_text=help_text
            ),
            'image': lambda: models.ImageField(
                upload_to=field_config.get('upload_to', 'dynamic_images/'),
                null=null,
                blank=blank,
                help_text=help_text
            ),
            'foreign_key': lambda: models.IntegerField(
                null=null,
                blank=blank,
                default=default,
                help_text=help_text + ' (Foreign Key ID)'
            ),
            'json': lambda: models.JSONField(
                null=null,
                blank=blank,
                default=default or dict,
                help_text=help_text
            ),
        }
        
        try:
            field_creator = field_mapping.get(field_type)
            if field_creator:
                return field_creator()
            else:
                logger.warning(f"Unknown field type: {field_type}")
                # Default to CharField for unknown types
                return models.CharField(
                    max_length=255,
                    null=null,
                    blank=blank,
                    default=default,
                    help_text=help_text
                )
        except Exception as e:
            logger.error(f"Failed to create Django field for type {field_type}: {e}")
            return None
    
    @classmethod
    def get_table_schema(cls, table_name: str) -> Optional[Dict[str, Any]]:
        """
        Get the current schema information for a table using Django's introspection.
        
        Args:
            table_name: Name of the table
            
        Returns:
            Dictionary containing table schema information or None if table doesn't exist
        """
        try:
            if not cls._table_exists(table_name):
                return None
            
            introspection = connection.introspection
            with connection.cursor() as cursor:
                table_description = introspection.get_table_description(cursor, table_name)
                
                schema = {
                    'table_name': table_name,
                    'columns': []
                }
                
                for row in table_description:
                    column_info = {
                        'name': row.name,
                        'type': row.type_code,
                        'display_size': row.display_size,
                        'internal_size': row.internal_size,
                        'precision': row.precision,
                        'scale': row.scale,
                        'null_ok': row.null_ok
                    }
                    schema['columns'].append(column_info)
                
                return schema
                
        except Exception as e:
            logger.error(f"Failed to get schema for table {table_name}: {e}")
            return None
    
    @classmethod
    def _execute_with_schema_editor(cls, operation_func):
        """
        Execute a schema operation with proper handling of SQLite foreign key constraints.
        
        Args:
            operation_func: Function that takes a schema_editor and performs the operation
        """
        is_sqlite = connection.vendor == 'sqlite'
        
        if is_sqlite:
            # For SQLite, disable foreign key constraints during schema changes
            with connection.cursor() as cursor:
                cursor.execute("PRAGMA foreign_keys = OFF")
            
            try:
                with connection.schema_editor() as schema_editor:
                    operation_func(schema_editor)
            finally:
                # Re-enable foreign key constraints
                with connection.cursor() as cursor:
                    cursor.execute("PRAGMA foreign_keys = ON")
        else:
            # For other databases, use schema editor normally within a transaction
            with transaction.atomic():
                with connection.schema_editor() as schema_editor:
                    operation_func(schema_editor)