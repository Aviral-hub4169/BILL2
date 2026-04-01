from django.urls import path
from django.views.generic import RedirectView

from .views import DashboardView, LoginView, RegisterAPIView, RegisterView, logout_view

app_name = 'accounts'

urlpatterns = [
    path('', RedirectView.as_view(pattern_name='accounts:dashboard', permanent=False), name='home'),
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', logout_view, name='logout'),
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    path('api/register/', RegisterAPIView.as_view(), name='api-register'),
]
