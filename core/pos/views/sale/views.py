import json
from datetime import datetime

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import Group
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, FormView, UpdateView

from config import settings
from core.pos.forms import SaleForm, ClientForm, ClientUserForm, Sale, SaleDetail, Client, Product, Receipt, CreditNote, CreditNoteDetail, CtasCollect, INVOICE_STATUS, PAYMENT_TYPE, VOUCHER_TYPE
from core.pos.mixins import ValidateInvoicePlanMixin
from core.pos.models import Inventory, SaleDetailInventory
from core.pos.utilities import printer
from core.pos.utilities.sri import SRI
from core.reports.forms import ReportForm
from core.security.mixins import GroupPermissionMixin


class SaleListView(GroupPermissionMixin, FormView):
    template_name = 'sale/admin/list.html'
    form_class = ReportForm
    permission_required = 'view_sale'

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'search':
                data = []
                start_date = request.POST['start_date']
                end_date = request.POST['end_date']
                queryset = Sale.objects.filter()
                if len(start_date) and len(end_date):
                    queryset = queryset.filter(
                        date_joined__range=[start_date, end_date])
                for i in queryset:
                    data.append(i.toJSON())
            elif action == 'search_detail_products':
                data = []
                for i in SaleDetail.objects.filter(sale_id=request.POST['id']):
                    data.append(i.toJSON())
            elif action == 'generate_invoice':
                sale = Sale.objects.get(pk=request.POST['id'])
                data = sale.generate_electronic_invoice()
            elif action == 'create_credit_note':
                with transaction.atomic():
                    sale = Sale.objects.get(pk=request.POST['id'])
                    company = sale.company
                    iva = float(company.iva) / 100
                    credit_note = CreditNote()
                    credit_note.sale_id = sale.id
                    credit_note.motive = F'NOTA DE CREDITO DE LA VENTA {sale.voucher_number_full}'
                    credit_note.company = company
                    credit_note.environment_type = credit_note.company.environment_type
                    credit_note.receipt = Receipt.objects.get(
                        code=VOUCHER_TYPE[2][0])
                    credit_note.voucher_number = credit_note.generate_voucher_number()
                    credit_note.voucher_number_full = credit_note.get_voucher_number_full()
                    credit_note.iva = iva
                    credit_note.save()
                    for sale_detail in sale.saledetail_set.all():
                        detail = CreditNoteDetail()
                        detail.credit_note_id = credit_note.id
                        detail.sale_detail_id = sale_detail.id
                        detail.product_id = sale_detail.product_id
                        detail.cant = sale_detail.cant
                        detail.price = sale_detail.price
                        detail.dscto = sale_detail.dscto
                        detail.save()
                        credit_note.calculate_detail()
                        detail.product.stock += detail.cant
                        detail.product.save()
                    credit_note.calculate_invoice()
                    data = credit_note.generate_electronic_invoice()
                    if not data['resp']:
                        transaction.set_rollback(True)
                    else:
                        sale.status = INVOICE_STATUS[-1][0]
                        sale.save()
                if 'error' in data:
                    SRI().create_voucher_errors(credit_note, data)
            elif action == 'send_invoice_by_email':
                sale = Sale.objects.get(pk=request.POST['id'])
                xml_electronic_signature = SRI()
                xml_electronic_signature.notify_by_email(
                    instance=sale, company=sale.company, client=sale.client)
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Listado de Ventas'
        context['create_url'] = reverse_lazy('sale_admin_create')
        return context


