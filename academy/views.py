from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from urllib.parse import urlencode

from datetime import date
import json

from .forms import (
    AttendanceRecordForm,
    FeeRecordForm,
    RegisterAcademyForm,
    ResultRecordForm,
    StudentForm,
)
from .models import Academy, AttendanceRecord, FeeRecord, PrincipalProfile, ResultRecord, Student

CLASS_LEVELS = [9, 10, 11, 12]
STUDENT_SESSION_KEY = 'student_access_id'

MONTH_DAYS = {
    'January': 31,
    'February': 28,
    'March': 31,
    'April': 30,
    'May': 31,
    'June': 30,
    'July': 31,
    'August': 31,
    'September': 30,
    'October': 31,
    'November': 30,
    'December': 31,
}


def _format_display_date(date_str):
    try:
        return date.fromisoformat(date_str).strftime('%d/%m/%Y')
    except (TypeError, ValueError):
        return date.today().strftime('%d/%m/%Y')


def _attendance_month_label(month_name):
    if month_name:
        return f'{month_name} {date.today().year}'
    return date.today().strftime('%B %Y')


def _get_attendance_values(students, mode, selected_month, attendance_date):
    if mode == 'daily':
        label = _format_display_date(attendance_date)
    else:
        label = _attendance_month_label(selected_month)

    records = AttendanceRecord.objects.filter(
        student__in=students,
        month=label,
    ).order_by('student_id', '-id')

    values = {
        str(student.pk): {
            'status': 'A',
            'days_present': 0,
            'days_total': 31,
        }
        for student in students
    }

    seen = set()
    for record in records:
        student_id = str(record.student_id)
        if student_id in seen:
            continue
        seen.add(student_id)
        values[student_id]['days_present'] = record.days_present
        values[student_id]['days_total'] = record.days_total
        values[student_id]['status'] = 'P' if record.days_present else 'A'

    return values


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


def _get_student_record(user, student_id, model, record_id):
    academy, student = _get_student_for_principal(user, student_id)
    if not student:
        return None, None, None
    record = get_object_or_404(model, pk=record_id, student=student)
    return academy, student, record


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


