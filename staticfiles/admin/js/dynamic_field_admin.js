/**
 * Dynamic Field Admin JavaScript
 * Provides enhanced functionality for the dynamic field management interface
 */

(function($) {
    'use strict';
    
    $(document).ready(function() {
        initializeFieldTypeHandlers();
        initializeSectionManagement();
        initializeFieldReordering();
    });
    
    function initializeFieldTypeHandlers() {
        // Handle field type changes to show/hide relevant options
        $(document).on('change', 'select[id$="-field_type"]', function() {
            var fieldType = $(this).val();
            var row = $(this).closest('tr, .form-row');
            
            // Hide all constraint fields first
            row.find('.field-max_length, .field-max_digits, .field-decimal_places').hide();
            row.find('.field-choices, .field-related_model').hide();
            
            // Show relevant fields based on type
            switch(fieldType) {
                case 'char':
                case 'email':
                case 'url':
                case 'slug':
                case 'choice':
                    row.find('.field-max_length').show();
                    break;
                
                case 'decimal':
                    row.find('.field-max_digits, .field-decimal_places').show();
                    break;
                
                case 'choice':
                case 'multiple_choice':
                    row.find('.field-choices').show();
                    break;
                
                case 'foreign_key':
                case 'many_to_many':
                    row.find('.field-related_model').show();
                    break;
            }
        });
        
        // Trigger on page load for existing fields
        $('select[id$="-field_type"]').trigger('change');
    }
    
    function initializeSectionManagement() {
        // Add section grouping visual indicators
        var sections = {};
        
        $('.inline-related').each(function() {
            var sectionInput = $(this).find('input[id$="-section"]');
            var sectionName = sectionInput.val() || 'General';
            
            if (!sections[sectionName]) {
                sections[sectionName] = [];
            }
            sections[sectionName].push($(this));
        });
        
        // Add section headers
        Object.keys(sections).forEach(function(sectionName) {
            if (sections[sectionName].length > 0) {
                var header = $('<h3 class="section-header">' + sectionName + '</h3>');
                sections[sectionName][0].before(header);
            }
        });
    }
    
    function initializeFieldReordering() {
        // Make field rows sortable within sections
        $('.inline-group').sortable({
            items: '.inline-related',
            handle: '.drag-handle',
            axis: 'y',
            update: function(event, ui) {
                updateFieldOrder();
            }
        });
        
        // Add drag handles
        $('.inline-related').each(function() {
            $(this).prepend('<div class="drag-handle">⋮⋮</div>');
        });
    }
    
    function updateFieldOrder() {
        // Update order fields based on current position
        $('.inline-related').each(function(index) {
            $(this).find('input[id$="-order"]').val(index * 10);
        });
    }
    
    // Helper functions for field validation
    window.validateDynamicField = function(fieldRow) {
        var fieldType = fieldRow.find('select[id$="-field_type"]').val();
        var fieldName = fieldRow.find('input[id$="-name"]').val();
        var isValid = true;
        var errors = [];
        
        // Validate field name
        if (!/^[a-z][a-z0-9_]*$/.test(fieldName)) {
            errors.push('Field name must be lowercase and contain only letters, numbers, and underscores');
            isValid = false;
        }
        
        // Validate field type specific requirements
        switch(fieldType) {
            case 'char':
            case 'email':
            case 'url':
            case 'slug':
                var maxLength = fieldRow.find('input[id$="-max_length"]').val();
                if (!maxLength || maxLength <= 0) {
                    errors.push(fieldType + ' fields require a positive max_length');
                    isValid = false;
                }
                break;
            
            case 'decimal':
                var maxDigits = fieldRow.find('input[id$="-max_digits"]').val();
                var decimalPlaces = fieldRow.find('input[id$="-decimal_places"]').val();
                
                if (!maxDigits || maxDigits <= 0) {
                    errors.push('Decimal fields require a positive max_digits');
                    isValid = false;
                }
                
                if (decimalPlaces === '' || decimalPlaces < 0) {
                    errors.push('Decimal fields require decimal_places >= 0');
                    isValid = false;
                }
                break;
            
            case 'choice':
            case 'multiple_choice':
                var choices = fieldRow.find('textarea[id$="-choices"]').val();
                if (!choices || choices.trim() === '{}') {
                    errors.push('Choice fields require choices to be defined');
                    isValid = false;
                } else {
                    try {
                        JSON.parse(choices);
                    } catch (e) {
                        errors.push('Choices must be valid JSON');
                        isValid = false;
                    }
                }
                break;
            
            case 'foreign_key':
            case 'many_to_many':
                var relatedModel = fieldRow.find('input[id$="-related_model"]').val();
                if (!relatedModel || !relatedModel.includes('.')) {
                    errors.push('Related fields require a valid related_model (e.g., accounts.Account)');
                    isValid = false;
                }
                break;
        }
        
        // Display validation errors
        var errorContainer = fieldRow.find('.field-errors');
        if (!errorContainer.length) {
            errorContainer = $('<div class="field-errors"></div>');
            fieldRow.append(errorContainer);
        }
        
        if (isValid) {
            errorContainer.hide().empty();
            fieldRow.removeClass('has-errors');
        } else {
            errorContainer.html(errors.map(function(error) {
                return '<div class="error">' + error + '</div>';
            }).join('')).show();
            fieldRow.addClass('has-errors');
        }
        
        return isValid;
    };
    
})(jQuery || django.jQuery);