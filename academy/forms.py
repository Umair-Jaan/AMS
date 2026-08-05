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
    GROUPS_9_10 = [
        ('Science - Biology', 'Science Group — Biology'),
        ('Science - Computer', 'Science Group — Computer'),
        ('General', 'General Group'),
    ]
    GROUPS_11_12 = [
        ('ICS', 'ICS'),
        ('Medical', 'Medical'),
        ('Non-Medical', 'Non-Medical'),
    ]

    class Meta:
        model = Student
        fields = ['roll_no', 'name', 'father_name', 'section', 'phone', 'remarks']

    def __init__(self, *args, class_level=None, **kwargs):
        if class_level is None and 'instance' in kwargs and kwargs['instance'] is not None:
            class_level = getattr(kwargs['instance'], 'class_level', None)
        self.class_level = class_level
        super().__init__(*args, **kwargs)

        if class_level in (9, 10):
            choices = self.GROUPS_9_10
        elif class_level in (11, 12):
            choices = self.GROUPS_11_12
        else:
            choices = self.GROUPS_9_10 + self.GROUPS_11_12

        self.fields['section'] = forms.ChoiceField(
            label='Groups',
            choices=[('', 'Select group')] + choices,
            required=True,
        )

    def clean(self):
        cleaned = super().clean()
        roll_no = cleaned.get('roll_no', '').strip()
        name = cleaned.get('name', '').strip()
        academy = getattr(self.instance, 'academy', None)
        class_level = getattr(self.instance, 'class_level', None)
        gender = getattr(self.instance, 'gender', None)

        if academy and class_level is not None and gender:
            existing_roll = None
            existing_name = None
            if roll_no:
                existing_roll = Student.objects.filter(
                    academy=academy,
                    class_level=class_level,
                    gender=gender,
                    roll_no__iexact=roll_no,
                )
            if name:
                existing_name = Student.objects.filter(
                    academy=academy,
                    class_level=class_level,
                    gender=gender,
                    name__iexact=name,
                )
            if self.instance.pk:
                existing_roll = existing_roll.exclude(pk=self.instance.pk) if existing_roll is not None else None
                existing_name = existing_name.exclude(pk=self.instance.pk) if existing_name is not None else None

            errors = []
            if existing_roll and existing_roll.exists():
                errors.append('A student with this roll number already exists in this class and gender.')
            if existing_name and existing_name.exists():
                errors.append('A student with this name already exists in this class and gender.')
            if errors:
                raise forms.ValidationError(errors)

        return cleaned

    def clean_section(self):
        section = self.cleaned_data.get('section', '').strip()
        allowed = [choice[0] for choice in self.GROUPS_9_10 + self.GROUPS_11_12]
        if section not in allowed:
            raise forms.ValidationError('Please select a valid group.')
        return section


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
