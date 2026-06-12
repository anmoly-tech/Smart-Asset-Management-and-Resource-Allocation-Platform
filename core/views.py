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
from datetime import datetime, timedelta
from django.contrib.auth import get_user_model

@login_required
def read_single_notification(request, notification_id):
    """Removes the red dot from a single notification by marking it read"""
    notification = get_object_or_404(Notification, id=notification_id, user=request.user)
    notification.is_read = True
    notification.save()
    return redirect(request.META.get('HTTP_REFERER', 'dashboard'))

@login_required
def clear_all_notifications(request):
    """Wipes out the entire notification history like a phone's 'Clear All' button"""
    Notification.objects.filter(user=request.user).delete()
    return redirect(request.META.get('HTTP_REFERER', 'dashboard'))

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

    for asset in assets:
        # 1. Units actively in users' hands TODAY
        active_count = Booking.objects.filter(
            asset=asset,
            status='Approved',
            start_date__lte=today,
            end_date__gte=today
        ).aggregate(total=Sum('quantity_requested'))['total'] or 0
        
        # 2. Maintenance is simply: Total Capacity minus Functional Pool
        asset.units_in_maintenance = asset.total_quantity - asset.quantity_available
        
        # 3. Live availability (On the shelf right now): Functional minus Active Handouts
        asset.live_available = asset.quantity_available - active_count
        
        # Safety catch so it never shows negative
        if asset.live_available < 0: 
            asset.live_available = 0

    has_unread = False
    if hasattr(request.user, 'notifications'):
        has_unread = request.user.notifications.filter(is_read=False).exists()

    # --- REGULAR USER DASHBOARD ---
    if not request.user.is_staff:
        five_days_ago = today - timedelta(days=5)
        my_bookings = Booking.objects.filter(user=request.user, end_date__gte=five_days_ago).order_by('-start_date')
        return render(request, 'core/dashboard.html', {
            'assets': assets,
            'my_bookings': my_bookings,
            'is_admin': False,
            'has_unread': has_unread,
        })

    # --- ADMIN DASHBOARD ---
    total_assets = Asset.objects.count()
    deployed_units = Booking.objects.filter(status='Approved', start_date__lte=today, end_date__gte=today).aggregate(total=Sum('quantity_requested'))['total'] or 0
    pending_approvals = Booking.objects.filter(status='Pending').count()
    overdue_count = Booking.objects.filter(status='Approved', end_date__lt=today).count()
    active_handouts = Booking.objects.filter(status='Approved', start_date__lte=today, end_date__gte=today)
    future_bookings = Booking.objects.filter(
    status='Approved', 
    start_date__gt=today
).order_by('asset__name', 'start_date')

    # --- FIXED CHART MATH ---
    chart_labels, chart_green, chart_red, chart_yellow = [], [], [], []
    for asset in assets:
        chart_labels.append(asset.name)
        
        # Active today
        active = Booking.objects.filter(
            asset=asset, status='Approved', start_date__lte=today, end_date__gte=today
        ).aggregate(total=Sum('quantity_requested'))['total'] or 0
        
        # Future bookings
        future = Booking.objects.filter(
            asset=asset, status='Approved', start_date__gt=today
        ).aggregate(total=Sum('quantity_requested'))['total'] or 0
        
        # Correctly calculate green (available) bar so it doesn't duplicate total units
        live_shelf = asset.quantity_available - active
        if live_shelf < 0: live_shelf = 0
        
        chart_red.append(active)
        chart_yellow.append(future)
        chart_green.append(live_shelf) 
        
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

@login_required(login_url='login')
def book_asset(request, asset_id):
    asset = get_object_or_404(Asset, id=asset_id)
    
    # === POST REQUEST (When user clicks Submit) ===
    if request.method == 'POST':
        requested_qty = int(request.POST.get('quantity', 1))
        start_date_str = request.POST.get('start_date')
        end_date_str = request.POST.get('end_date')
        
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        
        overlapping_bookings = Booking.objects.filter(
            asset=asset,
            status__in=['Approved', 'Pending'],
            start_date__lte=end_date,
            end_date__gte=start_date
        )
        
        max_used_in_range = 0
        current_day = start_date
        while current_day <= end_date:
            daily_used = sum(
                b.quantity_requested for b in overlapping_bookings 
                if b.start_date <= current_day <= b.end_date
            )
            if daily_used > max_used_in_range:
                max_used_in_range = daily_used
            current_day += timedelta(days=1)
            
        available_for_dates = asset.quantity_available - max_used_in_range
        if available_for_dates < 0:
            available_for_dates = 0

        if requested_qty > available_for_dates:
            messages.error(
                request, 
                f"Date Conflict: Only {available_for_dates} units are available to cover the entire duration of {start_date_str} to {end_date_str}."
            )
            return redirect('book_asset', asset_id=asset.id)
            
        Booking.objects.create(
            user=request.user,
            asset=asset,
            quantity_requested=requested_qty,
            start_date=start_date,
            end_date=end_date,
            status='Pending'
        )
        
        User = get_user_model()
        admin_users = User.objects.filter(is_staff=True)
        for admin in admin_users:
            Notification.objects.create(
                user=admin,
                message=f"New request from {request.user.username}: {requested_qty}x {asset.name} ({start_date_str} to {end_date_str})."
            )
        
        messages.success(request, f"Successfully requested {requested_qty}x {asset.name}. Awaiting admin approval.")
        return redirect('dashboard')

    # === GET REQUEST (When user first loads the page) ===
    today = timezone.now().date()
    
    # 1. Grab future reservations for the table
    future_reservations = Booking.objects.filter(
        asset=asset,
        status__in=['Approved', 'Pending'],
        end_date__gte=today
    ).order_by('start_date')

    # 2. Calculate live shelf availability to show on the form
    active_count = Booking.objects.filter(
        asset=asset,
        status='Approved',
        start_date__lte=today,
        end_date__gte=today
    ).aggregate(total=Sum('quantity_requested'))['total'] or 0
    
    live_available = asset.quantity_available - active_count
    if live_available < 0:
        live_available = 0

    context = {
        'asset': asset,
        'future_reservations': future_reservations,
        'live_available': live_available
    }
    return render(request, 'core/book_asset.html', context)

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
    asset = get_object_or_404(Asset, id=asset_id)
    
    # Maintenance is just Total minus Functional. Active bookings don't change if a unit is broken.
    current_maintenance = asset.total_quantity - asset.quantity_available
    
    if request.method == 'POST':
        to_maintenance = int(request.POST.get('units_to_maintenance', 0))
        to_functional = int(request.POST.get('units_to_functional', 0))
        global_status = request.POST.get('health_status')
        
        if to_maintenance > 0:
            if to_maintenance <= asset.quantity_available:
                asset.quantity_available -= to_maintenance
            else:
                messages.error(request, f"Cannot move {to_maintenance} units to maintenance. Only {asset.quantity_available} functional units left.")
                return redirect('report_asset_health', asset_id=asset.id)
                
        if to_functional > 0:
            if to_functional <= current_maintenance:
                asset.quantity_available += to_functional
            else:
                messages.error(request, f"Cannot restore {to_functional} units. Only {current_maintenance} are in maintenance.")
                return redirect('report_asset_health', asset_id=asset.id)

        if global_status:
            asset.status = global_status
            
        asset.save()
        messages.success(request, f"Health logs updated for {asset.name}.")
        return redirect('dashboard')
        
    return render(request, 'core/report_health.html', {
        'asset': asset,
        'current_maintenance': current_maintenance
    })