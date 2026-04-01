from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.generic import DetailView, TemplateView
from rest_framework import generics, permissions

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from .models import Invoice
from .serializers import BillingProductSerializer, InvoiceCreateSerializer, InvoiceReadSerializer

from products.models import Product


TWOPLACES = Decimal('0.01')
STATE_CODE_MAP = {
    '01': 'JAMMU AND KASHMIR',
    '02': 'HIMACHAL PRADESH',
    '03': 'PUNJAB',
    '04': 'CHANDIGARH',
    '05': 'UTTARAKHAND',
    '06': 'HARYANA',
    '07': 'DELHI',
    '08': 'RAJASTHAN',
    '09': 'UTTAR PRADESH',
    '10': 'BIHAR',
    '11': 'SIKKIM',
    '12': 'ARUNACHAL PRADESH',
    '13': 'NAGALAND',
    '14': 'MANIPUR',
    '15': 'MIZORAM',
    '16': 'TRIPURA',
    '17': 'MEGHALAYA',
    '18': 'ASSAM',
    '19': 'WEST BENGAL',
    '20': 'JHARKHAND',
    '21': 'ODISHA',
    '22': 'CHHATTISGARH',
    '23': 'MADHYA PRADESH',
    '24': 'GUJARAT',
    '27': 'MAHARASHTRA',
    '29': 'KARNATAKA',
    '30': 'GOA',
    '32': 'KERALA',
    '33': 'TAMIL NADU',
    '34': 'PUDUCHERRY',
    '36': 'TELANGANA',
    '37': 'ANDHRA PRADESH',
}


def _to_decimal(value):
    return Decimal(str(value or '0')).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _money(value):
    return f'{_to_decimal(value):,.2f}'


def _crop_text(value, limit=30):
    value = str(value or '')
    if len(value) <= limit:
        return value
    return f'{value[:limit - 3]}...'


def _wrap_text(value, max_chars):
    text = str(value or '').strip()
    if not text:
        return ['']

    words = text.split()
    lines = []
    current = words[0]
    for word in words[1:]:
        candidate = f'{current} {word}'
        if len(candidate) <= max_chars:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _state_from_gstin(gstin):
    gstin = str(gstin or '').strip()
    if len(gstin) >= 2 and gstin[:2].isdigit():
        code = gstin[:2]
        state = STATE_CODE_MAP.get(code, 'UNKNOWN')
        return f'{code}-{state}'
    return 'NA'


def _two_digit_words(number):
    ones = [
        'Zero',
        'One',
        'Two',
        'Three',
        'Four',
        'Five',
        'Six',
        'Seven',
        'Eight',
        'Nine',
        'Ten',
        'Eleven',
        'Twelve',
        'Thirteen',
        'Fourteen',
        'Fifteen',
        'Sixteen',
        'Seventeen',
        'Eighteen',
        'Nineteen',
    ]
    tens = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety']
    if number < 20:
        return ones[number]
    ten = number // 10
    unit = number % 10
    if unit == 0:
        return tens[ten]
    return f'{tens[ten]} {ones[unit]}'


def _number_to_words_indian(number):
    number = int(number)
    if number == 0:
        return 'Zero'

    parts = []

    crore = number // 10000000
    if crore:
        parts.append(f'{_number_to_words_indian(crore)} Crore')
    number %= 10000000

    lakh = number // 100000
    if lakh:
        parts.append(f'{_number_to_words_indian(lakh)} Lakh')
    number %= 100000

    thousand = number // 1000
    if thousand:
        parts.append(f'{_number_to_words_indian(thousand)} Thousand')
    number %= 1000

    hundred = number // 100
    if hundred:
        parts.append(f'{_two_digit_words(hundred)} Hundred')
    number %= 100

    if number:
        parts.append(_two_digit_words(number))

    return ' '.join(parts)


