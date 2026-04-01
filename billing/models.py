from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from products.models import Product


TWOPLACES = Decimal('0.01')


def as_money(value):
    return Decimal(value).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


class Invoice(models.Model):
    class PaymentModeChoices(models.TextChoices):
        CASH = 'Cash', 'Cash'
        UPI = 'UPI', 'UPI'
        CREDIT = 'Credit', 'Credit'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='invoices',
    )
    invoice_number = models.CharField(max_length=20)
    customer_name = models.CharField(max_length=150)
    customer_mobile = models.CharField(max_length=15)
    payment_mode = models.CharField(
        max_length=10,
        choices=PaymentModeChoices.choices,
        default=PaymentModeChoices.CASH,
    )
    date = models.DateField(default=timezone.localdate)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    gst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    final_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        ordering = ['-date', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'invoice_number'],
                name='unique_invoice_number_per_user',
            )
        ]

    def __str__(self):
        return f'{self.invoice_number} - {self.customer_name}'

    def save(self, *args, **kwargs):
        if not self.invoice_number and self.user_id:
            self.invoice_number = self.generate_invoice_number()

        self.total_amount = as_money(self.total_amount or Decimal('0.00'))
        self.gst_amount = as_money(self.gst_amount or Decimal('0.00'))
        self.final_amount = as_money(self.final_amount or Decimal('0.00'))
        super().save(*args, **kwargs)

    def generate_invoice_number(self):
        last_invoice = (
            Invoice.objects.filter(user=self.user)
            .exclude(invoice_number='')
            .order_by('-id')
            .first()
        )
        next_number = 1

        if last_invoice and last_invoice.invoice_number:
            try:
                next_number = int(last_invoice.invoice_number.split('-')[-1]) + 1
            except (IndexError, ValueError):
                next_number = last_invoice.id + 1

        return f'INV-{next_number:04d}'

    @property
    def cgst_amount(self):
        return as_money(self.gst_amount / 2)

    @property
    def sgst_amount(self):
        return as_money(self.gst_amount / 2)

    def update_totals(self, save=True):
        subtotal = Decimal('0.00')
        total_gst = Decimal('0.00')

        for item in self.items.all():
            subtotal += item.amount
            total_gst += item.gst_amount

        self.total_amount = as_money(subtotal)
        self.gst_amount = as_money(total_gst)
        self.final_amount = as_money(subtotal + total_gst)

        if save and self.pk:
            Invoice.objects.filter(pk=self.pk).update(
                total_amount=self.total_amount,
                gst_amount=self.gst_amount,
                final_amount=self.final_amount,
            )

        return self.total_amount, self.gst_amount, self.final_amount


class InvoiceItem(models.Model):
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name='items',
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name='invoice_items',
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    discount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    gst = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.invoice.invoice_number} - {self.product.name}'

    @property
    def gst_amount(self):
        return as_money((self.amount * self.gst) / Decimal('100'))

    @property
    def final_amount(self):
        return as_money(self.amount + self.gst_amount)

    def clean(self):
        if self.invoice_id and self.product_id and self.invoice.user_id != self.product.user_id:
            raise ValidationError('Selected product must belong to the same user as the invoice.')

        if self.quantity is not None and self.quantity != self.quantity.to_integral_value():
            raise ValidationError({'quantity': 'Quantity must be a whole number (1, 2, 3...).'})

        if self.quantity is not None and self.rate is not None:
            line_subtotal = as_money(self.quantity * self.rate)
            if self.discount and self.discount > line_subtotal:
                raise ValidationError({'discount': 'Discount cannot exceed the line subtotal.'})

    def save(self, *args, **kwargs):
        if self.product_id:
            if self.rate in (None, ''):
                self.rate = self.product.price
            if self.gst in (None, ''):
                self.gst = self.product.gst_percentage

        self.quantity = as_money(self.quantity or Decimal('0.00'))
        self.rate = as_money(self.rate or Decimal('0.00'))
        self.discount = as_money(self.discount or Decimal('0.00'))
        self.gst = as_money(self.gst or Decimal('0.00'))
        self.full_clean(exclude=['amount'])

        taxable_amount = as_money((self.quantity * self.rate) - self.discount)
        if taxable_amount < Decimal('0.00'):
            raise ValidationError({'discount': 'Discount cannot make the item amount negative.'})

        self.amount = taxable_amount
        super().save(*args, **kwargs)
