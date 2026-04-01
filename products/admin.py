from django.contrib import admin

from .models import Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'hsn_code', 'price', 'gst_percentage', 'quantity', 'unit']
    search_fields = ['name', 'hsn_code', 'user__email', 'user__shop_name']
    list_filter = ['unit', 'gst_percentage']
