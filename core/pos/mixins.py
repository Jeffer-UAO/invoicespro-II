from datetime import datetime

from django.contrib import messages
from django.http import HttpResponseRedirect

from config import settings


class ValidateInvoicePlanMixin(object):
    model = None
    success_url = settings.LOGIN_REDIRECT_URL

    def get(self, request, *args, **kwargs):
        if self.model:
            if request.tenant.company.plan.quantity == 0:
                return super().get(request, *args, **kwargs)
            current_date = datetime.now().date()
            queryset = self.model.objects.filter(date_joined__year=current_date.year, date_joined__month=current_date.month)
            if queryset.count() > request.tenant.company.plan.quantity:
                messages.error(request, f'Tu plan {request.tenant.company.plan.name} solo te permite {request.tenant.company.plan.quantity} facturas al mes y ya has superado el limite permitido')
                return HttpResponseRedirect(self.success_url)
        return super().get(request, *args, **kwargs)
