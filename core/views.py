from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from datetime import date
from django.db.models import Sum
from .models import Asset, Booking, Notification, MaintenanceLog
from datetime import timedelta
from django.contrib.auth.models import User
import json

from django.contrib.auth.decorators import user_passes_test

@login_required(login_url='login')
@user_passes_test(lambda u: u.is_staff, login_url='dashboard')
def admin_clear_history(request):
    Booking.objects.filter(status__in=['Returned', 'Rejected', 'Canceled']).delete()
    return redirect('dashboard')

def signup_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Registration successful!")
            return redirect('dashboard')
    else:
        form = UserCreationForm()
    return render(request, 'core/signup.html', {'form': form})

def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                return redirect('dashboard')
    else:
        form = AuthenticationForm()
    return render(request, 'core/login.html', {'form': form})

def logout_view(request):
    logout(request)
    return redirect('login')


@login_required(login_url='login')
def dashboard(request):
    today = timezone.now().date()
    assets = Asset.objects.all()

    # --- NOTIFICATION BUG FIX ---
    # Filter only unread notifications if your model uses 'is_read', otherwise fallback
    has_unread = False
    if hasattr(request.user, 'notifications'):
        try:
            has_unread = request.user.notifications.filter(is_read=False).exists()
        except:
            has_unread = request.user.notifications.all().exists()

    # --- 1. REGULAR USER VIEW (Last 5 Days Filter) ---
    if not request.user.is_staff:
        # Calculates date threshold for the past 5 days
        five_days_ago = today - timedelta(days=5)
        
        # Only pull bookings active or completed within the last 5 days
        my_bookings = Booking.objects.filter(
            user=request.user,
            end_date__gte=five_days_ago
        ).order_by('-start_date')
        
        context = {
            'assets': assets,
            'my_bookings': my_bookings,
            'is_admin': False,
            'has_unread': has_unread, # Pass fix flag to template
        }
        return render(request, 'core/dashboard.html', context)

    # --- 2. ADMIN VIEW ---
    total_assets = Asset.objects.count()
    deployed_units = Booking.objects.filter(status='Approved', start_date__lte=today, end_date__gte=today).aggregate(total=Sum('quantity_requested'))['total'] or 0
    pending_approvals = Booking.objects.filter(status='Pending').count()
    overdue_count = Booking.objects.filter(status='Approved', end_date__lt=today).count()
    active_handouts = Booking.objects.filter(status='Approved', start_date__lte=today, end_date__gte=today)
    future_bookings = Booking.objects.filter(status='Approved', start_date__gt=today)

    chart_labels, chart_green, chart_red, chart_yellow = [], [], [], []
    for asset in assets:
        chart_labels.append(asset.name)
        active = Booking.objects.filter(asset=asset, status='Approved', start_date__lte=today, end_date__gte=today).aggregate(total=Sum('quantity_requested'))['total'] or 0
        future = Booking.objects.filter(asset=asset, status='Approved', start_date__gt=today).aggregate(total=Sum('quantity_requested'))['total'] or 0
        available = max(0, asset.quantity_available - active)
        chart_red.append(active)
        chart_yellow.append(future)
        chart_green.append(available)
        
    context = {
        'assets': assets,
        'is_admin': True,
        'has_unread': has_unread, 
        'total_assets': total_assets,
        'deployed_units': deployed_units,
        'pending_approvals': pending_approvals,
        'overdue_count': overdue_count,
        'active_handouts': active_handouts,
        'future_bookings': future_bookings,
        'chart_labels': json.dumps(chart_labels),
        'chart_red': json.dumps(chart_red),
        'chart_yellow': json.dumps(chart_yellow),
        'chart_green': json.dumps(chart_green),
    }
    return render(request, 'core/dashboard.html', context)

@login_required(login_url='login')
def clear_notifications(request):
    if hasattr(request.user, 'notifications'):
        try:
            # Tries to mark them read so they stop twinkling
            request.user.notifications.filter(is_read=False).update(is_read=True)
        except:
            # Fallback: Clears out notification history data if field structures differ
            request.user.notifications.all().delete()
    return redirect('dashboard')

@login_required
def book_asset(request, asset_id):
    asset = get_object_or_404(Asset, id=asset_id)
    today = timezone.localdate()
    
    today_bookings = Booking.objects.filter(
        asset=asset, 
        status='Approved',
        start_date__lte=today,
        end_date__gte=today
    )
    taken_today = today_bookings.aggregate(Sum('quantity_requested'))['quantity_requested__sum'] or 0
    unreserved_count = asset.quantity_available - taken_today

    if request.method == 'POST':
        quantity = int(request.POST.get('quantity', 1))
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')

        total_capacity = asset.quantity_available
        overlapping_bookings = Booking.objects.filter(
            asset=asset,
            status='Approved',
            start_date__lte=end_date,  
            end_date__gte=start_date   
        )
        taken_units = overlapping_bookings.aggregate(Sum('quantity_requested'))['quantity_requested__sum'] or 0

        if quantity > (total_capacity - taken_units):
            messages.error(request, f"Date Conflict: Only {total_capacity - taken_units} units are available between those specific dates.")
            return render(request, 'core/book_asset.html', {
                'asset': asset, 
                'unreserved_count': unreserved_count
            })
            
        # 1. Capture the newly created booking instance into a variable named 'booking'
        booking = Booking.objects.create(
            user=request.user, 
            asset=asset, 
            quantity_requested=quantity,
            start_date=start_date, 
            end_date=end_date
        )
        
        # 2. Trigger notifications to admins immediately upon successful booking creation
        admin_users = User.objects.filter(is_staff=True)
        for admin in admin_users:
            Notification.objects.create(
                user=admin,
                message=f"New Request: {request.user.username} has requested {booking.quantity_requested}x {booking.asset.name}.",
                is_read=False
            )
            
        messages.success(request, "Booking requested successfully!")
        return redirect('history')  # Redirect user to history timeline page
        
    # Standard GET request renders the template form normally
    return render(request, 'core/book_asset.html', {
        'asset': asset, 
        'unreserved_count': unreserved_count
    })