class SaleCreateView(GroupPermissionMixin, ValidateInvoicePlanMixin, CreateView):
    model = Sale
    template_name = 'sale/admin/create.html'
    form_class = SaleForm
    success_url = reverse_lazy('sale_admin_list')
    permission_required = 'add_sale'

    def get_first_final_consumer(self):
        client = Client.objects.filter().first()
        return client.toJSON() if client else dict()

    def get(self, request, *args, **kwargs):
        if request.tenant.company.plan.quantity == 0:
            return super().get(request, *args, **kwargs)
        current_date = datetime.now().date()
        queryset = Sale.objects.filter(date_joined__year=current_date.year,
                                       date_joined__month=current_date.month, receipt__code=VOUCHER_TYPE[0][0])
        if queryset.count() >= request.tenant.company.plan.quantity:
            messages.error(request, f'Tu plan {request.tenant.company.plan.name} solo te permite {request.tenant.company.plan.quantity} facturas al mes y ya has superado el limite permitido')
            return HttpResponseRedirect(self.success_url)
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        action = request.POST['action']
        data = {}
        try:
            if action == 'add':
                with transaction.atomic():
                    sale = Sale()
                    sale.date_joined = request.POST['date_joined']
                    sale.company = request.tenant.company
                    sale.environment_type = sale.company.environment_type
                    sale.receipt_id = request.POST['receipt']
                    sale.voucher_number = sale.generate_voucher_number()
                    sale.voucher_number_full = sale.get_voucher_number_full()
                    sale.employee_id = request.user.id
                    sale.client_id = int(request.POST['client'])
                    sale.payment_type = request.POST['payment_type']
                    additional_info = [
                        {'name': 'Dirección', 'value': sale.client.address},
                        {'name': 'Teléfono', 'value': sale.client.mobile},
                        {'name': 'Email', 'value': sale.client.user.email}
                    ]
                    additional_info_json = json.loads(
                        request.POST['additional_info'])
                    if len(additional_info_json):
                        additional_info.extend(additional_info_json)
                    sale.additional_info = {'rows': additional_info}
                    sale.iva = float(sale.company.iva) / 100
                    sale.create_electronic_invoice = False
                    if sale.receipt.code == VOUCHER_TYPE[0][0]:
                        sale.time_limit = int(request.POST['time_limit'])
                        sale.payment_method = request.POST['payment_method']
                        sale.create_electronic_invoice = 'create_electronic_invoice' in request.POST
                    if sale.payment_type == PAYMENT_TYPE[0][0]:
                        sale.cash = float(request.POST['cash'])
                        sale.change = float(request.POST['change'])
                    elif sale.payment_type == PAYMENT_TYPE[1][0]:
                        sale.end_credit = request.POST['end_credit']
                        sale.cash = 0.00
                        sale.change = 0.00
                    sale.save()
                    for i in json.loads(request.POST['products']):
                        quantity = int(i['cant'])
                        product = Product.objects.get(pk=i['id'])
                        detail = SaleDetail()
                        detail.sale_id = sale.id
                        detail.product_id = product.id
                        detail.cant = quantity
                        detail.price = float(i['price_current'])
                        detail.dscto = float(i['dscto']) / 100
                        detail.save()
                        if product.inventoried:
                            for inventory in Inventory.objects.filter(product_id=product.id, saldo__gt=0, active=True).order_by('expiration_date', 'date_joined'):
                                if quantity == 0:
                                    break
                                if inventory.saldo >= quantity:
                                    SaleDetailInventory.objects.create(sale_detail_id=detail.id, inventory_id=inventory.id, quantity=quantity)
                                    inventory.saldo -= quantity
                                    inventory.save()
                                    quantity = 0
                                else:
                                    SaleDetailInventory.objects.create(sale_detail_id=detail.id, inventory_id=inventory.id, quantity=inventory.saldo)
                                    quantity -= inventory.saldo
                                    inventory.saldo = 0
                                    inventory.save()
                    sale.calculate_detail()
                    sale.calculate_invoice()
                    if sale.payment_type == PAYMENT_TYPE[1][0]:
                        ctas_collect = CtasCollect()
                        ctas_collect.sale_id = sale.id
                        ctas_collect.date_joined = sale.date_joined
                        ctas_collect.end_date = sale.end_credit
                        ctas_collect.debt = sale.total
                        ctas_collect.saldo = sale.total
                        ctas_collect.save()
                    data = {'print_url': str(reverse_lazy(
                        'sale_admin_print_invoice', kwargs={'pk': sale.id}))}
                    if sale.create_electronic_invoice:
                        data = sale.generate_electronic_invoice()
                        if not data['resp']:
                            transaction.set_rollback(True)
                if 'error' in data:
                    SRI().create_voucher_errors(sale, data)
            elif action == 'search_product':
                ids = json.loads(request.POST['ids'])
                data = []
                term = request.POST['term']
                queryset = Product.objects.filter().exclude(id__in=ids).order_by('name')
                if len(term):
                    queryset = queryset.filter(Q(name__icontains=term) | Q(code__icontains=term))
                    queryset = queryset[:10]
                for i in queryset:
                    if i.stock > 0 or not i.inventoried:
                        item = i.toJSON()
                        item['price_list'] = i.get_price_list()
                        item['pvp'] = float(i.pvp)
                        item['value'] = i.get_full_name()
                        item['dscto'] = 0.00
                        item['total_dscto'] = 0.00
                        data.append(item)
            elif action == 'search_product_code':
                data = {}
                code = request.POST['code']
                if len(code):
                    product = Product.objects.filter(code=code).first()
                    if product:
                        data = product.toJSON()
                        data['price_list'] = product.get_price_list()
                        data['dscto'] = 0.00
                        data['total_dscto'] = 0.00
            elif action == 'search_client':
                data = []
                term = request.POST['term']
                for i in Client.objects.filter(Q(user__names__icontains=term) | Q(dni__icontains=term)).order_by('user__names')[0:10]:
                    data.append(i.toJSON())
            elif action == 'validate_client':
                data = {'valid': True}
                pattern = request.POST['pattern']
                parameter = request.POST['parameter'].strip()
                queryset = Client.objects.all()
                if pattern == 'dni':
                    data['valid'] = not queryset.filter(dni=parameter).exists()
                elif pattern == 'mobile':
                    data['valid'] = not queryset.filter(
                        mobile=parameter).exists()
                elif pattern == 'email':
                    data['valid'] = not queryset.filter(
                        user__email=parameter).exists()
            elif action == 'create_client':
                with transaction.atomic():
                    form1 = ClientUserForm(
                        self.request.POST, self.request.FILES)
                    form2 = ClientForm(request.POST)
                    if form1.is_valid() and form2.is_valid():
                        user = form1.save(commit=False)
                        user.username = form2.cleaned_data['dni']
                        user.set_password(user.username)
                        user.save()
                        user.groups.add(Group.objects.get(
                            pk=settings.GROUPS['client']))
                        form_client = form2.save(commit=False)
                        form_client.user = user
                        form_client.save()
                        data = Client.objects.get(pk=form_client.id).toJSON()
                    else:
                        if not form1.is_valid():
                            data['error'] = form1.errors
                        elif not form2.is_valid():
                            data['error'] = form2.errors
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['title'] = f'Nuevo registro de una Venta - {Sale().generate_voucher_number_full()}'
        context['frmClient'] = ClientForm()
        context['list_url'] = self.success_url
        context['action'] = 'add'
        context['frmUser'] = ClientUserForm()
        context['final_consumer'] = json.dumps(self.get_first_final_consumer())
        context['products'] = []
        return context


