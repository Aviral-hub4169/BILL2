from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import InvoiceItem


@receiver(post_save, sender=InvoiceItem)
def update_invoice_totals_on_save(sender, instance, **kwargs):
    instance.invoice.update_totals(save=True)


@receiver(post_delete, sender=InvoiceItem)
def update_invoice_totals_on_delete(sender, instance, **kwargs):
    if instance.invoice_id:
        instance.invoice.update_totals(save=True)
