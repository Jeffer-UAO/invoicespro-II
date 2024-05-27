import os

import django
from django_tenants.utils import schema_context

from config import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from datetime import datetime

from core.tenant.models import Company
from core.pos.models import Sale, CreditNote, INVOICE_STATUS, VOUCHER_TYPE
from core.pos.utilities.sri import SRI


def electronic_invoicing_receipts_invoice():
    sri = SRI()
    for company in Company.objects.filter().exclude(scheme__schema_name=settings.DEFAULT_SCHEMA):
        with schema_context(company.scheme.schema_name):
            date_joined = datetime.now().date()
            for instance in Sale.objects.filter(date_joined=date_joined, receipt__code=VOUCHER_TYPE[0][0], create_electronic_invoice=True).exclude(status__in=[INVOICE_STATUS[-2][0], INVOICE_STATUS[-1][0]]):
                if instance.status == INVOICE_STATUS[0][0]:
                    instance.generate_electronic_invoice()
                elif instance.status == INVOICE_STATUS[1][0]:
                    sri.notify_by_email(instance=instance, company=instance.company, client=instance.client)
            for instance in CreditNote.objects.filter(date_joined=date_joined, create_electronic_invoice=True).exclude(status__in=[INVOICE_STATUS[-2][0], INVOICE_STATUS[-1][0]]):
                if instance.status == INVOICE_STATUS[0][0]:
                    instance.generate_electronic_invoice()
                elif instance.status == INVOICE_STATUS[1][0]:
                    sri.notify_by_email(instance=instance, company=instance.company, client=instance.client)


electronic_invoicing_receipts_invoice()
