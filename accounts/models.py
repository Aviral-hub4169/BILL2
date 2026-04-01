from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    shop_name = models.CharField(max_length=150)
    owner_name = models.CharField(max_length=150)
    mobile = models.CharField(max_length=15)
    email = models.EmailField(unique=True)
    address = models.TextField()
    gst_number = models.CharField(max_length=15, blank=True)
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['shop_name', 'owner_name', 'mobile', 'address']

    class Meta:
        ordering = ['shop_name', 'email']

    def __str__(self):
        return f'{self.shop_name} ({self.email})'
