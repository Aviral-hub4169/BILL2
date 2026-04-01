from django.urls import path

from .views import ProductCreateView, ProductDeleteView, ProductListView, ProductUpdateView

app_name = 'products'

urlpatterns = [
    path('', ProductListView.as_view(), name='list'),
    path('add/', ProductCreateView.as_view(), name='add'),
    path('<int:pk>/edit/', ProductUpdateView.as_view(), name='edit'),
    path('<int:pk>/delete/', ProductDeleteView.as_view(), name='delete'),
]