@login_required
def borrowing_history(request):
    bookings = Booking.objects.filter(user=request.user).order_by('-created_at')
    context = {
        'bookings': bookings,
        'today': timezone.localdate(),
    }
    return render(request, 'core/history.html', context)

@login_required
def admin_workflow(request):
    if not request.user.is_staff:
        messages.error(request, "Unauthorized access.")
        return redirect('dashboard')

    today = timezone.localdate()
    pending_requests = Booking.objects.filter(status='Pending').order_by('-created_at')
    active_handouts = Booking.objects.filter(status='Approved', start_date__lte=today).order_by('-created_at')
    future_bookings = Booking.objects.filter(status='Approved', start_date__gt=today).order_by('start_date')

    context = {
        'pending_requests': pending_requests,
        'active_handouts': active_handouts,
        'future_bookings': future_bookings,
    }
    return render(request, 'core/admin_workflow.html', context)


@login_required
def update_booking_status(request, booking_id, action):
    if not request.user.is_staff:
        return redirect('dashboard')
        
    booking = get_object_or_404(Booking, id=booking_id)

    if action == 'approve':
        booking.status = 'Approved'
        booking.save()
        messages.success(request, "Booking Request Approved.")
        create_notification(booking.user, f"🎉 Your reservation for {booking.asset.name} was Approved.")
    elif action == 'reject':
        booking.status = 'Rejected'
        booking.save()
        messages.info(request, "Booking Request Rejected.")
        create_notification(booking.user, f"❌ Your request for {booking.asset.name} was Rejected.")
    elif action == 'return':
        booking.status = 'Returned'
        booking.save()
        messages.success(request, "Asset Marked as Safely Returned.")
        create_notification(booking.user, f"✅ Your return of {booking.asset.name} has been processed.")

    return redirect('admin_workflow')


def create_notification(user, message):
    Notification.objects.create(user=user, message=message)

@login_required
def qr_asset_action(request, asset_id):
    asset = get_object_or_404(Asset, id=asset_id)
    messages.info(request, f"🔍 Scanned QR Code for: {asset.name}")
    return redirect('book_asset', asset_id=asset.id)

@login_required
def notification_center(request):
    user_notifications = request.user.notifications.all()
    user_notifications.update(is_read=True)
    return render(request, 'core/notifications.html', {'notifications': user_notifications})


# --- CRITICAL UPDATE: ADMIN LOCKDOWN & QUANTITY DEDUCTION MATH ---
@login_required
def report_asset_health(request, asset_id):
    if not request.user.is_staff:
        messages.error(request, "Access Denied: Only administrators can modify health status metrics.")
        return redirect('dashboard')
        
    asset = get_object_or_404(Asset, id=asset_id)
    
    if request.method == 'POST':
        status_update = request.POST.get('health_status')
        description = request.POST.get('description')
        
        # RULE: Out of Stock means no inventory modification/damage deduction is required
        if status_update == 'Out of Stock':
            asset.status = 'Out of Stock'
            asset.save()
            
            MaintenanceLog.objects.create(
                asset=asset,
                reported_by=request.user,
                issue_description=f"[Manually set to Out of Stock] {description}",
                units_damaged=0
            )
            messages.success(request, f"📦 {asset.name} updated successfully to Out of Stock layout.")
            return redirect('dashboard')
            
        # Processing Maintenance Damage Math
        try:
            damaged_units = int(request.POST.get('damaged_units', 0))
        except ValueError:
            damaged_units = 0
            
        if damaged_units > asset.quantity_available:
            messages.error(request, f"Operation Failed: Cannot log {damaged_units} broken units. Only {asset.quantity_available} remain functional.")
            return render(request, 'core/report_health.html', {'asset': asset})
        
        # Log to Database Audit Table
        MaintenanceLog.objects.create(
            asset=asset,
            reported_by=request.user,
            issue_description=description,
            units_damaged=damaged_units
        )
        
        # Subtract operational inventory
        asset.quantity_available -= damaged_units
        
        # If units are still left on shelves, keep overall line active ('Available')
        if asset.quantity_available > 0:
            asset.status = 'Available'
        else:
            asset.status = 'Maintenance'
            
        asset.save()
        messages.success(request, f"🔧 Log saved. {asset.quantity_available} remaining units are available for bookings.")
        return redirect('dashboard')
        
    return render(request, 'core/report_health.html', {'asset': asset})