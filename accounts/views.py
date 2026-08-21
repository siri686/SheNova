from django.shortcuts import render, redirect,get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from .models import Loan, Repayment, Fund, Profile, Application, Transaction,Notification
from django.contrib import messages
import random
import os
from decimal import Decimal
from django.db.models import Sum
from django.utils.timezone import now
from django.conf import settings
from django.contrib.auth import update_session_auth_hash
from django.core.mail import send_mail
from django.conf import settings
from django.utils.timezone import now
from datetime import timedelta
from .models import Loan
import re
from .risk_engine import analyze_application


def calculate_credit_score(student_profile, application):

    score = 500  # Base score

    # 1️⃣ Income factor
    income = int(application.family_income)

    if income > 100000:
        score += 120
    elif income > 50000:
        score += 70
    else:
        score -= 50

    # 2️⃣ Loan usage factor
    if student_profile.max_limit > 0:
        usage_ratio = student_profile.used_amount / student_profile.max_limit
    else:
        usage_ratio = 1

    if usage_ratio < 0.3:
        score += 120
    elif usage_ratio < 0.6:
        score += 60
    else:
        score -= 80

    # 3️⃣ Requested amount check
    if application.amount_requested <= student_profile.remaining_limit():
        score += 50
    else:
        score -= 100

    return score
# ---------------- LOGIN PAGE ----------------
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from .models import Profile

def login_view(request):
    if request.method == 'POST':

        role = request.POST.get('role')

        # ✅ STEP 1: GET CREDENTIALS
        if role == "student":
            username = request.POST.get('student_username')
            password = request.POST.get('student_password')

        elif role == "supervisor":
            username = request.POST.get('supervisor_username')
            password = request.POST.get('supervisor_password')

        elif role == "admin":
            username = request.POST.get('admin_username')
            password = request.POST.get('admin_password')

        else:
            return render(request, 'accounts/login.html',
                          {'error': 'Invalid role'})

        # ✅ STEP 2: AUTHENTICATE FIRST (VERY IMPORTANT)
        user = authenticate(request, username=username, password=password)

        if user is None:
            return render(request, 'accounts/login.html',
                          {'error': 'Invalid username or password'})

        # ✅ STEP 3: ADMIN CHECK AFTER AUTH
        if role == "admin":
            if user.is_superuser:
                login(request, user)
                return redirect('admin_dashboard')
            else:
                return render(request, 'accounts/login.html',
                              {'error': 'Not an admin'})

        # ✅ STEP 4: PROFILE FOR OTHER USERS
        profile = Profile.objects.filter(user=user).first()

        if not profile:
            return render(request, 'accounts/login.html',
                          {'error': 'Profile not found'})

        if profile.role != role:
            return render(request, 'accounts/login.html',
                          {'error': f'Unauthorized as {role}'})

        # ✅ STEP 5: LOGIN
        login(request, user)

        if role == 'student':
            return redirect('student_dashboard')

        elif role == 'supervisor':
            return redirect('supervisor_dashboard')

    return render(request, 'accounts/login.html')

# ---------------- DASHBOARDS ----------------



