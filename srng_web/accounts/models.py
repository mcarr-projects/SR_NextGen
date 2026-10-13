from django.db import models
from django.contrib.auth.models import AbstractUser
from .managers import UserManager
# Create your models here.

class User(AbstractUser):
    class ApprovalStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    username = None
    email = models.EmailField(unique=True)

    approval_status = models.CharField(
        max_length=10,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING
    )

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []
    objects = UserManager()