class SaleUpdateView(GroupPermissionMixin, UpdateView):
    model = Sale
    template_name = 'sale/admin/create.html'
    form_class = SaleForm
    success_url = reverse_lazy('sale_admin_list')
    permission_required = 'add_sale'

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super().dispatch(request, *args, **kwargs)

    def get_products(self):
        data = []
        for detail in self.object.saledetail_set.all():
            product = detail.product.toJSON()
            product['cant'] = detail.cant
            product['stock'] += detail.cant
            product['dscto'] = float(detail.dscto)
            product['total_dscto'] = float(detail.total_dscto)
            data.append(product)
        return json.dumps(data)

    def get(self, request, *args, **kwargs):
        if request.tenant.company.plan.quantity == 0:
            return super().get(request, *args, **kwargs)
        current_date = datetime.now().date()
        queryset = Sale.objects.filter(date_joined__year=current_date.year,
                                       date_joined__month=current_date.month, receipt__code=VOUCHER_TYPE[0][0])
        if queryset.count() >= request.tenant.company.plan.quantity:
            messages.error(
                request, f'Tu plan {request.tenant.company.plan.name} solo te permite {request.tenant.company.plan.quantity} facturas al mes y ya has superado el limite permitido')
            return HttpResponseRedirect(self.success_url)
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        action = request.POST['action']
        data = {}
        try:
            if action == 'edit':
                with transaction.atomic():
                    sale = self.object
                    sale.date_joined = request.POST['date_joined']
                    sale.company = request.tenant.company
                    sale.environment_type = sale.company.environment_type
                    sale.receipt_id = request.POST['receipt']
                    # sale.voucher_number = sale.generate_voucher_number()
                    # sale.voucher_number_full = sale.get_voucher_number_full()
                    sale.employee_id = request.user.id
                    sale.client_id = int(request.POST['client'])
                    sale.payment_type = request.POST['payment_type']
                    additional_info = [
                        {'name': 'Dirección', 'value': sale.client.address},
                        {'name': 'Teléfono', 'value': sale.client.mobile},
                        {'name': 'Email', 'value': sale.client.user.email}
                    ]
                    additional_info_json = json.loads(
                        request.POST['additional_info'])
                    if len(additional_info_json):
                        additional_info.extend(additional_info_json)
                    sale.additional_info = {'rows': additional_info}
                    sale.iva = float(sale.company.iva) / 100
                    sale.create_electronic_invoice = False
                    if sale.receipt.code == VOUCHER_TYPE[0][0]:
                        sale.time_limit = int(request.POST['time_limit'])
                        sale.payment_method = request.POST['payment_method']
                        sale.create_electronic_invoice = 'create_electronic_invoice' in request.POST
                    if sale.payment_type == PAYMENT_TYPE[0][0]:
                        sale.cash = float(request.POST['cash'])
                        sale.change = float(request.POST['change'])
                    elif sale.payment_type == PAYMENT_TYPE[1][0]:
                        sale.end_credit = request.POST['end_credit']
                        sale.cash = 0.00
                        sale.change = 0.00
                    sale.save()
                    for detail in SaleDetailInventory.objects.filter(sale_detail__sale_id=sale.id):
                        detail.inventory.saldo += detail.quantity
                        detail.inventory.save()
                        detail.sale_detail.delete()
                        detail.delete()
                    sale.saledetail_set.all().delete()
                    for i in json.loads(request.POST['products']):
                        quantity = int(i['cant'])
                        product = Product.objects.get(pk=i['id'])
                        detail = SaleDetail()
                        detail.sale_id = sale.id
                        detail.product_id = product.id
                        detail.cant = int(i['cant'])
                        detail.price = float(i['price_current'])
                        detail.dscto = float(i['dscto']) / 100
                        detail.save()
                        if product.inventoried:
                            for inventory in Inventory.objects.filter(product_id=product.id, saldo__gt=0, active=True).order_by('expiration_date', 'date_joined'):
                                if quantity == 0:
                                    break
                                if inventory.saldo >= quantity:
                                    SaleDetailInventory.objects.create(sale_detail_id=detail.id, inventory_id=inventory.id, quantity=quantity)
                                    inventory.saldo -= quantity
                                    inventory.save()
                                    quantity = 0
                                else:
                                    SaleDetailInventory.objects.create(sale_detail_id=detail.id, inventory_id=inventory.id, quantity=inventory.saldo)
                                    quantity -= inventory.saldo
                                    inventory.saldo = 0
                                    inventory.save()
                    sale.calculate_detail()
                    sale.calculate_invoice()
                    if sale.payment_type == PAYMENT_TYPE[1][0]:
                        ctas_collect = CtasCollect()
                        ctas_collect.sale_id = sale.id
                        ctas_collect.date_joined = sale.date_joined
                        ctas_collect.end_date = sale.end_credit
                        ctas_collect.debt = sale.total
                        ctas_collect.saldo = sale.total
                        ctas_collect.save()
                    data = {'print_url': str(reverse_lazy(
                        'sale_admin_print_invoice', kwargs={'pk': sale.id}))}
                    if sale.create_electronic_invoice:
                        data = sale.generate_electronic_invoice()
                        if not data['resp']:
                            transaction.set_rollback(True)
                if 'error' in data:
                    SRI().create_voucher_errors(sale, data)
            elif action == 'search_product':
                ids = json.loads(request.POST['ids'])
                data = []
                term = request.POST['term']
                queryset = Product.objects.filter().exclude(id__in=ids).order_by('name')
                if len(term):
                    queryset = queryset.filter(Q(name__icontains=term) | Q(code__icontains=term))
                    queryset = queryset[:10]
                for i in queryset:
                    if i.stock > 0 or not i.inventoried:
                        item = i.toJSON()
                        item['price_list'] = i.get_price_list()
                        item['pvp'] = float(i.pvp)
                        item['value'] = i.get_full_name()
                        item['dscto'] = 0.00
                        item['total_dscto'] = 0.00
                        data.append(item)
            elif action == 'search_product_code':
                data = {}
                code = request.POST['code']
                if len(code):
                    product = Product.objects.filter(code=code).first()
                    if product:
                        data = product.toJSON()
                        data['price_list'] = product.get_price_list()
                        data['dscto'] = 0.00
                        data['total_dscto'] = 0.00
            elif action == 'search_client':
                data = []
                term = request.POST['term']
                for i in Client.objects.filter(Q(user__names__icontains=term) | Q(dni__icontains=term)).order_by('user__names')[0:10]:
                    data.append(i.toJSON())
            elif action == 'validate_client':
                data = {'valid': True}
                pattern = request.POST['pattern']
                parameter = request.POST['parameter'].strip()
                queryset = Client.objects.all()
                if pattern == 'dni':
                    data['valid'] = not queryset.filter(dni=parameter).exists()
                elif pattern == 'mobile':
                    data['valid'] = not queryset.filter(
                        mobile=parameter).exists()
                elif pattern == 'email':
                    data['valid'] = not queryset.filter(
                        user__email=parameter).exists()
            elif action == 'create_client':
                with transaction.atomic():
                    form1 = ClientUserForm(
                        self.request.POST, self.request.FILES)
                    form2 = ClientForm(request.POST)
                    if form1.is_valid() and form2.is_valid():
                        user = form1.save(commit=False)
                        user.username = form2.cleaned_data['dni']
                        user.set_password(user.username)
                        user.save()
                        user.groups.add(Group.objects.get(
                            pk=settings.GROUPS['client']))
                        form_client = form2.save(commit=False)
                        form_client.user = user
                        form_client.save()
                        data = Client.objects.get(pk=form_client.id).toJSON()
                    else:
                        if not form1.is_valid():
                            data['error'] = form1.errors
                        elif not form2.is_valid():
                            data['error'] = form2.errors
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['title'] = f'Edición registro de una Venta - {self.object.voucher_number_full}'
        context['frmClient'] = ClientForm()
        context['list_url'] = self.success_url
        context['action'] = 'edit'
        context['frmUser'] = ClientUserForm()
        context['final_consumer'] = json.dumps(self.object.client.toJSON())
        context['products'] = self.get_products()
        return context