@login_required
def student_dashboard(request):
    check_due_payments()

    profile = Profile.objects.get(user=request.user)

    applications = Application.objects.filter(student=request.user)
    loans = Loan.objects.filter(student=request.user, status="Active")
    next_payment = loans.filter(
    remaining_amount__gt=0,
    deadline__isnull=False
).order_by('deadline').first()
    transactions = Transaction.objects.filter(
        student=request.user
    ).order_by('-date')

    notifications = Notification.objects.filter(
        student=request.user
    ).order_by('-created_at')[:5]

    # ===============================
    # ✅ USAGE %
    # ===============================
    usage_percent = 0
    if profile.max_limit > 0:
        usage_percent = (profile.used_amount / profile.max_limit) * 100
    else:
        usage_percent = 0

    # ===============================
    # ✅ CREDIT SCORE (CIBIL STYLE)
    # ===============================
    repayments = Transaction.objects.filter(
        student=request.user,
        type="Repayment"
    )

    total_repayments = repayments.count()
    late_payments = repayments.filter(is_late=True).count()
    on_time_payments = total_repayments - late_payments
    # Base score
    credit_score = 650

    # ✅ Reward good behavior
    credit_score += on_time_payments * 15

    # ❌ Penalize late payments
    credit_score -= late_payments * 25

    # 🎯 Bonus for closing loans
    closed_loans = loans.filter(status="Closed").count()
    credit_score += closed_loans * 20

    # 💳 Usage penalty (light)
    if profile.max_limit > 0:
        usage_ratio = profile.used_amount / profile.max_limit
        credit_score -= int(usage_ratio * 50)

    # ✅ Keep in valid range
    credit_score = max(300, min(850, credit_score))

    # ===============================
    # 🎨 CIRCLE UI CALCULATION
    # ===============================
    percent = (credit_score - 300) / (850 - 300)
    score_offset = int(440 * (1 - percent))

    # ===============================
    # ✅ APPLY LOCK LOGIC
    # ===============================
    can_apply = True
    remaining_to_unlock = 0

    active_loan = loans.filter(status="Active").first()

    if active_loan:
        paid_amount = active_loan.total_amount - active_loan.remaining_amount

        if paid_amount < (active_loan.total_amount * Decimal('0.5')):
            can_apply = False
        remaining_to_unlock = (active_loan.total_amount * Decimal('0.5')) - paid_amount


    # ===============================
    # 🔍 DEBUG (OPTIONAL REMOVE LATER)
    # ===============================
    print("Total repayments:", total_repayments)
    print("On-time:", on_time_payments)
    print("Late:", late_payments)
    print("Credit score:", credit_score)

    # ===============================
    # ✅ FINAL RENDER
    # ===============================
    return render(request, 'accounts/student_dashboard.html', {
        'profile': profile,
        'applications': applications,
        'loans': loans,
        "next_payment": next_payment,
        'transactions': transactions,
        'notifications': notifications,
        'usage_percent': usage_percent,
        'credit_score': credit_score,
        'score_offset': score_offset,
        'can_apply': can_apply,
        "remaining_to_unlock": remaining_to_unlock,
        'today': now().date()
    })

