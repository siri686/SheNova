def analyze_application(application):
    score = 0
    reasons = []

    student = application.student

    income = float(student.family_income or 0)
    requested = float(application.amount_requested or 0)

    # Requested amount compared with family income
    if income > 0:
        ratio = requested / income

        if ratio > 0.50:
            score += 40
            reasons.append("Requested amount is high compared with family income.")
        elif ratio > 0.25:
            score += 20
            reasons.append("Requested amount is moderately high compared with income.")
        else:
            reasons.append("Requested amount is reasonable compared with income.")

    # Example risk based on application history
    previous_rejected = application.__class__.objects.filter(
        student=student,
        status="Rejected"
    ).exclude(id=application.id).count()

    if previous_rejected >= 2:
        score += 25
        reasons.append("Multiple previous applications were rejected.")
    elif previous_rejected == 1:
        score += 10
        reasons.append("One previous application was rejected.")

    if score >= 60:
        level = "High"
        recommendation = "Additional verification is recommended before approval."
    elif score >= 30:
        level = "Medium"
        recommendation = "Review the student's financial details carefully."
    else:
        level = "Low"
        recommendation = "Application appears to have relatively low financial risk."

    return {
        "score": min(score, 100),
        "level": level,
        "reasons": reasons,
        "recommendation": recommendation,
    }