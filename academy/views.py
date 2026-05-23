from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render

from .forms import (
    AttendanceRecordForm,
    FeeRecordForm,
    RegisterAcademyForm,
    ResultRecordForm,
    StudentForm,
)
from .models import Academy, PrincipalProfile, Student

CLASS_LEVELS = [9, 10, 11, 12]
STUDENT_SESSION_KEY = 'student_access_id'


def _get_principal_academy(user):
    try:
        return user.principal_profile.academy
    except (PrincipalProfile.DoesNotExist, AttributeError):
        return None


def _get_student_for_principal(user, student_id):
    academy = _get_principal_academy(user)
    if not academy:
        return None, None
    student = get_object_or_404(Student, pk=student_id, academy=academy)
    return academy, student


def _grant_student_session(request, student):
    request.session[STUDENT_SESSION_KEY] = student.pk


def _get_student_for_readonly(request, student_id):
    student = get_object_or_404(Student, pk=student_id)
    if request.session.get(STUDENT_SESSION_KEY) != student.pk:
        messages.error(request, 'Please log in with your academy code and roll number first.')
        return None
    return student


def _handle_record_view(
    request,
    student_id,
    form_class,
    related_name,
    template_name,
    redirect_name=None,
    readonly=False,
):
    if readonly:
        student = _get_student_for_readonly(request, student_id)
        if not student:
            return redirect('student_lookup')
        academy = student.academy
        records = getattr(student, related_name).all()
        form = None
    else:
        academy, student = _get_student_for_principal(request.user, student_id)
        if not student:
            return redirect('home')
        records = getattr(student, related_name).all()
        if request.method == 'POST':
            form = form_class(request.POST)
            if form.is_valid():
                record = form.save(commit=False)
                record.student = student
                record.save()
                messages.success(request, 'Record added.')
                return redirect(redirect_name, student_id=student_id)
        else:
            form = form_class()

    return render(request, template_name, {
        'student': student,
        'academy': academy,
        'records': records,
        'form': form,
        'readonly': readonly,
        'grade': student.class_level,
        'gender': student.gender,
    })


def home(request):
    return render(request, 'academy/home.html')


def register_academy(request):
    if request.method == 'POST':
        form = RegisterAcademyForm(request.POST)
        if form.is_valid():
            academy = Academy.objects.create(
                name=form.cleaned_data['academy_name'],
                code=form.cleaned_data['academy_code'],
                address=form.cleaned_data.get('address', ''),
                phone=form.cleaned_data.get('phone', ''),
            )
            user = User.objects.create_user(
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password'],
            )
            PrincipalProfile.objects.create(user=user, academy=academy)
            messages.success(request, 'Academy registered. You can log in as principal.')
            return redirect('principal_login')
    else:
        form = RegisterAcademyForm()
    return render(request, 'academy/register_academy.html', {'form': form})


def principal_login(request):
    if request.user.is_authenticated and _get_principal_academy(request.user):
        return redirect('principal_dashboard')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None and _get_principal_academy(user):
            login(request, user)
            return redirect('principal_dashboard')
        messages.error(request, 'Invalid principal login.')
    return render(request, 'academy/principal_login.html')


@login_required
def principal_logout(request):
    logout(request)
    return redirect('home')


@login_required
def principal_dashboard(request):
    academy = _get_principal_academy(request.user)
    if not academy:
        messages.error(request, 'You are not registered as a principal.')
        return redirect('home')
    return render(request, 'academy/principal_dashboard.html', {
        'academy': academy,
        'class_levels': CLASS_LEVELS,
    })


@login_required
def class_gender_select(request, grade):
    if grade not in CLASS_LEVELS:
        return redirect('principal_dashboard')
    academy = _get_principal_academy(request.user)
    if not academy:
        return redirect('home')
    return render(request, 'academy/class_gender_select.html', {
        'academy': academy,
        'grade': grade,
    })


@login_required
def class_students(request, grade, gender):
    if grade not in CLASS_LEVELS or gender not in ('boys', 'girls'):
        return redirect('principal_dashboard')

    academy = _get_principal_academy(request.user)
    if not academy:
        return redirect('home')

    students = Student.objects.filter(
        academy=academy,
        class_level=grade,
        gender=gender,
    )

    if request.method == 'POST':
        form = StudentForm(request.POST)
        if form.is_valid():
            student = form.save(commit=False)
            student.academy = academy
            student.class_level = grade
            student.gender = gender
            student.save()
            messages.success(request, f'Student {student.roll_no} added.')
            return redirect('class_students', grade=grade, gender=gender)
    else:
        form = StudentForm()

    return render(request, 'academy/class_students.html', {
        'academy': academy,
        'grade': grade,
        'gender': gender,
        'gender_label': 'Boys' if gender == 'boys' else 'Girls',
        'students': students,
        'form': form,
    })


@login_required
def student_fees(request, student_id):
    return _handle_record_view(
        request, student_id, FeeRecordForm, 'fee_records',
        'academy/student_fees.html', redirect_name='student_fees',
    )


@login_required
def student_results(request, student_id):
    return _handle_record_view(
        request, student_id, ResultRecordForm, 'result_records',
        'academy/student_results.html', redirect_name='student_results',
    )


@login_required
def student_attendance(request, student_id):
    return _handle_record_view(
        request, student_id, AttendanceRecordForm, 'attendance_records',
        'academy/student_attendance.html', redirect_name='student_attendance',
    )


def student_fees_readonly(request, student_id):
    return _handle_record_view(
        request, student_id, FeeRecordForm, 'fee_records',
        'academy/student_fees.html', readonly=True,
    )


def student_results_readonly(request, student_id):
    return _handle_record_view(
        request, student_id, ResultRecordForm, 'result_records',
        'academy/student_results.html', readonly=True,
    )


def student_attendance_readonly(request, student_id):
    return _handle_record_view(
        request, student_id, AttendanceRecordForm, 'attendance_records',
        'academy/student_attendance.html', readonly=True,
    )


def student_lookup(request):
    student = None
    roll_no = ''
    academy_code = ''

    if request.method == 'POST':
        roll_no = request.POST.get('roll_no', '').strip()
        academy_code = request.POST.get('academy_code', '').strip().upper()
        student = Student.objects.filter(
            roll_no=roll_no,
            academy__code__iexact=academy_code,
        ).select_related('academy').first()
        if student:
            _grant_student_session(request, student)
        else:
            messages.error(request, 'No student found for this academy code and roll number.')

    return render(request, 'academy/student_lookup.html', {
        'student': student,
        'roll_no': roll_no,
        'academy_code': academy_code,
    })