@login_required
def student_apply(request):

    profile = get_object_or_404(Profile, user=request.user)

    if request.method == 'POST':

        # 🆕 Emergency + Priority
        is_emergency = request.POST.get('is_emergency') == 'True'
        priority_level = request.POST.get('priority_level')

        # ===== 🔒 CHECK ACTIVE LOAN =====
        active_loan = Loan.objects.filter(
            student=request.user,
            status="Active"
        ).first()

        if active_loan and active_loan.remaining_amount > 0:
            paid_amount = active_loan.total_amount - active_loan.remaining_amount

            if paid_amount < (active_loan.total_amount * Decimal('0.5')):
                messages.error(
                    request,
                    "⚠️ You must repay at least 50% of your current loan before applying again."
                )
                return redirect('student_dashboard')

        # ===== 🟡 GET FORM DATA =====
        try:
            amount = Decimal(request.POST.get('amount'))
            plan = request.POST.get('repayment_plan')
            reason = request.POST.get('reason')
            family_income = request.POST.get('family_income')
        except:
            messages.error(request, "Invalid input data")
            return redirect('student_apply')
        # ===== 🔒 EXTRA VALIDATIONS (ADD HERE) =====
        phone = request.POST.get('phone')
        year = request.POST.get('year')
        roll = request.POST.get('student_id_number')
        ref_phone = request.POST.get('reference_phone')

        if not ref_phone or not ref_phone.isdigit() or len(ref_phone) != 10:
            messages.error(request, "📱 Reference phone must be 10 digits")
            return redirect('student_apply')
        print("PHONE:", phone)
        # 📱 PHONE VALIDATION
        if not phone or not phone.isdigit() or len(phone) != 10:
            messages.error(request, "📱 Phone must be exactly 10 digits")
            return redirect('student_apply')

        # 🎓 YEAR VALIDATION
        if year not in ['1', '2', '3', '4']:
            messages.error(request, "🎓 Invalid year selected")
            return redirect('student_apply')

        # 🆔 ROLL NUMBER VALIDATION
        if not roll or len(roll) < 6:
            messages.error(request, "🆔 Invalid roll number")
            return redirect('student_apply')
        
        aadhaar = request.POST.get('aadhaar_number')
        pan = request.POST.get('pan_number')

        # 🪪 AADHAAR VALIDATION (12 digits only)
        if not aadhaar or not aadhaar.isdigit() or len(aadhaar) != 12:
            messages.error(request, "🪪 Aadhaar must be exactly 12 digits")
            return redirect('student_apply')

        # 🆔 PAN VALIDATION (ABCDE1234F format)
        pan_pattern = r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$'

        if not pan or not re.match(pan_pattern, pan.upper()):
            messages.error(request, "🆔 Invalid PAN format (ABCDE1234F)")
            return redirect('student_apply')


        # ===== 🔒 BASIC VALIDATION =====
        if not amount or not plan or not reason or not family_income:
            messages.error(request, "Please fill all required fields")
            return redirect('student_apply')

        # ===== 🔒 YEARLY LIMIT CHECK =====
        current_year = now().year

        used_this_year = Application.objects.filter(
            student=request.user,
            applied_date__year=current_year
        ).aggregate(total=Sum('amount_requested'))['total'] or Decimal('0')

        if used_this_year + amount > Decimal('10000'):
            messages.error(
                request,
                "🚫 Yearly loan limit of ₹10,000 exceeded."
            )
            return redirect('student_apply')

        # ===== 🔒 PROFILE LIMIT CHECK =====
        remaining_limit = profile.remaining_limit()

        if amount > remaining_limit:
            messages.error(
                request,
                f"🚫 Limit exceeded. Remaining limit: ₹{remaining_limit}"
            )
            return redirect('student_apply')

        # ===== 📂 FILES =====
        aadhar_card = request.FILES.get('aadhar_card')
        pan_card = request.FILES.get('pan_card')
        student_id_card = request.FILES.get('student_id_card')
        
        if not aadhar_card or not pan_card or not student_id_card:
            messages.error(request, "📄 All documents are required")
            return redirect('student_apply')
        # ===== ✅ CREATE APPLICATION =====
        app = Application.objects.create(
            student=request.user,
            amount_requested=amount,
            reason=reason,
            family_income=family_income,
            repayment_plan=plan,
            
            status="Pending",
            is_emergency=is_emergency,
            priority_level=priority_level,
            aadhaar_number=request.POST.get('aadhaar_number'),
            pan_number=pan.upper(),
            student_id_number=request.POST.get('student_id_number'),
            reference_name=request.POST.get('reference_name'),
            reference_relation=request.POST.get('reference_relation'),
            reference_phone=request.POST.get('reference_phone'),
            aadhar_card=aadhar_card,
            pan_card=pan_card,
            student_id_card=student_id_card,
        )
        result = analyze_application(app)

        app.ai_risk_score = result["score"]
        app.ai_risk_level = result["level"]
        app.ai_risk_reasons = "\n".join(result["reasons"])
        app.ai_recommendation = result["recommendation"]

        app.save()

        print("AI RISK SCORE:", app.ai_risk_score)
        print("AI RISK LEVEL:", app.ai_risk_level)
        print("APPLICATION CREATED:", app.id, app.status)

        # 🔔 Notification
        if is_emergency:
            Notification.objects.create(
                student=request.user,
                message="🚨 Emergency loan request submitted! Fast review in progress."
            )

        messages.success(request, "✅ Application submitted successfully!")

        # ✅ VERY IMPORTANT
        return redirect('student_dashboard')

    # ✅ GET request
    return render(request, 'accounts/student_apply.html', {
        'profile': profile
    })

