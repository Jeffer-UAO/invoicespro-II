import base64
import math
import tempfile
import time
from datetime import datetime
from django.utils import timezone
from io import BytesIO
from xml.etree import ElementTree
from django.urls import reverse
import uuid
from django.utils.text import slugify

import barcode
import unicodedata
from barcode import writer
from crum import get_current_request
from django.core.files import File
from django.core.files.base import ContentFile
from django.db import models
from django.db.models import FloatField, IntegerField
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.forms import model_to_dict

from config import settings
from core.pos.choices import *
from core.pos.utilities import printer
from core.pos.utilities.sri import SRI
from core.security.fields import CustomImageField, CustomFileField
from core.tenant.choices import RETENTION_AGENT
from core.tenant.models import Company, ENVIRONMENT_TYPE
from core.user.models import User


class Provider(models.Model):
    first_name = models.CharField(max_length=50, blank=True, null=True, verbose_name='Nombre')
    last_name = models.CharField(max_length=50, blank=True, null=True, verbose_name='Apellido')
    dv = models.PositiveSmallIntegerField(verbose_name='Digito de Verificacion')
    name = models.CharField(max_length=100, verbose_name='Razón Social')
    ruc = models.BigIntegerField(unique=True, verbose_name='Número de NIT')
    mobile = models.BigIntegerField(verbose_name='Teléfono celular')
    email = models.CharField(max_length=50, verbose_name='Email')
    address = models.CharField(max_length=500, null=True, blank=True, verbose_name='Dirección')
    provider = models.BooleanField(default=True, verbose_name='Proveedor')
    cust = models.BooleanField(default=False, verbose_name='Cliente')
    employer = models.BooleanField(default=False, verbose_name='Empleado')
    other = models.BooleanField(default=False, verbose_name='Otros')
    active = models.BooleanField(default=True, verbose_name='Activo')
    created_date = models.DateTimeField(auto_now_add=True, verbose_name='Creado')

    def __str__(self):
        return self.get_full_name()

    def get_full_name(self):
        return f'{self.name} ({self.ruc})'

    def toJSON(self):
        item = model_to_dict(self)
        item['text'] = self.get_full_name()
        return item

    class Meta:
        verbose_name = 'Proveedor'
        verbose_name_plural = 'Proveedores'


class Category(models.Model):
    name = models.CharField(max_length=50, unique=True, verbose_name='Nombre')
    slug = models.SlugField(max_length=50, blank=True, verbose_name=("Url"))
    image = CustomImageField(folder='category', null=True,
                             blank=True, verbose_name='Imagen')
    image_alterna = models.CharField(
        max_length=600, null=True, blank=True, verbose_name=("Imagen Alterna")
    )
    created_date = models.DateTimeField(
        auto_now_add=True, verbose_name=("Creado"))
    modified_date = models.DateTimeField(
        auto_now=True, verbose_name=("Modificado"))

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super(Category, self).save(*args, **kwargs)

    def get_image(self):
        if self.image:
            return f'{settings.MEDIA_URL}/{self.image}'
        return f'{settings.STATIC_URL}img/default/empty.png'

    def toJSON(self):
        item = model_to_dict(self)
        item['image'] = self.get_image()
        return item

    class Meta:
        verbose_name = 'Categoria'
        verbose_name_plural = 'Categorias'


class Product(models.Model):
    item = models.UUIDField(editable=False, blank=True, null=True, unique=True)
    code = models.CharField(max_length=20, unique=True, verbose_name='Código')
    name = models.CharField(max_length=150, unique=True, verbose_name='Nombre')
    ref = models.CharField(max_length=80, blank=True, null=True, default="", verbose_name='Referencia')
    flag = models.CharField(max_length=80, blank=True, null=True, default="", verbose_name='Grupo')
    description = models.CharField(max_length=500, null=True, blank=True, verbose_name='Descripción')
    price_list = models.JSONField(default=dict, verbose_name='Precios de venta')
    category = models.ForeignKey(Category, on_delete=models.PROTECT, verbose_name='Categoría')
    price = models.DecimalField(max_digits=9, decimal_places=2, default=0.00, verbose_name='Precio de Compra')
    pvp = models.DecimalField(max_digits=9, decimal_places=2, default=0.00, verbose_name='Precio de Venta')
    pvp1 = models.DecimalField(max_digits=9, decimal_places=2, default=0.00, verbose_name='Precio 1')
    pvp2 = models.DecimalField(max_digits=9, decimal_places=2, default=0.00, verbose_name='Precio 2')
    pvp3 = models.DecimalField(max_digits=9, decimal_places=2, default=0.00, verbose_name='Precio 3')
    image = CustomImageField(null=True, blank=True, verbose_name='Imagen')
    image_alterna = models.CharField(max_length=500, null=True, default="", blank=True, verbose_name='Imagen Alterna')
    slug = models.SlugField(max_length=150, blank=True, verbose_name='Url')
    barcode = CustomImageField(folder='barcode', null=True, blank=True, verbose_name='Código de barra')
    inventoried = models.BooleanField(default=True, verbose_name='¿Es inventariado?')
    max_cant = models.IntegerField(default=0, verbose_name='Cantidad Max')
    max_pvp = models.DecimalField(max_digits=9, decimal_places=2, default=0.00, verbose_name='Precio max')
    has_expiration_date = models.BooleanField(default=False, verbose_name='¿Tiene fecha de caducidad?')
    with_tax = models.BooleanField(default=True, verbose_name='¿Se cobra impuesto?')
    active = models.BooleanField(default=True, verbose_name='Activo')
    soldout = models.BooleanField(default=False, verbose_name='Agotado')
    offer = models.BooleanField(default=False, verbose_name='Oferta')
    published = models.BooleanField(default=True, verbose_name='Publico')
    home = models.BooleanField(default=False, verbose_name='Exclusivo')
    created_date = models.DateTimeField(auto_now_add=True, verbose_name='Creado')
    modified_date = models.DateTimeField(auto_now=True, verbose_name='Modificado')

    def __str__(self):
        return self.get_full_name()

    @property
    def stock(self):
        return self.inventory_set.filter(active=True).aggregate(result=Coalesce(Sum('saldo'), 0, output_field=IntegerField())).get('result', 0)

    def get_full_name(self):
        return f'{self.name} ({self.code}) ({self.category.name})'

    def get_short_name(self):
        return f'{self.name} ({self.category.name})'

    def get_inventoried(self):
        if self.inventoried:
            return 'Inventariado'
        return 'No inventariado'

    def get_price_promotion(self):
        promotions = self.promotionsdetail_set.filter(
            promotion__state=True).first()
        if promotions:
            return promotions.price_final
        return 0.00

    def first_price_list(self):
        if self.price_list and isinstance(self.price_list, list):
            price_list = sorted(self.price_list, key=lambda x: x['quantity'])
            return price_list[0]['gross_price']
        return 0.00

    def get_price_current(self):
        price_promotion = self.get_price_promotion()
        if price_promotion > 0:
            return price_promotion
        return self.first_price_list()

    def get_image(self):
        if self.image:
            return f'{settings.MEDIA_URL}/{self.image}'
        return f'{settings.STATIC_URL}img/default/empty.png'

    def get_barcode(self):
        if self.barcode:
            return f'{settings.MEDIA_URL}/{self.barcode}'
        return f'{settings.STATIC_URL}img/default/empty.png'

    def get_benefit(self):
        benefit = float(self.pvp) - float(self.price)
        return round(benefit, 2)

    def generate_barcode(self):
        image_io = BytesIO()
        barcode.Gs1_128(
            self.code, writer=barcode.writer.ImageWriter()).write(image_io)
        filename = f'{self.code}.png'
        self.barcode.save(filename, content=ContentFile(
            image_io.getvalue()), save=False)

    def calculate_gross_price(self, price):
        company = Company.objects.first()
        if company:
            return round(price / (1 + (float(company.iva) / 100)), 2)
        return price

    def get_price_list(self):
        return self.price_list if self.price_list else []

    def toJSON(self):
        item = model_to_dict(self)
        item['stock'] = self.stock
        item['full_name'] = self.get_full_name()
        item['short_name'] = self.get_short_name()
        item['category'] = self.category.toJSON()
        item['price'] = float(self.price)
        item['price_promotion'] = float(self.get_price_promotion())
        item['price_current'] = float(self.get_price_current())
        item['pvp'] = float(self.pvp)
        item['pvp1'] = float(self.pvp1)
        item['pvp2'] = float(self.pvp2)
        item['pvp3'] = float(self.pvp3)
        item['max_cant'] = float(self.max_cant)
        item['max_pvp'] = float(self.max_pvp)
        item['image'] = self.get_image()
        item['barcode'] = self.get_barcode()
        item['price_list'] = self.price_list if self.price_list else []
        return item

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        if not self.item:
            self.item = uuid.uuid4()

        if not self.slug:
            self.slug = slugify(self.name)

        self.generate_barcode()

        super(Product, self).save()

    def edit(self):
        super(Product, self).save()

    class Meta:
        verbose_name = 'Producto'
        verbose_name_plural = 'Productos'
        default_permissions = ()
        permissions = (
            ('view_product', 'Can view Producto'),
            ('add_product', 'Can add Producto'),
            ('change_product', 'Can change Producto'),
            ('delete_product', 'Can delete Producto'),
            ('adjust_product_stock', 'Can adjust_product_stock Producto'),
        )


class Purchase(models.Model):
    number = models.CharField(
        max_length=8, unique=True, verbose_name='Número de factura')
    provider = models.ForeignKey(
        Provider, on_delete=models.PROTECT, verbose_name='Proveedor')
    payment_type = models.CharField(
        choices=PAYMENT_TYPE, max_length=50, default=PAYMENT_TYPE[0][0], verbose_name='Tipo de pago')
    date_joined = models.DateField(
        default=timezone.now, verbose_name='Fecha de registro')
    end_credit = models.DateField(
        default=timezone.now, verbose_name='Fecha de plazo de credito')
    subtotal = models.DecimalField(
        max_digits=9, decimal_places=2, default=0.00)

    def __str__(self):
        return self.provider.name

    def calculate_invoice(self):
        subtotal = 0.00
        for i in self.purchasedetail_set.all():
            subtotal += float(i.price) * int(i.cant)
        self.subtotal = subtotal
        self.save()

    def delete(self, using=None, keep_parents=False):
        try:
            for i in self.purchasedetail_set.all():
                i.product.stock -= i.cant
                i.product.save()
                i.delete()
        except:
            pass
        super(Purchase, self).delete()

    def toJSON(self):
        item = model_to_dict(self)
        item['date_joined'] = self.date_joined.strftime('%Y-%m-%d')
        item['end_credit'] = self.end_credit.strftime('%Y-%m-%d')
        item['provider'] = self.provider.toJSON()
        item['payment_type'] = {'id': self.payment_type,
                                'name': self.get_payment_type_display()}
        item['subtotal'] = float(self.subtotal)
        return item

    class Meta:
        verbose_name = 'Compra'
        verbose_name_plural = 'Compras'
        default_permissions = ()
        permissions = (
            ('view_purchase', 'Can view Compra'),
            ('add_purchase', 'Can add Compra'),
            ('delete_purchase', 'Can delete Compra'),
        )


class PurchaseDetail(models.Model):
    purchase = models.ForeignKey(Purchase, on_delete=models.PROTECT)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    cant = models.IntegerField(default=0)
    price = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    dscto = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    subtotal = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)

    def __str__(self):
        return self.product.name

    def toJSON(self):
        item = model_to_dict(self, exclude=['purchase'])
        item['product'] = self.product.toJSON()
        item['price'] = float(self.price)
        item['dscto'] = float(self.dscto)
        item['subtotal'] = float(self.subtotal)
        return item

    class Meta:
        verbose_name = 'Detalle de Compra'
        verbose_name_plural = 'Detalle de Compras'
        default_permissions = ()


