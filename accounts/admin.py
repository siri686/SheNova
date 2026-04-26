from django.contrib import admin

from .models import Profile, Application, Fund, Loan, Repayment, Transaction


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):

    list_display = ['user', 'role', 'max_limit', 'used_amount']


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):

    list_display = ['student', 'amount_requested', 'status', 'applied_date']


@admin.register(Fund)
class FundAdmin(admin.ModelAdmin):

    list_display = ['total_fund', 'available_fund', 'last_updated']


@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):

    list_display = ['student', 'total_amount', 'remaining_amount', 'created_at']


@admin.register(Repayment)
class RepaymentAdmin(admin.ModelAdmin):

    list_display = ['loan', 'amount_paid', 'paid_on']


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):

    list_display = ['student', 'loan', 'amount', 'type', 'date']