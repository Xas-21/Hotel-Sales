/**
 * Form Composer JavaScript
 * 
 * Handles drag-and-drop functionality, HTMX integration,
 * and interactive form building features.
 */

class FormComposer {
    constructor() {
        this.currentSelection = null;
        this.isDragging = false;
        this.dragData = {};
        this.csrfToken = this.getCSRFToken();
        
        this.init();
    }
    
    init() {
        console.log('Form Composer initializing...');
        this.setupDragAndDrop();
        this.setupEventListeners();
        this.setupHTMXEvents();
        console.log('Form Composer ready!');
    }
    
    /**
     * Get CSRF token from cookie or meta tag
     */
    getCSRFToken() {
        // Try cookie first
        const cookies = document.cookie.split(';');
        for (let cookie of cookies) {
            const [name, value] = cookie.trim().split('=');
            if (name === 'csrftoken') {
                return value;
            }
        }
        
        // Try meta tag
        const metaToken = document.querySelector('meta[name="csrf-token"]');
        if (metaToken) {
            return metaToken.getAttribute('content');
        }
        
        // Try hidden input
        const hiddenToken = document.querySelector('[name=csrfmiddlewaretoken]');
        if (hiddenToken) {
            return hiddenToken.value;
        }
        
        console.error('CSRF token not found');
        return '';
    }
    
    /**
     * Setup drag and drop functionality
     */
    setupDragAndDrop() {
        // Make sections sortable
        const sectionsContainer = document.getElementById('formSections');
        if (sectionsContainer) {
            new Sortable(sectionsContainer, {
                handle: '.section-header',
                animation: 150,
                ghostClass: 'sortable-ghost',
                chosenClass: 'sortable-chosen',
                onStart: (evt) => {
                    this.isDragging = true;
                    evt.item.style.transform = 'rotate(2deg)';
                },
                onEnd: (evt) => {
                    this.isDragging = false;
                    evt.item.style.transform = '';
                    this.updateSectionOrder();
                }
            });
        }
        
        // Make field lists sortable within sections
        document.querySelectorAll('.field-list').forEach(fieldList => {
            new Sortable(fieldList, {
                group: 'fields',
                animation: 150,
                ghostClass: 'sortable-ghost',
                chosenClass: 'sortable-chosen',
                onStart: (evt) => {
                    this.isDragging = true;
                    evt.item.style.transform = 'rotate(1deg)';
                },
                onEnd: (evt) => {
                    this.isDragging = false;
                    evt.item.style.transform = '';
                    
                    const fromSectionId = evt.from.dataset.sectionId;
                    const toSectionId = evt.to.dataset.sectionId;
                    const fieldId = evt.item.dataset.fieldId;
                    
                    if (fromSectionId !== toSectionId) {
                        // Cross-section move
                        this.moveFieldToSection(fieldId, toSectionId, evt.newIndex);
                    } else {
                        // Same section reorder
                        this.updateFieldOrder(toSectionId);
                    }
                }
            });
        });
        
        // Setup palette field dragging
        this.setupPaletteDragging();
    }
    
    /**
     * Setup drag and drop from field palette
     */
    setupPaletteDragging() {
        document.querySelectorAll('.palette-field').forEach(paletteField => {
            paletteField.addEventListener('dragstart', (e) => {
                this.dragData = {
                    fieldKey: paletteField.dataset.fieldKey || this.generateFieldKey(),
                    fieldType: paletteField.dataset.fieldType,
                    fieldLabel: paletteField.dataset.fieldLabel || paletteField.querySelector('span:last-child').textContent,
                    isDynamic: paletteField.dataset.isDynamic === 'true'
                };
                
                paletteField.classList.add('dragging');
                e.dataTransfer.effectAllowed = 'copy';
                e.dataTransfer.setData('text/plain', JSON.stringify(this.dragData));
            });
            
            paletteField.addEventListener('dragend', () => {
                paletteField.classList.remove('dragging');
            });
        });
        
        // Setup drop zones
        document.querySelectorAll('.field-list').forEach(fieldList => {
            fieldList.addEventListener('dragover', (e) => {
                e.preventDefault();
                e.dataTransfer.dropEffect = 'copy';
                fieldList.classList.add('drag-over');
            });
            
            fieldList.addEventListener('dragleave', (e) => {
                if (!fieldList.contains(e.relatedTarget)) {
                    fieldList.classList.remove('drag-over');
                }
            });
            
            fieldList.addEventListener('drop', (e) => {
                e.preventDefault();
                fieldList.classList.remove('drag-over');
                
                try {
                    const data = JSON.parse(e.dataTransfer.getData('text/plain'));
                    this.addFieldToSection(fieldList.dataset.sectionId, data);
                } catch (error) {
                    console.error('Error parsing drop data:', error);
                }
            });
        });
    }
    