@login_required
def student_transactions(request):

    transactions = Transaction.objects.filter(
        student=request.user
    ).order_by('-date')

    return render(request,
        'accounts/student_transactions.html',
        {'transactions': transactions}
    )
from django.db.models import Q
@login_required
def supervisor_dashboard(request):

    profile = Profile.objects.get(user=request.user)

    # 🔒 Only supervisors allowed
    if profile.role != 'supervisor':
        return redirect('login')
    query = request.GET.get('q')
    applications = Application.objects.all()
    if query:
        applications = applications.filter(
            Q(student__username__icontains=query) |
            Q(reason__icontains=query) |
            Q(status__icontains=query)
        )
    # calculate credit score for each application
    for app in applications:

        student_profile = Profile.objects.get(user=app.student)

        score = calculate_credit_score(student_profile, app)

        # assign risk level
        if score >= 650:
            app.risk_level = "Low"
        elif score >= 550:
            app.risk_level = "Medium"
        else:
            app.risk_level = "High"
    total_apps = applications.count()
    pending_count = applications.filter(status__iexact="Pending").count()
    approved_count = applications.filter(Q(status__iexact="Approved") | Q(status__iexact="Funded")).count()
    rejected_count = applications.filter(status__iexact="Rejected").count()
    completed_count = applications.filter(status__iexact="Completed").count()


    return render(request, "accounts/supervisor_dashboard.html", {
        "applications": applications,
        "total_apps": total_apps,
        "pending_count": pending_count,
        "approved_count": approved_count,
        "rejected_count": rejected_count,
        "completed_count": completed_count,
    })
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from .models import Application, Profile, Notification

@login_required
def review_application(request, app_id):

    profile = Profile.objects.get(user=request.user)

    # Only supervisor allowed
    if profile.role != 'supervisor':
        return redirect('login')

    application = get_object_or_404(Application, id=app_id)
    student_profile = Profile.objects.get(user=application.student)

    # Check if application is already processed
    readonly = application.status.lower() != "pending"

    # Credit Score
    score = calculate_credit_score(student_profile, application)
    if score < 600:
        risk = "High"
    elif score < 750:
        risk = "Medium"
    else:
        risk = "Low"

    # Only allow POST if the application is pending
    if request.method == "POST" and not readonly:

        decision = request.POST.get("decision")
        notes = request.POST.get("notes")

        if not decision:
            messages.error(request, "Invalid action")
            return redirect('applications_list')

        application.supervisor_notes = notes
        application.risk_level = risk

        if decision == "approve":
            application.status = "Approved"
            Notification.objects.create(
                student=application.student,
                message="✅ Your application has been approved by supervisor"
            )
        elif decision == "reject":
            application.status = "Rejected"
            Notification.objects.create(
                student=application.student,
                message="❌ Your application has been rejected"
            )

        application.save()
        messages.success(request, f"Application {decision}d successfully")
        return redirect('applications_list')

    # Always render the page for GET requests
    return render(request, 'accounts/review_application.html', {
        'application': application,
        'student_profile': student_profile,
        'score': score,
        'risk': risk,
        'readonly': readonly
    })

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.db.models import Sum

