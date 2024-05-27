from rest_framework.serializers import ModelSerializer
from core.pos.models import Category, Product, Provider




class ProviderSerializer(ModelSerializer):
    class Meta:
        model = Provider
        fields = ["id", "name", "ruc", "mobile", "email", 
                  "address", "first_name", "last_name", "dv", 
                  "provider", "cust", "employer", "other", 
                  "active", "created_date"]


class CategorySerializer(ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "image", "slug", "image_alterna"]


class ProductSerializer(ModelSerializer):
    # atributData = AttributSerializer(source='atribut', read_only=True, many=True)
    class Meta:
        model = Product
        fields = [
            "id",
            "code",
            "ref",
            "flag",
            "name",
            "slug",
            "description",          
            "category",
            "image",        
            "image_alterna",
            "pvp",
            "price",
            "stock",      
            "active",
            "soldout",
            "offer",
            "home",       
        ]
