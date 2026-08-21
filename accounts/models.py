from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
# ---------------- PROFILE ----------------

class Profile(models.Model):

    ROLE_CHOICES = (
        ('student', 'Student'),
        ('supervisor', 'Supervisor'),
        ('admin', 'Admin'),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE)

    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    full_name = models.CharField(max_length=100, blank=True, null=True)
    phone = models.CharField(max_length=15, blank=True, null=True)
    college = models.CharField(max_length=200, blank=True, null=True)
    course = models.CharField(max_length=100, blank=True, null=True)
    year = models.CharField(max_length=10, blank=True, null=True)
    # OTP + Security
    otp = models.CharField(max_length=6, blank=True, null=True)
    otp_verified = models.BooleanField(default=False)
    otp_created_at = models.DateTimeField(null=True, blank=True)
    otp_attempts = models.IntegerField(default=0)

    # Financial
    max_limit = models.IntegerField(default=10000)
    used_amount = models.IntegerField(default=0)
    account_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)  # virtual wallet
    def remaining_limit(self):
        return self.max_limit - self.used_amount

    def __str__(self):
        return f"{self.user.username} ({self.role})"


# ---------------- APPLICATION ----------------

class Application(models.Model):
    is_emergency = models.BooleanField(default=False)
    PRIORITY_CHOICES = [
        ('Low', 'Low'),
        ('Medium', 'Medium'),
        ('High', 'High'),
        ('Critical', 'Critical'),
    ]

    priority_level = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default='Medium'
    )
    STATUS_CHOICES = (
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Funded', 'Funded'),
        ('Rejected', 'Rejected'),
        ('Completed', 'Completed'),
    )
    REPAYMENT_CHOICES = [
        ('30', '30 Days'),
        ('60', '60 Days'),
        ('90', '90 Days'),
    ]


    student = models.ForeignKey(User, on_delete=models.CASCADE)
    amount_requested = models.IntegerField()
    reason = models.TextField()
    family_income = models.IntegerField()
    phone = models.CharField(max_length=10, null=True, blank=True)
    year = models.CharField(max_length=10, null=True, blank=True)
    aadhaar_number = models.CharField(max_length=12, blank=True, null=True)
    pan_number = models.CharField(max_length=10, blank=True, null=True)
    student_id_number = models.CharField(max_length=20, blank=True, null=True)

    aadhar_card = models.FileField(upload_to='documents/aadhaar/', blank=True, null=True)
    pan_card = models.FileField(upload_to='documents/pan/', blank=True, null=True)
    student_id_card = models.FileField(upload_to='documents/student_id/', blank=True, null=True)
    reference_name = models.CharField(max_length=100, blank=True, null=True)
    reference_relation = models.CharField(max_length=50, blank=True, null=True)
    reference_phone = models.CharField(max_length=15, blank=True, null=True)
    cibil_score = models.IntegerField(null=True, blank=True)
    risk_level = models.CharField(max_length=20, null=True, blank=True)

    supervisor_notes = models.TextField(blank=True, null=True)

    applied_date = models.DateTimeField(auto_now_add=True)
    repayment_plan = models.CharField(max_length=10,choices=REPAYMENT_CHOICES)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    ai_risk_score = models.IntegerField(null=True, blank=True)
    ai_risk_level = models.CharField(max_length=20, null=True, blank=True)
    ai_risk_reasons = models.TextField(null=True, blank=True)
    ai_recommendation = models.TextField(null=True, blank=True)
    def __str__(self):
        return f"{self.student.username} - {self.amount_requested}"


# ---------------- FUND ----------------

class Fund(models.Model):
    total_fund = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    available_fund = models.IntegerField(default=1000000)
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "System Fund"


# ---------------- LOAN ----------------

class Loan(models.Model):

    student = models.ForeignKey(User, on_delete=models.CASCADE)
    application = models.OneToOneField(Application, on_delete=models.CASCADE)

    total_amount = models.IntegerField()
    remaining_amount = models.IntegerField()

    interest_rate = models.FloatField(default=5.0)

    deadline = models.DateField(null=True, blank=True)   # ✅ IMPORTANT
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, default="Active")
    created_at = models.DateTimeField(auto_now_add=True)
    reminder_sent = models.BooleanField(default=False)
    def __str__(self):
        return self.student.username


# ---------------- REPAYMENT ----------------

class Repayment(models.Model):

    loan = models.ForeignKey(Loan, on_delete=models.CASCADE)
    amount_paid = models.IntegerField()
    paid_on = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.loan.student.username} - ₹{self.amount_paid}"


# ---------------- TRANSACTION ----------------

class Transaction(models.Model):

    TYPE_CHOICES = (
        ('Credit', 'Credit'),
        ('Repayment', 'Repayment'),
    )

    STATUS_CHOICES = (
        ('Pending','Pending'),
        ('Approved','Approved'),
        ('Rejected','Rejected'),
        ('Completed','Completed')
    )

    student = models.ForeignKey(User, on_delete=models.CASCADE)
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, null=True, blank=True)

    amount = models.IntegerField()
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Pending')

    date = models.DateTimeField(auto_now_add=True)
    is_late = models.BooleanField(default=False)

    admin_note = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"{self.student.username} - {self.type} - ₹{self.amount}"


# ---------------- NOTIFICATION ----------------

class Notification(models.Model):

    student = models.ForeignKey(User, on_delete=models.CASCADE)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.student.username} - Notification"