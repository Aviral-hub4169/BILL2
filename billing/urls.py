from django.urls import path

from .views import (
    BillingCreatePageView,
    BillingProductListAPIView,
    generate_invoice_pdf,
    InvoicePreviewPageView,
    InvoiceDetailAPIView,
    InvoiceListCreateAPIView,
)

app_name = 'billing'

urlpatterns = [
    path('create/', BillingCreatePageView.as_view(), name='create'),
    path('products/', BillingProductListAPIView.as_view(), name='product-list'),
    path('invoices/', InvoiceListCreateAPIView.as_view(), name='invoice-list-create'),
    path('invoices/<int:pk>/', InvoiceDetailAPIView.as_view(), name='invoice-detail'),
    path('invoices/<int:pk>/preview/', InvoicePreviewPageView.as_view(), name='invoice-preview'),
    path('invoices/<int:invoice_id>/pdf/', generate_invoice_pdf, name='invoice-pdf'),
]