def _amount_to_words(value):
    amount = _to_decimal(value)
    rupees = int(amount)
    paise = int(((amount - Decimal(rupees)) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    words = _number_to_words_indian(rupees)
    if paise:
        paise_words = _number_to_words_indian(paise)
        return f'INR {words} Rupees and {paise_words} Paise Only.'
    return f'INR {words} Rupees Only.'


class BillingCreatePageView(LoginRequiredMixin, TemplateView):
    template_name = 'billing/create_invoice.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['payment_modes'] = Invoice.PaymentModeChoices.choices
        context['today'] = timezone.localdate().isoformat()
        return context


class BillingProductListAPIView(generics.ListAPIView):
    serializer_class = BillingProductSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        queryset = Product.objects.filter(user=self.request.user).order_by('name')
        query = self.request.query_params.get('q', '').strip()
        if query:
            queryset = queryset.filter(
                Q(name__icontains=query) | Q(hsn_code__icontains=query)
            )
        return queryset


class InvoicePreviewPageView(LoginRequiredMixin, DetailView):
    model = Invoice
    template_name = 'billing/invoice_preview.html'
    context_object_name = 'invoice'

    def get_queryset(self):
        return (
            Invoice.objects.filter(user=self.request.user)
            .prefetch_related('items__product')
            .select_related('user')
        )


@login_required
def generate_invoice_pdf(request, invoice_id):
    invoice = get_object_or_404(
        Invoice.objects.filter(user=request.user).prefetch_related('items__product').select_related('user'),
        pk=invoice_id,
    )

    items = list(invoice.items.all())
    due_date = invoice.date + timedelta(days=1)
    place_of_supply = _state_from_gstin(invoice.user.gst_number)

    taxable_amount = _to_decimal(invoice.total_amount)
    cgst_amount = _to_decimal(invoice.cgst_amount)
    sgst_amount = _to_decimal(invoice.sgst_amount)
    final_amount = _to_decimal(invoice.final_amount)
    total_qty = sum(int(_to_decimal(item.quantity)) for item in items)
    round_off = final_amount - (taxable_amount + cgst_amount + sgst_amount)
    effective_gst_rate = Decimal('0.00')
    if taxable_amount > 0:
        effective_gst_rate = ((cgst_amount / taxable_amount) * 100).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

    table_rows = []
    for index, item in enumerate(items, start=1):
        item_name_lines = _wrap_text(item.product.name, 28)
        item_name_lines.append(f'HSN: {item.product.hsn_code}')
        table_rows.append(
            {
                'index': str(index),
                'item_lines': item_name_lines,
                'mrp': _money(item.product.price),
                'selling': _money(item.rate),
                'qty': f"{int(_to_decimal(item.quantity))} {item.product.unit}",
                'amount': _money(item.final_amount),
                'height': max(30, (len(item_name_lines) * 11) + 8),
            }
        )

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    page_width, page_height = A4

    margin = 10 * mm
    outer_left = margin
    outer_right = page_width - margin
    outer_bottom = margin
    outer_top = page_height - margin
    outer_width = outer_right - outer_left
    outer_height = outer_top - outer_bottom
    content_left = outer_left + 8
    content_right = outer_right - 8
    content_width = content_right - content_left

    table_header_height = 19
    min_table_bottom = outer_bottom + 250

    def write_in_box(text, x1, x2, y_top, y_bottom, align='left', bold=False, font_size=9):
        text = str(text or '')
        font_name = 'Helvetica-Bold' if bold else 'Helvetica'
        pdf.setFont(font_name, font_size)
        if align == 'right':
            pdf.drawRightString(x2 - 4, y_bottom + ((y_top - y_bottom) / 2) - 3, text)
        elif align == 'center':
            pdf.drawCentredString((x1 + x2) / 2, y_bottom + ((y_top - y_bottom) / 2) - 3, text)
        else:
            pdf.drawString(x1 + 4, y_bottom + ((y_top - y_bottom) / 2) - 3, text)

    def draw_static_header(page_number, total_pages):
        pdf.setStrokeColor(colors.black)
        pdf.setLineWidth(1)
        pdf.rect(outer_left, outer_bottom, outer_width, outer_height, stroke=1, fill=0)

        y = outer_top - 10
        pdf.setFont('Helvetica-Bold', 10)
        pdf.drawCentredString((outer_left + outer_right) / 2, y, 'TAX INVOICE ORIGINAL FOR RECIPIENT')
        y -= 18

        seller_height = 62
        pdf.rect(content_left, y - seller_height, content_width, seller_height, stroke=1, fill=0)

        pdf.setFont('Helvetica-Bold', 15)
        pdf.drawString(content_left + 6, y - 18, _crop_text(invoice.user.shop_name, 46))
        pdf.setFont('Helvetica', 9)
        pdf.drawString(content_left + 6, y - 32, f'GSTIN {invoice.user.gst_number or "N/A"}    PAN N/A')
        for idx, line in enumerate(_wrap_text(invoice.user.address, 72)[:2], start=1):
            pdf.drawString(content_left + 6, y - (32 + idx * 12), line)
        pdf.drawString(
            content_left + 6,
            y - 56,
            f'Mobile +91 {invoice.user.mobile}   Email billing@{invoice.user.shop_name.lower().replace(" ", "")}.com',
        )
        y -= (seller_height + 8)

        meta_height = 20
        pdf.rect(content_left, y - meta_height, content_width, meta_height, stroke=1, fill=0)
        pdf.setFont('Helvetica', 9)
        invoice_line = (
            f'Invoice #: {invoice.invoice_number}     '
            f'Invoice Date: {invoice.date.strftime("%d %b %Y")}     '
            f'Due Date: {due_date.strftime("%d %b %Y")}'
        )
        pdf.drawString(content_left + 6, y - 14, invoice_line)
        y -= (meta_height + 8)

        party_height = 74
        pdf.rect(content_left, y - party_height, content_width, party_height, stroke=1, fill=0)
        split_x = content_left + (content_width * 0.57)
        pdf.line(split_x, y, split_x, y - party_height)

        pdf.setFont('Helvetica-Bold', 9)
        pdf.drawString(content_left + 6, y - 12, 'Customer Details:')
        pdf.setFont('Helvetica', 9)
        pdf.drawString(content_left + 6, y - 27, _crop_text(invoice.customer_name, 42))
        pdf.drawString(content_left + 6, y - 41, f'Ph: {invoice.customer_mobile}')

        pdf.setFont('Helvetica-Bold', 9)
        pdf.drawString(split_x + 6, y - 12, 'Dispatch From:')
        pdf.setFont('Helvetica', 9)
        dispatch_lines = _wrap_text(f'{invoice.user.shop_name} {invoice.user.address}', 41)[:3]
        for idx, line in enumerate(dispatch_lines):
            pdf.drawString(split_x + 6, y - (27 + idx * 12), line)
        pdf.setFont('Helvetica-Bold', 9)
        pdf.drawString(split_x + 6, y - 61, 'Place of Supply:')
        pdf.setFont('Helvetica', 9)
        pdf.drawString(split_x + 90, y - 61, place_of_supply)

        y -= (party_height + 8)

        table_headers = ['#', 'Item', 'MRP', 'Selling Price', 'Qty', 'Amount']
        ratios = [0.05, 0.43, 0.12, 0.14, 0.10, 0.16]
        x_positions = [content_left]
        x_pointer = content_left
        for ratio in ratios:
            x_pointer += content_width * ratio
            x_positions.append(x_pointer)

        pdf.setFillColor(colors.HexColor('#f4f4f4'))
        pdf.rect(content_left, y - table_header_height, content_width, table_header_height, stroke=1, fill=1)
        pdf.setFillColor(colors.black)
        for x in x_positions[1:-1]:
            pdf.line(x, y, x, y - table_header_height)
        for idx, title in enumerate(table_headers):
            write_in_box(
                title,
                x_positions[idx],
                x_positions[idx + 1],
                y,
                y - table_header_height,
                align='center',
                bold=True,
                font_size=9,
            )

        footer_text = f'Page {page_number} / {total_pages}   |   This is a digitally signed document.'
        pdf.setFont('Helvetica', 8)
        pdf.drawCentredString((outer_left + outer_right) / 2, outer_bottom + 5, footer_text)

        return y - table_header_height, x_positions

    paginated_rows = []
    current_page_rows = []
    consumed_height = 0
    base_available_height = (outer_top - 10) - min_table_bottom - 200
    safe_available_height = max(80, int(base_available_height))
    for row in table_rows:
        if current_page_rows and (consumed_height + row['height'] > safe_available_height):
            paginated_rows.append(current_page_rows)
            current_page_rows = []
            consumed_height = 0
        current_page_rows.append(row)
        consumed_height += row['height']
    if current_page_rows or not paginated_rows:
        paginated_rows.append(current_page_rows)

    total_pages = len(paginated_rows)

    for page_index, page_rows in enumerate(paginated_rows, start=1):
        table_y, x_positions = draw_static_header(page_index, total_pages)
        y_cursor = table_y

        for row in page_rows:
            row_height = row['height']
            pdf.rect(content_left, y_cursor - row_height, content_width, row_height, stroke=1, fill=0)
            for x in x_positions[1:-1]:
                pdf.line(x, y_cursor, x, y_cursor - row_height)

            write_in_box(row['index'], x_positions[0], x_positions[1], y_cursor, y_cursor - row_height, align='center')
            write_in_box(row['mrp'], x_positions[2], x_positions[3], y_cursor, y_cursor - row_height, align='right')
            write_in_box(row['selling'], x_positions[3], x_positions[4], y_cursor, y_cursor - row_height, align='right')
            write_in_box(row['qty'], x_positions[4], x_positions[5], y_cursor, y_cursor - row_height, align='center')
            write_in_box(row['amount'], x_positions[5], x_positions[6], y_cursor, y_cursor - row_height, align='right')

            pdf.setFont('Helvetica', 8.5)
            line_y = y_cursor - 12
            for line in row['item_lines']:
                pdf.drawString(x_positions[1] + 4, line_y, _crop_text(line, 46))
                line_y -= 11

            y_cursor -= row_height

        is_last_page = page_index == total_pages
        if is_last_page:
            summary_top = y_cursor - 10
            summary_x = content_right - 230
            summary_width = 230
            summary_row_h = 19
            summary_rows = [
                ('Total', _money(final_amount)),
                ('Taxable Amount', _money(taxable_amount)),
                (f'CGST @{_money(effective_gst_rate)}%', _money(cgst_amount)),
                (f'SGST @{_money(effective_gst_rate)}%', _money(sgst_amount)),
                ('Round Off', f'{round_off:.2f}'),
            ]

            summary_height = summary_row_h * len(summary_rows)
            split_x = summary_x + (summary_width * 0.56)
            pdf.rect(summary_x, summary_top - summary_height, summary_width, summary_height, stroke=1, fill=0)
            pdf.line(split_x, summary_top, split_x, summary_top - summary_height)
            for idx in range(1, len(summary_rows)):
                line_y = summary_top - (idx * summary_row_h)
                pdf.line(summary_x, line_y, summary_x + summary_width, line_y)

            for idx, (label, value) in enumerate(summary_rows):
                row_top = summary_top - (idx * summary_row_h)
                row_bottom = row_top - summary_row_h
                write_in_box(label, summary_x, split_x, row_top, row_bottom, align='left', bold=(idx == 0))
                write_in_box(value, split_x, summary_x + summary_width, row_top, row_bottom, align='right', bold=(idx == 0))

            left_section_x = content_left
            left_section_right = summary_x - 10
            line_y = summary_top - 2
            pdf.setFont('Helvetica', 9)
            pdf.drawString(left_section_x, line_y, f'Total Items / Qty : {len(items)} / {total_qty}')
            line_y -= 14
            amount_words = _amount_to_words(final_amount)
            words_lines = _wrap_text(f'Total amount (in words): {amount_words}', 72)
            for line in words_lines[:3]:
                pdf.drawString(left_section_x, line_y, line)
                line_y -= 12

            payable_box_y = line_y - 6
            payable_h = 18
            pdf.rect(left_section_x, payable_box_y - payable_h, left_section_right - left_section_x, payable_h, stroke=1, fill=0)
            write_in_box(
                'Amount Payable:',
                left_section_x,
                left_section_x + (left_section_right - left_section_x) * 0.55,
                payable_box_y,
                payable_box_y - payable_h,
                bold=True,
            )
            write_in_box(
                f'Rs {_money(final_amount)}',
                left_section_x + (left_section_right - left_section_x) * 0.55,
                left_section_right,
                payable_box_y,
                payable_box_y - payable_h,
                align='right',
                bold=True,
            )

            balance_y = payable_box_y - payable_h - 3
            pdf.rect(left_section_x, balance_y - payable_h, left_section_right - left_section_x, payable_h, stroke=1, fill=0)
            write_in_box(
                'Total Balance due:',
                left_section_x,
                left_section_x + (left_section_right - left_section_x) * 0.55,
                balance_y,
                balance_y - payable_h,
                bold=True,
            )
            write_in_box(
                f'Rs {_money(final_amount)}',
                left_section_x + (left_section_right - left_section_x) * 0.55,
                left_section_right,
                balance_y,
                balance_y - payable_h,
                align='right',
                bold=True,
            )

            bank_y = balance_y - payable_h - 10
            pdf.setFont('Helvetica-Bold', 9)
            pdf.drawString(left_section_x, bank_y, 'Bank Details:')
            pdf.setFont('Helvetica', 9)
            pdf.drawString(left_section_x, bank_y - 12, 'Bank: N/A')
            pdf.drawString(left_section_x, bank_y - 24, 'Account #: N/A')
            pdf.drawString(left_section_x, bank_y - 36, 'IFSC Code: N/A')
            pdf.drawString(left_section_x, bank_y - 48, 'Branch: N/A')

            sign_x = summary_x + 8
            sign_y = bank_y - 6
            pdf.setFont('Helvetica-Bold', 9)
            pdf.drawString(sign_x, sign_y, f'For {invoice.user.shop_name}')
            pdf.setFont('Helvetica', 9)
            pdf.drawString(sign_x, sign_y - 44, 'Authorized Signatory')

        if page_index < total_pages:
            pdf.showPage()

    pdf.save()
    buffer.seek(0)

    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{invoice.invoice_number}.pdf"'
    return response


class InvoiceListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            Invoice.objects.filter(user=self.request.user)
            .prefetch_related('items__product')
            .select_related('user')
        )

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return InvoiceCreateSerializer
        return InvoiceReadSerializer


class InvoiceDetailAPIView(generics.RetrieveAPIView):
    serializer_class = InvoiceReadSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            Invoice.objects.filter(user=self.request.user)
            .prefetch_related('items__product')
            .select_related('user')
        )
