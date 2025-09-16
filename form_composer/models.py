"""
Modern Form Composer Models

A comprehensive, flexible configuration system for Django admin forms.
Provides drag-and-drop section management, field customization, and
universal support for all Django models.
"""

from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
import json


class FormDefinition(models.Model):
    """
    Defines the complete configuration for a Django admin form.
    Links to any Django model via ContentType for universal compatibility.
    """
    
    name = models.CharField(
        max_length=200,
        help_text="Human-readable name for this form configuration"
    )
    
    form_type = models.SlugField(
        max_length=100,
        unique=True,
        help_text="Unique identifier for this form (e.g., 'sales_calls_salescall')"
    )
    
    target_model = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        help_text="The Django model this configuration applies to"
    )
    
    description = models.TextField(
        blank=True,
        help_text="Optional description of what this form is for"
    )
    
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this configuration is currently in use"
    )
    
    version = models.PositiveIntegerField(
        default=1,
        help_text="Version number for tracking changes"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='created_form_definitions'
    )
    
    # Configuration metadata
    layout_settings = models.JSONField(
        default=dict,
        help_text="Global layout settings like column widths, styling preferences"
    )
    
    class Meta:
        ordering = ['name']
        verbose_name = "Form Configuration"
        verbose_name_plural = "Form Configurations"
    
    def __str__(self):
        return f"{self.name} ({self.form_type})"
    
    def get_model_class(self):
        """Get the Django model class this configuration applies to"""
        return self.target_model.model_class()
    
    def get_sections_ordered(self):
        """Get all sections ordered by their order field"""
        return self.sections.filter(is_active=True).order_by('order')
    
    def clean(self):
        """Validate the form definition"""
        super().clean()
        
        # Ensure the target model exists and is valid
        try:
            model_class = self.get_model_class()
            if not model_class:
                raise ValidationError("Target model does not exist or is not accessible")
        except Exception as e:
            raise ValidationError(f"Invalid target model: {e}")


