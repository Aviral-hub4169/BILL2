from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .forms import AdminUserChangeForm, AdminUserCreationForm
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    form = AdminUserChangeForm
    add_form = AdminUserCreationForm
    ordering = ['email']
    list_display = ['email', 'shop_name', 'owner_name', 'mobile', 'is_staff', 'is_active']
    search_fields = ['email', 'shop_name', 'owner_name', 'mobile', 'gst_number']

    fieldsets = (
        ('Account Info', {'fields': ('email', 'password')}),
        ('Business Details', {'fields': ('shop_name', 'owner_name', 'mobile', 'address', 'gst_number')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important Dates', {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (
            None,
            {
                'classes': ('wide',),
                'fields': (
                    'email',
                    'shop_name',
                    'owner_name',
                    'mobile',
                    'address',
                    'gst_number',
                    'password1',
                    'password2',
                ),
            },
        ),
    )
