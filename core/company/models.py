# from django.db import models

# from config import settings
# from core.security.fields import CustomImageField, CustomFileField
# from core.tenant.choices import OBLIGATED_ACCOUNTING, ENVIRONMENT_TYPE, RETENTION_AGENT, EMISSION_TYPE


# class Company(models.Model):
#     ruc = models.CharField(max_length=13, verbose_name='Identificación')
#     business_name = models.CharField(max_length=50, verbose_name='Razón social')
#     tradename = models.CharField(max_length=50, verbose_name='Nombre Comercial')
#     main_address = models.CharField(max_length=200, verbose_name='Dirección del Establecimiento Matriz')
#     establishment_address = models.CharField(max_length=200, verbose_name='Dirección del Establecimiento Emisor')
#     establishment_code = models.CharField(max_length=3, verbose_name='Código del Establecimiento Emisor')
#     issuing_point_code = models.CharField(max_length=3, verbose_name='Código del Punto de Emisión')
#     special_taxpayer = models.CharField(max_length=13, verbose_name='Contribuyente Especial (Número de Resolución)')
#     obligated_accounting = models.CharField(max_length=2, choices=OBLIGATED_ACCOUNTING, default=OBLIGATED_ACCOUNTING[1][0], verbose_name='Obligado a Llevar Contabilidad')
#     image = CustomImageField(null=True, blank=True, folder='company', scheme=settings.DEFAULT_SCHEMA, verbose_name='Logotipo de la empresa')
#     environment_type = models.PositiveIntegerField(choices=ENVIRONMENT_TYPE, default=1, verbose_name='Tipo de Ambiente')
#     emission_type = models.PositiveIntegerField(choices=EMISSION_TYPE, default=1, verbose_name='Tipo de Emisión')
#     retention_agent = models.CharField(max_length=2, choices=RETENTION_AGENT, default=RETENTION_AGENT[1][0], verbose_name='Agente de Retención')
#     mobile = models.CharField(max_length=10, verbose_name='Teléfono celular')
#     phone = models.CharField(max_length=9, verbose_name='Teléfono convencional')
#     email = models.CharField(max_length=50, verbose_name='Email')
#     website = models.CharField(max_length=250, verbose_name='Dirección de página web')
#     description = models.CharField(max_length=500, null=True, blank=True, verbose_name='Descripción')
#     iva = models.DecimalField(default=0.00, decimal_places=2, max_digits=9, verbose_name='IVA')
#     electronic_signature = CustomFileField(null=True, blank=True, folder='company', scheme=settings.DEFAULT_SCHEMA, verbose_name='Firma electrónica (Archivo P12)')
#     electronic_signature_key = models.CharField(max_length=100, verbose_name='Clave de firma electrónica')
#     email_host = models.CharField(max_length=30, default='smtp.gmail.com', verbose_name='Servidor de correo')
#     email_port = models.IntegerField(default=587, verbose_name='Puerto del servidor de correo')
#     email_host_user = models.CharField(max_length=100, verbose_name='Username del servidor de correo')
#     email_host_password = models.CharField(max_length=30, verbose_name='Password del servidor de correo')
#     schema_name = models.CharField(max_length=30, null=True, blank=True, verbose_name='Nombre del esquema')
#     scheme = models.OneToOneField(Scheme, on_delete=models.CASCADE, verbose_name='Esquema')
#     plan = models.ForeignKey(Plan, on_delete=models.CASCADE, verbose_name='Plan de facturación')

#     def __str__(self):
#         return self.business_name

#     def get_image(self):
#         if self.image:
#             return f'{settings.MEDIA_URL}{self.image}'
#         return f'{settings.STATIC_URL}img/default/empty.png'

#     def get_full_path_image(self):
#         if self.image:
#             return self.image.path
#         return f'{settings.BASE_DIR}{settings.STATIC_URL}img/default/empty.png'

#     def image_base64(self):
#         try:
#             if self.image:
#                 with open(self.image.path, 'rb') as image_file:
#                     base64_data = base64.b64encode(image_file.read()).decode('utf-8')
#                     extension = os.path.splitext(self.image.name)[1]
#                     content_type = f'image/{extension.lstrip(".")}'
#                     return f"data:{content_type};base64,{base64_data}"
#         except:
#             pass
#         return None

#     def get_iva(self):
#         return float(self.iva)

#     def get_electronic_signature(self):
#         if self.electronic_signature:
#             return f'{settings.MEDIA_URL}{self.electronic_signature}'
#         return None

#     def toJSON(self):
#         item = model_to_dict(self)
#         item['image'] = self.get_image()
#         item['electronic_signature'] = self.get_electronic_signature()
#         item['iva'] = float(self.iva)
#         item['scheme'] = self.scheme.toJSON()
#         item['plan'] = self.plan.toJSON()
#         return item
