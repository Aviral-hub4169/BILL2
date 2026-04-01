from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from products.models import Product

from .models import Invoice, InvoiceItem


class BillingProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ['id', 'name', 'hsn_code', 'price', 'gst_percentage', 'quantity', 'unit']


class InvoiceItemWriteSerializer(serializers.ModelSerializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    rate = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    discount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        default=Decimal('0.00'),
    )
    gst = serializers.DecimalField(max_digits=5, decimal_places=2, required=False)

    class Meta:
        model = InvoiceItem
        fields = ['product', 'quantity', 'rate', 'discount', 'gst', 'amount']
        read_only_fields = ['amount']

    def validate(self, attrs):
        request = self.context['request']
        product = attrs['product']
        quantity = attrs['quantity']
        rate = attrs.get('rate', product.price)
        discount = attrs.get('discount', Decimal('0.00'))

        if product.user_id != request.user.id:
            raise serializers.ValidationError('Selected product does not belong to the logged-in user.')

        if quantity != quantity.to_integral_value():
            raise serializers.ValidationError({'quantity': 'Quantity must be a whole number (1, 2, 3...).'})

        line_subtotal = quantity * rate
        if discount > line_subtotal:
            raise serializers.ValidationError({'discount': 'Discount cannot exceed line subtotal.'})

        attrs['quantity'] = quantity.to_integral_value()
        attrs['rate'] = rate
        attrs['gst'] = attrs.get('gst', product.gst_percentage)
        attrs['discount'] = discount
        return attrs


class InvoiceItemReadSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(source='product.id', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_hsn_code = serializers.CharField(source='product.hsn_code', read_only=True)
    gst_amount = serializers.SerializerMethodField()
    final_amount = serializers.SerializerMethodField()

    class Meta:
        model = InvoiceItem
        fields = [
            'id',
            'product_id',
            'product_name',
            'product_hsn_code',
            'quantity',
            'rate',
            'discount',
            'gst',
            'amount',
            'gst_amount',
            'final_amount',
        ]

    def get_gst_amount(self, obj):
        return str(obj.gst_amount)

    def get_final_amount(self, obj):
        return str(obj.final_amount)


class InvoiceReadSerializer(serializers.ModelSerializer):
    items = InvoiceItemReadSerializer(many=True, read_only=True)
    cgst_amount = serializers.SerializerMethodField()
    sgst_amount = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = [
            'id',
            'invoice_number',
            'customer_name',
            'customer_mobile',
            'payment_mode',
            'date',
            'total_amount',
            'gst_amount',
            'cgst_amount',
            'sgst_amount',
            'final_amount',
            'items',
        ]

    def get_cgst_amount(self, obj):
        return str(obj.cgst_amount)

    def get_sgst_amount(self, obj):
        return str(obj.sgst_amount)


class InvoiceCreateSerializer(serializers.ModelSerializer):
    items = InvoiceItemWriteSerializer(many=True, write_only=True)
    invoice_number = serializers.CharField(read_only=True)
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    gst_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    final_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    cgst_amount = serializers.SerializerMethodField(read_only=True)
    sgst_amount = serializers.SerializerMethodField(read_only=True)
    item_details = InvoiceItemReadSerializer(source='items', many=True, read_only=True)

    class Meta:
        model = Invoice
        fields = [
            'id',
            'invoice_number',
            'customer_name',
            'customer_mobile',
            'payment_mode',
            'date',
            'total_amount',
            'gst_amount',
            'cgst_amount',
            'sgst_amount',
            'final_amount',
            'items',
            'item_details',
        ]
        read_only_fields = ['id']

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError('At least one invoice item is required.')
        return value

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop('items')
        request = self.context['request']

        invoice = Invoice.objects.create(
            user=request.user,
            **validated_data,
        )

        for item_data in items_data:
            InvoiceItem.objects.create(invoice=invoice, **item_data)

        invoice.refresh_from_db()
        invoice.update_totals(save=True)
        invoice.refresh_from_db()
        return invoice

    def get_cgst_amount(self, obj):
        return str(obj.cgst_amount)

    def get_sgst_amount(self, obj):
        return str(obj.sgst_amount)