class FormSection(models.Model):
    """
    Represents a section (fieldset) within a form.
    Sections can be reordered, collapsed, and have conditional visibility.
    """
    
    form_definition = models.ForeignKey(
        FormDefinition,
        on_delete=models.CASCADE,
        related_name='sections'
    )
    
    name = models.CharField(
        max_length=200,
        help_text="Section title displayed in the form"
    )
    
    slug = models.SlugField(
        max_length=100,
        help_text="URL-friendly identifier for this section"
    )
    
    description = models.TextField(
        blank=True,
        help_text="Optional description shown in the section header"
    )
    
    order = models.PositiveIntegerField(
        default=0,
        help_text="Display order (lower numbers appear first)"
    )
    
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this section is currently visible"
    )
    
    is_collapsed = models.BooleanField(
        default=False,
        help_text="Whether this section starts collapsed"
    )
    
    # Advanced features
    conditional_logic = models.JSONField(
        default=dict,
        blank=True,
        help_text="JSON rules for when this section should be visible"
    )
    
    permissions = models.JSONField(
        default=dict,
        blank=True,
        help_text="Permission rules for who can see this section"
    )
    
    css_classes = models.CharField(
        max_length=200,
        blank=True,
        help_text="Additional CSS classes to apply to this section"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['form_definition', 'order', 'name']
        unique_together = [['form_definition', 'slug']]
        verbose_name = "Form Section"
        verbose_name_plural = "Form Sections"
    
    def __str__(self):
        return f"{self.form_definition.name} → {self.name}"
    
    def get_fields_ordered(self):
        """Get all fields in this section ordered by their order field"""
        return self.field_configs.filter(is_active=True).order_by('order')


class FieldConfig(models.Model):
    """
    Configuration for individual form fields.
    Supports both core model fields and custom dynamic fields.
    """
    
    WIDGET_CHOICES = [
        ('default', 'Default Widget'),
        ('text', 'Text Input'),
        ('textarea', 'Textarea'),
        ('number', 'Number Input'),
        ('email', 'Email Input'),
        ('url', 'URL Input'),
        ('password', 'Password Input'),
        ('checkbox', 'Checkbox'),
        ('radio', 'Radio Buttons'),
        ('select', 'Select Dropdown'),
        ('multiselect', 'Multiple Select'),
        ('date', 'Date Picker'),
        ('datetime', 'DateTime Picker'),
        ('time', 'Time Picker'),
        ('file', 'File Upload'),
        ('image', 'Image Upload'),
        ('hidden', 'Hidden Field'),
    ]
    
    FIELD_TYPE_CHOICES = [
        ('char', 'Text Field'),
        ('text', 'Long Text'),
        ('integer', 'Integer'),
        ('decimal', 'Decimal Number'),
        ('boolean', 'Boolean'),
        ('date', 'Date'),
        ('datetime', 'Date & Time'),
        ('time', 'Time'),
        ('email', 'Email'),
        ('url', 'URL'),
        ('choice', 'Single Choice'),
        ('multiple_choice', 'Multiple Choice'),
        ('file', 'File'),
        ('image', 'Image'),
        ('json', 'JSON Data'),
        ('foreign_key', 'Foreign Key'),
    ]
    
    section = models.ForeignKey(
        FormSection,
        on_delete=models.CASCADE,
        related_name='field_configs'
    )
    
    # Field identification
    field_key = models.CharField(
        max_length=100,
        help_text="Model field name or dynamic field identifier"
    )
    
    # Display configuration
    label = models.CharField(
        max_length=200,
        blank=True,
        help_text="Custom field label (overrides model field label)"
    )
    
    help_text = models.TextField(
        blank=True,
        help_text="Help text displayed with the field"
    )
    
    placeholder = models.CharField(
        max_length=200,
        blank=True,
        help_text="Placeholder text for input fields"
    )
    
    # Field behavior
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this field is displayed in the form"
    )
    
    is_required = models.BooleanField(
        default=False,
        help_text="Whether this field is required for form submission"
    )
    
    is_readonly = models.BooleanField(
        default=False,
        help_text="Whether this field is read-only"
    )
    
    order = models.PositiveIntegerField(
        default=0,
        help_text="Display order within the section"
    )
    
    # Field type and widget
    field_type = models.CharField(
        max_length=50,
        choices=FIELD_TYPE_CHOICES,
        default='char',
        help_text="Type of field for dynamic fields"
    )
    
    widget_type = models.CharField(
        max_length=50,
        choices=WIDGET_CHOICES,
        default='default',
        help_text="Widget to use for rendering this field"
    )
    
    widget_attrs = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional attributes for the widget (e.g., {'rows': 3})"
    )
    
    # Choice fields
    choices_source = models.CharField(
        max_length=200,
        blank=True,
        help_text="Source for choice values (JSON array, model method, or callable)"
    )
    
    choices_data = models.JSONField(
        default=list,
        blank=True,
        help_text="Static choice data as [['key', 'label'], ...] pairs"
    )
    
    # Validation
    validation_rules = models.JSONField(
        default=dict,
        blank=True,
        help_text="Custom validation rules for this field"
    )
    
    default_value = models.TextField(
        blank=True,
        help_text="Default value for new instances"
    )
    
    # Dynamic field handling
    is_dynamic = models.BooleanField(
        default=False,
        help_text="Whether this is a custom field not in the model"
    )
    
    storage_type = models.CharField(
        max_length=50,
        choices=[
            ('model_field', 'Store in model field'),
            ('value_store', 'Store in generic value store'),
            ('computed', 'Computed/display only'),
        ],
        default='model_field',
        help_text="How field data is stored"
    )
    
    # Metadata
    css_classes = models.CharField(
        max_length=200,
        blank=True,
        help_text="Additional CSS classes for this field"
    )
    
    conditional_logic = models.JSONField(
        default=dict,
        blank=True,
        help_text="JSON rules for when this field should be visible/enabled"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['section', 'order', 'field_key']
        unique_together = [['section', 'field_key']]
        verbose_name = "Field Configuration"
        verbose_name_plural = "Field Configurations"
    
    def __str__(self):
        return f"{self.section} → {self.label or self.field_key}"
    
    def get_effective_label(self):
        """Get the label to display (custom label or field name)"""
        return self.label or self.field_key.replace('_', ' ').title()
    
    def get_widget_attrs_merged(self):
        """Get widget attributes merged with defaults"""
        attrs = {
            'class': self.css_classes or '',
            'placeholder': self.placeholder or '',
        }
        attrs.update(self.widget_attrs)
        return {k: v for k, v in attrs.items() if v}  # Remove empty values


class DynamicFieldValue(models.Model):
    """
    Stores values for dynamic fields that aren't part of the model.
    Uses generic foreign keys to link to any model instance.
    """
    
    field_config = models.ForeignKey(
        FieldConfig,
        on_delete=models.CASCADE,
        related_name='dynamic_values'
    )
    
    # Generic foreign key to link to any model instance
    content_type = models.ForeignKey(
        ContentType, 
        on_delete=models.CASCADE,
        related_name='form_composer_values'
    )
    object_id = models.PositiveIntegerField()
    
    # Value storage for different data types
    value_text = models.TextField(blank=True, null=True)
    value_integer = models.IntegerField(blank=True, null=True)
    value_decimal = models.DecimalField(max_digits=20, decimal_places=10, blank=True, null=True)
    value_boolean = models.BooleanField(blank=True, null=True)
    value_date = models.DateField(blank=True, null=True)
    value_datetime = models.DateTimeField(blank=True, null=True)
    value_time = models.TimeField(blank=True, null=True)
    value_file = models.FileField(upload_to='dynamic_fields/', blank=True, null=True)
    value_json = models.JSONField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = [['field_config', 'content_type', 'object_id']]
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
        ]
        verbose_name = "Dynamic Field Value"
        verbose_name_plural = "Dynamic Field Values"
    
    def __str__(self):
        return f"{self.field_config.field_key} for {self.content_type.model} #{self.object_id}"
    
    def get_value(self):
        """Get the appropriate value based on field type"""
        field_type = self.field_config.field_type
        
        type_mapping = {
            'char': 'value_text',
            'text': 'value_text',
            'email': 'value_text',
            'url': 'value_text',
            'integer': 'value_integer',
            'decimal': 'value_decimal',
            'boolean': 'value_boolean',
            'date': 'value_date',
            'datetime': 'value_datetime',
            'time': 'value_time',
            'file': 'value_file',
            'image': 'value_file',
            'json': 'value_json',
            'choice': 'value_text',
            'multiple_choice': 'value_json',
            'foreign_key': 'value_integer',
        }
        
        attr_name = type_mapping.get(field_type, 'value_text')
        return getattr(self, attr_name)
    
    def set_value(self, value):
        """Set the appropriate value based on field type"""
        field_type = self.field_config.field_type
        
        # Clear all values first
        for field in ['value_text', 'value_integer', 'value_decimal', 'value_boolean', 
                     'value_date', 'value_datetime', 'value_time', 'value_file', 'value_json']:
            setattr(self, field, None)
        
        # Set the appropriate value
        if field_type in ['char', 'text', 'email', 'url', 'choice']:
            self.value_text = str(value) if value is not None else None
        elif field_type == 'integer':
            self.value_integer = int(value) if value is not None else None
        elif field_type == 'decimal':
            from decimal import Decimal
            self.value_decimal = Decimal(str(value)) if value is not None else None
        elif field_type == 'boolean':
            self.value_boolean = bool(value) if value is not None else None
        elif field_type == 'date':
            self.value_date = value
        elif field_type == 'datetime':
            self.value_datetime = value
        elif field_type == 'time':
            self.value_time = value
        elif field_type in ['file', 'image']:
            self.value_file = value
        elif field_type in ['json', 'multiple_choice']:
            self.value_json = value
        elif field_type == 'foreign_key':
            # Store foreign key as primary key value in value_integer
            self.value_integer = int(value.pk if hasattr(value, 'pk') else value) if value is not None else None
        else:
            self.value_text = str(value) if value is not None else None


class UserPreference(models.Model):
    """
    Stores user-specific preferences for the form composer interface.
    Allows customization of navigation placement, UI settings, etc.
    """
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='form_composer_preferences'
    )
    
    preference_key = models.CharField(
        max_length=100,
        help_text="Unique identifier for this preference type"
    )
    
    preference_value = models.JSONField(
        help_text="The preference value (any JSON-serializable data)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = [['user', 'preference_key']]
        verbose_name = "User Preference"
        verbose_name_plural = "User Preferences"
    
    def __str__(self):
        return f"{self.user.username}: {self.preference_key}"
    
    @classmethod
    def get_user_preference(cls, user, key, default=None):
        """Get a user preference value with a default fallback"""
        try:
            pref = cls.objects.get(user=user, preference_key=key)
            return pref.preference_value
        except cls.DoesNotExist:
            return default
    
    @classmethod
    def set_user_preference(cls, user, key, value):
        """Set a user preference value"""
        pref, created = cls.objects.update_or_create(
            user=user,
            preference_key=key,
            defaults={'preference_value': value}
        )
        return pref
