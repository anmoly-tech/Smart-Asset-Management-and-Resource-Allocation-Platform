from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class Asset(models.Model):
    STATUS_CHOICES = [
        ('Available', 'Available'),
        ('Maintenance', 'Maintenance'),
        ('Out of Stock', 'Out of Stock'),
    ]
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    total_quantity = models.PositiveIntegerField(default=1)
    quantity_available = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Available')

    def save(self, *args, **kwargs):
        if self.quantity_available == 0:
            self.status = 'Out of Stock'
        elif self.status == 'Out of Stock' and self.quantity_available > 0:
            self.status = 'Available'
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} - {self.category} ({self.quantity_available}/{self.total_quantity} Available)"

class Booking(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
        ('Returned', 'Returned'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    quantity_requested = models.PositiveIntegerField(default=1)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_overdue(self):
        return self.status == 'Approved' and self.end_date < timezone.now().date()

    def __str__(self):
        return f"{self.user.username} - {self.asset.name} ({self.status})"