def _student_attendance_view(request, student_id, readonly=False):
    if readonly:
        student = _get_student_for_readonly(request, student_id)
        if not student:
            return redirect('student_lookup')
        academy = student.academy
    else:
        academy, student = _get_student_for_principal(request.user, student_id)
        if not student:
            return redirect('home')

    attendance_date_input = request.GET.get('attendance_date_input', date.today().isoformat())
    attendance_date_label = _format_display_date(attendance_date_input)
    daily_record = AttendanceRecord.objects.filter(
        student=student,
        month=attendance_date_label,
    ).first()
    daily_status = 'P' if daily_record and daily_record.days_present else 'A'
    monthly_form = None if readonly else AttendanceRecordForm()

    if not readonly and request.method == 'POST':
        action = request.POST.get('attendance_action')
        if action == 'save_daily':
            attendance_date = request.POST.get('attendance_date_input', attendance_date_input).strip()
            try:
                attendance_date_obj = date.fromisoformat(attendance_date)
                record_label = attendance_date_obj.strftime('%d/%m/%Y')
                attendance_date = attendance_date_obj.isoformat()
            except (TypeError, ValueError):
                record_label = date.today().strftime('%d/%m/%Y')
                attendance_date = date.today().isoformat()

            status = request.POST.get('status', 'A')
            days_present = 1 if status == 'P' else 0
            AttendanceRecord.objects.update_or_create(
                student=student,
                month=record_label,
                defaults={
                    'days_present': days_present,
                    'days_total': 1,
                },
            )
            messages.success(request, 'Daily attendance saved.')
            query_string = urlencode({'attendance_date_input': attendance_date})
            return redirect(f'{reverse("student_attendance", kwargs={"student_id": student_id})}?{query_string}')

        if action == 'save_monthly':
            monthly_form = AttendanceRecordForm(request.POST)
            if monthly_form.is_valid():
                record = monthly_form.save(commit=False)
                record.student = student
                record.save()
                messages.success(request, 'Monthly attendance record added.')
                return redirect('student_attendance', student_id=student_id)

    records = student.attendance_records.all()

    return render(request, 'academy/student_attendance.html', {
        'student': student,
        'academy': academy,
        'records': records,
        'readonly': readonly,
        'grade': student.class_level,
        'gender': student.gender,
        'attendance_date_input': attendance_date_input,
        'attendance_date_display': attendance_date_label,
        'daily_record': daily_record,
        'daily_status': daily_status,
        'monthly_form': monthly_form,
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

    search_by = request.GET.get('search_by', 'roll_no')
    query = request.GET.get('query', '').strip()

    students = Student.objects.filter(
        academy=academy,
        class_level=grade,
        gender=gender,
    )

    if query:
        if search_by == 'name':
            students = students.filter(name__icontains=query)
        else:
            students = students.filter(roll_no__icontains=query)

    attendance_date_input = request.GET.get('attendance_date_input', date.today().isoformat())

    if request.method == 'POST':
        if request.POST.get('attendance_action') == 'save_attendance':
            attendance_date = request.POST.get('attendance_date_input', attendance_date_input).strip()
            try:
                attendance_date_obj = date.fromisoformat(attendance_date)
                record_label = attendance_date_obj.strftime('%d/%m/%Y')
                attendance_date = attendance_date_obj.isoformat()
            except (TypeError, ValueError):
                record_label = date.today().strftime('%d/%m/%Y')
                attendance_date = date.today().isoformat()

            for student in students:
                status = request.POST.get(f'status_{student.pk}', 'A')
                days_present = 1 if status == 'P' else 0
                days_total = 1

                AttendanceRecord.objects.update_or_create(
                    student=student,
                    month=record_label,
                    defaults={
                        'days_present': days_present,
                        'days_total': days_total,
                    },
                )

            messages.success(request, 'Attendance saved for all students.')
            query_string = urlencode({
                'attendance_date_input': attendance_date,
            })
            return redirect(f'{reverse("class_students", kwargs={"grade": grade, "gender": gender})}?{query_string}')

        form = StudentForm(request.POST, class_level=grade)
        # populate instance fields used by model-level validation so
        # `validate_unique` can catch duplicates (academy + roll_no)
        form.instance.academy = academy
        form.instance.class_level = grade
        form.instance.gender = gender
        if form.is_valid():
            student = form.save()
            messages.success(request, f'Student {student.roll_no} added.')
            return redirect('class_students', grade=grade, gender=gender)
    else:
        form = StudentForm(class_level=grade)

    attendance_values = _get_attendance_values(
        students,
        'daily',
        None,
        attendance_date_input,
    )

    return render(request, 'academy/class_students.html', {
        'academy': academy,
        'grade': grade,
        'gender': gender,
        'gender_label': 'Boys' if gender == 'boys' else 'Girls',
        'students': students,
        'form': form,
        'search_by': search_by,
        'query': query,
        'attendance_date_input': attendance_date_input,
        'attendance_date_display': _format_display_date(attendance_date_input),
        'attendance_values_json': json.dumps(attendance_values),
    })


@login_required
def student_edit(request, student_id):
    academy, student = _get_student_for_principal(request.user, student_id)
    if not student:
        return redirect('home')

    if request.method == 'POST':
        form = StudentForm(request.POST, instance=student)
        if form.is_valid():
            form.save()
            messages.success(request, f'Student {student.roll_no} updated.')
            return redirect(
                'class_students',
                grade=student.class_level,
                gender=student.gender,
            )
    else:
        form = StudentForm(instance=student, class_level=student.class_level)

    return render(request, 'academy/student_edit.html', {
        'form': form,
        'student': student,
        'academy': academy,
    })


@login_required
@require_POST
def student_delete(request, student_id):
    academy, student = _get_student_for_principal(request.user, student_id)
    if not student:
        return redirect('home')

    grade = student.class_level
    gender = student.gender
    roll = student.roll_no
    student.delete()
    messages.success(request, f'Student {roll} deleted.')
    return redirect('class_students', grade=grade, gender=gender)


@login_required
def student_fees(request, student_id):
    return _handle_record_view(
        request, student_id, FeeRecordForm, 'fee_records',
        'academy/student_fees.html', redirect_name='student_fees',
    )


@login_required
@require_POST
def student_fee_delete(request, student_id, record_id):
    academy, student, record = _get_student_record(request.user, student_id, FeeRecord, record_id)
    if not student:
        return redirect('home')
    record.delete()
    messages.success(request, 'Fee record removed.')
    return redirect('student_fees', student_id=student_id)


@login_required
def student_results(request, student_id):
    return _handle_record_view(
        request, student_id, ResultRecordForm, 'result_records',
        'academy/student_results.html', redirect_name='student_results',
    )


@login_required
@require_POST
def student_result_delete(request, student_id, record_id):
    academy, student, record = _get_student_record(request.user, student_id, ResultRecord, record_id)
    if not student:
        return redirect('home')
    record.delete()
    messages.success(request, 'Result record removed.')
    return redirect('student_results', student_id=student_id)


@login_required
def student_attendance(request, student_id):
    return _student_attendance_view(request, student_id, readonly=False)


@login_required
@require_POST
def student_attendance_record_delete(request, student_id, record_id):
    academy, student, record = _get_student_record(request.user, student_id, AttendanceRecord, record_id)
    if not student:
        return redirect('home')
    record.delete()
    messages.success(request, 'Attendance record removed.')
    return redirect('student_attendance', student_id=student_id)


def student_attendance_readonly(request, student_id):
    return _student_attendance_view(request, student_id, readonly=True)


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
    class_level = ''
    gender = ''
    section = ''

    if request.method == 'POST':
        roll_no = request.POST.get('roll_no', '').strip()
        academy_code = request.POST.get('academy_code', '').strip().upper()
        class_level = request.POST.get('class_level', '').strip()
        gender = request.POST.get('gender', '').strip()
        section = request.POST.get('section', '').strip()

        if class_level not in {str(g) for g in CLASS_LEVELS}:
            messages.error(request, 'Please select a valid class.')
        elif gender not in ('boys', 'girls'):
            messages.error(request, 'Please select Boys or Girls.')
        elif class_level in {'9', '10'} and section not in dict(Student.GROUP_CHOICES_9_10):
            messages.error(request, 'Please select a valid group for Class 9 or 10.')
        elif class_level in {'11', '12'} and section not in dict(Student.GROUP_CHOICES_11_12):
            messages.error(request, 'Please select a valid group for Class 11 or 12.')
        elif section not in dict(Student.GROUP_CHOICES):
            messages.error(request, 'Please select a valid group.')
        else:
            student = Student.objects.filter(
                roll_no=roll_no,
                academy__code__iexact=academy_code,
                class_level=int(class_level),
                gender=gender,
                section=section,
            ).select_related('academy').first()
            if student:
                _grant_student_session(request, student)
            else:
                messages.error(
                    request,
                    'No student found. Check academy code, roll, class, gender, and group.',
                )

    return render(request, 'academy/student_lookup.html', {
        'student': student,
        'roll_no': roll_no,
        'academy_code': academy_code,
        'class_level': class_level,
        'gender': gender,
        'section': section,
        'class_levels': CLASS_LEVELS,
    })
