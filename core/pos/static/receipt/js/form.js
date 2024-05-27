var fv;

document.addEventListener('DOMContentLoaded', function (e) {
    fv = FormValidation.formValidation(document.getElementById('frmForm'), {
            locale: 'es_ES',
            localization: FormValidation.locales.es_ES,
            plugins: {
                trigger: new FormValidation.plugins.Trigger(),
                submitButton: new FormValidation.plugins.SubmitButton(),
                bootstrap: new FormValidation.plugins.Bootstrap(),
                icon: new FormValidation.plugins.Icon({
                    valid: 'fa fa-check',
                    invalid: 'fa fa-times',
                    validating: 'fa fa-refresh',
                }),
            },
            fields: {
                name: {
                    validators: {
                        notEmpty: {},
                        stringLength: {
                            min: 2,
                        },
                    }
                },
                code: {
                    validators: {
                        notEmpty: {},
                        stringLength: {
                            min: 2,
                        },
                        remote: {
                            url: pathname,
                            data: function () {
                                return {
                                    parameter: fv.form.querySelector('[name="code"]').value,
                                    pattern: 'code',
                                    action: 'validate_data'
                                };
                            },
                            message: 'El código ya se encuentra registrado',
                            method: 'POST',
                            headers: {
                                'X-CSRFToken': csrftoken
                            },
                        }
                    }
                },
                start_number: {
                    validators: {
                        notEmpty: {},
                        digits: {},
                    }
                },
                end_number: {
                    validators: {
                        notEmpty: {},
                        digits: {},
                    }
                },
                current_number: {
                    validators: {
                        notEmpty: {},
                        digits: {},
                    }
                },
            },
        }
    )
        .on('core.element.validated', function (e) {
            if (e.valid) {
                const groupEle = FormValidation.utils.closest(e.element, '.form-group');
                if (groupEle) {
                    FormValidation.utils.classSet(groupEle, {
                        'has-success': false,
                    });
                }
                FormValidation.utils.classSet(e.element, {
                    'is-valid': false,
                });
            }
            const iconPlugin = fv.getPlugin('icon');
            const iconElement = iconPlugin && iconPlugin.icons.has(e.element) ? iconPlugin.icons.get(e.element) : null;
            iconElement && (iconElement.style.display = 'none');
        })
        .on('core.validator.validated', function (e) {
            if (!e.result.valid) {
                const messages = [].slice.call(fv.form.querySelectorAll('[data-field="' + e.field + '"][data-validator]'));
                messages.forEach((messageEle) => {
                    const validator = messageEle.getAttribute('data-validator');
                    messageEle.style.display = validator === e.validator ? 'block' : 'none';
                });
            }
        })
        .on('core.form.valid', function () {
            var args = {
                'params': new FormData(fv.form),
                'form': fv.form
            };
            submit_with_formdata(args);
        });
});

$(function () {
    $('input[name="start_number"]')
        .TouchSpin({
            min: 0,
            max: 999999999,
            step: 1
        })
        .on('change touchspin.on.min touchspin.on.max', function () {
            fv.revalidateField('start_number');
        })
        .on('keypress', function (e) {
            return validate_text_box({'event': e, 'type': 'numbers'});
        });

    $('input[name="end_number"]')
        .TouchSpin({
            min: 1,
            max: 999999999,
            step: 1
        })
        .on('change touchspin.on.min touchspin.on.max', function () {
            $('input[name="current_number"]').trigger("touchspin.updatesettings", {max: parseInt($(this).val())});
            fv.revalidateField('end_number');
        })
        .on('keypress', function (e) {
            return validate_text_box({'event': e, 'type': 'numbers'});
        });

    $('input[name="current_number"]')
        .TouchSpin({
            min: 0,
            max: 999999999,
            step: 1
        })
        .on('change touchspin.on.min touchspin.on.max', function () {
            fv.revalidateField('current_number');
        })
        .on('keypress', function (e) {
            return validate_text_box({'event': e, 'type': 'numbers'});
        });

    $('i[data-field="start_number"]').hide();
    $('i[data-field="end_number"]').hide();
    $('i[data-field="current_number"]').hide();
});
