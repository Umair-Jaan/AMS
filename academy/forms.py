from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from .models import Academy, AttendanceRecord, FeeRecord, ResultRecord, Student

User = get_user_model()


class RegisterAcademyForm(forms.Form):
    academy_name = forms.CharField(max_length=200, label='Academy name')
    academy_code = forms.CharField(
        max_length=20,
        label='Academy code',
        help_text='Unique code for students (letters/numbers only)',
    )
    address = forms.CharField(widget=forms.Textarea(attrs={'rows': 2}), required=False)
    phone = forms.CharField(max_length=20, required=False)
    username = forms.CharField(max_length=150, label='Principal username')
    password = forms.CharField(widget=forms.PasswordInput)
    password_confirm = forms.CharField(widget=forms.PasswordInput, label='Confirm password')

    def clean_academy_code(self):
        from django.utils.text import slugify
        raw = self.cleaned_data['academy_code'].strip().upper()
        code = slugify(raw).replace('-', '').upper()
        if not code:
            raise forms.ValidationError('Enter a valid academy code.')
        if Academy.objects.filter(code__iexact=code).exists():
            raise forms.ValidationError('This academy code is already taken.')
        return code

    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError('This username is already taken.')
        return username

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('password')
        p2 = cleaned.get('password_confirm')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError('Passwords do not match.')
        if p1:
            validate_password(p1)
        return cleaned


class StudentForm(forms.ModelForm):
    section = forms.ChoiceField(
        label='Groups',
        choices=[('', 'Select group')] + Student.GROUP_CHOICES,
        required=False,
    )

    class Meta:
        model = Student
        fields = ['roll_no', 'name', 'father_name', 'section', 'phone', 'remarks']


class FeeRecordForm(forms.ModelForm):
    due_date = forms.DateField(
        label='Due date',
        widget=forms.DateInput(
            attrs={'type': 'date'},
            format='%Y-%m-%d',
        ),
        input_formats=['%Y-%m-%d'],
    )

    class Meta:
        model = FeeRecord
        fields = ['month', 'due_date', 'amount_due', 'amount_paid', 'status', 'note']
        widgets = {
            'month': forms.TextInput(attrs={'placeholder': 'e.g. May 2026'}),
        }


class ResultRecordForm(forms.ModelForm):
    exam_date = forms.DateField(
        label='Exam date',
        widget=forms.DateInput(
            attrs={'type': 'date'},
            format='%Y-%m-%d',
        ),
        input_formats=['%Y-%m-%d'],
    )

    class Meta:
        model = ResultRecord
        fields = ['subject', 'exam_date', 'marks_obtained', 'total_marks', 'term', 'note']


class AttendanceRecordForm(forms.ModelForm):
    class Meta:
        model = AttendanceRecord
        fields = ['month', 'days_present', 'days_total', 'note']
