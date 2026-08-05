from django.conf import settings
from django.db import models


class Academy(models.Model):
    name = models.CharField(max_length=200)
    code = models.SlugField(
        max_length=20,
        unique=True,
        help_text='Unique code students use with roll number (e.g. GPS2026)',
    )
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.code:
            from django.utils.text import slugify
            base = slugify(self.name).replace('-', '')[:12] or 'academy'
            candidate = base.upper()
            n = 1
            while Academy.objects.filter(code__iexact=candidate).exclude(pk=self.pk).exists():
                candidate = f'{base}{n}'.upper()[:20]
                n += 1
            self.code = candidate
        else:
            self.code = self.code.upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class PrincipalProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='principal_profile',
    )
    academy = models.ForeignKey(
        Academy,
        on_delete=models.CASCADE,
        related_name='principals',
    )

    def __str__(self):
        return f'{self.user.username} — {self.academy.name}'


class Student(models.Model):
    CLASS_CHOICES = [
        (9, 'Class 9'),
        (10, 'Class 10'),
        (11, 'Class 11'),
        (12, 'Class 12'),
    ]
    GENDER_CHOICES = [
        ('boys', 'Boys'),
        ('girls', 'Girls'),
    ]

    academy = models.ForeignKey(
        Academy,
        on_delete=models.CASCADE,
        related_name='students',
    )
    roll_no = models.CharField(max_length=20)
    name = models.CharField(max_length=100)
    father_name = models.CharField(max_length=100, blank=True)
    class_level = models.IntegerField(choices=CLASS_CHOICES)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES)
    GROUP_CHOICES = [
        ('ICS', 'ICS'),
        ('Medical', 'Medical'),
        ('Non-Medical', 'Non-Medical'),
    ]
    section = models.CharField(max_length=20, choices=GROUP_CHOICES, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    remarks = models.TextField(blank=True)

    class Meta:
        unique_together = ['academy', 'roll_no']
        ordering = ['class_level', 'gender', 'roll_no']

    def __str__(self):
        return f'{self.roll_no} — {self.name}'


class FeeRecord(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('partial', 'Partial'),
        ('paid', 'Paid'),
    ]

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='fee_records',
    )
    month = models.CharField(max_length=30, help_text='e.g. May 2026')
    due_date = models.DateField(null=True, blank=True)
    amount_due = models.DecimalField(max_digits=10, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['-id']

    def __str__(self):
        return f'{self.student.roll_no} — {self.month}'


class ResultRecord(models.Model):
    TERM_CHOICES = [
        ('monthly', 'Monthly'),
        ('mid', 'Mid Term'),
        ('final', 'Final'),
    ]

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='result_records',
    )
    subject = models.CharField(max_length=100)
    exam_date = models.DateField(null=True, blank=True)
    marks_obtained = models.DecimalField(max_digits=6, decimal_places=2)
    total_marks = models.DecimalField(max_digits=6, decimal_places=2, default=100)
    term = models.CharField(max_length=20, choices=TERM_CHOICES, default='monthly')
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['subject']

    @property
    def percentage(self):
        if self.total_marks:
            return round(float(self.marks_obtained) / float(self.total_marks) * 100, 1)
        return 0

    def __str__(self):
        return f'{self.student.roll_no} — {self.subject}'


class AttendanceRecord(models.Model):
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='attendance_records',
    )
    month = models.CharField(max_length=30, help_text='e.g. May 2026')
    days_present = models.PositiveIntegerField()
    days_total = models.PositiveIntegerField()
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['-id']

    @property
    def percentage(self):
        if self.days_total:
            return round(self.days_present / self.days_total * 100, 1)
        return 0

    def __str__(self):
        return f'{self.student.roll_no} — {self.month}'
