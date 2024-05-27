import json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12
from django.http import HttpResponse
from django.views.generic import UpdateView

from config import settings
from core.security.mixins import GroupPermissionMixin
from core.tenant.forms import CompanyForm, Company


class CompanyUpdateView(GroupPermissionMixin, UpdateView):
    template_name = 'company/create.html'
    form_class = CompanyForm
    model = Company
    permission_required = 'change_company'
    success_url = settings.LOGIN_REDIRECT_URL

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        del form.fields['schema_name']
        del form.fields['plan']
        return form

    def get_object(self, queryset=None):
        return self.request.tenant.company

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'edit':
                form = CompanyForm(request.POST, request.FILES, instance=self.get_object())
                form.data._mutable = True
                form.data['schema_name'] = request.tenant.schema_name
                form.data['plan'] = self.request.tenant.company.plan
                data = form.save()
            elif action == 'load_certificate':
                instance = self.get_object()
                electronic_signature_key = request.POST['electronic_signature_key']
                archive = None
                if 'certificate' in request.FILES:
                    archive = request.FILES['certificate'].file
                elif instance.pk is not None:
                    archive = open(instance.electronic_signature.path, 'rb')
                if archive:
                    with archive as file:
                        private_key, certificate, additional_certificates = pkcs12.load_key_and_certificates(file.read(), electronic_signature_key.encode())
                        for s in certificate.subject:
                            data[s.oid._name] = s.value
                        public_key = certificate.public_key().public_bytes(encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo).decode('utf-8')
                        data['public_key'] = public_key
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['title'] = 'Configuración de la Compañia'
        context['list_url'] = self.success_url
        context['action'] = 'edit'
        return context
