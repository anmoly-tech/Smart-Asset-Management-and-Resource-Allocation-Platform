from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from .models import Asset, Booking
from datetime import date
from django.db.models import Sum

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
    today = timezone.localdate()
    assets = Asset.objects.all()

    # 1. SYSTEM METRICS
    total_assets = Asset.objects.count()
    pending_approvals_count = Booking.objects.filter(status='Pending').count()
    
    # --- FIX: Calculate Deployed UNITS instead of Orders ---
    # Find bookings that are approved AND actively checked out today
    currently_active_bookings = Booking.objects.filter(
        status='Approved',
        start_date__lte=today,
        end_date__gte=today
    )
    # Sum up the quantities of those specific active bookings
    deployed_units_count = currently_active_bookings.aggregate(Sum('quantity_requested'))['quantity_requested__sum'] or 0
    # -------------------------------------------------------

    overdue_count = Booking.objects.filter(status='Approved', end_date__lt=today).count()

    # --- ADVANCED DASHBOARD CALENDAR MATH ---
    for asset in assets:
        total_capacity = asset.quantity_available
        today_bookings = Booking.objects.filter(
            asset=asset,
            status='Approved',
            start_date__lte=today,
            end_date__gte=today
        )
        taken_today = today_bookings.aggregate(Sum('quantity_requested'))['quantity_requested__sum'] or 0
        asset.dynamic_available = total_capacity - taken_today

    # --- TRANSPARENCY LEDGER DATA ---
    active_handouts = Booking.objects.filter(status='Approved', start_date__lte=today, end_date__gte=today).order_by('-start_date')
    future_bookings = Booking.objects.filter(status='Approved', start_date__gt=today).order_by('start_date')

    # Search and Filtering Operations
    query = request.GET.get('search')
    category = request.GET.get('category')
    if query:
        assets = assets.filter(name__icontains=query)
    if category:
        assets = assets.filter(category__icontains=category)

    # CRITICAL: If variables are not in this dictionary, the HTML cannot see them!
    context = {
        'assets': assets,
        'total_assets': total_assets,
        
        # Sending our new math to the dashboard
        'deployed_units': deployed_units_count, 
        
        'pending_approvals': pending_approvals_count,
        'overdue_count': overdue_count,
        
        # Sending the table data to the dashboard
        'active_handouts': active_handouts,
        'future_bookings': future_bookings,
    }
    return render(request, 'core/dashboard.html', context)

@login_required
def book_asset(request, asset_id):
    asset = get_object_or_404(Asset, id=asset_id)
    today = timezone.localdate()
    
    # --- UI MATH FIX: Calculate what is available on the shelf TODAY ---
    # We only care about bookings that are actively checked out EXACTLY today.
    today_bookings = Booking.objects.filter(
        asset=asset, 
        status='Approved',
        start_date__lte=today,
        end_date__gte=today
    )
    taken_today = today_bookings.aggregate(Sum('quantity_requested'))['quantity_requested__sum'] or 0
    
    # Total Capacity minus what is currently out of the vault right now
    unreserved_count = asset.quantity_available - taken_today
    # -----------------------------------------------------------

    if request.method == 'POST':
        quantity = int(request.POST.get('quantity', 1))
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')

        # 1. The true capacity is the unedited database quantity
        total_capacity = asset.quantity_available

        # 2. Find any approved bookings that overlap with the user's requested dates
        overlapping_bookings = Booking.objects.filter(
            asset=asset,
            status='Approved',
            start_date__lte=end_date,  
            end_date__gte=start_date   
        )

        # 3. Sum up how many units are busy during those specific overlapping dates
        taken_units = overlapping_bookings.aggregate(Sum('quantity_requested'))['quantity_requested__sum'] or 0

        # 4. Math Check: Do we have enough capacity?
        if quantity > (total_capacity - taken_units):
            messages.error(request, f"Date Conflict: Only {total_capacity - taken_units} units are available between those specific dates.")
            
            # We use 'render' instead of 'redirect' so the error message shows instantly!
            return render(request, 'core/book_asset.html', {
                'asset': asset, 
                'unreserved_count': unreserved_count
            })
            
        # If dates are clear, create booking
        Booking.objects.create(
            user=request.user, asset=asset, quantity_requested=quantity,
            start_date=start_date, end_date=end_date
        )
        messages.success(request, "Booking requested successfully!")
        return redirect('history')
        
    # Pass our newly calculated 'unreserved_count' to the HTML page
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

    # Split the tables!
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

    # Simplified status updating logic
    if action == 'approve':
        booking.status = 'Approved'
        booking.save()
        messages.success(request, "Booking Request Approved.")
    elif action == 'reject':
        booking.status = 'Rejected'
        booking.save()
        messages.info(request, "Booking Request Rejected.")
    elif action == 'return':
        booking.status = 'Returned'
        booking.save()
        messages.success(request, "Asset Marked as Safely Returned.")

    return redirect('admin_workflow')