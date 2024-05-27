from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters


from ..models import Category, Product, Provider
from .serializers import CategorySerializer, ProductSerializer, ProviderSerializer



class ProviderApiViewSet(ModelViewSet):
    permission_classes = [IsAuthenticatedOrReadOnly]
    serializer_class = ProviderSerializer
    queryset = Provider.objects.all().order_by('name')
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    filter_fields = ['active']


class CategoryApiViewSet(ModelViewSet):
    permission_classes = [IsAuthenticatedOrReadOnly]
    serializer_class = CategorySerializer
    queryset = Category.objects.all()
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['slug']

class ProductApiViewSet(ModelViewSet):
    permission_classes = [IsAuthenticatedOrReadOnly]
    serializer_class = ProductSerializer
    queryset = Product.objects.all().order_by('name')
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ['flag', 'name', 'description', 'ref', 'code', 'pvp']
    filterset_fields = ['slug', 'flag', 'active', 'category']
