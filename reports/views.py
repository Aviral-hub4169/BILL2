from datetime import timedelta
from decimal import Decimal
from collections import defaultdict

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import DecimalField, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.views.generic import TemplateView

from billing.models import Invoice, InvoiceItem


class ReportsDashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'reports/dashboard.html'

    def _parse_date(self, value, fallback):
        if not value:
            return fallback
        try:
            return timezone.datetime.strptime(value, '%Y-%m-%d').date()
        except ValueError:
            return fallback

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        default_start = today - timedelta(days=29)

        start_date = self._parse_date(self.request.GET.get('start_date'), default_start)
        end_date = self._parse_date(self.request.GET.get('end_date'), today)

        if start_date > end_date:
            start_date, end_date = end_date, start_date

        invoices = Invoice.objects.filter(
            user=self.request.user,
            date__range=(start_date, end_date),
        )

        money_field = DecimalField(max_digits=12, decimal_places=2)
        qty_field = DecimalField(max_digits=12, decimal_places=2)

        total_revenue = invoices.aggregate(
            total=Coalesce(Sum('final_amount'), Value(Decimal('0.00'), output_field=money_field))
        )['total']

        daily_sales_amount = invoices.filter(date=end_date).aggregate(
            total=Coalesce(Sum('final_amount'), Value(Decimal('0.00'), output_field=money_field))
        )['total']

        monthly_sales_amount = invoices.filter(
            date__year=end_date.year,
            date__month=end_date.month,
        ).aggregate(
            total=Coalesce(Sum('final_amount'), Value(Decimal('0.00'), output_field=money_field))
        )['total']

        daily_totals = defaultdict(lambda: Decimal('0.00'))
        monthly_totals = defaultdict(lambda: Decimal('0.00'))
        for row in invoices.values('date', 'final_amount'):
            sale_date = row['date']
            amount = row['final_amount'] or Decimal('0.00')
            daily_totals[sale_date] += amount
            monthly_key = sale_date.replace(day=1)
            monthly_totals[monthly_key] += amount

        top_products_data = (
            InvoiceItem.objects.filter(
                invoice__user=self.request.user,
                invoice__date__range=(start_date, end_date),
            )
            .values('product__name')
            .annotate(
                total_quantity=Coalesce(Sum('quantity'), Value(Decimal('0.00'), output_field=qty_field)),
                total_amount=Coalesce(Sum('amount'), Value(Decimal('0.00'), output_field=money_field)),
            )
            .order_by('-total_quantity')[:10]
        )

        ordered_daily_dates = sorted(daily_totals.keys())
        daily_labels = [day.strftime('%d %b') for day in ordered_daily_dates]
        daily_values = [float(daily_totals[day]) for day in ordered_daily_dates]

        ordered_months = sorted(monthly_totals.keys())
        monthly_labels = [month.strftime('%b %Y') for month in ordered_months]
        monthly_values = [float(monthly_totals[month]) for month in ordered_months]

        top_product_labels = [entry['product__name'] for entry in top_products_data]
        top_product_values = [float(entry['total_quantity']) for entry in top_products_data]

        context.update(
            {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'end_date_obj': end_date,
                'daily_sales_amount': f'{daily_sales_amount:.2f}',
                'monthly_sales_amount': f'{monthly_sales_amount:.2f}',
                'total_revenue': f'{total_revenue:.2f}',
                'daily_labels': daily_labels,
                'daily_values': daily_values,
                'monthly_labels': monthly_labels,
                'monthly_values': monthly_values,
                'top_product_labels': top_product_labels,
                'top_product_values': top_product_values,
                'top_products': top_products_data,
            }
        )

        return context
