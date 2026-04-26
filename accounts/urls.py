from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('', views.login_view, name='login'),
    path('payment/<int:transaction_id>/', views.payment_page, name='payment_page'),
    path('student/dashboard/', views.student_dashboard, name='student_dashboard'),
    path('supervisor/dashboard/', views.supervisor_dashboard, name='supervisor_dashboard'),
    path('system-admin/dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('system-admin/approve/<int:app_id>/', views.admin_approve_application, name='admin_approve_application'),
    path(
        'student_transactions/',
        views.student_transactions,
        name='student_transactions'
    ),
    path('payment/<int:transaction_id>/', views.payment_page, name='payment_page'),
    path(
        'admin_fund/',
        views.admin_fund,
        name='admin_fund'
    ),

    path(
        'admin_transactions/',
        views.admin_transactions,
        name='admin_transactions'
    ),
    path('add-money/', views.add_money, name='add_money'),
    path('payment-success/', views.payment_success, name='payment_success'),
    path('applications/', views.applications_list, name='applications_list'),
    path('admin-applications/', views.admin_applications, name='admin_applications'),
    path('reports/', views.reports, name='reports'),
    path('settings/', views.settings_page, name='settings'),
    path('repay/<int:loan_id>/', views.repay_loan, name='repay_loan'),
    path('review/<int:app_id>/', views.review_application, name='review_application'),
    path('student/register/', views.student_register, name='student_register'),
    path('supervisor/register/', views.supervisor_register, name='supervisor_register'),
    path('student/apply/', views.student_apply, name='student_apply'),
    path('logout/', views.logout_view, name='logout'),
    path('forgot-password/', views.forgot_password, name='forgot_password'),
    path('reset-password/<int:user_id>/', views.reset_password, name='reset_password'),
]+ static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)