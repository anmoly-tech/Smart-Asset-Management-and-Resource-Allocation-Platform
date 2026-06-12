from django.contrib import admin
from django.urls import path
from core import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.dashboard, name='dashboard'),
    path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('book/<int:asset_id>/', views.book_asset, name='book_asset'),
    path('history/', views.borrowing_history, name='history'),
    path('manage-requests/', views.admin_workflow, name='admin_workflow'),
    path('booking-action/<int:booking_id>/<str:action>/', views.update_booking_status, name='update_booking'),
    path('asset/<int:asset_id>/check/', views.qr_asset_action, name='qr_asset_action'),
    path('notifications/', views.notification_center, name='notification_center'),
    path('asset/<int:asset_id>/health/', views.report_asset_health, name='report_asset_health'),
    path('notifications/clear/', views.clear_notifications, name='clear_notifications'),
    path('admin-workspace/purge-history/', views.admin_clear_history, name='admin_clear_history'),
    path('notification/read/<int:notification_id>/', views.read_single_notification, name='read_single_notification'),
    path('notifications/clear-all/', views.clear_all_notifications, name='clear_all_notifications'),
]