    /**
     * Setup general event listeners
     */
    setupEventListeners() {
        // Click handlers for selection
        document.addEventListener('click', (e) => {
            if (e.target.closest('.form-section') && !this.isDragging) {
                const section = e.target.closest('.form-section');
                this.selectSection(section.dataset.sectionId);
            } else if (e.target.closest('.field-item') && !this.isDragging) {
                const field = e.target.closest('.field-item');
                this.selectField(field.dataset.fieldId);
            } else if (!e.target.closest('.composer-properties')) {
                this.clearSelection();
            }
        });
        
        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey || e.metaKey) {
                switch (e.key) {
                    case 's':
                        e.preventDefault();
                        this.saveFormConfiguration();
                        break;
                    case 'z':
                        e.preventDefault();
                        this.undo();
                        break;
                    case 'y':
                        e.preventDefault();
                        this.redo();
                        break;
                }
            } else if (e.key === 'Delete' && this.currentSelection) {
                this.deleteSelectedItem();
            }
        });
        
        // Auto-save on property changes
        document.addEventListener('input', (e) => {
            if (e.target.closest('.composer-properties')) {
                clearTimeout(this.autoSaveTimeout);
                this.autoSaveTimeout = setTimeout(() => {
                    this.savePropertyChanges();
                }, 1000);
            }
        });
    }
    
    /**
     * Setup HTMX event handlers
     */
    setupHTMXEvents() {
        document.addEventListener('htmx:afterRequest', (event) => {
            if (event.detail.successful) {
                this.refreshDragAndDrop();
                this.showMessage('Changes saved successfully', 'success');
            } else {
                this.showMessage('Error saving changes', 'error');
            }
        });
        
        document.addEventListener('htmx:beforeRequest', (event) => {
            this.showLoading(true);
        });
        
        document.addEventListener('htmx:afterSettle', (event) => {
            this.showLoading(false);
        });
    }
    
    /**
     * Section Management
     */
    selectSection(sectionId) {
        this.clearSelection();
        const section = document.querySelector(`[data-section-id="${sectionId}"]`);
        if (section) {
            section.classList.add('selected');
            this.currentSelection = { type: 'section', id: sectionId };
            this.loadSectionProperties(sectionId);
        }
    }
    
    selectField(fieldId) {
        this.clearSelection();
        const field = document.querySelector(`[data-field-id="${fieldId}"]`);
        if (field) {
            field.classList.add('selected');
            this.currentSelection = { type: 'field', id: fieldId };
            this.loadFieldProperties(fieldId);
        }
    }
    
    clearSelection() {
        document.querySelectorAll('.selected').forEach(el => {
            el.classList.remove('selected');
        });
        this.currentSelection = null;
        this.showDefaultProperties();
    }
    
    /**
     * Add field to section via HTMX
     */
    addFieldToSection(sectionId, fieldData) {
        const formData = new FormData();
        formData.append('csrfmiddlewaretoken', this.csrfToken);
        formData.append('field_key', fieldData.fieldKey);
        formData.append('field_type', fieldData.fieldType);
        formData.append('label', fieldData.fieldLabel);
        formData.append('is_dynamic', fieldData.isDynamic);
        
        fetch(`/form-composer/section/${sectionId}/add-field/`, {
            method: 'POST',
            body: formData,
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                this.refreshFieldList(sectionId);
                this.showMessage('Field added successfully', 'success');
            } else {
                this.showMessage('Error adding field: ' + data.error, 'error');
            }
        })
        .catch(error => {
            console.error('Error adding field:', error);
            this.showMessage('Network error occurred', 'error');
        });
    }
    
    /**
     * Update section order after drag and drop
     */
    updateSectionOrder() {
        const sections = document.querySelectorAll('#formSections .form-section');
        const orderData = Array.from(sections).map((section, index) => ({
            id: section.dataset.sectionId,
            order: index + 1
        }));
        
        fetch('/form-composer/update-section-order/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.csrfToken,
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify({ sections: orderData })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                console.log('Section order updated');
            } else {
                console.error('Failed to update section order:', data.error);
            }
        })
        .catch(error => {
            console.error('Network error updating section order:', error);
        });
    }
    
    /**
     * Move field to different section
     */
    moveFieldToSection(fieldId, targetSectionId, newOrder) {
        fetch(`/form-composer/section/${targetSectionId}/move-field/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.csrfToken,
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify({ 
                field_id: fieldId, 
                order: newOrder + 1
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                console.log('Field moved to new section');
            } else {
                console.error('Failed to move field:', data.error);
                this.showMessage('Error moving field', 'error');
            }
        })
        .catch(error => {
            console.error('Network error moving field:', error);
            this.showMessage('Network error occurred', 'error');
        });
    }
    
    /**
     * Update field order after drag and drop
     */
    updateFieldOrder(sectionId) {
        const fields = document.querySelectorAll(`[data-section-id="${sectionId}"] .field-item`);
        const orderData = Array.from(fields).map((field, index) => ({
            id: field.dataset.fieldId,
            order: index + 1
        }));
        
        fetch(`/form-composer/section/${sectionId}/update-field-order/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.csrfToken,
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify({ fields: orderData })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                console.log('Field order updated');
            } else {
                console.error('Failed to update field order:', data.error);
            }
        })
        .catch(error => {
            console.error('Network error updating field order:', error);
        });
    }
    
    /**
     * Property Panel Management
     */
    loadSectionProperties(sectionId) {
        fetch(`/form-composer/section/${sectionId}/properties/`)
        .then(response => response.text())
        .then(html => {
            document.getElementById('propertiesPanel').innerHTML = html;
        })
        .catch(error => {
            console.error('Error loading section properties:', error);
        });
    }
    
    loadFieldProperties(fieldId) {
        fetch(`/form-composer/field/${fieldId}/properties/`)
        .then(response => response.text())
        .then(html => {
            document.getElementById('propertiesPanel').innerHTML = html;
        })
        .catch(error => {
            console.error('Error loading field properties:', error);
        });
    }
    
    showDefaultProperties() {
        document.getElementById('propertiesPanel').innerHTML = `
            <div class="text-center text-muted py-4">
                <i class="bi bi-gear"></i>
                <h6 class="mt-2">Properties</h6>
                <p class="small">Select a section or field to edit its properties.</p>
            </div>
        `;
    }
    
    /**
     * Utility functions
     */
    generateFieldKey() {
        return 'custom_field_' + Date.now();
    }
    
    refreshDragAndDrop() {
        // Reinitialize sortable on new elements
        setTimeout(() => {
            this.setupDragAndDrop();
        }, 100);
    }
    
    refreshFieldList(sectionId) {
        fetch(`/form-composer/section/${sectionId}/fields/`)
        .then(response => response.text())
        .then(html => {
            const fieldList = document.querySelector(`[data-section-id="${sectionId}"] .field-list`);
            fieldList.innerHTML = html;
            this.refreshDragAndDrop();
        });
    }
    
    showMessage(message, type = 'info') {
        // Create toast notification
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.innerHTML = `
            <div class="toast-body">
                <i class="bi bi-${type === 'success' ? 'check-circle' : 'exclamation-triangle'}"></i>
                ${message}
            </div>
        `;
        
        document.body.appendChild(toast);
        
        setTimeout(() => {
            toast.classList.add('show');
        }, 100);
        
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }
    
    showLoading(show) {
        const spinner = document.querySelector('.loading-spinner');
        if (show) {
            if (!spinner) {
                const loader = document.createElement('div');
                loader.className = 'loading-spinner';
                document.body.appendChild(loader);
            }
        } else if (spinner) {
            spinner.remove();
        }
    }
    
    saveFormConfiguration() {
        fetch('/form-composer/save-configuration/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': this.csrfToken,
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                this.showMessage('Configuration saved successfully', 'success');
            } else {
                this.showMessage('Error saving configuration', 'error');
            }
        })
        .catch(error => {
            console.error('Error saving configuration:', error);
            this.showMessage('Network error occurred', 'error');
        });
    }
    
    savePropertyChanges() {
        if (!this.currentSelection) return;
        
        const form = document.querySelector('.composer-properties form');
        if (!form) return;
        
        const formData = new FormData(form);
        const url = this.currentSelection.type === 'section' 
            ? `/form-composer/section/${this.currentSelection.id}/update/`
            : `/form-composer/field/${this.currentSelection.id}/update/`;
        
        fetch(url, {
            method: 'POST',
            body: formData,
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                console.log('Properties updated');
            } else {
                console.error('Failed to update properties:', data.error);
            }
        })
        .catch(error => {
            console.error('Network error updating properties:', error);
        });
    }
}

