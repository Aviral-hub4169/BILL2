from django.contrib import admin

from .models import Invoice, InvoiceItem


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0
    readonly_fields = ['amount']


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = [
        'invoice_number',
        'user',
        'customer_name',
        'payment_mode',
        'date',
        'total_amount',
        'gst_amount',
        'final_amount',
    ]
    search_fields = ['invoice_number', 'customer_name', 'customer_mobile', 'user__email', 'user__shop_name']
    list_filter = ['payment_mode', 'date']
    inlines = [InvoiceItemInline]


@admin.register(InvoiceItem)
class InvoiceItemAdmin(admin.ModelAdmin):
    list_display = ['invoice', 'product', 'quantity', 'rate', 'discount', 'gst', 'amount']
    search_fields = ['invoice__invoice_number', 'product__name']