class SaleDeleteView(GroupPermissionMixin, DeleteView):
    model = Sale
    template_name = 'delete.html'
    success_url = reverse_lazy('sale_admin_list')
    permission_required = 'delete_sale'

    def post(self, request, *args, **kwargs):
        data = {}
        try:
            self.get_object().delete()
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Notificación de eliminación'
        context['list_url'] = self.success_url
        return context


class SalePrintInvoiceView(LoginRequiredMixin, View):
    success_url = reverse_lazy('sale_admin_list')

    def get_success_url(self):
        if self.request.user.is_client():
            return reverse_lazy('sale_client_list')
        return self.success_url

    def get(self, request, *args, **kwargs):
        try:
            sale = Sale.objects.filter(id=self.kwargs['pk']).first()
            if sale:
                context = {'sale': sale, 'height': 450 +
                                                   sale.saledetail_set.all().count() * 10}
                pdf_file = printer.create_pdf(
                    context=context, template_name='sale/format/ticket.html')
                return HttpResponse(pdf_file, content_type='application/pdf')
        except:
            pass
        return HttpResponseRedirect(self.get_success_url())


class SaleClientListView(GroupPermissionMixin, FormView):
    template_name = 'sale/client/list.html'
    form_class = ReportForm
    permission_required = 'view_sale_client'

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'search':
                data = []
                start_date = request.POST['start_date']
                end_date = request.POST['end_date']
                queryset = Sale.objects.filter(client__user_id=request.user.id)
                if len(start_date) and len(end_date):
                    queryset = queryset.filter(
                        date_joined__range=[start_date, end_date])
                for i in queryset:
                    data.append(i.toJSON())
            elif action == 'search_detail_products':
                data = []
                for i in SaleDetail.objects.filter(sale_id=request.POST['id']):
                    data.append(i.toJSON())
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Listado de Ventas'
        return context
