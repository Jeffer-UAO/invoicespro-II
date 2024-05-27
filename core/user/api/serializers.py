from rest_framework import serializers
from ..models import User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'names', 'username', 'image', 'is_active', 'is_staff', 'email', 'role',
                  'date_joined', 'is_change_password', 'email_reset_token', 'password']

# class AddressSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Address
#         fields = ['id', 'title', 'name_lastname', 'address',
#                   'city', 'country', 'active', 'phone', 'user']
