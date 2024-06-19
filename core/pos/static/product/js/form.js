var fv;
var input_inventoried;
var tblPrices;

var product = {
    prices: [],
    listPrices: function () {
        tblPrices = $('#tblPrices').DataTable({
            autoWidth: false,
            destroy: true,
            data: this.prices,
            ordering: false,
            lengthChange: false,
            searching: false,
            paginate: false,
            info: false,
            columns: [
                {data: "quantity"},
                {data: "quantity"},
                {data: "net_price"},
            ],
            columnDefs: [
                {
                    targets: [0],
                    class: 'text-center',
                    render: function (data, type, row) {
                        return '<a rel="remove" class="btn btn-danger btn-flat btn-xs"><i class="fas fa-times"></i></a>';
                    }
                },
                {
                    targets: [-2],
                    class: 'text-center',
                    render: function (data, type, row) {
                        return '<input type="text" class="form-control" autocomplete="off" name="quantity" value="' + row.quantity + '">';
                    }
                },
                {
                    targets: [-1],
                    class: 'text-center',
                    render: function (data, type, row) {
                        return '<input type="text" class="form-control" autocomplete="off" name="net_price" value="' + row.net_price + '">';
                    }
                }
            ],
            rowCallback: function (row, data, index) {
                var tr = $(row).closest('tr');
                tr.find('input[name="quantity"]')
                    .TouchSpin({
                        min: 0,
                        max: 1000000,
                        step: 1
                    })
                    .on('keypress', function (e) {
                        return validate_text_box({'event': e, 'type': 'numbers'});
                    });

                tr.find('input[name="net_price"]')
                    .TouchSpin({
                        min: 0.00,
                        max: 1000000,
                        step: 0.01,
                        decimals: 2,
                        boostat: 5,
                        maxboostedstep: 1,
                    })
                    .on('keypress', function (e) {
                        return validate_text_box({'event': e, 'type': 'decimals'});
                    });
            },
            initComplete: function (settings, json) {
                $(this).wrap('<div class="dataTables_scroll"><div/>');
            }
        });
    }
};

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
                        remote: {
                            url: pathname,
                            data: function () {
                                return {
                                    pattern: 'name',
                                    name: fv.form.querySelector('[name="name"]').value,
                                    category: fv.form.querySelector('[name="category"]').value,
                                    action: 'validate_data'
                                };
                            },
                            message: 'El nomnre del producto ya se encuentra registrado',
                            method: 'POST',
                            headers: {
                                'X-CSRFToken': csrftoken
                            },
                        }
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
                                    pattern: 'code',
                                    code: fv.form.querySelector('[name="code"]').value,
                                    action: 'validate_data'
                                };
                            },
                            message: 'El código del producto ya se encuentra registrado',
                            method: 'POST',
                            headers: {
                                'X-CSRFToken': csrftoken
                            },
                        }
                    }
                },
                ref: {
                    validators: {
                        // notEmpty: {},
                        // stringLength: {
                        //     min: 2
                        // }
                    }
                },
                flag: {
                    validators: {
                        // notEmpty: {},
                        // stringLength: {
                        //     min: 2
                        // }
                    }
                },
                category: {
                    validators: {
                        notEmpty: {
                            message: 'Seleccione una categoría'
                        },
                    }
                },
                image: {
                    validators: {
                        file: {
                            extension: 'jpeg,jpg,png',
                            type: 'image/jpeg,image/png',
                            maxFiles: 1,
                            message: 'Introduce una imagen válida'
                        }
                    }
                },
                price: {
                    validators: {
                        notEmpty: {},
                        numeric: {
                            message: 'El valor no es un número',
                            thousandsSeparator: '',
                            decimalSeparator: '.'
                        }
                    }
                },
                pvp: {
                    validators: {
                        notEmpty: {},
                        numeric: {
                            message: 'El valor no es un número',
                            thousandsSeparator: '',
                            decimalSeparator: '.'
                        }
                    }
                },
                description: {
                    validators: {
                        // notEmpty: {},
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
            var params = new FormData(fv.form);
            params.append('price_list', JSON.stringify(tblPrices.rows().data().toArray()));
            var args = {
                'params': params,
                'form': fv.form
            };
            submit_with_formdata(args);
        });
});

$(function () {

    input_inventoried = $('input[name="inventoried"]');

    $('.select2').select2({
        theme: 'bootstrap4',
        language: "es"
    });

    $('select[name="category"]').on('change', function () {
        fv.revalidateField('category');
        fv.revalidateField('name');
    });

    $('input[name="price"]')
        .TouchSpin({
            min: 0.01,
            max: 1000000,
            step: 0.01,
            decimals: 2,
            boostat: 5,
            maxboostedstep: 10,
            prefix: '$'
        })
        .on('change touchspin.on.min touchspin.on.max', function () {
            $('input[name="pvp"]').trigger("touchspin.updatesettings", {min: parseFloat($(this).val())});
            fv.revalidateField('price');
        })
        .on('keypress', function (e) {
            return validate_text_box({'event': e, 'type': 'decimals'});
        });

    $('input[name="pvp"]')
        .TouchSpin({
            min: 0.01,
            max: 1000000,
            step: 0.01,
            decimals: 2,
            boostat: 5,
            maxboostedstep: 10,
            prefix: '$'
        })
        .on('change touchspin.on.min touchspin.on.max', function () {
            fv.revalidateField('pvp');
        })
        .on('keypress', function (e) {
            return validate_text_box({'event': e, 'type': 'decimals'});
        });

    input_inventoried.on('change', function () {
        var container = $(this).closest('.container-fluid').find('input[name="price"]').closest('.form-group');
        $(container).show();
        if (!this.checked) {
            $(container).hide();
        }
    });

    input_inventoried.trigger('change');

    $('input[name="code"]')
        .on('keypress', function (e) {
            return validate_text_box({'event': e, 'type': 'numbers_letters'});
        })
        .on('keyup', function (e) {
            var value = $(this).val();
            $(this).val(value.toUpperCase());
        });

    // Prices

    $('.btnCreatePrice').on('click', function () {
        product.prices.push({'quantity': 1, 'net_price': 0.00});
        product.listPrices();
    });

    $('#tblPrices tbody')
        .off()
        .on('click', 'a[rel="remove"]', function () {
            var tr = tblPrices.cell($(this).closest('td, li')).index();
            product.prices.splice(tr.row, 1);
            tblPrices.row(tr.row).remove().draw();
            $('.tooltip').remove();
        })
        .on('change', 'input[name="quantity"]', function () {
            var tr = tblPrices.cell($(this).closest('td, li')).index();
            var data = tblPrices.row(tr.row).data();
            data.quantity = parseInt($(this).val());
        })
        .on('change', 'input[name="net_price"]', function () {
            var tr = tblPrices.cell($(this).closest('td, li')).index();
            var data = tblPrices.row(tr.row).data();
            data.net_price = $(this).val();
        });

    $('i[data-field="price"]').hide();
    $('i[data-field="pvp"]').hide();
});