// Global functions for template event handlers
window.toggleSection = function(sectionId) {
    const section = document.querySelector(`[data-section-id="${sectionId}"]`);
    const body = section.querySelector('.section-body');
    const indicator = section.querySelector('.collapse-indicator');
    
    if (body.classList.contains('d-none')) {
        body.classList.remove('d-none');
        indicator.className = 'bi bi-chevron-up collapse-indicator';
    } else {
        body.classList.add('d-none');
        indicator.className = 'bi bi-chevron-down collapse-indicator';
    }
    
    // Update server
    fetch(`/form-composer/section/${sectionId}/toggle/`, {
        method: 'POST',
        headers: {
            'X-CSRFToken': formComposer.csrfToken,
            'X-Requested-With': 'XMLHttpRequest'
        }
    });
};

window.editSection = function(sectionId) {
    formComposer.selectSection(sectionId);
};

window.deleteSection = function(sectionId) {
    if (confirm('Are you sure you want to delete this section and all its fields?')) {
        fetch(`/form-composer/section/${sectionId}/delete/`, {
            method: 'DELETE',
            headers: {
                'X-CSRFToken': formComposer.csrfToken,
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                document.querySelector(`[data-section-id="${sectionId}"]`).remove();
                formComposer.showMessage('Section deleted', 'success');
            }
        });
    }
};

