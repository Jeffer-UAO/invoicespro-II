var tblProducts;
var product = {
    list: function () {
        tblProducts = $("#data").DataTable({
            autoWidth: false,
            destroy: true,
            deferRender: true,
            ajax: {
                url: pathname,
                type: "POST",
                headers: {
                    "X-CSRFToken": csrftoken,
                },
                data: {
                    action: "search",
                },
                dataSrc: "",
            },
            columns: [
                {data: "id"},
                {data: "name"},
                {data: "code"},
                {data: "inventoried"},
                {data: "price"},
                {data: "price_list"},
                {data: "price_promotion"},
                {data: "stock"},
                {data: "id"},
            ],
            columnDefs: [
                {
                    targets: [3],
                    class: "text-center",
                    render: function (data, type, row) {
                        if (row.inventoried) {
                            return '<span class="badge badge-success badge-pill">Si</span>';
                        }
                        return '<span class="badge badge-danger badge-pill">No</span>';
                    },
                },
                {
                    targets: [-7],
                    class: "text-center",
                    render: function (data, type, row) {
                        return data;
                    },
                },
                {
                    targets: [-6],
                    class: "text-center",
                    render: function (data, type, row) {
                        if (data <= 0) {
                            return '<span class="badge badge-danger badge-pill">0</span>';
                        }
                        return '<span class="badge badge-success badge-pill">' + data + '</span>';
                    },
                },
                {
                    targets: [-4],
                    class: "text-center",
                    render: function (data, type, row) {
                        var html = '<p class="p-0 mb-0">';
                        row.price_list.forEach(function (value, index, array) {
                            html += 'Cantidad: ' + value.quantity + ' = Precio: ' + value.net_price.toFixed(2) + '<br>'
                        });
                        html += '</p>';
                        return html
                    },
                },
                {
                    targets: [-5, -3],
                    class: "text-center",
                    render: function (data, type, row) {
                        return "$" + data.toFixed(2);
                    },
                },
                {
                    targets: [-2],
                    class: "text-center",
                    render: function (data, type, row) {
                        if (row.inventoried) {
                            if (row.stock > 0) {
                                return (
                                    '<span class="badge badge-success badge-pill">' +
                                    row.stock +
                                    "</span>"
                                );
                            }
                            return (
                                '<span class="badge badge-danger badge-pill">' +
                                row.stock +
                                "</span>"
                            );
                        }
                        return '<span class="badge badge-secondary badge-pill">Sin stock</span>';
                    },
                },
                {
                    targets: [-1],
                    class: "text-center",
                    render: function (data, type, row) {
                        var buttons =
                            '<a href="' +
                            pathname +
                            "update/" +
                            row.id +
                            '/" data-toggle="tooltip" title="Editar" class="btn btn-warning btn-xs btn-flat"><i class="fas fa-edit"></i></a> ';
                        buttons +=
                            '<a href="' +
                            pathname +
                            "delete/" +
                            row.id +
                            '/" data-toggle="tooltip" title="Eliminar" class="btn btn-danger btn-xs btn-flat"><i class="fas fa-trash"></i></a>';
                        return buttons;
                    },
                },
            ],
            rowCallback: function (row, data, index) {
            },
            initComplete: function (settings, json) {
                $('[data-toggle="tooltip"]').tooltip();
                $(this).wrap('<div class="dataTables_scroll"><div/>');
            },
        });
    },
};

$(function () {
    product.list();

    $("#data").addClass("table-sm");

    $("#data tbody")
        .off()
        .on("click", 'a[rel="inventory"]', function () {
            var tr = tblProducts.cell($(this).closest("td, li")).index();
            var data = tblProducts.row(tr.row).data();
            $('#tblInventory').DataTable({
                autoWidth: false,
                destroy: true,
                ajax: {
                    url: pathname,
                    type: 'POST',
                    headers: {
                        'X-CSRFToken': csrftoken
                    },
                    data: {
                        'action': 'search_detail_products',
                        'id': row.id
                    },
                    dataSrc: ""
                },
                columns: [
                    {data: "date_joined"},
                    {data: "quantity"},
                    {data: "saldo"},
                    {data: "expiration_date"},
                ],
                columnDefs: [
                    {
                        targets: [-1, -3],
                        class: 'text-center',
                        render: function (data, type, row) {
                            return '$' + data.toFixed(2);
                        }
                    },
                    {
                        targets: [-2],
                        class: 'text-center',
                        render: function (data, type, row) {
                            return data.toFixed(2);
                        }
                    }
                ],
                initComplete: function (settings, json) {
                    $(this).wrap('<div class="dataTables_scroll"><div/>');
                }
            });
            $('#myModalDetails').modal('show');
        })
        .on("click", 'a[rel="image"]', function () {
            var tr = tblProducts.cell($(this).closest("td, li")).index();
            var data = tblProducts.row(tr.row).data();
            load_image({url: data.image});
        })
        .on("click", 'a[rel="barcode"]', function () {
            var tr = tblProducts.cell($(this).closest("td, li")).index();
            var data = tblProducts.row(tr.row).data();
            load_image({url: data.barcode});
        });
});
