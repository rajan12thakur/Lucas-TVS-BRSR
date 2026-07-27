/**
 * BRSR Dynamic Validation System
 * Production-ready client-side validation for JSON-driven forms.
 * All validators are driven by field_type from JSON schema.
 */

(function() {
    'use strict';

    // ============================================================
    // 1. VALIDATOR DEFINITIONS
    // ============================================================

    /**
     * Each validator is an object with:
     *   - test: function(value) => boolean (true = valid)
     *   - message: string or function(fieldName) => string (only used when field is required)
     *   - format: optional function(value) => formatted string
     *   - pattern: optional regex for HTML5 pattern attribute
     *   - inputmode: optional string for HTML5 inputmode
     *   - maxlength: optional number
     */
    const VALIDATORS = {

        alphabetic: {
            test: (v) => /^[A-Za-z\s]+$/.test(v),
            message: (name) => `${name} must contain only letters and spaces.`,
            pattern: '^[A-Za-z\\s]+$',
            inputmode: 'text',
            maxlength: 100,
        },

        alphanumeric: {
            test: (v) => /^[A-Za-z0-9\s]+$/.test(v),
            message: (name) => `${name} must contain only letters, numbers, and spaces.`,
            pattern: '^[A-Za-z0-9\\s]+$',
            inputmode: 'text',
            maxlength: 100,
        },

        phone: {
            test: (v) => /^[0-9]{10,15}$/.test(v),
            message: (name) => `${name} must be a valid 10-15 digit phone number.`,
            pattern: '[0-9]{10,15}',
            inputmode: 'tel',
            maxlength: 15,
            format: (v) => v.replace(/[^0-9]/g, ''),
        },

        telephone: {
            test: (v) => /^[0-9+\-()\s]{8,20}$/.test(v),
            message: (name) => `${name} must be a valid telephone number (8-20 digits, +, -, (), space).`,
            inputmode: 'tel',
            maxlength: 20,
            format: (v) => v.replace(/[^0-9+\-()\s]/g, ''),
        },

        email: {
            test: (v) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v),
            message: (name) => `${name} must be a valid email address (e.g., name@domain.com).`,
            inputmode: 'email',
            maxlength: 254,
        },

        url: {
            test: (v) => {
                try {
                    const url = new URL(v);
                    return url.protocol === 'http:' || url.protocol === 'https:';
                } catch { return false; }
            },
            message: (name) => `${name} must be a valid URL (e.g., https://example.com).`,
            inputmode: 'url',
            maxlength: 2048,
        },

        number: {
            test: (v) => /^-?\d+$/.test(v.trim()),
            message: (name) => `${name} must be a valid whole number.`,
            inputmode: 'numeric',
        },

        decimal: {
            test: (v) => /^-?\d+(\.\d+)?$/.test(v.trim()),
            message: (name) => `${name} must be a valid decimal number.`,
            inputmode: 'decimal',
        },

        percentage: {
            test: (v) => /^-?\d+(\.\d+)?$/.test(v.trim()),
            message: (name) => `${name} must be a valid percentage (number only).`,
            inputmode: 'decimal',
            maxlength: 10,
        },

        year: {
            test: (v) => /^[0-9]{4}$/.test(v),
            message: (name) => `${name} must be a valid 4-digit year (e.g., 2024).`,
            pattern: '[0-9]{4}',
            inputmode: 'numeric',
            maxlength: 4,
            format: (v) => v.replace(/[^0-9]/g, '').slice(0, 4),
        },

        financial_year: {
            test: (v) => /^[0-9]{4}-[0-9]{4}$/.test(v),
            message: (name) => `${name} must be in format YYYY-YYYY (e.g., 2024-2025).`,
            maxlength: 9,
        },

        cin: {
            test: (v) => /^[A-Z0-9]{21}$/.test(v),
            message: (name) => `${name} must be a valid 21-character Corporate Identification Number.`,
            maxlength: 21,
            format: (v) => v.toUpperCase().replace(/[^A-Z0-9]/g, ''),
        },

        pan: {
            test: (v) => /^[A-Z]{5}[0-9]{4}[A-Z]{1}$/.test(v),
            message: (name) => `${name} must be a valid 10-character PAN (e.g., ABCDE1234F).`,
            maxlength: 10,
            format: (v) => v.toUpperCase().replace(/[^A-Z0-9]/g, ''),
        },

        gst: {
            test: (v) => /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}[Z]{1}[0-9A-Z]{1}$/.test(v),
            message: (name) => `${name} must be a valid 15-character GSTIN.`,
            maxlength: 15,
            format: (v) => v.toUpperCase().replace(/[^A-Z0-9]/g, ''),
        },

        aadhaar: {
            test: (v) => /^[0-9]{12}$/.test(v),
            message: (name) => `${name} must be a valid 12-digit Aadhaar number.`,
            pattern: '[0-9]{12}',
            inputmode: 'numeric',
            maxlength: 12,
            format: (v) => v.replace(/[^0-9]/g, '').slice(0, 12),
        },

        pin_code: {
            test: (v) => /^[0-9]{6}$/.test(v),
            message: (name) => `${name} must be a valid 6-digit PIN code.`,
            pattern: '[0-9]{6}',
            inputmode: 'numeric',
            maxlength: 6,
            format: (v) => v.replace(/[^0-9]/g, '').slice(0, 6),
        },

        ifsc: {
            test: (v) => /^[A-Z]{4}0[A-Z0-9]{6}$/.test(v),
            message: (name) => `${name} must be a valid 11-character IFSC code (e.g., SBIN0001234).`,
            maxlength: 11,
            format: (v) => v.toUpperCase().replace(/[^A-Z0-9]/g, ''),
        },

        account_number: {
            test: (v) => /^[0-9]{9,18}$/.test(v),
            message: (name) => `${name} must be a valid account number (9-18 digits).`,
            inputmode: 'numeric',
            maxlength: 18,
            format: (v) => v.replace(/[^0-9]/g, ''),
        },

        number_with_unit: {
            test: (v) => /^\d+(\.\d+)?\s*(cr|crore|lakh|thousand|k|m)?$/i.test(v.trim()),
            message: (name) => `${name} must be a valid number with optional unit (cr, lakh, thousand, k, m).`,
            inputmode: 'text',
            maxlength: 50,
        },

        text: {
            test: (v) => true, // Always valid for text, only check required separately
            message: (name) => `${name} is required.`,
        },

        textarea: {
            test: (v) => true, // Always valid for textarea, only check required separately
            message: (name) => `${name} is required.`,
        },

    };

    // ============================================================
    // 2. CORE VALIDATION FUNCTIONS
    // ============================================================

    /**
     * Get validator for a field type
     */
    function getValidator(fieldType) {
        return VALIDATORS[fieldType] || null;
    }

    /**
     * Validate a single field
     * Returns { valid: boolean, message: string }
     */
    function validateField(element) {
        const fieldType = element.dataset.validation || 'text';
        const isRequired = element.dataset.required === 'true';
        const fieldName = element.dataset.fieldName || 'Field';
        const value = element.value || '';

        // For radio buttons, get the group value
        let actualValue = value;
        if (element.type === 'radio') {
            const groupName = element.name;
            const checked = document.querySelector(`input[name="${groupName}"]:checked`);
            actualValue = checked ? checked.value : '';
        } else if (element.type === 'checkbox' && element.closest('.choice-stack')) {
            // Checkbox group: collect all checked values
            const groupName = element.dataset.fieldName;
            const checkedBoxes = document.querySelectorAll(`input[type="checkbox"][data-field-name="${groupName}"]:checked`);
            actualValue = Array.from(checkedBoxes).map(el => el.value).join(',');
        }

        const validator = getValidator(fieldType);

        // If not required and empty, skip validation (no error)
        if (!isRequired && (actualValue === '' || actualValue === null || actualValue === undefined)) {
            return { valid: true, message: '' };
        }

        // If required and empty, show required message
        if (isRequired && (actualValue === '' || actualValue === null || actualValue === undefined)) {
            return { valid: false, message: `${fieldName} is required.` };
        }

        // Apply validator if available
        if (validator && typeof validator.test === 'function') {
            const valid = validator.test(actualValue);
            const message = valid ? '' : (typeof validator.message === 'function' ? validator.message(fieldName) : validator.message);
            return { valid, message };
        }

        // No validator found, assume valid
        return { valid: true, message: '' };
    }

    /**
     * Show validation state on an element
     * Only show errors if the field has been blurred (touched) or during form submission
     */
    function showValidation(element, valid, message, forceShow = false) {
        const formGroup = element.closest('.form-group');
        if (!formGroup) return;

        const feedback = formGroup.querySelector('.invalid-feedback');
        const input = formGroup.querySelector('input, textarea, select');
        
        // Check if field has been blurred (touched)
        const isBlurred = element.dataset.blurred === 'true';
        
        // Only show error if:
        // 1. forceShow is true (form submission), OR
        // 2. Field has been blurred AND (it's invalid OR it's valid with content)
        const shouldShow = forceShow || isBlurred;

        if (!shouldShow) {
            // Field hasn't been blurred yet - keep clean state
            formGroup.classList.remove('has-error');
            if (input) {
                input.classList.remove('is-invalid');
                input.classList.remove('is-valid');
            }
            if (feedback) {
                feedback.textContent = '';
                feedback.style.display = 'none';
            }
            return;
        }

        // Field has been blurred - show validation state
        if (!valid && message) {
            formGroup.classList.add('has-error');
            if (input) {
                input.classList.add('is-invalid');
                input.classList.remove('is-valid');
            }
            if (feedback) {
                feedback.textContent = message;
                feedback.style.display = 'block';
            }
        } else {
            formGroup.classList.remove('has-error');
            if (input) {
                input.classList.remove('is-invalid');
                // Only show is-valid if field has content
                if (element.value && element.value.trim() !== '') {
                    input.classList.add('is-valid');
                } else {
                    input.classList.remove('is-valid');
                }
            }
            if (feedback) {
                feedback.textContent = '';
                feedback.style.display = 'none';
            }
        }
    }

    /**
     * Clear validation state on an element
     */
    function clearValidation(element) {
        const formGroup = element.closest('.form-group');
        if (!formGroup) return;

        const feedback = formGroup.querySelector('.invalid-feedback');
        const input = formGroup.querySelector('input, textarea, select');

        formGroup.classList.remove('has-error');
        if (input) {
            input.classList.remove('is-invalid');
            input.classList.remove('is-valid');
        }
        if (feedback) {
            feedback.textContent = '';
            feedback.style.display = 'none';
        }
        // Reset blurred state
        element.dataset.blurred = 'false';
    }

    /**
     * Mark field as blurred
     */
    function markBlurred(element) {
        element.dataset.blurred = 'true';
        
        // For radio groups, mark all radios in group as blurred
        if (element.type === 'radio') {
            const groupName = element.name;
            document.querySelectorAll(`input[name="${groupName}"]`).forEach(input => {
                input.dataset.blurred = 'true';
            });
        }
        
        // For checkbox groups, mark all checkboxes in group as blurred
        if (element.type === 'checkbox' && element.closest('.choice-stack')) {
            const groupName = element.dataset.fieldName;
            document.querySelectorAll(`input[type="checkbox"][data-field-name="${groupName}"]`).forEach(input => {
                input.dataset.blurred = 'true';
            });
        }
    }

    /**
     * Attach validation events to an element
     */
    function attachValidation(element) {
        if (!element) return;

        // Skip elements that already have validation attached
        if (element._validationAttached) return;
        element._validationAttached = true;

        // Initialize blurred state
        element.dataset.blurred = 'false';

        // On blur, mark as blurred and validate
        element.addEventListener('blur', function(e) {
            markBlurred(this);
            
            // For radios, validate the group
            if (this.type === 'radio') {
                const groupName = this.name;
                const groupInputs = document.querySelectorAll(`input[name="${groupName}"]`);
                groupInputs.forEach(input => {
                    if (input._validationAttached) {
                        const result = validateField(input);
                        showValidation(input, result.valid, result.message, false);
                    }
                });
                return;
            }

            // For checkboxes in groups
            if (this.type === 'checkbox' && this.closest('.choice-stack')) {
                const groupName = this.dataset.fieldName;
                const groupInputs = document.querySelectorAll(`input[type="checkbox"][data-field-name="${groupName}"]`);
                groupInputs.forEach(input => {
                    if (input._validationAttached) {
                        const result = validateField(input);
                        showValidation(input, result.valid, result.message, false);
                    }
                });
                return;
            }

            const result = validateField(this);
            showValidation(this, result.valid, result.message, false);
        });

        // On input, only validate if field has been blurred
        element.addEventListener('input', function(e) {
            // For radios and checkboxes, this is handled by their blur/change events
            if (this.type === 'radio' || (this.type === 'checkbox' && this.closest('.choice-stack'))) {
                return;
            }
            
            // Only validate if field has been blurred before
            if (this.dataset.blurred === 'true') {
                const result = validateField(this);
                showValidation(this, result.valid, result.message, false);
            }
        });

        // On change (for selects, checkboxes, radios)
        element.addEventListener('change', function(e) {
            // For radios and checkboxes, validate on change if already blurred
            if (this.type === 'radio' || this.type === 'checkbox') {
                if (this.dataset.blurred === 'true') {
                    markBlurred(this);
                    
                    if (this.type === 'radio') {
                        const groupName = this.name;
                        const groupInputs = document.querySelectorAll(`input[name="${groupName}"]`);
                        groupInputs.forEach(input => {
                            if (input._validationAttached) {
                                const result = validateField(input);
                                showValidation(input, result.valid, result.message, false);
                            }
                        });
                        return;
                    }
                    
                    if (this.type === 'checkbox' && this.closest('.choice-stack')) {
                        const groupName = this.dataset.fieldName;
                        const groupInputs = document.querySelectorAll(`input[type="checkbox"][data-field-name="${groupName}"]`);
                        groupInputs.forEach(input => {
                            if (input._validationAttached) {
                                const result = validateField(input);
                                showValidation(input, result.valid, result.message, false);
                            }
                        });
                        return;
                    }
                }
                return;
            }
            
            // Regular inputs
            if (this.dataset.blurred === 'true') {
                const result = validateField(this);
                showValidation(this, result.valid, result.message, false);
            }
        });

        // On paste, validate only if already blurred
        element.addEventListener('paste', function(e) {
            if (this.dataset.blurred === 'true') {
                // Use setTimeout to let the paste complete
                setTimeout(() => {
                    const result = validateField(this);
                    showValidation(this, result.valid, result.message, false);
                }, 10);
            }
        });

        // Restrict input based on field type (only for specific types)
        element.addEventListener('input', function(e) {
            const fieldType = this.dataset.validation || 'text';
            const validator = getValidator(fieldType);
            if (validator && typeof validator.format === 'function') {
                const cursorPos = this.selectionStart;
                const oldValue = this.value;
                const newValue = validator.format(this.value);
                if (newValue !== oldValue) {
                    this.value = newValue;
                    const newCursorPos = Math.min(cursorPos, newValue.length);
                    this.setSelectionRange(newCursorPos, newCursorPos);
                }
            }
        });
    }

    /**
     * Perform validation on an element with force show
     */
    function performValidation(element, forceShow = false) {
        const result = validateField(element);
        showValidation(element, result.valid, result.message, forceShow);
        return result.valid;
    }

    // ============================================================
    // 3. FORM VALIDATION
    // ============================================================

    /**
     * Validate entire form
     * Returns true if all fields are valid
     */
    function validateForm() {
        const inputs = document.querySelectorAll('[data-validation]');
        let allValid = true;

        // Process all visible input groups
        const groups = new Set();
        inputs.forEach(input => {
            // For radios, validate the group once
            if (input.type === 'radio') {
                const groupName = input.name;
                if (groups.has(groupName)) return;
                groups.add(groupName);
                const groupInputs = document.querySelectorAll(`input[name="${groupName}"]`);
                const firstInput = groupInputs[0];
                if (firstInput && firstInput.closest('.form-group')) {
                    // Mark all as blurred before validation
                    groupInputs.forEach(inp => inp.dataset.blurred = 'true');
                    const result = validateField(firstInput);
                    showValidation(firstInput, result.valid, result.message, true);
                    if (!result.valid) allValid = false;
                }
                return;
            }

            // For checkbox groups
            if (input.type === 'checkbox' && input.closest('.choice-stack')) {
                const groupName = input.dataset.fieldName;
                const groupKey = `checkbox_${groupName}`;
                if (groups.has(groupKey)) return;
                groups.add(groupKey);
                const groupInputs = document.querySelectorAll(`input[type="checkbox"][data-field-name="${groupName}"]`);
                const firstInput = groupInputs[0];
                if (firstInput && firstInput.closest('.form-group')) {
                    // Mark all as blurred before validation
                    groupInputs.forEach(inp => inp.dataset.blurred = 'true');
                    const result = validateField(firstInput);
                    showValidation(firstInput, result.valid, result.message, true);
                    if (!result.valid) allValid = false;
                }
                return;
            }

            // Regular inputs - mark as blurred before validation
            input.dataset.blurred = 'true';
            const result = validateField(input);
            showValidation(input, result.valid, result.message, true);
            if (!result.valid) allValid = false;
        });

        return allValid;
    }

    // ============================================================
    // 4. AUTO-ATTACH ON DYNAMIC CONTENT
    // ============================================================

    /**
     * Attach validation to all elements in a container
     */
    function attachValidationToContainer(container) {
        if (!container) return;
        const inputs = container.querySelectorAll('[data-validation]');
        inputs.forEach(input => attachValidation(input));
    }

    // ============================================================
    // 5. PUBLIC API
    // ============================================================

    window.BRSRValidation = {
        // Core functions
        getValidator: getValidator,
        validateField: validateField,
        validateForm: validateForm,
        showValidation: showValidation,
        clearValidation: clearValidation,
        performValidation: performValidation,
        markBlurred: markBlurred,

        // Attachment
        attachValidation: attachValidation,
        attachValidationToContainer: attachValidationToContainer,

        // Validator registry
        validators: VALIDATORS,
    };

    // ============================================================
    // 6. DOM READY - AUTO-INIT
    // ============================================================

    // Auto-attach to existing inputs when DOM is ready
    document.addEventListener('DOMContentLoaded', function() {
        // Attach to all existing validation inputs
        const inputs = document.querySelectorAll('[data-validation]');
        inputs.forEach(input => attachValidation(input));

        // Watch for new content via MutationObserver
        const observer = new MutationObserver(function(mutations) {
            mutations.forEach(mutation => {
                mutation.addedNodes.forEach(node => {
                    if (node.nodeType === 1) { // Element node
                        // Check if node itself has data-validation
                        if (node.hasAttribute && node.hasAttribute('data-validation')) {
                            attachValidation(node);
                        }
                        // Check descendants
                        const descendants = node.querySelectorAll ? node.querySelectorAll('[data-validation]') : [];
                        descendants.forEach(el => attachValidation(el));
                    }
                });
            });
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true,
        });
    });

})();