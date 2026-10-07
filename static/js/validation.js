/**
 * AcxiomCRM — Client-side Form Validation Helper (Phase 4)
 * Provides progressive enhancement and instant feedback on inputs.
 * Server-side validation remains authoritative for all security and business rules.
 */

document.addEventListener("DOMContentLoaded", function () {
    // Enable Bootstrap custom validation styles on forms with 'needs-validation' class
    const forms = document.querySelectorAll(".needs-validation");

    Array.from(forms).forEach(function (form) {
        form.addEventListener("submit", function (event) {
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
            }
            form.classList.add("was-validated");
        }, false);
    });
});