@login_required
def admin_dashboard(request):

    user = request.user

    # 🔥 ADMIN CHECK (BEST WAY)
    if not user.is_superuser:
        return redirect('login')

    # 📄 Show only important applications
    applications = Application.objects.filter(
        status__in=['Approved', 'Funded']
    ).order_by('-applied_date')[:5]

    fund = Fund.objects.first()

    # 📊 COUNTS
    total_apps = Application.objects.count()
    released_count = Application.objects.filter(status="Funded").count()
    pending_count = Application.objects.filter(status="Pending").count()

    # 💰 TOTAL RELEASED AMOUNT
    released_amount = Application.objects.filter(
        status="Funded"
    ).aggregate(Sum('amount_requested'))['amount_requested__sum'] or 0

    return render(request, 'accounts/admin_dashboard.html', {
        'applications': applications,
        'fund': fund,
        'released_count': released_count,
        'pending_count': pending_count,
        'total_apps': total_apps,
        'released_amount': released_amount
    })
from django.db import transaction

@login_required
def admin_approve_application(request, app_id):

    application = get_object_or_404(Application, id=app_id)

    if application.status.lower() == "funded":
        messages.error(request, "Funds already released")
        return redirect('admin_dashboard')

    if application.status.lower() != "approved":
        messages.error(request, "Application must be approved by supervisor first")
        return redirect('admin_dashboard')

    if Loan.objects.filter(application=application).exists():
        messages.error(request, "Loan already exists")
        return redirect('admin_dashboard')

    student_profile = application.student.profile
    fund = Fund.objects.select_for_update().first()

    amount = application.amount_requested

    if student_profile.used_amount + amount > student_profile.max_limit:
        messages.error(request, "Loan limit exceeded")
        return redirect('admin_dashboard')

    if fund.available_fund < amount:
        messages.error(request, "Insufficient fund")
        return redirect('admin_dashboard')

    with transaction.atomic():

        fund.available_fund -= amount
        fund.save()

        student_profile.used_amount = (student_profile.used_amount or 0) + amount
        student_profile.account_balance = (student_profile.account_balance or 0) + amount
        student_profile.save()

        plan_days = int(application.repayment_plan)
        due_date = now().date() + timedelta(days=plan_days)

        loan = Loan.objects.create(
            student=application.student,
            application=application,
            total_amount=amount,
            remaining_amount=amount,
            status="Active",
            due_date=due_date
        )

        Transaction.objects.create(
            student=application.student,
            loan=loan,
            amount=amount,
            type="Credit",
            status="Completed"
        )

        application.status = "Funded"
        application.save()

    messages.success(request, "💰 Fund released successfully")
    return redirect('admin_dashboard')
# ---------------- LOGOUT ----------------
def logout_view(request):
    logout(request)
    return redirect('login')


