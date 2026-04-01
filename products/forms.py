from django import forms

from .models import Product


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'hsn_code', 'price', 'gst_percentage', 'quantity', 'unit']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Product name'}),
            'hsn_code': forms.TextInput(attrs={'placeholder': 'HSN code'}),
            'price': forms.NumberInput(attrs={'step': '0.01', 'placeholder': 'Price'}),
            'gst_percentage': forms.NumberInput(attrs={'step': '0.01', 'placeholder': 'GST %'}),
            'quantity': forms.NumberInput(attrs={'step': '0.01', 'placeholder': 'Quantity'}),
            'unit': forms.Select(),
        }

    def clean_name(self):
        return self.cleaned_data['name'].strip()

    def clean_hsn_code(self):
        return self.cleaned_data['hsn_code'].strip().upper()