window.editField = function(fieldId) {
    formComposer.selectField(fieldId);
};

window.deleteField = function(fieldId) {
    if (confirm('Are you sure you want to delete this field?')) {
        fetch(`/form-composer/field/${fieldId}/delete/`, {
            method: 'DELETE',
            headers: {
                'X-CSRFToken': formComposer.csrfToken,
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                document.querySelector(`[data-field-id="${fieldId}"]`).remove();
                formComposer.showMessage('Field deleted', 'success');
            }
        });
    }
};

window.addField = function(sectionId) {
    // Show field selection dialog or add default field
    const fieldData = {
        fieldKey: 'new_field_' + Date.now(),
        fieldType: 'text',
        fieldLabel: 'New Field',
        isDynamic: true
    };
    
    formComposer.addFieldToSection(sectionId, fieldData);
};

window.previewForm = function() {
    window.open('/form-composer/preview/', '_blank');
};

window.saveFormConfiguration = function() {
    formComposer.saveFormConfiguration();
};

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    window.formComposer = new FormComposer();
});

// Add toast styles
const toastStyles = `
    .toast {
        position: fixed;
        top: 20px;
        right: 20px;
        background: white;
        border: 1px solid #dee2e6;
        border-radius: 4px;
        padding: 12px 16px;
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        z-index: 1050;
        opacity: 0;
        transform: translateX(100%);
        transition: all 0.3s ease;
    }
    
    .toast.show {
        opacity: 1;
        transform: translateX(0);
    }
    
    .toast.toast-success {
        border-left: 4px solid #28a745;
    }
    
    .toast.toast-error {
        border-left: 4px solid #dc3545;
    }
    
    .toast.toast-info {
        border-left: 4px solid #17a2b8;
    }
    
    .toast-body {
        display: flex;
        align-items: center;
        gap: 8px;
    }
`;

// Inject toast styles
const styleSheet = document.createElement('style');
styleSheet.textContent = toastStyles;
document.head.appendChild(styleSheet);