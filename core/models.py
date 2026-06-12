import qrcode
import io
import base64
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
        # Automated baseline check: if pool runs completely dry, auto-flag out of stock
        if self.quantity_available == 0 and self.status != 'Maintenance':
            self.status = 'Out of Stock'
                
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} - {self.category} ({self.quantity_available}/{self.total_quantity} Available)"

    @property
    def qr_code_base64(self):
        qr_data = f"http://127.0.0.1:8000/asset/{self.id}/check/"
        qr = qrcode.QRCode(version=1, box_size=4, border=2)
        qr.add_data(qr_data)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        
        encoded_img = base64.b64encode(buffer.getvalue()).decode('utf-8')
        return f"data:image/png;base64,{encoded_img}"


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


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    message = models.CharField(max_length=255)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Notification for {self.user.username} - Read: {self.is_read}"

class MaintenanceLog(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='maintenance_history')
    reported_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    issue_description = models.TextField()
    units_damaged = models.PositiveIntegerField(default=0) # <-- NEW TRACKING COLUMN
    action_taken = models.TextField(blank=True, null=True)
    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    date_logged = models.DateTimeField(default=timezone.now)
    is_resolved = models.BooleanField(default=False)

    def __str__(self):
        return f"Log ({self.units_damaged} units) for {self.asset.name} on {self.date_logged.date()}"