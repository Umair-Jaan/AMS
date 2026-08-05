from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from datetime import date

from .forms import (
    AttendanceRecordForm,
    FeeRecordForm,
    RegisterAcademyForm,
    ResultRecordForm,
    StudentForm,
)
from .models import Academy, AttendanceRecord, PrincipalProfile, Student

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

    if request.method == 'POST':
        if request.POST.get('attendance_action') == 'save_attendance':
            mode = request.POST.get('attendance_mode', 'monthly')
            selected_month = request.POST.get('attendance_month', '').strip()
            attendance_date = request.POST.get('attendance_date_input', '').strip()
            for student in students:
                if mode == 'daily':
                    status = request.POST.get(f'status_{student.pk}', 'A')
                    days_present = 1 if status == 'P' else 0
                    days_total = 1
                    if attendance_date:
                        record_label = attendance_date
                    else:
                        record_label = date.today().strftime('%d/%m/%Y')
                else:
                    try:
                        days_present = int(request.POST.get(f'present_{student.pk}', 0))
                    except ValueError:
                        days_present = 0
                    days_total = 31
                    if selected_month:
                        month_map = {
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
                        days_total = month_map.get(selected_month, 31)
                    days_present = min(max(days_present, 0), days_total)
                    record_label = f'{selected_month} {date.today().year}' if selected_month else date.today().strftime('%B %Y')

                AttendanceRecord.objects.create(
                    student=student,
                    month=record_label,
                    days_present=days_present,
                    days_total=days_total,
                )
            messages.success(request, 'Attendance saved for all students.')
            return redirect('class_students', grade=grade, gender=gender)

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

    return render(request, 'academy/class_students.html', {
        'academy': academy,
        'grade': grade,
        'gender': gender,
        'gender_label': 'Boys' if gender == 'boys' else 'Girls',
        'students': students,
        'form': form,
        'search_by': search_by,
        'query': query,
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
