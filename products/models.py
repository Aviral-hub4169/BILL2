from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Product(models.Model):
    class UnitChoices(models.TextChoices):
        LITER = 'LTR', 'LTR'
        KILOGRAM = 'KG', 'KG'
        PIECE = 'PCS', 'PCS'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='products',
    )
    name = models.CharField(max_length=150)
    hsn_code = models.CharField(max_length=20)
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    gst_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    unit = models.CharField(max_length=3, choices=UnitChoices.choices, default=UnitChoices.PIECE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name', '-created_at']
        unique_together = ('user', 'name', 'hsn_code')

    def __str__(self):
        return f'{self.name} ({self.unit})'