class Inventory(models.Model):
    date_joined = models.DateTimeField(auto_now_add=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    expiration_date = models.DateField(null=True, blank=True)
    quantity = models.IntegerField(default=0)
    saldo = models.IntegerField(default=0)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.product.name

    def days_to_expire(self):
        if self.expiration_date:
            return (self.expiration_date - datetime.now().date()).days
        return 0

    def toJSON(self):
        item = model_to_dict(self)
        return item

    def save(self, force_insert=False, force_update=False, using=None,
             update_fields=None):
        self.active = self.saldo > 0
        super(Inventory, self).save()

    class Meta:
        verbose_name = 'Inventario'
        verbose_name_plural = 'Inventarios'
        default_permissions = ()


class Client(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    dni = models.CharField(max_length=13, unique=True,
                           verbose_name='Identificación')
    mobile = models.CharField(
        max_length=10, unique=True, verbose_name='Teléfono')
    birthdate = models.DateField(
        default=timezone.now, verbose_name='Fecha de nacimiento')
    address = models.CharField(max_length=500, verbose_name='Dirección')
    identification_type = models.CharField(
        max_length=30, choices=IDENTIFICATION_TYPE, default=IDENTIFICATION_TYPE[0][0], verbose_name='Tipo de identificación')
    send_email_invoice = models.BooleanField(
        default=True, verbose_name='¿Enviar email de factura?')

    def __str__(self):
        return self.get_full_name()

    def get_full_name(self):
        return f'{self.user.names} ({self.dni})'

    def birthdate_format(self):
        return self.birthdate.strftime('%Y-%m-%d')

    def toJSON(self):
        item = model_to_dict(self)
        item['text'] = self.get_full_name()
        item['user'] = self.user.toJSON()
        item['identification_type'] = {
            'id': self.identification_type, 'name': self.get_identification_type_display()}
        item['birthdate'] = self.birthdate.strftime('%Y-%m-%d')
        return item

    def delete(self, using=None, keep_parents=False):
        super(Client, self).delete()
        try:
            self.user.delete()
        except:
            pass

    class Meta:
        verbose_name = 'Cliente'
        verbose_name_plural = 'Clientes'


class Receipt(models.Model):
    name = models.CharField(max_length=200, verbose_name='Nombre')
    code = models.CharField(max_length=10, unique=True, verbose_name='Código')
    start_number = models.PositiveIntegerField(default=1, verbose_name='Desde')
    end_number = models.PositiveIntegerField(
        default=999999999, verbose_name='Hasta')
    current_number = models.PositiveIntegerField(
        default=999999999, verbose_name='Actual')

    def __str__(self):
        return self.name

    def get_name_xml(self):
        return self.remove_accents(self.name.replace(' ', '_').lower())

    def remove_accents(self, text):
        return ''.join((c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn'))

    def get_current_number(self):
        return f'{self.current_number:09d}'

    def toJSON(self):
        item = model_to_dict(self)
        item['start_number'] = f'{self.start_number:09d}'
        item['end_number'] = f'{self.end_number:09d}'
        return item

    class Meta:
        verbose_name = 'Comprobante'
        verbose_name_plural = 'Comprobantes'
        ordering = ['id']


class Sale(models.Model):
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, verbose_name='Compañia')
    client = models.ForeignKey(
        Client, on_delete=models.PROTECT, verbose_name='Cliente')
    receipt = models.ForeignKey(Receipt, on_delete=models.PROTECT, limit_choices_to={
        'code__in': [VOUCHER_TYPE[0][0], VOUCHER_TYPE[-1][0]]}, verbose_name='Tipo de comprobante')
    voucher_number = models.CharField(
        max_length=9, verbose_name='Número de comprobante')
    voucher_number_full = models.CharField(
        max_length=20, verbose_name='Número de comprobante completo')
    employee = models.ForeignKey(
        User, on_delete=models.PROTECT, verbose_name='Empleado')
    payment_type = models.CharField(
        choices=PAYMENT_TYPE, max_length=50, default=PAYMENT_TYPE[0][0], verbose_name='Tipo de pago')
    payment_method = models.CharField(
        choices=PAYMENT_METHOD, max_length=50, default=PAYMENT_METHOD[5][0], verbose_name='Método de pago')
    time_limit = models.IntegerField(default=31, verbose_name='Plazo')
    creation_date = models.DateTimeField(
        default=timezone.now, verbose_name='Fecha y hora de registro')
    date_joined = models.DateField(
        default=timezone.now, verbose_name='Fecha de registro')
    end_credit = models.DateField(
        default=timezone.now, verbose_name='Fecha limite de credito')
    additional_info = models.JSONField(
        default=dict, verbose_name='Información adicional')
    subtotal_12 = models.DecimalField(
        max_digits=9, decimal_places=2, default=0.00, verbose_name='Subtotal 19%')
    subtotal_0 = models.DecimalField(
        max_digits=9, decimal_places=2, default=0.00, verbose_name='Subtotal 0%')
    total_dscto = models.DecimalField(
        max_digits=9, decimal_places=2, default=0.00, verbose_name='Valor del descuento')
    iva = models.DecimalField(
        max_digits=9, decimal_places=2, default=0.00, verbose_name='Iva')
    total_iva = models.DecimalField(
        max_digits=9, decimal_places=2, default=0.00, verbose_name='Valor de iva')
    total = models.DecimalField(
        max_digits=9, decimal_places=2, default=0.00, verbose_name='Total a pagar')
    cash = models.DecimalField(
        max_digits=9, decimal_places=2, default=0.00, verbose_name='Efectivo recibido')
    change = models.DecimalField(
        max_digits=9, decimal_places=2, default=0.00, verbose_name='Cambio')
    environment_type = models.PositiveIntegerField(
        choices=ENVIRONMENT_TYPE, default=ENVIRONMENT_TYPE[0][0])
    access_code = models.CharField(
        max_length=49, null=True, blank=True, verbose_name='Clave de acceso')
    authorization_date = models.DateField(
        null=True, blank=True, verbose_name='Fecha de emisión')
    xml_authorized = CustomFileField(
        null=True, blank=True, verbose_name='XML Autorizado')
    pdf_authorized = CustomFileField(
        folder='pdf_authorized', null=True, blank=True, verbose_name='PDF Autorizado')
    create_electronic_invoice = models.BooleanField(
        default=True, verbose_name='Crear factura electrónica')
    status = models.CharField(max_length=50, choices=INVOICE_STATUS,
                              default=INVOICE_STATUS[0][0], verbose_name='Estado')

    def __str__(self):
        return self.get_full_name()

    def get_full_name(self):
        return f'{self.voucher_number_full} / {self.client.get_full_name()})'

    def get_iva_percent(self):
        return int(self.iva * 100)

    def get_full_subtotal(self):
        return float(self.subtotal_0) + float(self.subtotal_12)

    def get_subtotal_without_taxes(self):
        return float(self.saledetail_set.filter().aggregate(result=Coalesce(Sum('subtotal'), 0.00, output_field=FloatField()))['result'])

    def get_authorization_date(self):
        return self.authorization_date.strftime('%Y-%m-%d')

    def get_date_joined(self):
        return (datetime.strptime(self.date_joined, '%Y-%m-%d') if isinstance(self.date_joined, str) else self.date_joined).strftime('%Y-%m-%d')

    def get_end_credit(self):
        return (datetime.strptime(self.end_credit, '%Y-%m-%d') if isinstance(self.end_credit, str) else self.end_credit).strftime('%Y-%m-%d')

    def get_xml_authorized(self):
        if self.xml_authorized:
            return f'{settings.MEDIA_URL}/{self.xml_authorized}'
        return None

    def get_pdf_authorized(self):
        if self.pdf_authorized:
            return f'{settings.MEDIA_URL}/{self.pdf_authorized}'
        return None

    def get_voucher_number_full(self):
        return f'{self.company.establishment_code}-{self.company.issuing_point_code}-{self.voucher_number}'

    def generate_voucher_number(self):
        number = int(self.receipt.get_current_number()) + 1
        return f'{number:09d}'

    def generate_voucher_number_full(self):
        request = get_current_request()
        if self.company_id is None:
            self.company = request.tenant.company
        if self.receipt_id is None:
            self.receipt = Receipt.objects.get(code=VOUCHER_TYPE[0][0])
        self.voucher_number = self.generate_voucher_number()
        return self.get_voucher_number_full()

    def generate_pdf_authorized(self):
        rv = BytesIO()
        barcode.Code128(self.access_code,
                        writer=barcode.writer.ImageWriter()).write(rv)
        file = base64.b64encode(rv.getvalue()).decode("ascii")
        context = {'sale': self,
                   'access_code_barcode': f"data:image/png;base64,{file}"}
        pdf_file = printer.create_pdf(
            context=context, template_name='sale/format/invoice.html')
        with tempfile.NamedTemporaryFile(delete=True) as file_temp:
            file_temp.write(pdf_file)
            file_temp.flush()
            self.pdf_authorized.save(
                name=f'{self.receipt.get_name_xml()}_{self.access_code}.pdf', content=File(file_temp))

    def generate_xml(self):
        access_key = SRI().create_access_key(self)
        # root = ElementTree.Element('factura', id="comprobante", version="1.0.0")
        root = ElementTree.Element('Invoice',
                                   xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
                                   xmlns_cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
                                   xmlns_cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
                                   xmlns_ds="http://www.w3.org/2000/09/xmldsig#",
                                   xmlns_ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
                                   xmlns_sts="dian:gov:co:facturaelectronica:Structures-2-1",
                                   xmlns_xades="http://uri.etsi.org/01903/v1.3.2#",
                                   xmlns_xades141="http://uri.etsi.org/01903/v1.4.1#",
                                   xmlns_xsi="http://www.w3.org/2001/XMLSchema-instance",
                                   xsi_schemaLocation="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2 http://docs.oasis-open.org/ubl/os-UBL-2.1/xsd/maindoc/UBL-Invoice-2.1.xsd")
        # infoTributaria

        xml_UBLExtensions = ElementTree.SubElement(root, 'ext:UBLExtensions')
        xml_UBLExtension = ElementTree.SubElement(
            xml_UBLExtensions, 'ext:UBLExtension')
        xml_ExtensionContent = ElementTree.SubElement(
            xml_UBLExtension, 'ext:ExtensionContent')
        xml_DianExtensions = ElementTree.SubElement(
            xml_ExtensionContent, 'sts:DianExtensions')
        xml_InvoiceControl = ElementTree.SubElement(
            xml_DianExtensions, 'sts:InvoiceControl')

        xml_InvoiceAuthorization = ElementTree.SubElement(
            xml_InvoiceControl, 'sts:InvoiceAuthorization')
        xml_InvoiceAuthorization.text = '18760000001'

        # Crea el subelemento AuthorizationPeriod y sus subelementos
        xml_AuthorizationPeriod = ElementTree.SubElement(
            xml_InvoiceControl, 'sts:AuthorizationPeriod')
        xml_StartDate = ElementTree.SubElement(
            xml_AuthorizationPeriod, 'cbc:StartDate')
        xml_StartDate.text = '2019-01-19'
        xml_EndDate = ElementTree.SubElement(
            xml_AuthorizationPeriod, 'cbc:EndDate')
        xml_EndDate.text = '2030-01-19'

        # Crea el subelemento AuthorizedInvoices y sus subelementos
        xml_AuthorizedInvoices = ElementTree.SubElement(
            xml_InvoiceControl, 'sts:AuthorizedInvoices')
        xml_Prefix = ElementTree.SubElement(
            xml_AuthorizedInvoices, 'sts:Prefix')
        xml_Prefix.text = 'SETP'
        xml_From = ElementTree.SubElement(xml_AuthorizedInvoices, 'sts:From')
        xml_From.text = '990000000'
        xml_To = ElementTree.SubElement(xml_AuthorizedInvoices, 'sts:To')
        xml_To.text = '995000000'

        # Crea el elemento InvoiceSource y sus subelementos
        xml_InvoiceSource = ElementTree.SubElement(
            xml_DianExtensions, 'sts:InvoiceSource')
        xml_IdentificationCode = ElementTree.SubElement(
            xml_InvoiceSource, 'cbc:IdentificationCode')
        xml_IdentificationCode.set('listAgencyID', '6')
        xml_IdentificationCode.set(
            'listAgencyName', 'United Nations Economic Commission for Europe')
        xml_IdentificationCode.set(
            'listSchemeURI', 'urn:oasis:names:specification:ubl:codelist:gc:CountryIdentificationCode-2.1')
        xml_IdentificationCode.text = 'CO'

        # Agregar el elemento sts:SoftwareProvider
        xml_SoftwareProvider = ElementTree.SubElement(
            xml_DianExtensions, 'sts:SoftwareProvider')

        xml_ProviderID = ElementTree.SubElement(
            xml_SoftwareProvider, 'sts:ProviderID')
        xml_ProviderID.text = '800197268'
        xml_ProviderID.set('schemeAgencyID', '195')
        xml_ProviderID.set(
            'schemeAgencyName', 'CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)')
        xml_ProviderID.set('schemeID', '4')
        xml_ProviderID.set('schemeName', '31')
        xml_SoftwareID = ElementTree.SubElement(
            xml_SoftwareProvider, 'sts:SoftwareID')
        xml_SoftwareID.text = '56f2ae4e-9812-4fad-9255-08fcfcd5ccb0'
        xml_SoftwareID.set('schemeAgencyID', '195')
        xml_SoftwareID.set(
            'schemeAgencyName', 'CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)')
        xml_SoftwareSecurityCode = ElementTree.SubElement(
            xml_SoftwareProvider, 'sts:SoftwareSecurityCode')
        xml_SoftwareSecurityCode.text = 'a8d18e4e5aa00b44a0b1f9ef413ad8215116bd3ce91730d580eaed795c83b5a32fe6f0823abc71400b3d59eb542b7de8'
        xml_SoftwareSecurityCode.set('schemeAgencyID', '195')
        xml_SoftwareSecurityCode.set(
            'schemeAgencyName', 'CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)')

        # Agregar la subextensión sts:SoftwareSecurityCode
        xml_SoftwareSecurityCode = ElementTree.SubElement(
            xml_DianExtensions, 'sts:SoftwareSecurityCode')
        xml_SoftwareSecurityCode.set('schemeAgencyID', '195')
        xml_SoftwareSecurityCode.set(
            'schemeAgencyName', 'CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)')
        xml_SoftwareSecurityCode.text = 'a8d18e4e5aa00b44a0b1f9ef413ad8215116bd3ce91730d580eaed795c83b5a32fe6f0823abc71400b3d59eb542b7de8'

        # Agregar el elemento sts:AuthorizationProvider
        xml_AuthorizationProvider = ElementTree.SubElement(
            xml_DianExtensions, 'sts:AuthorizationProvider')

        # Agregar el subelemento de sts:AuthorizationProvider
        xml_AuthorizationProviderID = ElementTree.SubElement(
            xml_AuthorizationProvider, 'sts:AuthorizationProviderID')
        xml_AuthorizationProviderID.set('schemeAgencyID', '195')
        xml_AuthorizationProviderID.set(
            'schemeAgencyName', 'CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)')
        xml_AuthorizationProviderID.set('schemeID', '4')
        xml_AuthorizationProviderID.set('schemeName', '31')
        xml_AuthorizationProviderID.text = '800197268'

        # Agregar el elemento sts:QRCode
        xml_QRCode = ElementTree.SubElement(xml_DianExtensions, 'sts:QRCode')
        xml_QRCode.text = '''NroFactura=SETP990000002
        NitFacturador=800197268
        NitAdquiriente=900108281
        FechaFactura=2019-06-20
        ValorTotalFactura=14024.07
        CUFE=941cf36af62dbbc06f105d2a80e9bfe683a90e84960eae4d351cc3afbe8f848c26c39bac4fbc80fa254824c6369ea694
        URL=https://catalogo-vpfe-hab.dian.gov.co/Document/FindDocument?documentKey=941cf36af62dbbc06f105d2a80e9bfe683a90e84960eae4d351cc3afbe8f848c26c39bac4fbc80fa254824c6369ea694&amp;partitionKey=co|06|94&amp;emissionDate=20190620'''

        # Crear el elemento ds:Signature con su atributo Id

        xml_UBLExtension = ElementTree.SubElement(
            xml_UBLExtensions, 'ext:UBLExtension')
        xml_ExtensionContent = ElementTree.SubElement(
            xml_UBLExtension, 'ext:ExtensionContent')
        xml_Signature = ElementTree.SubElement(
            xml_ExtensionContent, 'ds:Signature')
        xml_Signature.set('Id', 'xmldsig-d0322c4f-be87-495a-95d5-9244980495f4')

        xml_SignedInfo = ElementTree.SubElement(xml_Signature, 'ds:SignedInfo')

        ds_CanonicalizationMethod = ElementTree.SubElement(
            xml_SignedInfo, 'ds:CanonicalizationMethod')
        ds_CanonicalizationMethod.set(
            'Algorithm', 'http://www.w3.org/TR/2001/REC-xml-c14n-20010315')
        ds_SignatureMethod = ElementTree.SubElement(
            xml_SignedInfo, 'ds:SignatureMethod')
        ds_SignatureMethod.set(
            'Algorithm', 'http://www.w3.org/2001/04/xmldsig-more#rsa-sha256')

        ds_Reference1 = ElementTree.SubElement(xml_SignedInfo, 'ds:Reference')
        ds_Reference1.set(
            'Id', 'xmldsig-d0322c4f-be87-495a-95d5-9244980495f4-ref0')
        ds_Transforms1 = ElementTree.SubElement(ds_Reference1, 'ds:Transforms')
        ds_Transform1 = ElementTree.SubElement(ds_Transforms1, 'ds:Transform')
        ds_Transform1.set(
            'Algorithm', 'http://www.w3.org/2000/09/xmldsig#enveloped-signature')
        ds_DigestMethod1 = ElementTree.SubElement(
            ds_Reference1, 'ds:DigestMethod')
        ds_DigestMethod1.set(
            'Algorithm', 'http://www.w3.org/2001/04/xmlenc#sha256')
        ds_DigestValue1 = ElementTree.SubElement(
            ds_Reference1, 'ds:DigestValue')
        ds_DigestValue1.text = 'akcOQ5qEh4dkMwt0d5BoXRR8Bo4vdy9DBZtfF5O0SsA='

        ds_Reference2 = ElementTree.SubElement(xml_SignedInfo, 'ds:Reference')
        ds_Reference2.set(
            'URI', '#xmldsig-87d128b5-aa31-4f0b-8e45-3d9cfa0eec26-keyinfo')
        ds_DigestMethod2 = ElementTree.SubElement(
            ds_Reference2, 'ds:DigestMethod')
        ds_DigestMethod2.set(
            'Algorithm', 'http://www.w3.org/2001/04/xmlenc#sha256')
        ds_DigestValue2 = ElementTree.SubElement(
            ds_Reference2, 'ds:DigestValue')
        ds_DigestValue2.text = 'troRYR2fcmJLV6gYibVM6XlArbddSCkjYkACZJP47/4='

        ds_Reference3 = ElementTree.SubElement(xml_SignedInfo, 'ds:Reference')
        ds_Reference3.set('Type', 'http://uri.etsi.org/01903#SignedProperties')
        ds_Reference3.set(
            'URI', '#xmldsig-d0322c4f-be87-495a-95d5-9244980495f4-signedprops')
        ds_DigestMethod3 = ElementTree.SubElement(
            ds_Reference3, 'ds:DigestMethod')
        ds_DigestMethod3.set(
            'Algorithm', 'http://www.w3.org/2001/04/xmlenc#sha256')
        ds_DigestValue3 = ElementTree.SubElement(
            ds_Reference3, 'ds:DigestValue')
        ds_DigestValue3.text = 'hpIsyD/08hVUc1exnfEyhGyKX5s3pUPbpMKmPhkPPqU='

        # Agregar el elemento ds:SignatureValue con su atributo Id
        ds_SignatureValue = ElementTree.SubElement(
            xml_Signature, 'ds:SignatureValue')
        ds_SignatureValue.set(
            'Id', 'xmldsig-d0322c4f-be87-495a-95d5-9244980495f4-sigvalue')
        ds_SignatureValue.text = """
                        q4HWeb47oLdDM4D3YiYDOSXE4YfSHkQKxUfSYiEiPuP2XWvD7ELZTC4ENFv6krgDAXczmi0W7OMi
                        LIVvuFz0ohPUc4KNlUEzqSBHVi6sC34sCqoxuRzOmMEoCB9Tr4VICxU1Ue9XhgP7o6X4f8KFAQWW
                        NaeTtA6WaO/yUtq91MKP59aAnFMfYl8lXpaS0kpUwuui3wdCZsGycsl1prEWiwzpaukEUOXyTo7o
                        RBOuNsDIUhP24Fv1alRFnX6/9zEOpRTs4rEQKN3IQnibF757LE/nnkutElZHTXaSV637gpHjXoUN
                        5JrUwTNOXvmFS98N6DczCQfeNuDIozYwtFVlMw==
                    """

        # Agregar el elemento ds:KeyInfo
        ds_KeyInfo = ElementTree.SubElement(xml_Signature, 'ds:KeyInfo')
        ds_KeyInfo.set(
            'Id', 'xmldsig-87d128b5-aa31-4f0b-8e45-3d9cfa0eec26-keyinfo')

        # Agregar el subelemento ds:X509Data
        ds_X509Data = ElementTree.SubElement(ds_KeyInfo, 'ds:X509Data')

        # Agregar el subelemento ds:X509Certificate dentro de ds:X509Data
        ds_X509Certificate = ElementTree.SubElement(
            ds_X509Data, 'ds:X509Certificate')
        ds_X509Certificate.text = """
                                MIIIODCCBiCgAwIBAgIIbAsHYmJtoOIwDQYJKoZIhvcNAQELBQAwgbQxIzAhBgkqhkiG9w0BCQEW
                                FGluZm9AYW5kZXNzY2QuY29tLmNvMSMwIQYDVQQDExpDQSBBTkRFUyBTQ0QgUy5BLiBDbGFzZSBJ
                                STEwMC4GA1UECxMnRGl2aXNpb24gZGUgY2VydGlmaWNhY2lvbiBlbnRpZGFkIGZpbmFsMRMwEQYD
                                VQQKEwpBbmRlcyBTQ0QuMRQwEgYDVQQHEwtCb2dvdGEgRC5DLjELMAkGA1UEBhMCQ08wHhcNMTcw
                                OTE2MTM0ODE5WhcNMjAwOTE1MTM0ODE5WjCCARQxHTAbBgNVBAkTFENhbGxlIEZhbHNhIE5vIDEy
                                IDM0MTgwNgYJKoZIhvcNAQkBFilwZXJzb25hX2p1cmlkaWNhX3BydWViYXMxQGFuZGVzc2NkLmNv
                                bS5jbzEsMCoGA1UEAxMjVXN1YXJpbyBkZSBQcnVlYmFzIFBlcnNvbmEgSnVyaWRpY2ExETAPBgNV
                                BAUTCDExMTExMTExMRkwFwYDVQQMExBQZXJzb25hIEp1cmlkaWNhMSgwJgYDVQQLEx9DZXJ0aWZp
                                Y2FkbyBkZSBQZXJzb25hIEp1cmlkaWNhMQ8wDQYDVQQHEwZCb2dvdGExFTATBgNVBAgTDEN1bmRp
                                bmFtYXJjYTELMAkGA1UEBhMCQ08wggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIBAQC0Dn8t
                                oZ2CXun+63zwYecJ7vNmEmS+YouH985xDek7ImeE9lMBHXE1M5KDo7iT/tUrcFwKj717PeVL52Nt
                                B6WU4+KBt+nrK+R+OSTpTno5EvpzfIoS9pLI74hHc017rY0wqjl0lw+8m7fyLfi/JO7AtX/dthS+
                                MKHIcZ1STPlkcHqmbQO6nhhr/CGl+tKkCMrgfEFIm1kv3bdWqk3qHrnFJ6s2GoVNZVCTZW/mOzPC
                                NnnUW12LDd/Kd+MjN6aWbP0D/IJbB42Npqv8+/oIwgCrbt0sS1bysUgdT4im9bBhb00MWVmNRBBe
                                3pH5knzkBid0T7TZsPCyiMBstiLT3yfpAgMBAAGjggLpMIIC5TAMBgNVHRMBAf8EAjAAMB8GA1Ud
                                IwQYMBaAFKhLtPQLp7Zb1KAohRCdBBMzxKf3MDcGCCsGAQUFBwEBBCswKTAnBggrBgEFBQcwAYYb
                                aHR0cDovL29jc3AuYW5kZXNzY2QuY29tLmNvMIIB4wYDVR0gBIIB2jCCAdYwggHSBg0rBgEEAYH0
                                SAECCQIFMIIBvzBBBggrBgEFBQcCARY1aHR0cDovL3d3dy5hbmRlc3NjZC5jb20uY28vZG9jcy9E
                                UENfQW5kZXNTQ0RfVjIuNS5wZGYwggF4BggrBgEFBQcCAjCCAWoeggFmAEwAYQAgAHUAdABpAGwA
                                aQB6AGEAYwBpAPMAbgAgAGQAZQAgAGUAcwB0AGUAIABjAGUAcgB0AGkAZgBpAGMAYQBkAG8AIABl
                                AHMAdADhACAAcwB1AGoAZQB0AGEAIABhACAAbABhAHMAIABQAG8AbADtAHQAaQBjAGEAcwAgAGQA
                                ZQAgAEMAZQByAHQAaQBmAGkAYwBhAGQAbwAgAGQAZQAgAFAAZQByAHMAbwBuAGEAIABKAHUAcgDt
                                AGQAaQBjAGEAIAAoAFAAQwApACAAeQAgAEQAZQBjAGwAYQByAGEAYwBpAPMAbgAgAGQAZQAgAFAA
                                cgDhAGMAdABpAGMAYQBzACAAZABlACAAQwBlAHIAdABpAGYAaQBjAGEAYwBpAPMAbgAgACgARABQ
                                AEMAKQAgAGUAcwB0AGEAYgBsAGUAYwBpAGQAYQBzACAAcABvAHIAIABBAG4AZABlAHMAIABTAEMA
                                RDAdBgNVHSUEFjAUBggrBgEFBQcDAgYIKwYBBQUHAwQwRgYDVR0fBD8wPTA7oDmgN4Y1aHR0cDov
                                L3d3dy5hbmRlc3NjZC5jb20uY28vaW5jbHVkZXMvZ2V0Q2VydC5waHA/Y3JsPTEwHQYDVR0OBBYE
                                FL9BXJHmFVE5c5Ai8B1bVBWqXsj7MA4GA1UdDwEB/wQEAwIE8DANBgkqhkiG9w0BAQsFAAOCAgEA
                                b/pa7yerHOu1futRt8QTUVcxCAtK9Q00u7p4a5hp2fVzVrhVQIT7Ey0kcpMbZVPgU9X2mTHGfPdb
                                R0hYJGEKAxiRKsmAwmtSQgWh5smEwFxG0TD1chmeq6y0GcY0lkNA1DpHRhSK368vZlO1p2a6S13Y
                                1j3tLFLqf5TLHzRgl15cfauVinEHGKU/cMkjLwxNyG1KG/FhCeCCmawATXWLgQn4PGgvKcNrz+y0
                                cwldDXLGKqriw9dce2Zerc7OCG4/XGjJ2PyZOJK9j1VYIG4pnmoirVmZbKwWaP4/TzLs6LKaJ4b6
                                6xLxH3hUtoXCzYQ5ehYyrLVwCwTmKcm4alrEht3FVWiWXA/2tj4HZiFoG+I1OHKmgkNv7SwHS7z9
                                tFEFRaD3W3aD7vwHEVsq2jTeYInE0+7r2/xYFZ9biLBrryl+q22zM5W/EJq6EJPQ6SM/eLqkpzqM
                                EF5OdcJ5kIOxLbrIdOh0+grU2IrmHXr7cWNP6MScSL7KSxhjPJ20F6eqkO1Z/LAxqNslBIKkYS24
                                VxPbXu0pBXQvu+zAwD4SvQntIG45y/67h884I/tzYOEJi7f6/NFAEuV+lokw/1MoVsEgFESASI9s
                                N0DfUniabyrZ3nX+LG3UFL1VDtDPWrLTNKtb4wkKwGVwqtAdGFcE+/r/1WG0eQ64xCq0NLutCxg=
                            """
        ds_Object = ElementTree.SubElement(xml_Signature, 'ds:Object')

        xades_QualifyingProperties = ElementTree.SubElement(
            ds_Object, 'xades:QualifyingProperties')
        xades_QualifyingProperties.set(
            'Target', '#xmldsig-d0322c4f-be87-495a-95d5-9244980495f4')
        xades_SignedProperties = ElementTree.SubElement(
            xades_QualifyingProperties, 'xades:SignedProperties')
        xades_SignedProperties.set(
            'Id', 'xmldsig-d0322c4f-be87-495a-95d5-9244980495f4-signedprops')
        xades_SignedSignatureProperties = ElementTree.SubElement(
            xades_SignedProperties, 'xades:SignedSignatureProperties')
        xades_SigningTime = ElementTree.SubElement(
            xades_SignedSignatureProperties, 'xades:SigningTime')
        xades_SigningTime.text = '2019-06-21T19:09:35.993-05:00'
        xades_SigningCertificate = ElementTree.SubElement(
            xades_SignedSignatureProperties, 'xades:SigningCertificate')
        xades_Cert = ElementTree.SubElement(
            xades_SigningCertificate, 'xades:Cert')
        xades_CertDigest = ElementTree.SubElement(
            xades_Cert, 'xades:CertDigest')
        ds_DigestMethod = ElementTree.SubElement(
            xades_CertDigest, 'ds:DigestMethod')
        ds_DigestMethod.set(
            'Algorithm', 'http://www.w3.org/2001/04/xmlenc#sha256')
        ds_DigestValue = ElementTree.SubElement(
            xades_CertDigest, 'ds:DigestValue')
        ds_DigestValue.text = 'nem6KXhqlV0A0FK5o+MwJZ3Y1aHgmL1hDs/RMJu7HYw='
        xades_SignaturePolicyIdentifier = ElementTree.SubElement(
            xades_SignedSignatureProperties, 'xades:SignaturePolicyIdentifier')
        xades_SigPolicyId = ElementTree.SubElement(
            xades_SignaturePolicyIdentifier, 'xades:SignaturePolicyId')
        xades_Identifier = ElementTree.SubElement(
            xades_SigPolicyId, 'xades:Identifier')
        xades_Identifier.text = 'https://facturaelectronica.dian.gov.co/politicadefirma/v1/politicadefirmav2.pdf'
        xades_SigPolicyHash = ElementTree.SubElement(
            xades_SigPolicyId, 'xades:SigPolicyHash')
        ds_DigestMethod2 = ElementTree.SubElement(
            xades_SigPolicyHash, 'ds:DigestMethod')
        ds_DigestMethod2.set(
            'Algorithm', 'http://www.w3.org/2001/04/xmlenc#sha256')
        ds_DigestValue2 = ElementTree.SubElement(
            xades_SigPolicyHash, 'ds:DigestValue')
        ds_DigestValue2.text = 'dMoMvtcG5aIzgYo0tIsSQeVJBDnUnfSOfBpxXrmor0Y='
        xades_SignerRole = ElementTree.SubElement(
            xades_SignedSignatureProperties, 'xades:SignerRole')
        xades_ClaimedRoles = ElementTree.SubElement(
            xades_SignerRole, 'xades:ClaimedRoles')
        xades_ClaimedRole = ElementTree.SubElement(
            xades_ClaimedRoles, 'xades:ClaimedRole')
        xades_ClaimedRole.text = 'supplier'

        xml_UBLVersionID = ElementTree.SubElement(root, 'cbc:UBLVersionID')
        xml_UBLVersionID.text = 'UBL 2.1'

        xml_CustomizationID = ElementTree.SubElement(
            root, 'cbc:CustomizationID')
        xml_CustomizationID.text = '10'

        xml_ProfileID = ElementTree.SubElement(root, 'cbc:ProfileID')
        xml_ProfileID.text = 'DIAN 2.1'

        xml_ProfileExecutionID = ElementTree.SubElement(
            root, 'cbc:ProfileExecutionID')
        xml_ProfileExecutionID.text = '2'

        xml_ID = ElementTree.SubElement(root, 'cbc:ID')
        xml_ID.text = 'SETP990000002'

        xml_UUID = ElementTree.SubElement(root, 'cbc:UUID')
        xml_UUID.text = '941cf36af62dbbc06f105d2a80e9bfe683a90e84960eae4d351cc3afbe8f848c26c39bac4fbc80fa254824c6369ea694'
        xml_UUID.set('schemeID', '2')
        xml_UUID.set('schemeName', 'CUFE-SHA384')

        xml_IssueDate = ElementTree.SubElement(root, 'cbc:IssueDate')
        xml_IssueDate.text = '2019-06-20'

        xml_IssueTime = ElementTree.SubElement(root, 'cbc:IssueTime')
        xml_IssueTime.text = '09:15:23-05:00'

        xml_InvoiceTypeCode = ElementTree.SubElement(
            root, 'cbc:InvoiceTypeCode')
        xml_InvoiceTypeCode.text = '01'

        xml_DocumentCurrencyCode = ElementTree.SubElement(
            root, 'cbc:DocumentCurrencyCode')
        xml_DocumentCurrencyCode.text = 'COP'
        xml_DocumentCurrencyCode.set('listAgencyID', '6')
        xml_DocumentCurrencyCode.set(
            'listAgencyName', 'United Nations Economic Commission for Europe')
        xml_DocumentCurrencyCode.set('listID', 'ISO 4217 Alpha')

        # Numero de productos en la fctura
        xml_LineCountNumeric = ElementTree.SubElement(
            root, 'cbc:LineCountNumeric')
        xml_LineCountNumeric.text = '2'

        xml_InvoicePeriod = ElementTree.SubElement(root, 'cac:InvoicePeriod')
        xml_StartDate = ElementTree.SubElement(
            xml_InvoicePeriod, 'cbc:StartDate')
        xml_StartDate.text = '2019-05-01'
        xml_EndDate = ElementTree.SubElement(xml_InvoicePeriod, 'cbc:EndDate')
        xml_EndDate.text = '2019-05-30'

        # Agregar elemento cac:AccountingSupplierParty
        cac_AccountingSupplierParty = ElementTree.SubElement(
            root, 'cac:AccountingSupplierParty')

        cbc_AdditionalAccountID = ElementTree.SubElement(
            cac_AccountingSupplierParty, 'cbc:AdditionalAccountID')
        cbc_AdditionalAccountID.text = '1'
        cac_Party = ElementTree.SubElement(
            cac_AccountingSupplierParty, 'cac:Party')
        cbc_IndustryClasificationCode = ElementTree.SubElement(
            cac_Party, 'cbc:IndustryClasificationCode')
        cbc_IndustryClasificationCode.text = '45624'

        for party_name in ['Nombre Tienda', 'Establecimiento Principal', 'DIAN']:
            cac_PartyName = ElementTree.SubElement(cac_Party, 'cac:PartyName')
            cbc_Name = ElementTree.SubElement(cac_PartyName, 'cbc:Name')
            cbc_Name.text = party_name

        # Agregar subelemento cac:PhysicalLocation
        cac_PhysicalLocation = ElementTree.SubElement(
            cac_Party, 'cac:PhysicalLocation')
        cac_Address = ElementTree.SubElement(
            cac_PhysicalLocation, 'cac:Address')
        cbc_ID = ElementTree.SubElement(cac_Address, 'cbc:ID')
        cbc_ID.text = '11001'
        cbc_CityName = ElementTree.SubElement(cac_Address, 'cbc:CityName')
        cbc_CityName.text = 'Bogotá, D.C.'
        cbc_CountrySubentity = ElementTree.SubElement(
            cac_Address, 'cbc:CountrySubentity')
        cbc_CountrySubentity.text = 'Bogotá'
        cbc_CountrySubentityCode = ElementTree.SubElement(
            cac_Address, 'cbc:CountrySubentityCode')
        cbc_CountrySubentityCode.text = '11'
        cac_AddressLine = ElementTree.SubElement(
            cac_Address, 'cac:AddressLine')
        cbc_Line = ElementTree.SubElement(cac_AddressLine, 'cbc:Line')
        cbc_Line.text = 'Av. #97 - 13'
        cac_Country = ElementTree.SubElement(cac_Address, 'cac:Country')
        cbc_IdentificationCode = ElementTree.SubElement(
            cac_Country, 'cbc:IdentificationCode')
        cbc_IdentificationCode.text = 'CO'
        cbc_Name = ElementTree.SubElement(
            cac_Country, 'cbc:Name', languageID="es")
        cbc_Name.text = 'Colombia'

        # Agregar subelemento cac:PartyTaxScheme
        cac_PartyTaxScheme = ElementTree.SubElement(
            cac_Party, 'cac:PartyTaxScheme')
        cbc_RegistrationName = ElementTree.SubElement(
            cac_PartyTaxScheme, 'cbc:RegistrationName')
        cbc_RegistrationName.text = 'DIAN'
        cbc_CompanyID = ElementTree.SubElement(cac_PartyTaxScheme, 'cbc:CompanyID', schemeAgencyID="195",
                                               schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)", schemeID="4", schemeName="31")
        cbc_CompanyID.text = '800197268'
        cbc_TaxLevelCode = ElementTree.SubElement(
            cac_PartyTaxScheme, 'cbc:TaxLevelCode', listName="05")
        cbc_TaxLevelCode.text = 'O-99'
        cac_RegistrationAddress = ElementTree.SubElement(
            cac_PartyTaxScheme, 'cac:RegistrationAddress')
        cbc_ID = ElementTree.SubElement(cac_RegistrationAddress, 'cbc:ID')
        cbc_ID.text = '11001'
        cbc_CityName = ElementTree.SubElement(
            cac_RegistrationAddress, 'cbc:CityName')
        cbc_CityName.text = 'Bogotá, D.C.'
        cbc_CountrySubentity = ElementTree.SubElement(
            cac_RegistrationAddress, 'cbc:CountrySubentity')
        cbc_CountrySubentity.text = 'Bogotá'
        cbc_CountrySubentityCode = ElementTree.SubElement(
            cac_RegistrationAddress, 'cbc:CountrySubentityCode')
        cbc_CountrySubentityCode.text = '11'
        cac_AddressLine = ElementTree.SubElement(
            cac_RegistrationAddress, 'cac:AddressLine')
        cbc_Line = ElementTree.SubElement(cac_AddressLine, 'cbc:Line')
        cbc_Line.text = 'Av. Jiménez #7 - 13'
        cac_Country = ElementTree.SubElement(
            cac_RegistrationAddress, 'cac:Country')
        cbc_IdentificationCode = ElementTree.SubElement(
            cac_Country, 'cbc:IdentificationCode')
        cbc_IdentificationCode.text = 'CO'
        cbc_Name = ElementTree.SubElement(
            cac_Country, 'cbc:Name', languageID="es")
        cbc_Name.text = 'Colombia'
        cac_TaxScheme = ElementTree.SubElement(
            cac_PartyTaxScheme, 'cac:TaxScheme')
        cbc_ID = ElementTree.SubElement(cac_TaxScheme, 'cbc:ID')
        cbc_ID.text = '01'
        cbc_Name = ElementTree.SubElement(cac_TaxScheme, 'cbc:Name')
        cbc_Name.text = 'IVA'

        # Agregar subelemento cac:PartyLegalEntity
        cac_PartyLegalEntity = ElementTree.SubElement(
            cac_Party, 'cac:PartyLegalEntity')
        cbc_RegistrationName = ElementTree.SubElement(
            cac_PartyLegalEntity, 'cbc:RegistrationName')
        cbc_RegistrationName.text = 'DIAN'
        cbc_CompanyID = ElementTree.SubElement(cac_PartyLegalEntity, 'cbc:CompanyID', schemeAgencyID="195",
                                               schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)", schemeID="9", schemeName="31")
        cbc_CompanyID.text = '800197268'

        cac_AccountingCustomerParty = ElementTree.SubElement(
            root, 'cac:AccountingCustomerParty')
        cbc_AdditionalAccountID = ElementTree.SubElement(
            cac_AccountingCustomerParty, 'cbc:AdditionalAccountID')
        cbc_AdditionalAccountID.text = '1'
        cac_Party = ElementTree.SubElement(
            cac_AccountingCustomerParty, 'cac:Party')
        cac_PartyName = ElementTree.SubElement(cac_Party, 'cac:PartyName')
        cbc_Name = ElementTree.SubElement(cac_PartyName, 'cbc:Name')
        cbc_Name.text = 'OPTICAS GMO COLOMBIA S A S'
        cac_PhysicalLocation = ElementTree.SubElement(
            cac_Party, 'cac:PhysicalLocation')
        cac_Address = ElementTree.SubElement(
            cac_PhysicalLocation, 'cac:Address')
        cbc_ID = ElementTree.SubElement(cac_Address, 'cbc:ID')
        cbc_ID.text = '11001'
        cbc_CityName = ElementTree.SubElement(cac_Address, 'cbc:CityName')
        cbc_CityName.text = 'Bogotá, D.C.'
        cbc_CountrySubentity = ElementTree.SubElement(
            cac_Address, 'cbc:CountrySubentity')
        cbc_CountrySubentity.text = 'Bogotá'
        cbc_CountrySubentityCode = ElementTree.SubElement(
            cac_Address, 'cbc:CountrySubentityCode')
        cbc_CountrySubentityCode.text = '11'
        cac_AddressLine = ElementTree.SubElement(
            cac_Address, 'cac:AddressLine')
        cbc_Line = ElementTree.SubElement(cac_AddressLine, 'cbc:Line')
        cbc_Line.text = 'CARRERA 8 No 20-14/40'
        cac_Country = ElementTree.SubElement(cac_Address, 'cac:Country')
        cbc_IdentificationCode = ElementTree.SubElement(
            cac_Country, 'cbc:IdentificationCode')
        cbc_IdentificationCode.text = 'CO'
        cbc_Name = ElementTree.SubElement(
            cac_Country, 'cbc:Name', languageID="es")
        cbc_Name.text = 'Colombia'

        # Agregar subelemento cac:PartyTaxScheme
        cac_PartyTaxScheme = ElementTree.SubElement(
            cac_Party, 'cac:PartyTaxScheme')
        cbc_RegistrationName = ElementTree.SubElement(
            cac_PartyTaxScheme, 'cbc:RegistrationName')
        cbc_RegistrationName.text = 'OPTICAS GMO COLOMBIA S A S'
        cbc_CompanyID = ElementTree.SubElement(cac_PartyTaxScheme, 'cbc:CompanyID', schemeAgencyID="195",
                                               schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)", schemeID="3", schemeName="31")
        cbc_CompanyID.text = '900108281'
        cbc_TaxLevelCode = ElementTree.SubElement(
            cac_PartyTaxScheme, 'cbc:TaxLevelCode', listName="04")
        cbc_TaxLevelCode.text = 'O-99'
        cac_RegistrationAddress = ElementTree.SubElement(
            cac_PartyTaxScheme, 'cac:RegistrationAddress')
        cbc_ID = ElementTree.SubElement(cac_RegistrationAddress, 'cbc:ID')
        cbc_ID.text = '11001'
        cbc_CityName = ElementTree.SubElement(
            cac_RegistrationAddress, 'cbc:CityName')
        cbc_CityName.text = 'Bogotá, D.C.'
        cbc_CountrySubentity = ElementTree.SubElement(
            cac_RegistrationAddress, 'cbc:CountrySubentity')
        cbc_CountrySubentity.text = 'Bogotá'
        cbc_CountrySubentityCode = ElementTree.SubElement(
            cac_RegistrationAddress, 'cbc:CountrySubentityCode')
        cbc_CountrySubentityCode.text = '11'
        cac_AddressLine = ElementTree.SubElement(
            cac_RegistrationAddress, 'cac:AddressLine')
        cbc_Line = ElementTree.SubElement(cac_AddressLine, 'cbc:Line')
        cbc_Line.text = 'CR 9 A N0 99 - 07 OF 802'
        cac_Country = ElementTree.SubElement(
            cac_RegistrationAddress, 'cac:Country')
        cbc_IdentificationCode = ElementTree.SubElement(
            cac_Country, 'cbc:IdentificationCode')
        cbc_IdentificationCode.text = 'CO'
        cbc_Name = ElementTree.SubElement(
            cac_Country, 'cbc:Name', languageID="es")
        cbc_Name.text = 'Colombia'
        cac_TaxScheme = ElementTree.SubElement(
            cac_PartyTaxScheme, 'cac:TaxScheme')
        cbc_ID = ElementTree.SubElement(cac_TaxScheme, 'cbc:ID')
        cbc_ID.text = 'ZZ'
        cbc_Name = ElementTree.SubElement(cac_TaxScheme, 'cbc:Name')
        cbc_Name.text = 'NO CAUSA'

        # Agregar subelemento cac:PartyLegalEntity
        cac_PartyLegalEntity = ElementTree.SubElement(
            cac_Party, 'cac:PartyLegalEntity')
        cbc_RegistrationName = ElementTree.SubElement(
            cac_PartyLegalEntity, 'cbc:RegistrationName')
        cbc_RegistrationName.text = 'OPTICAS GMO COLOMBIA S A S'
        cbc_CompanyID = ElementTree.SubElement(cac_PartyLegalEntity, 'cbc:CompanyID', schemeAgencyID="195",
                                               schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)", schemeID="3", schemeName="31")
        cbc_CompanyID.text = '900108281'

        taxes = [
            ('IVA', '01', '19.00'),
            ('IVA', '01', '16.00'),
            ('ICA', '03', '0.00'),
            ('INC', '04', '0.00'),
        ]

        # Agregar más impuestos según sea necesario
        for tax_percent in taxes:
            if 10 != 0.0:
                cac_TaxTotal = ElementTree.SubElement(root, 'cac:TaxTotal')
                cbc_TaxAmount = ElementTree.SubElement(
                    cac_TaxTotal, 'cbc:TaxAmount', currencyID="COP")
                cbc_TaxAmount.text = str(1)

                cac_TaxCategory = ElementTree.SubElement(
                    cac_TaxTotal, 'cac:TaxCategory')
                cbc_Percent = ElementTree.SubElement(
                    cac_TaxCategory, 'cbc:Percent')
                cbc_Percent.text = '10'
                cac_TaxScheme = ElementTree.SubElement(
                    cac_TaxCategory, 'cac:TaxScheme')
                cbc_ID = ElementTree.SubElement(cac_TaxScheme, 'cbc:ID')
                cbc_ID.text = '1'
                cbc_Name = ElementTree.SubElement(cac_TaxScheme, 'cbc:Name')
                cbc_Name.text = '1'

        cac_LegalMonetaryTotal = ElementTree.SubElement(
            root, 'cac:LegalMonetaryTotal')
        cbc_LineExtensionAmount = ElementTree.SubElement(
            cac_LegalMonetaryTotal, 'cbc:LineExtensionAmount', currencyID="COP")
        cbc_LineExtensionAmount.text = "12600.06"
        cbc_TaxExclusiveAmount = ElementTree.SubElement(
            cac_LegalMonetaryTotal, 'cbc:TaxExclusiveAmount', currencyID="COP")
        cbc_TaxExclusiveAmount.text = "12787.56"
        cbc_TaxInclusiveAmount = ElementTree.SubElement(
            cac_LegalMonetaryTotal, 'cbc:TaxInclusiveAmount', currencyID="COP")
        cbc_TaxInclusiveAmount.text = "15024.07"
        cbc_AllowanceTotalAmount = ElementTree.SubElement(
            cac_LegalMonetaryTotal, 'cbc:AllowanceTotalAmount', currencyID="COP")
        cbc_AllowanceTotalAmount.text = "0.00"
        cbc_PrepaidAmount = ElementTree.SubElement(
            cac_LegalMonetaryTotal, 'cbc:PrepaidAmount', currencyID="COP")
        cbc_PrepaidAmount.text = "0.00"
        cbc_PayableAmount = ElementTree.SubElement(
            cac_LegalMonetaryTotal, 'cbc:PayableAmount', currencyID="COP")
        cbc_PayableAmount.text = "15024.07"

        for producto in taxes:
            cac_InvoiceLine = ElementTree.SubElement(root, 'cac:InvoiceLine')
            cbc_ID = ElementTree.SubElement(cac_InvoiceLine, 'cbc:ID')
            cbc_ID.text = "1"
            cbc_InvoicedQuantity = ElementTree.SubElement(
                cac_InvoiceLine, 'cbc:InvoicedQuantity', unitCode="EA")
            cbc_InvoicedQuantity.text = "1.000000"
            cbc_LineExtensionAmount = ElementTree.SubElement(
                cac_InvoiceLine, 'cbc:LineExtensionAmount', currencyID="COP")
            cbc_LineExtensionAmount.text = "12600.06"
            cbc_FreeOfChargeIndicator = ElementTree.SubElement(
                cac_InvoiceLine, 'cbc:FreeOfChargeIndicator')
            cbc_FreeOfChargeIndicator.text = "false"

            cac_AllowanceCharge = ElementTree.SubElement(
                cac_InvoiceLine, 'cac:AllowanceCharge')
            cbc_ID = ElementTree.SubElement(cac_AllowanceCharge, 'cbc:ID')
            cbc_ID.text = "1"
            cbc_ChargeIndicator = ElementTree.SubElement(
                cac_AllowanceCharge, 'cbc:ChargeIndicator')
            cbc_ChargeIndicator.text = "false"
            cbc_AllowanceChargeReason = ElementTree.SubElement(
                cac_AllowanceCharge, 'cbc:AllowanceChargeReason')
            cbc_AllowanceChargeReason.text = "Descuento por cliente frecuente"
            cbc_MultiplierFactorNumeric = ElementTree.SubElement(
                cac_AllowanceCharge, 'cbc:MultiplierFactorNumeric')
            cbc_MultiplierFactorNumeric.text = "33.33"
            cbc_Amount = ElementTree.SubElement(
                cac_AllowanceCharge, 'cbc:Amount', currencyID="COP")
            cbc_Amount.text = "6299.94"
            cbc_BaseAmount = ElementTree.SubElement(
                cac_AllowanceCharge, 'cbc:BaseAmount', currencyID="COP")
            cbc_BaseAmount.text = "18900.00"

            cac_TaxTotal = ElementTree.SubElement(
                cac_InvoiceLine, 'cac:TaxTotal')
            cbc_TaxAmount = ElementTree.SubElement(
                cac_TaxTotal, 'cbc:TaxAmount', currencyID="COP")
            cbc_TaxAmount.text = "2394.01"
            cac_TaxSubtotal = ElementTree.SubElement(
                cac_TaxTotal, 'cac:TaxSubtotal')
            cbc_TaxableAmount = ElementTree.SubElement(
                cac_TaxSubtotal, 'cbc:TaxableAmount', currencyID="COP")
            cbc_TaxableAmount.text = "12600.06"
            cbc_TaxAmount = ElementTree.SubElement(
                cac_TaxSubtotal, 'cbc:TaxAmount', currencyID="COP")
            cbc_TaxAmount.text = "2394.01"
            cac_TaxCategory = ElementTree.SubElement(
                cac_TaxSubtotal, 'cac:TaxCategory')
            cbc_Percent = ElementTree.SubElement(
                cac_TaxCategory, 'cbc:Percent')
            cbc_Percent.text = "19.00"
            cac_TaxScheme = ElementTree.SubElement(
                cac_TaxCategory, 'cac:TaxScheme')
            cbc_ID = ElementTree.SubElement(cac_TaxScheme, 'cbc:ID')
            cbc_ID.text = "01"
            cbc_Name = ElementTree.SubElement(cac_TaxScheme, 'cbc:Name')
            cbc_Name.text = "IVA"

            cac_Item = ElementTree.SubElement(cac_InvoiceLine, 'cac:Item')
            cbc_Description = ElementTree.SubElement(
                cac_Item, 'cbc:Description')
            cbc_Description.text = "AV OASYS -2.25 (8.4) LENTE DE CONTATO"
            cac_SellersItemIdentification = ElementTree.SubElement(
                cac_Item, 'cac:SellersItemIdentification')
            cbc_ID = ElementTree.SubElement(
                cac_SellersItemIdentification, 'cbc:ID')
            cbc_ID.text = "AOHV84-225"
            cac_AdditionalItemIdentification = ElementTree.SubElement(
                cac_Item, 'cac:AdditionalItemIdentification')
            cbc_ID = ElementTree.SubElement(
                cac_AdditionalItemIdentification, 'cbc:ID', schemeID="999", schemeName="EAN13")
            cbc_ID.text = "6543542313534"

            cac_Price = ElementTree.SubElement(cac_InvoiceLine, 'cac:Price')
            cbc_PriceAmount = ElementTree.SubElement(
                cac_Price, 'cbc:PriceAmount', currencyID="COP")
            cbc_PriceAmount.text = "18900.00"
            cbc_BaseQuantity = ElementTree.SubElement(
                cac_Price, 'cbc:BaseQuantity', unitCode="EA")
            cbc_BaseQuantity.text = "1.000000"

        # ElementTree.SubElement(xml_tax_info, 'ambiente').text = str(self.company.environment_type)
        # ElementTree.SubElement(xml_tax_info, 'tipoEmision').text = str(self.company.emission_type)
        # ElementTree.SubElement(xml_tax_info, 'razonSocial').text = self.company.business_name
        # ElementTree.SubElement(xml_tax_info, 'nombreComercial').text = self.company.tradename
        # ElementTree.SubElement(xml_tax_info, 'ruc').text = self.company.ruc
        # ElementTree.SubElement(xml_tax_info, 'claveAcceso').text = access_key
        # ElementTree.SubElement(xml_tax_info, 'codDoc').text = self.receipt.code
        # ElementTree.SubElement(xml_tax_info, 'estab').text = self.company.establishment_code
        # ElementTree.SubElement(xml_tax_info, 'ptoEmi').text = self.company.issuing_point_code
        # ElementTree.SubElement(xml_tax_info, 'secuencial').text = self.voucher_number
        # ElementTree.SubElement(xml_tax_info, 'dirMatriz').text = self.company.main_address
        # infoFactura

        # xml_info_invoice = ElementTree.SubElement(root, 'infoFactura')
        # ElementTree.SubElement(xml_info_invoice, 'fechaEmision').text = datetime.now().strftime('%d/%m/%Y')
        # ElementTree.SubElement(xml_info_invoice, 'dirEstablecimiento').text = self.company.establishment_address
        # ElementTree.SubElement(xml_info_invoice, 'obligadoContabilidad').text = self.company.obligated_accounting
        # ElementTree.SubElement(xml_info_invoice, 'tipoIdentificacionComprador').text = self.client.identification_type
        # ElementTree.SubElement(xml_info_invoice, 'razonSocialComprador').text = self.client.user.names
        # ElementTree.SubElement(xml_info_invoice, 'identificacionComprador').text = self.client.dni
        # ElementTree.SubElement(xml_info_invoice, 'direccionComprador').text = self.client.address
        # ElementTree.SubElement(xml_info_invoice, 'totalSinImpuestos').text = f'{self.get_full_subtotal():.2f}'
        # ElementTree.SubElement(xml_info_invoice, 'totalDescuento').text = f'{self.total_dscto:.2f}'
        # # totalConImpuestos
        # xml_total_with_taxes = ElementTree.SubElement(xml_info_invoice, 'totalConImpuestos')
        # # totalImpuesto
        # if self.subtotal_0 != 0.0000:
        #     xml_total_tax_0 = ElementTree.SubElement(xml_total_with_taxes, 'totalImpuesto')
        #     ElementTree.SubElement(xml_total_tax_0, 'codigo').text = str(TAX_CODES[0][0])
        #     ElementTree.SubElement(xml_total_tax_0, 'codigoPorcentaje').text = '0'
        #     ElementTree.SubElement(xml_total_tax_0, 'baseImponible').text = f'{self.subtotal_0:.2f}'
        #     ElementTree.SubElement(xml_total_tax_0, 'valor').text = '0.00'
        # if self.subtotal_12 != 0.0000:
        #     xml_total_tax12 = ElementTree.SubElement(xml_total_with_taxes, 'totalImpuesto')
        #     ElementTree.SubElement(xml_total_tax12, 'codigo').text = str(TAX_CODES[0][0])
        #     ElementTree.SubElement(xml_total_tax12, 'codigoPorcentaje').text = str(TAX_CODES[0][0])
        #     ElementTree.SubElement(xml_total_tax12, 'baseImponible').text = f'{self.subtotal_12:.2f}'
        #     ElementTree.SubElement(xml_total_tax12, 'valor').text = f'{self.total_iva:.2f}'
        # ElementTree.SubElement(xml_info_invoice, 'propina').text = '0.00'
        # ElementTree.SubElement(xml_info_invoice, 'importeTotal').text = f'{self.total:.2f}'
        # ElementTree.SubElement(xml_info_invoice, 'moneda').text = 'DOLAR'
        # # pagos
        # xml_payments = ElementTree.SubElement(xml_info_invoice, 'pagos')
        # xml_payment = ElementTree.SubElement(xml_payments, 'pago')
        # ElementTree.SubElement(xml_payment, 'formaPago').text = self.payment_method
        # ElementTree.SubElement(xml_payment, 'total').text = f'{self.total:.2f}'
        # ElementTree.SubElement(xml_payment, 'plazo').text = str(self.time_limit)
        # ElementTree.SubElement(xml_payment, 'unidadTiempo').text = 'dias'

        # # detalles

        # xml_details = ElementTree.SubElement(root, 'detalles')
        # for detail in self.saledetail_set.all():
        #     xml_detail = ElementTree.SubElement(xml_details, 'detalle')
        #     ElementTree.SubElement(xml_detail, 'codigoPrincipal').text = detail.product.code
        #     ElementTree.SubElement(xml_detail, 'descripcion').text = detail.product.name
        #     ElementTree.SubElement(xml_detail, 'cantidad').text = f'{detail.cant:.2f}'
        #     ElementTree.SubElement(xml_detail, 'precioUnitario').text = f'{detail.price:.2f}'
        #     ElementTree.SubElement(xml_detail, 'descuento').text = f'{detail.total_dscto:.2f}'
        #     ElementTree.SubElement(xml_detail, 'precioTotalSinImpuesto').text = f'{detail.total:.2f}'
        #     xml_taxes = ElementTree.SubElement(xml_detail, 'impuestos')
        #     xml_tax = ElementTree.SubElement(xml_taxes, 'impuesto')
        #     ElementTree.SubElement(xml_tax, 'codigo').text = str(TAX_CODES[0][0])
        #     if detail.product.with_tax:
        #         ElementTree.SubElement(xml_tax, 'codigoPorcentaje').text = str(TAX_CODES[0][0])
        #         ElementTree.SubElement(xml_tax, 'tarifa').text = f'{detail.iva * 100:.2f}'
        #         ElementTree.SubElement(xml_tax, 'baseImponible').text = f'{detail.total:.2f}'
        #         ElementTree.SubElement(xml_tax, 'valor').text = f'{detail.total_iva:.2f}'
        #     else:
        #         ElementTree.SubElement(xml_tax, 'codigoPorcentaje').text = "0"
        #         ElementTree.SubElement(xml_tax, 'tarifa').text = "0"
        #         ElementTree.SubElement(xml_tax, 'baseImponible').text = f'{detail.total:.2f}'
        #         ElementTree.SubElement(xml_tax, 'valor').text = "0"
        # # infoAdicional
        # if len(self.additional_info):
        #     xml_additional_info = ElementTree.SubElement(root, 'infoAdicional')
        #     for additional_info in self.additional_info['rows']:
        #         ElementTree.SubElement(xml_additional_info, 'campoAdicional', nombre=additional_info['name']).text = additional_info['value']
        # print(ElementTree.tostring(root, xml_declaration=True, encoding='utf-8').decode('utf-8').replace("'", '"'), access_key)
        return ElementTree.tostring(root, xml_declaration=True, encoding='utf-8').decode('utf-8').replace("'", '"'), access_key

    def is_invoice(self):
        return self.receipt.code == VOUCHER_TYPE[0][0]

    def toJSON(self):
        item = model_to_dict(self)
        item['company'] = self.company.toJSON()
        item['client'] = self.client.toJSON()
        item['receipt'] = self.receipt.toJSON()
        item['employee'] = self.employee.toJSON()
        item['payment_type'] = {'id': self.payment_type,
                                'name': self.get_payment_type_display()}
        item['payment_method'] = {
            'id': self.payment_method, 'name': self.get_payment_method_display()}
        item['creation_date'] = self.creation_date.strftime(
            '%Y-%m-%d %H:%M:%S')
        item['date_joined'] = self.date_joined.strftime('%Y-%m-%d')
        item['end_credit'] = self.end_credit.strftime('%Y-%m-%d')
        item['subtotal_0'] = float(self.subtotal_0)
        item['subtotal_12'] = float(self.subtotal_12)
        item['subtotal'] = self.get_full_subtotal()
        item['total_dscto'] = float(self.total_dscto)
        item['iva'] = float(self.iva)
        item['total_iva'] = float(self.total_iva)
        item['total'] = float(self.total)
        item['cash'] = float(self.cash)
        item['change'] = float(self.change)
        item['environment_type'] = {
            'id': self.environment_type, 'name': self.get_environment_type_display()}
        item['authorization_date'] = '' if self.authorization_date is None else self.authorization_date.strftime(
            '%Y-%m-%d')
        item['xml_authorized'] = self.get_xml_authorized()
        item['pdf_authorized'] = self.get_pdf_authorized()
        item['status'] = {'id': self.status, 'name': self.get_status_display()}
        return item

    def calculate_detail(self):
        for detail in self.saledetail_set.filter():
            detail.price = float(detail.price)
            detail.iva = float(self.iva)
            detail.price_with_vat = detail.price + (detail.price * detail.iva)
            detail.subtotal = detail.price * detail.cant
            detail.total_dscto = detail.subtotal * float(detail.dscto)
            detail.total_iva = (
                                       detail.subtotal - detail.total_dscto) * detail.iva
            detail.total = detail.subtotal - detail.total_dscto
            detail.save()

    def calculate_invoice(self):
        self.subtotal_0 = float(self.saledetail_set.filter(product__with_tax=False).aggregate(
            result=Coalesce(Sum('total'), 0.00, output_field=FloatField()))['result'])
        self.subtotal_12 = float(self.saledetail_set.filter(product__with_tax=True).aggregate(
            result=Coalesce(Sum('total'), 0.00, output_field=FloatField()))['result'])
        self.total_iva = float(self.saledetail_set.filter(product__with_tax=True).aggregate(
            result=Coalesce(Sum('total_iva'), 0.00, output_field=FloatField()))['result'])
        self.total_dscto = float(self.saledetail_set.filter().aggregate(
            result=Coalesce(Sum('total_dscto'), 0.00, output_field=FloatField()))['result'])
        self.total = float(self.get_full_subtotal()) + float(self.total_iva)
        self.save()

    def save(self, force_insert=False, force_update=False, using=None,
             update_fields=None):
        if self.pk is None:
            self.receipt.current_number = int(self.voucher_number)
            self.receipt.save()
        super(Sale, self).save()

    def delete(self, using=None, keep_parents=False):
        try:
            for i in self.saledetail_set.filter(product__inventoried=True):
                i.product.stock += i.cant
                i.product.save()
                i.delete()
        except:
            pass
        super(Sale, self).delete()

    def generate_electronic_invoice(self):
        sri = SRI()
        result = sri.create_xml(self)
        print(result)
        if result['resp']:
            result = sri.firm_xml(instance=self, xml=result['xml'])
            print(result)
            if result['resp']:
                result = sri.validate_xml(instance=self, xml=result['xml'])
                if result['resp']:
                    result = sri.authorize_xml(instance=self)
                    index = 1
                    while not result['resp'] and index < 3:
                        time.sleep(1)
                        result = sri.authorize_xml(instance=self)
                        index += 1
                    if result['resp']:
                        result['print_url'] = self.get_pdf_authorized()
                    return result
        return result

    class Meta:
        verbose_name = 'Venta'
        verbose_name_plural = 'Ventas'
        default_permissions = ()
        permissions = (
            ('view_sale', 'Can view Venta'),
            ('add_sale', 'Can add Venta'),
            ('delete_sale', 'Can delete Venta'),
            ('view_sale_client', 'Can view_sale_client Venta'),
        )


class SaleDetail(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    cant = models.IntegerField(default=0)
    price = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    price_with_vat = models.DecimalField(
        max_digits=9, decimal_places=2, default=0.00)
    subtotal = models.DecimalField(
        max_digits=9, decimal_places=2, default=0.00)
    iva = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    total_iva = models.DecimalField(
        max_digits=9, decimal_places=2, default=0.00)
    dscto = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    total_dscto = models.DecimalField(
        max_digits=9, decimal_places=2, default=0.00)
    total = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)

    def __str__(self):
        return self.product.name

    def get_iva_percent(self):
        return int(self.iva * 100)

    def toJSON(self, args=None):
        item = model_to_dict(self, exclude=['sale'])
        item['product'] = self.product.toJSON()
        item['price'] = float(self.price)
        item['price_with_vat'] = float(self.price_with_vat)
        item['subtotal'] = float(self.subtotal)
        item['iva'] = float(self.subtotal)
        item['total_iva'] = float(self.subtotal)
        item['dscto'] = float(self.dscto) * 100
        item['total_dscto'] = float(self.total_dscto)
        item['total'] = float(self.total)
        if args is not None:
            item.update(args)
        return item

    class Meta:
        verbose_name = 'Detalle de Venta'
        verbose_name_plural = 'Detalle de Ventas'
        default_permissions = ()


class CtasCollect(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT)
    date_joined = models.DateField(default=timezone.now)
    end_date = models.DateField(default=timezone.now)
    debt = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    saldo = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    state = models.BooleanField(default=True)

    def __str__(self):
        return self.get_full_name()

    def get_full_name(self):
        return f"{self.sale.client.user.names} ({self.sale.client.dni}) / {self.date_joined.strftime('%Y-%m-%d')} / ${f'{self.debt:.2f}'}"

    def validate_debt(self):
        try:
            saldo = self.paymentsctacollect_set.aggregate(result=Coalesce(
                Sum('valor'), 0.00, output_field=FloatField()))['result']
            self.saldo = float(self.debt) - float(saldo)
            self.state = self.saldo > 0.00
            self.save()
        except:
            pass

    def toJSON(self):
        item = model_to_dict(self)
        item['sale'] = self.sale.toJSON()
        item['date_joined'] = self.date_joined.strftime('%Y-%m-%d')
        item['end_date'] = self.end_date.strftime('%Y-%m-%d')
        item['debt'] = float(self.debt)
        item['saldo'] = float(self.saldo)
        return item

    class Meta:
        verbose_name = 'Cuenta por cobrar'
        verbose_name_plural = 'Cuentas por cobrar'
        default_permissions = ()
        permissions = (
            ('view_ctas_collect', 'Can view Cuenta por cobrar'),
            ('add_ctas_collect', 'Can add Cuenta por cobrar'),
            ('delete_ctas_collect', 'Can delete Cuenta por cobrar'),
        )


class PaymentsCtaCollect(models.Model):
    ctas_collect = models.ForeignKey(
        CtasCollect, on_delete=models.CASCADE, verbose_name='Cuenta por cobrar')
    date_joined = models.DateField(
        default=datetime.now, verbose_name='Fecha de registro')
    description = models.CharField(
        max_length=500, null=True, blank=True, verbose_name='Detalles')
    valor = models.DecimalField(
        max_digits=9, decimal_places=2, default=0.00, verbose_name='Valor')

    def __str__(self):
        return self.ctas_collect.id

    def toJSON(self):
        item = model_to_dict(self, exclude=['ctas_collect'])
        item['date_joined'] = self.date_joined.strftime('%Y-%m-%d')
        item['valor'] = float(self.valor)
        return item

    def save(self, force_insert=False, force_update=False, using=None,
             update_fields=None):
        if self.description is None:
            self.description = 's/n'
        elif len(self.description) == 0:
            self.description = 's/n'
        super(PaymentsCtaCollect, self).save()

    class Meta:
        verbose_name = 'Pago Cuenta por cobrar'
        verbose_name_plural = 'Pagos Cuentas por cobrar'
        default_permissions = ()


class DebtsPay(models.Model):
    purchase = models.ForeignKey(Purchase, on_delete=models.PROTECT)
    date_joined = models.DateField(default=timezone.now)
    end_date = models.DateField(default=timezone.now)
    debt = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    saldo = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    state = models.BooleanField(default=True)

    def __str__(self):
        return self.get_full_name()

    def get_full_name(self):
        return f"{self.purchase.provider.name} ({self.purchase.number}) / {self.date_joined.strftime('%Y-%m-%d')} / ${f'{self.debt:.2f}'}"

    def validate_debt(self):
        try:
            saldo = self.paymentsdebtspay_set.aggregate(result=Coalesce(
                Sum('valor'), 0.00, output_field=FloatField()))['result']
            self.saldo = float(self.debt) - float(saldo)
            self.state = self.saldo > 0.00
            self.save()
        except:
            pass

    def toJSON(self):
        item = model_to_dict(self)
        item['purchase'] = self.purchase.toJSON()
        item['date_joined'] = self.date_joined.strftime('%Y-%m-%d')
        item['end_date'] = self.end_date.strftime('%Y-%m-%d')
        item['debt'] = float(self.debt)
        item['saldo'] = float(self.saldo)
        return item

    class Meta:
        verbose_name = 'Cuenta por pagar'
        verbose_name_plural = 'Cuentas por pagar'
        default_permissions = ()
        permissions = (
            ('view_debts_pay', 'Can view Cuenta por pagar'),
            ('add_debts_pay', 'Can add Cuenta por pagar'),
            ('delete_debts_pay', 'Can delete Cuenta por pagar'),
        )


class PaymentsDebtsPay(models.Model):
    debts_pay = models.ForeignKey(
        DebtsPay, on_delete=models.CASCADE, verbose_name='Cuenta por pagar')
    date_joined = models.DateField(
        default=timezone.now, verbose_name='Fecha de registro')
    description = models.CharField(
        max_length=500, null=True, blank=True, verbose_name='Detalles')
    valor = models.DecimalField(
        max_digits=9, decimal_places=2, default=0.00, verbose_name='Valor')

    def __str__(self):
        return self.debts_pay.id

    def toJSON(self):
        item = model_to_dict(self, exclude=['debts_pay'])
        item['date_joined'] = self.date_joined.strftime('%Y-%m-%d')
        item['valor'] = float(self.valor)
        return item

    def save(self, force_insert=False, force_update=False, using=None,
             update_fields=None):
        if self.description is None:
            self.description = 's/n'
        elif len(self.description) == 0:
            self.description = 's/n'
        super(PaymentsDebtsPay, self).save()

    class Meta:
        verbose_name = 'Det. Cuenta por pagar'
        verbose_name_plural = 'Det. Cuentas por pagar'
        default_permissions = ()


class TypeExpense(models.Model):
    name = models.CharField(max_length=50, unique=True, verbose_name='Nombre')

    def __str__(self):
        return self.name

    def toJSON(self):
        item = model_to_dict(self)
        return item

    class Meta:
        verbose_name = 'Tipo de Gasto'
        verbose_name_plural = 'Tipos de Gastos'
        default_permissions = ()
        permissions = (
            ('view_type_expense', 'Can view Tipo de Gasto'),
            ('add_type_expense', 'Can add Tipo de Gasto'),
            ('change_type_expense', 'Can change Tipo de Gasto'),
            ('delete_type_expense', 'Can delete Tipo de Gasto'),
        )


class Expenses(models.Model):
    type_expense = models.ForeignKey(
        TypeExpense, on_delete=models.PROTECT, verbose_name='Tipo de Gasto')
    description = models.CharField(
        max_length=500, null=True, blank=True, verbose_name='Descripción')
    date_joined = models.DateField(
        default=timezone.now, verbose_name='Fecha de Registro')
    valor = models.DecimalField(
        max_digits=9, decimal_places=2, default=0.00, verbose_name='Valor')

    def __str__(self):
        return self.description

    def toJSON(self):
        item = model_to_dict(self)
        item['type_expense'] = self.type_expense.toJSON()
        item['date_joined'] = self.date_joined.strftime('%Y-%m-%d')
        item['valor'] = float(self.valor)
        return item

    def save(self, force_insert=False, force_update=False, using=None,
             update_fields=None):
        if self.description is None:
            self.description = 's/n'
        elif len(self.description) == 0:
            self.description = 's/n'
        super(Expenses, self).save()

    class Meta:
        verbose_name = 'Gasto'
        verbose_name_plural = 'Gastos'


class Promotions(models.Model):
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(default=timezone.now)
    state = models.BooleanField(default=True)

    def __str__(self):
        return str(self.id)

    def toJSON(self):
        item = model_to_dict(self)
        item['start_date'] = self.start_date.strftime('%Y-%m-%d')
        item['end_date'] = self.end_date.strftime('%Y-%m-%d')
        return item

    class Meta:
        verbose_name = 'Promoción'
        verbose_name_plural = 'Promociones'


class PromotionsDetail(models.Model):
    promotion = models.ForeignKey(Promotions, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    price_current = models.DecimalField(
        max_digits=9, decimal_places=2, default=0.00)
    dscto = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    total_dscto = models.DecimalField(
        max_digits=9, decimal_places=2, default=0.00)
    price_final = models.DecimalField(
        max_digits=9, decimal_places=2, default=0.00)

    def __str__(self):
        return self.product.name

    def get_dscto_real(self):
        total_dscto = float(self.price_current) * float(self.dscto)
        n = 2
        return math.floor(total_dscto * 10 ** n) / 10 ** n

    def toJSON(self):
        item = model_to_dict(self, exclude=['promotion'])
        item['product'] = self.product.toJSON()
        item['price_current'] = float(self.price_current)
        item['dscto'] = float(self.dscto)
        item['total_dscto'] = float(self.total_dscto)
        item['price_final'] = float(self.price_final)
        return item

    class Meta:
        verbose_name = 'Detalle Promoción'
        verbose_name_plural = 'Detalle de Promociones'
        default_permissions = ()


class VoucherErrors(models.Model):
    date_joined = models.DateField(default=timezone.now)
    datetime_joined = models.DateTimeField(default=timezone.now)
    environment_type = models.PositiveIntegerField(
        choices=ENVIRONMENT_TYPE, default=ENVIRONMENT_TYPE[0][0])
    reference = models.CharField(max_length=20)
    receipt = models.ForeignKey(Receipt, on_delete=models.CASCADE)
    stage = models.CharField(
        max_length=20, choices=VOUCHER_STAGE, default=VOUCHER_STAGE[0][0])
    errors = models.JSONField(default=dict)

    def __str__(self):
        return self.stage

    def toJSON(self):
        item = model_to_dict(self)
        item['receipt'] = self.receipt.toJSON()
        item['environment_type'] = {
            'id': self.environment_type, 'name': self.get_environment_type_display()}
        item['stage'] = {'id': self.stage, 'name': self.get_stage_display()}
        item['date_joined'] = self.date_joined.strftime('%Y-%m-%d')
        item['datetime_joined'] = self.datetime_joined.strftime(
            '%Y-%m-%d %H:%M')
        return item

    class Meta:
        verbose_name = 'Errores del Comprobante'
        verbose_name_plural = 'Errores de los Comprobantes'
        default_permissions = ()
        permissions = (
            ('view_voucher_errors', 'Can view Errores del Comprobante'),
            ('delete_voucher_errors', 'Can delete Errores del Comprobante'),
        )


class CreditNote(models.Model):
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, verbose_name='Compañia')
    sale = models.ForeignKey(
        Sale, on_delete=models.PROTECT, verbose_name='Venta')
    date_joined = models.DateField(
        default=datetime.now, verbose_name='Fecha de registro')
    motive = models.CharField(
        max_length=300, null=True, blank=True, verbose_name='Motivo')
    receipt = models.ForeignKey(
        Receipt, on_delete=models.PROTECT, verbose_name='Tipo de comprobante')
    voucher_number = models.CharField(
        max_length=9, verbose_name='Número de comprobante')
    voucher_number_full = models.CharField(
        max_length=20, verbose_name='Número de comprobante completo')
    subtotal_12 = models.DecimalField(
        max_digits=9, decimal_places=2, default=0.00, verbose_name='Subtotal 19%')
    subtotal_0 = models.DecimalField(
        max_digits=9, decimal_places=2, default=0.00, verbose_name='Subtotal 0%')
    total_dscto = models.DecimalField(
        max_digits=9, decimal_places=2, default=0.00, verbose_name='Valor del descuento')
    iva = models.DecimalField(
        max_digits=9, decimal_places=2, default=0.00, verbose_name='Iva')
    total_iva = models.DecimalField(
        max_digits=9, decimal_places=2, default=0.00, verbose_name='Valor de iva')
    total = models.DecimalField(
        max_digits=9, decimal_places=2, default=0.00, verbose_name='Total a pagar')
    environment_type = models.PositiveIntegerField(
        choices=ENVIRONMENT_TYPE, default=ENVIRONMENT_TYPE[0][0])
    access_code = models.CharField(
        max_length=49, null=True, blank=True, verbose_name='Clave de acceso')
    authorization_date = models.DateTimeField(
        null=True, blank=True, verbose_name='Fecha de autorización')
    xml_authorized = CustomFileField(
        null=True, blank=True, verbose_name='XML Autorizado')
    pdf_authorized = CustomFileField(
        upload_to='pdf_authorized', verbose_name='PDF Autorizado')
    create_electronic_invoice = models.BooleanField(
        default=True, verbose_name='Crear factura electrónica')
    status = models.CharField(max_length=50, choices=INVOICE_STATUS,
                              default=INVOICE_STATUS[0][0], verbose_name='Estado')

    def __str__(self):
        return self.motive

    def get_iva_percent(self):
        return int(self.iva * 100)

    def get_full_subtotal(self):
        return float(self.subtotal_0) + float(self.subtotal_12)

    def get_subtotal_without_taxes(self):
        return float(self.creditnotedetail_set.filter().aggregate(result=Coalesce(Sum('subtotal'), 0.00, output_field=FloatField()))['result'])

    def get_authorization_date(self):
        return self.authorization_date.strftime('%Y-%m-%d %H:%M:%S')

    def get_date_joined(self):
        return (datetime.strptime(self.date_joined, '%Y-%m-%d') if isinstance(self.date_joined, str) else self.date_joined).strftime('%Y-%m-%d')

    def get_xml_authorized(self):
        if self.xml_authorized:
            return f'{settings.MEDIA_URL}/{self.xml_authorized}'
        return None

    def get_pdf_authorized(self):
        if self.pdf_authorized:
            return f'{settings.MEDIA_URL}/{self.pdf_authorized}'
        return None

    def get_voucher_number_full(self):
        return f'{self.company.establishment_code}-{self.company.issuing_point_code}-{self.voucher_number}'

    def generate_voucher_number(self):
        number = int(self.receipt.get_current_number()) + 1
        return f'{number:09d}'

    def generate_voucher_number_full(self):
        request = get_current_request()
        self.company = request.tenant.company
        self.receipt = Receipt.objects.get(code=VOUCHER_TYPE[2][0])
        self.voucher_number = self.generate_voucher_number()
        return self.get_voucher_number_full()

    def generate_pdf_authorized(self):
        rv = BytesIO()
        barcode.Code128(self.access_code,
                        writer=barcode.writer.ImageWriter()).write(rv)
        file = base64.b64encode(rv.getvalue()).decode("ascii")
        context = {'credit_note': self,
                   'access_code_barcode': f"data:image/png;base64,{file}"}
        pdf_file = printer.create_pdf(
            context=context, template_name='credit_note/format/invoice.html')
        with tempfile.NamedTemporaryFile(delete=True) as file_temp:
            file_temp.write(pdf_file)
            file_temp.flush()
            self.pdf_authorized.save(
                name=f'{self.receipt.get_name_xml()}_{self.access_code}.pdf', content=File(file_temp))

    def generate_xml(self):
        access_key = SRI().create_access_key(self)
        root = ElementTree.Element(
            'notaCredito', id="comprobante", version="1.1.0")
        # infoTributaria
        xml_tax_info = ElementTree.SubElement(root, 'infoTributaria')
        ElementTree.SubElement(xml_tax_info, 'ambiente').text = str(
            self.company.environment_type)
        ElementTree.SubElement(xml_tax_info, 'tipoEmision').text = str(
            self.company.emission_type)
        ElementTree.SubElement(
            xml_tax_info, 'razonSocial').text = self.company.business_name
        ElementTree.SubElement(
            xml_tax_info, 'nombreComercial').text = self.company.tradename
        ElementTree.SubElement(xml_tax_info, 'ruc').text = self.company.ruc
        ElementTree.SubElement(xml_tax_info, 'claveAcceso').text = access_key
        ElementTree.SubElement(xml_tax_info, 'codDoc').text = self.receipt.code
        ElementTree.SubElement(
            xml_tax_info, 'estab').text = self.company.establishment_code
        ElementTree.SubElement(
            xml_tax_info, 'ptoEmi').text = self.company.issuing_point_code
        ElementTree.SubElement(
            xml_tax_info, 'secuencial').text = self.voucher_number
        ElementTree.SubElement(
            xml_tax_info, 'dirMatriz').text = self.company.main_address
        if self.company.retention_agent == RETENTION_AGENT[0][0]:
            ElementTree.SubElement(xml_tax_info, 'agenteRetencion').text = '1'
        # infoNotaCredito
        xml_info_invoice = ElementTree.SubElement(root, 'infoNotaCredito')
        ElementTree.SubElement(
            xml_info_invoice, 'fechaEmision').text = datetime.now().strftime('%d/%m/%Y')
        ElementTree.SubElement(
            xml_info_invoice, 'dirEstablecimiento').text = self.company.establishment_address
        ElementTree.SubElement(
            xml_info_invoice, 'tipoIdentificacionComprador').text = self.sale.client.identification_type
        ElementTree.SubElement(
            xml_info_invoice, 'razonSocialComprador').text = self.sale.client.user.names
        ElementTree.SubElement(
            xml_info_invoice, 'identificacionComprador').text = self.sale.client.dni
        if not self.company.special_taxpayer == '000':
            ElementTree.SubElement(
                xml_info_invoice, 'contribuyenteEspecial').text = self.company.special_taxpayer
        ElementTree.SubElement(
            xml_info_invoice, 'obligadoContabilidad').text = self.company.obligated_accounting
        ElementTree.SubElement(
            xml_info_invoice, 'rise').text = 'Contribuyente Régimen Simplificado RISE'
        ElementTree.SubElement(
            xml_info_invoice, 'codDocModificado').text = self.sale.receipt.code
        ElementTree.SubElement(
            xml_info_invoice, 'numDocModificado').text = self.sale.voucher_number_full
        ElementTree.SubElement(
            xml_info_invoice, 'fechaEmisionDocSustento').text = self.sale.date_joined.strftime('%d/%m/%Y')
        ElementTree.SubElement(
            xml_info_invoice, 'totalSinImpuestos').text = f'{self.get_full_subtotal():.2f}'
        ElementTree.SubElement(
            xml_info_invoice, 'valorModificacion').text = f'{self.total:.2f}'
        ElementTree.SubElement(xml_info_invoice, 'moneda').text = 'DOLAR'
        # totalConImpuestos
        xml_total_with_taxes = ElementTree.SubElement(
            xml_info_invoice, 'totalConImpuestos')
        # totalImpuesto
        if self.subtotal_0 != 0.0000:
            xml_total_tax = ElementTree.SubElement(
                xml_total_with_taxes, 'totalImpuesto')
            ElementTree.SubElement(
                xml_total_tax, 'codigo').text = str(TAX_CODES[0][0])
            ElementTree.SubElement(
                xml_total_tax, 'codigoPorcentaje').text = '0'
            ElementTree.SubElement(
                xml_total_tax, 'baseImponible').text = f'{self.subtotal_0:.2f}'
            ElementTree.SubElement(xml_total_tax, 'valor').text = f'{0:.2f}'
        if self.subtotal_12 != 0.0000:
            xml_total_tax2 = ElementTree.SubElement(
                xml_total_with_taxes, 'totalImpuesto')
            ElementTree.SubElement(
                xml_total_tax2, 'codigo').text = str(TAX_CODES[0][0])
            ElementTree.SubElement(
                xml_total_tax2, 'codigoPorcentaje').text = str(TAX_CODES[0][0])
            ElementTree.SubElement(
                xml_total_tax2, 'baseImponible').text = f'{self.subtotal_12:.2f}'
            ElementTree.SubElement(
                xml_total_tax2, 'valor').text = f'{self.total_iva:.2f}'
        ElementTree.SubElement(xml_info_invoice, 'motivo').text = self.motive
        # detalles
        xml_details = ElementTree.SubElement(root, 'detalles')
        for detail in self.creditnotedetail_set.all():
            xml_detail = ElementTree.SubElement(xml_details, 'detalle')
            ElementTree.SubElement(
                xml_detail, 'codigoInterno').text = detail.product.code
            ElementTree.SubElement(
                xml_detail, 'descripcion').text = detail.product.name
            ElementTree.SubElement(
                xml_detail, 'cantidad').text = f'{detail.cant:.2f}'
            ElementTree.SubElement(
                xml_detail, 'precioUnitario').text = f'{detail.price:.2f}'
            ElementTree.SubElement(
                xml_detail, 'descuento').text = f'{detail.total_dscto:.2f}'
            ElementTree.SubElement(
                xml_detail, 'precioTotalSinImpuesto').text = f'{detail.total:.2f}'
            xml_taxes = ElementTree.SubElement(xml_detail, 'impuestos')
            xml_tax = ElementTree.SubElement(xml_taxes, 'impuesto')
            ElementTree.SubElement(
                xml_tax, 'codigo').text = str(TAX_CODES[0][0])
            if detail.product.with_tax:
                ElementTree.SubElement(
                    xml_tax, 'codigoPorcentaje').text = str(TAX_CODES[0][0])
                ElementTree.SubElement(
                    xml_tax, 'tarifa').text = f'{detail.iva * 100:.2f}'
                ElementTree.SubElement(
                    xml_tax, 'baseImponible').text = f'{detail.total:.2f}'
                ElementTree.SubElement(
                    xml_tax, 'valor').text = f'{detail.total_iva:.2f}'
            else:
                ElementTree.SubElement(xml_tax, 'codigoPorcentaje').text = "0"
                ElementTree.SubElement(xml_tax, 'tarifa').text = "0"
                ElementTree.SubElement(
                    xml_tax, 'baseImponible').text = f'{detail.total:.2f}'
                ElementTree.SubElement(xml_tax, 'valor').text = "0"
        # infoAdicional
        xml_additional_info = ElementTree.SubElement(root, 'infoAdicional')
        ElementTree.SubElement(xml_additional_info, 'campoAdicional',
                               nombre='dirCliente').text = self.sale.client.address
        ElementTree.SubElement(xml_additional_info, 'campoAdicional',
                               nombre='telfCliente').text = self.sale.client.mobile
        ElementTree.SubElement(xml_additional_info, 'campoAdicional',
                               nombre='Observacion').text = f'NOTA_CREDITO # {self.voucher_number}'
        return ElementTree.tostring(root, xml_declaration=True, encoding='UTF-8').decode('UTF-8').replace("'", '"'), access_key

    def toJSON(self):
        item = model_to_dict(self)
        item['date_joined'] = self.date_joined.strftime('%Y-%m-%d')
        item['sale'] = self.sale.toJSON()
        item['company'] = self.company.toJSON()
        item['receipt'] = self.receipt.toJSON()
        item['date_joined'] = self.date_joined.strftime('%Y-%m-%d')
        item['subtotal_12'] = float(self.subtotal_12)
        item['subtotal_0'] = float(self.subtotal_0)
        item['subtotal'] = self.get_full_subtotal()
        item['total_dscto'] = float(self.total_dscto)
        item['iva'] = float(self.iva)
        item['total_iva'] = float(self.total_iva)
        item['total'] = float(self.total)
        item['environment_type'] = {
            'id': self.environment_type, 'name': self.get_environment_type_display()}
        item['invoice'] = self.get_voucher_number_full()
        item['authorization_date'] = '' if self.authorization_date is None else self.authorization_date.strftime(
            '%Y-%m-%d')
        item['xml_authorized'] = self.get_xml_authorized()
        item['pdf_authorized'] = self.get_pdf_authorized()
        item['status'] = {'id': self.status, 'name': self.get_status_display()}
        return item

    def generate_electronic_invoice(self):
        sri = SRI()
        result = sri.create_xml(self)
        if result['resp']:
            result = sri.firm_xml(instance=self, xml=result['xml'])
            if result['resp']:
                result = sri.validate_xml(instance=self, xml=result['xml'])
                if result['resp']:
                    return sri.authorize_xml(instance=self)
        return result

    def calculate_detail(self):
        for detail in self.creditnotedetail_set.filter():
            detail.price = float(detail.price)
            detail.iva = float(self.iva)
            detail.price_with_vat = detail.price + (detail.price * detail.iva)
            detail.subtotal = detail.price * detail.cant
            detail.total_dscto = detail.subtotal * float(detail.dscto)
            detail.total_iva = (
                                       detail.subtotal - detail.total_dscto) * detail.iva
            detail.total = detail.subtotal - detail.total_dscto
            detail.save()

    def calculate_invoice(self):
        self.subtotal_0 = float(self.creditnotedetail_set.filter(product__with_tax=False).aggregate(
            result=Coalesce(Sum('total'), 0.00, output_field=FloatField()))['result'])
        self.subtotal_12 = float(self.creditnotedetail_set.filter(product__with_tax=True).aggregate(
            result=Coalesce(Sum('total'), 0.00, output_field=FloatField()))['result'])
        self.total_iva = float(self.creditnotedetail_set.filter(product__with_tax=True).aggregate(
            result=Coalesce(Sum('total_iva'), 0.00, output_field=FloatField()))['result'])
        self.total_dscto = float(self.creditnotedetail_set.filter().aggregate(
            result=Coalesce(Sum('total_dscto'), 0.00, output_field=FloatField()))['result'])
        self.total = float(self.get_full_subtotal()) + float(self.total_iva)
        self.save()

    def save(self, force_insert=False, force_update=False, using=None,
             update_fields=None):
        if self.motive is None:
            self.motive = 'Sin detalles'
        if self.pk is None:
            self.receipt.current_number = int(self.voucher_number)
            self.receipt.save()
        super(CreditNote, self).save()

    def delete(self, using=None, keep_parents=False):
        try:
            for i in self.creditnotedetail_set.filter(product__inventoried=True):
                i.product.stock += i.cant
                i.product.save()
                i.delete()
        except:
            pass
        super(CreditNote, self).delete()

    class Meta:
        verbose_name = 'Nota de Credito'
        verbose_name_plural = 'Notas de Credito'
        default_permissions = ()
        permissions = (
            ('view_credit_note', 'Can view Nota de Credito'),
            ('add_credit_note', 'Can add Nota de Credito'),
            ('delete_credit_note', 'Can delete Nota de Credito'),
            ('view_credit_note_client', 'Can view_credit_note_client Nota de Credito'),
        )


class CreditNoteDetail(models.Model):
    credit_note = models.ForeignKey(CreditNote, on_delete=models.CASCADE)
    sale_detail = models.ForeignKey(SaleDetail, on_delete=models.PROTECT)
    product = models.ForeignKey(
        Product, blank=True, null=True, on_delete=models.PROTECT)
    date_joined = models.DateField(default=timezone.now)
    cant = models.IntegerField(default=0)
    price = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    price_with_vat = models.DecimalField(
        max_digits=9, decimal_places=2, default=0.00)
    subtotal = models.DecimalField(
        max_digits=9, decimal_places=2, default=0.00)
    iva = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    total_iva = models.DecimalField(
        max_digits=9, decimal_places=2, default=0.00)
    dscto = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    total_dscto = models.DecimalField(
        max_digits=9, decimal_places=2, default=0.00)
    total = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)

    def __str__(self):
        return self.product.name

    def toJSON(self):
        item = model_to_dict(self)
        item['date_joined'] = self.date_joined.strftime('%Y-%m-%d')
        item['sale_detail'] = self.sale_detail.toJSON()
        item['product'] = self.product.toJSON()
        item['price'] = float(self.price)
        item['price_with_vat'] = float(self.price_with_vat)
        item['subtotal'] = float(self.subtotal)
        item['iva'] = float(self.subtotal)
        item['total_iva'] = float(self.subtotal)
        item['dscto'] = float(self.dscto)
        item['total_dscto'] = float(self.total_dscto)
        item['total'] = float(self.total)
        return item

    class Meta:
        verbose_name = 'Detalle Devolución Ventas'
        verbose_name_plural = 'Detalle Devoluciones Ventas'
        default_permissions = ()


class SaleProduct(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    price = models.DecimalField(default=0.00, max_digits=9, decimal_places=2)
    cant = models.IntegerField(default=0)
    subtotal = models.DecimalField(
        default=0.00, max_digits=9, decimal_places=2)

    def __str__(self):
        return self.product.name

    def toJSON(self):
        item = model_to_dict(self, exclude=['sale'])
        item['product'] = self.product.toJSON()
        item['price'] = f'{self.price:.2f}'
        item['subtotal'] = f'{self.subtotal:.2f}'
        return item

    class Meta:
        verbose_name = 'Detalle de Venta'
        verbose_name_plural = 'Detalle de Ventas'
        default_permissions = ()
        ordering = ['id']
