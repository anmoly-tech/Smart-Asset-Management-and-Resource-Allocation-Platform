from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from datetime import date
from django.db.models import Sum
from .models import Asset, Booking, Notification, MaintenanceLog
import json
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


@login_required
def dashboard(request):
    assets = Asset.objects.all()
    today = timezone.now().date()
    
    # --- 1. TOP CARDS & TABLE DATA (The missing numbers!) ---
    total_assets = Asset.objects.count()
    
    deployed_units = Booking.objects.filter(
        status='Approved', start_date__lte=today, end_date__gte=today
    ).aggregate(total=Sum('quantity_requested'))['total'] or 0
    
    pending_approvals = Booking.objects.filter(status='Pending').count()
    overdue_count = Booking.objects.filter(status='Approved', end_date__lt=today).count()
    
    active_handouts = Booking.objects.filter(status='Approved', start_date__lte=today, end_date__gte=today)
    future_bookings = Booking.objects.filter(status='Approved', start_date__gt=today)

    # --- 2. STACKED BAR CHART DATA ---
    chart_labels = []
    chart_green = []  
    chart_red = []    
    chart_yellow = [] 
    
    for asset in assets:
        chart_labels.append(asset.name)
        
        active_bookings = Booking.objects.filter(
            asset=asset, status='Approved', start_date__lte=today, end_date__gte=today
        ).aggregate(total=Sum('quantity_requested'))['total'] or 0
        
        future_bookings_count = Booking.objects.filter(
            asset=asset, status='Approved', start_date__gt=today
        ).aggregate(total=Sum('quantity_requested'))['total'] or 0
        
        available_units = asset.quantity_available - active_bookings
        if available_units < 0: 
            available_units = 0 
            
        chart_red.append(active_bookings)
        chart_yellow.append(future_bookings_count)
        chart_green.append(available_units)
        
    # --- 3. MERGED CONTEXT ---
    context = {
        'assets': assets,
        # Restored original variables
        'total_assets': total_assets,
        'deployed_units': deployed_units,
        'pending_approvals': pending_approvals,
        'overdue_count': overdue_count,
        'active_handouts': active_handouts,
        'future_bookings': future_bookings,
        # New chart variables
        'chart_labels': json.dumps(chart_labels),
        'chart_red': json.dumps(chart_red),
        'chart_yellow': json.dumps(chart_yellow),
        'chart_green': json.dumps(chart_green),
    }
    
    return render(request, 'core/dashboard.html', context)

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
            
        Booking.objects.create(
            user=request.user, asset=asset, quantity_requested=quantity,
            start_date=start_date, end_date=end_date
        )
        messages.success(request, "Booking requested successfully!")
        return redirect('history')
        
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