# ---------------- STUDENT REGISTER ----------------
from django.contrib.auth.models import User
from django.shortcuts import render, redirect
def student_register(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']

        # 🔒 Check if username already exists
        if User.objects.filter(username=username).exists():
            return render(request, 'accounts/student_register.html', {
                'error': 'Username already exists. Please choose another.'
            })

        user = User.objects.create_user(
            username=username,
            password=password
        )

        
        return redirect('login')

    return render(request, 'accounts/student_register.html')


# ---------------- SUPERVISOR REGISTER ----------------
def supervisor_register(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']

        if User.objects.filter(username=username).exists():
            return render(request, 'accounts/supervisor_register.html', {
                'error': 'Username already exists.'
            })

        user = User.objects.create_user(
            username=username,
            password=password
        )

        # ✅ Create profile ONLY if it does not exist
        profile, created = Profile.objects.get_or_create(user=user)

        # ✅ Set role explicitly
        profile.role = 'supervisor'
        profile.save()

        return redirect('login')

    return render(request, 'accounts/supervisor_register.html')

from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .models import Loan, Profile, Transaction, Fund

@login_required
def repay_loan(request, loan_id):
    profile = Profile.objects.get(user=request.user)
    
    if profile.role != 'student':
        return redirect('login')
    
    loan = get_object_or_404(Loan, id=loan_id, student=request.user)
    
    if request.method == 'POST':
        try:
            amount = Decimal(request.POST.get('amount'))
        except:
            messages.error(request, "Invalid amount format")
            return redirect('student_dashboard')
        
        if amount <= 0:
            messages.error(request, "Amount must be greater than zero")
            return redirect('repay_loan', loan_id=loan.id)

        if amount > loan.remaining_amount:
            messages.error(request, "Amount exceeds remaining balance")
            return redirect('repay_loan', loan_id=loan.id)

        if amount > profile.account_balance:
            messages.error(request, "Insufficient wallet balance")
            return redirect('repay_loan', loan_id=loan.id)
        
        # Deduct from student's wallet
        profile.account_balance -= amount
        profile.save()
        
        # Deduct from loan
        loan.remaining_amount -= amount
        if loan.remaining_amount <= 0:
            loan.status = "Closed"
        loan.save()
        
        # Update system fund
        fund = Fund.objects.first()
        if fund:
            fund.available_fund += int(amount)
            fund.save()
        
        # Create transaction
        Transaction.objects.create(
            student=request.user,
            loan=loan,
            amount=amount,
            type="Repayment",
            status="Success"
        )
        
        messages.success(request, f"₹{amount} successfully repaid from your wallet!")
        return redirect('student_dashboard')
    
    return render(request, 'accounts/repay.html', {'loan': loan, 'profile': profile})

@login_required
def admin_fund(request):

    # 🔥 ADMIN CHECK (CORRECT WAY)
    if not request.user.is_superuser:
        return redirect('login')

    fund = Fund.objects.first()

    if request.method == "POST":
        amount = request.POST.get('amount')

        if fund:
            fund.total_amount += int(amount)
            fund.save()
        else:
            Fund.objects.create(total_amount=int(amount))

        return redirect('admin_fund')

    return render(request, 'accounts/admin_fund.html', {
        'fund': fund
    })

@login_required
def admin_transactions(request):
    transactions = Transaction.objects.all().order_by('-date')
    if request.method == 'POST':
        tid = request.POST.get('transaction_id')
        action = request.POST.get('action')
        t = Transaction.objects.get(id=tid)
        if action == 'approve':
            t.status = 'Approved'
        else:
            t.status = 'Rejected'
        t.save()
    return render(request, 'accounts/admin_transactions.html', {'transactions': transactions})


@login_required
def request_funds(request):
    if request.method == 'POST':
        amount = request.POST.get('amount')
        Transaction.objects.create(student=request.user, amount=amount)
        return redirect('transaction_history')
    return render(request, 'request_funds.html')

@login_required
def transaction_history(request):
    transactions = Transaction.objects.filter(student=request.user)
    return render(request, 'transaction_history.html', {'transactions': transactions})

def get_repayment_status(student):

    loans = Loan.objects.filter(student=student)
    repayment_info = []
    for loan in loans:
        total_loan = loan.amount
        total_repaid = Transaction.objects.filter(student=student, loan=loan, type='Repayment', status='Completed').aggregate(Sum('amount'))['amount__sum'] or 0
        pending = total_loan - total_repaid
        repayment_info.append({
            'loan': loan,
            'total_loan': total_loan,
            'total_repaid': total_repaid,
            'pending': pending
        })
    return repayment_info

@login_required
def payment_page(request, transaction_id):

    transaction = get_object_or_404(
        Transaction,
        id=transaction_id,
        student=request.user
    )

    if request.method == 'POST':

        # ✅ mark transaction completed
        transaction.status = "Completed"
        transaction.save()

        loan = transaction.loan
        amount = transaction.amount

        # ✅ NOW deduct loan (moved from repay_loan)
        loan.remaining_amount -= amount

        # 🔔 Notification
        Notification.objects.create(
            student=request.user,
            message=f"You paid ₹{amount}. Remaining: ₹{loan.remaining_amount}"
        )

        # ✅ Close loan if needed
        if loan.remaining_amount <= 0:
            loan.remaining_amount = 0
            loan.status = "Closed"

            Notification.objects.create(
                student=request.user,
                message="🎉 Loan fully repaid!"
            )

        loan.save()

        # ✅ Add to fund
        fund = Fund.objects.first()
        if fund:
            fund.available_fund += amount
            fund.save()

        # ✅ Repayment record
        Repayment.objects.create(
            loan=loan,
            amount_paid=amount
        )

        return redirect('payment_success')

    return render(request, 'accounts/payment_page.html', {'transaction': transaction})
from django.db.models import Sum

def repayment_data(user):
    loans = Loan.objects.filter(student=user)
    data = []

    for loan in loans:
        total = loan.amount
        paid = Transaction.objects.filter(
            student=user,
            loan=loan,
            type='Repayment',
            status='Completed'
        ).aggregate(Sum('amount'))['amount__sum'] or 0

        percent = int((paid / total) * 100) if total > 0 else 0

        data.append({
            'loan': loan,
            'total': total,
            'paid': paid,
            'percent': percent
        })

    return data


@login_required
def applications_list(request):

    profile = Profile.objects.get(user=request.user)

    if profile.role != 'supervisor':
        return redirect('login')

    applications = Application.objects.all().order_by('-id')

    # Add risk level
    for app in applications:
        student_profile = Profile.objects.get(user=app.student)
        score = calculate_credit_score(student_profile, app)

        if score >= 650:
            app.risk_level = "Low"
        elif score >= 550:
            app.risk_level = "Medium"
        else:
            app.risk_level = "High"

    return render(request, "accounts/applications.html", {
        "applications": applications
    })


@login_required
def reports(request):
    from django.db.models import Sum, Q

    total_loans = Loan.objects.aggregate(total=Sum('total_amount'))['total'] or 0
    total_remaining = Loan.objects.aggregate(total=Sum('remaining_amount'))['total'] or 0
    total_repaid = total_loans - total_remaining

    # ⚠ IMPORTANT: DON'T slice here
    applications = Application.objects.all().order_by('-id')

    total_apps = applications.count()

    approved = applications.filter(Q(status__iexact="Approved") | Q(status__iexact="Funded")).count()
    rejected = applications.filter(status__iexact="Rejected").count()
    pending = applications.filter(status__iexact="Pending").count()

    # ✅ Slice ONLY for recent display
    recent_apps = applications[:5]

    return render(request, "accounts/reports.html", {
        "total_loans": total_loans,
        "total_repaid": total_repaid,
        "total_remaining": total_remaining,
        "total_apps": total_apps,
        "approved": approved,
        "rejected": rejected,
        "pending": pending,
        "recent_apps": recent_apps,  # 🔥 IMPORTANT
    })

from django.contrib.auth.decorators import login_required
from django.contrib.auth import update_session_auth_hash
from django.contrib import messages
from django.shortcuts import render, redirect
from .models import Profile


@login_required
def settings_page(request):

    profile, created = Profile.objects.get_or_create(user=request.user)

    if request.method == "POST":

        updated = False
        password_changed = False

        # ===== PROFILE UPDATE =====
        username = request.POST.get("username")
        email = request.POST.get("email")

        if username:
            request.user.username = username
        if email:
            request.user.email = email

        request.user.save()
        updated = True

        # ===== PASSWORD UPDATE =====
        old_password = request.POST.get("old_password")
        new_password = request.POST.get("new_password")

        if old_password and new_password:
            if request.user.check_password(old_password):

                user = request.user
                user.set_password(new_password)
                user.save()

                update_session_auth_hash(request, user)

                password_changed = True
            else:
                messages.error(request, "Old password is incorrect")

        # ===== PREFERENCES =====
        profile.dark_mode = bool(request.POST.get("dark_mode"))
        profile.notifications_enabled = bool(request.POST.get("notifications"))
        profile.save()

        # ===== MESSAGES =====
        if password_changed:
            messages.success(request, "Password updated successfully")

        if updated:
            messages.success(request, "Settings updated successfully")

        return redirect('settings')

    return render(request, "accounts/settings.html", {"profile": profile})
@login_required
def admin_applications(request):

    applications = Application.objects.all()

    return render(request, 'accounts/admin_applications.html', {
        'applications': applications
    })

def send_due_email(user, loan):
    subject = "Loan Payment Reminder 💳"

    message = f"""
Hi {user.username},

Your loan payment is due soon.

Amount Remaining: ₹{loan.remaining_amount}
Due Date: {loan.due_date}

⚡ Pay on time to avoid penalty & improve credit score!

- SheNova Team
"""

    send_mail(
        subject,
        message,
        settings.EMAIL_HOST_USER,
        [user.email],
        fail_silently=False,
    )

def check_due_payments():

    today = now().date()
    loans = Loan.objects.filter(status="Active")

    for loan in loans:

        days_left = (loan.due_date - today).days

        # 🔔 ONLY 1 DAY BEFORE
        if days_left == 1:
            send_due_email(loan.student, loan)

        # ❌ REMOVE SAME DAY REMINDER
        # elif days_left == 0:
        #     send_due_email(loan.student, loan)

        # 🚨 OPTIONAL: OVERDUE ALERT
        elif days_left < 0:
            print(f"Loan overdue for {loan.student.username}")

from django.contrib import messages
from django.shortcuts import redirect, render

def forgot_password(request):
    if request.method == "POST":
        username = request.POST.get("username")

        try:
            user = User.objects.get(username=username)

            reset_link = request.build_absolute_uri(
                f"/reset-password/{user.id}/"
            )

            send_mail(
                subject="Password Reset - SheNova",
                message=f"Click this link to reset your password:\n{reset_link}",
                from_email=settings.EMAIL_HOST_USER,
                recipient_list=[user.email],
                fail_silently=False,
            )

            messages.success(request, "✅ Reset link sent to your email!")
        
            # ✅ IMPORTANT FIX
            return redirect('forgot_password')   # or 'login'

        except User.DoesNotExist:
            messages.error(request, "❌ User not found!")
            return redirect('forgot_password')

    return render(request, "accounts/forgot_password.html")
def reset_password(request, user_id):

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        messages.error(request, "Invalid user")
        return redirect('forgot_password')

    if request.method == "POST":
        password = request.POST.get("password")
        confirm = request.POST.get("confirm_password")

        if password != confirm:
            messages.error(request, "Passwords do not match")
            return redirect('reset_password', user_id=user_id)

        user.set_password(password)
        user.save()

        messages.success(request, "✅ Password updated successfully")
        return redirect('login')

    return render(request, "accounts/reset_password.html")


import razorpay
from django.conf import settings
from decimal import Decimal

@login_required
def add_money(request):
    profile = request.user.profile

    if request.method == "POST":
        amount = int(request.POST.get("amount")) * 100  # paise

        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        request.session['amount'] = amount // 100   # store ₹ value
        payment = client.order.create({
            "amount": amount,
            "currency": "INR",
            "payment_capture": 1
        })

        return render(request, "accounts/payment.html", {
            "payment": payment,
            "razorpay_key": settings.RAZORPAY_KEY_ID,
            "amount": amount // 100
        })

    return render(request, "accounts/add_money.html", {"profile": profile})

from decimal import Decimal

@login_required
def payment_success(request):
    amount = request.session.get('amount')

    if not amount:
        messages.error(request, "Payment amount not found!")
        return redirect('student_dashboard')

    amount = Decimal(amount)

    profile = request.user.profile

    profile.account_balance += amount
    profile.save()

    Transaction.objects.create(
        student=request.user,
        amount=int(amount),
        type="Credit",
        status="Completed"
    )

    messages.success(request, f"₹{amount} added successfully!")

    return redirect('student_dashboard')