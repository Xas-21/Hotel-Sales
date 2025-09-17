"""
Emergency fix to ensure date fields work in all admin forms
"""
from django import forms
from django.contrib import admin

# Force all date and time fields to use admin widgets globally
def patch_all_admin_forms():
    """Patch all admin forms to use correct date/time widgets"""
    
    # Store original formfield_for_dbfield
    original_formfield = admin.ModelAdmin.formfield_for_dbfield
    
    def patched_formfield_for_dbfield(self, db_field, request, **kwargs):
        """Override to force admin widgets for date/time fields"""
        from django.db import models
        
        # Force admin widgets for date/time fields
        if isinstance(db_field, models.DateField):
            kwargs['widget'] = admin.widgets.AdminDateWidget
        elif isinstance(db_field, models.TimeField):
            kwargs['widget'] = admin.widgets.AdminTimeWidget
        elif isinstance(db_field, models.DateTimeField):
            kwargs['widget'] = admin.widgets.AdminSplitDateTime
        
        # Call original method with our overrides
        return original_formfield(self, db_field, request, **kwargs)
    
    # Replace the method
    admin.ModelAdmin.formfield_for_dbfield = patched_formfield_for_dbfield
    
    # Also patch the Media property to ensure JS is loaded
    original_media_property = admin.ModelAdmin.media.fget
    
    def patched_media(self):
        """Ensure DateTimeShortcuts.js is always included"""
        from django.forms import Media
        
        # Get original media
        media = original_media_property(self) if original_media_property else Media()
        
        # Add our required JS
        extra_js = ['admin/js/admin/DateTimeShortcuts.js', 'admin/js/calendar.js']
        
        # Merge with existing
        if hasattr(media, '_js'):
            existing_js = list(media._js)
            for js in extra_js:
                if js not in existing_js:
                    existing_js.append(js)
            media._js = existing_js
        else:
            media = Media(js=extra_js)
        
        return media
    
    # Replace the media property
    admin.ModelAdmin.media = property(patched_media)
    
    print("Applied emergency patch for date fields in admin forms")

# Apply the patch
patch_all_admin_forms()