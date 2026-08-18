from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from urllib.parse import urlencode
import re
from datetime import date, datetime
import json

from .forms import (
    AttendanceRecordForm,
    FeeRecordForm,
    RegisterAcademyForm,
    ResultRecordForm,
    StudentForm,
)
from django.forms.widgets import HiddenInput
from .models import (
    Academy,
    AttendanceRecord,
    AttendanceSession,
    AttendanceSessionEntry,
    FeeRecord,
    PrincipalProfile,
    ResultRecord,
    Student,
)

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
        try:
            return datetime.strptime(date_str, '%m/%d/%Y').strftime('%d/%m/%Y')
        except (TypeError, ValueError):
            return date.today().strftime('%d/%m/%Y')


def _parse_search_date(date_str):
    if not date_str:
        return None
    try:
        return date.fromisoformat(date_str)
    except (TypeError, ValueError):
        try:
            return datetime.strptime(date_str, '%m/%d/%Y').date()
        except (TypeError, ValueError):
            return None


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
    date_filter_field=None,
    date_filter_input_name=None,
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

    date_filter_value = ''
    if date_filter_field and date_filter_input_name:
        date_filter_value = request.GET.get(date_filter_input_name, '').strip()
        if date_filter_value:
            parsed_date = _parse_search_date(date_filter_value)
            if parsed_date is not None:
                records = records.filter(**{date_filter_field: parsed_date})

    # For result records, compute a displayable date range (From - To)
    result_date_range = ''
    try:
        if related_name == 'result_records':
            # Prefer exam_date min/max when present
            dates_qs = records.exclude(exam_date__isnull=True).order_by('exam_date')
            if dates_qs.exists():
                first = dates_qs.first().exam_date
                last = dates_qs.last().exam_date
                result_date_range = f"{first.strftime('%d/%m/%Y')} to {last.strftime('%d/%m/%Y')}" if first and last else ''
            else:
                # Fall back to any note on records
                note = records.exclude(note='').values_list('note', flat=True).first()
                if note:
                    result_date_range = note
    except Exception:
        result_date_range = ''

    context = {
        'student': student,
        'academy': academy,
        'records': records,
        'form': form,
        'readonly': readonly,
        'grade': student.class_level,
        'gender': student.gender,
    }

    if related_name == 'result_records':
        context['result_date_range'] = result_date_range

        # Build per-student record batches for student results page
        try:
            records_qs = records.order_by('id')
            batches = OrderedDict()
            for r in records_qs:
                label = r.note if r.note else (r.exam_date.strftime('%d/%m/%Y') if r.exam_date else 'No date')
                batches.setdefault(label, []).append(r)
            record_batches = []
            for label, recs in batches.items():
                # Compute per-record percentage and batch totals
                total_obtained = 0
                total_marks = 0
                for r in recs:
                    try:
                        r.percentage = round(float(r.marks_obtained) / float(r.total_marks) * 100, 1) if r.total_marks else 0
                    except Exception:
                        r.percentage = 0
                    try:
                        total_obtained += r.marks_obtained or 0
                    except Exception:
                        pass
                    try:
                        total_marks += r.total_marks or 0
                    except Exception:
                        pass

                batch_percentage = round(float(total_obtained) / float(total_marks) * 100, 1) if total_marks else 0
                record_batches.append({
                    'label': label,
                    'records': recs,
                    'total_obtained': total_obtained,
                    'total_marks': total_marks,
                    'percentage': batch_percentage,
                })
            context['record_batches'] = record_batches
        except Exception:
            context['record_batches'] = []

    if date_filter_input_name:
        context[date_filter_input_name] = date_filter_value
    return render(request, template_name, context)


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

    history_search_type = request.GET.get('attendance_history_search_type', 'date')
    history_date_input = request.GET.get('attendance_history_date_input', date.today().isoformat())
    history_month = request.GET.get('attendance_history_month', date.today().strftime('%B'))
    history_year = request.GET.get('attendance_history_year', str(date.today().year))

    def _month_number(month_name):
        try:
            return f'{list(MONTH_DAYS.keys()).index(month_name) + 1:02}'
        except ValueError:
            return None

    records = student.attendance_records.all()
    session_entries = AttendanceSessionEntry.objects.filter(
        student=student,
    ).select_related('session').order_by('session__created_at')

    if history_search_type == 'date':
        history_date_obj = _parse_search_date(history_date_input)
        if history_date_obj is not None:
            history_date_label = history_date_obj.strftime('%d/%m/%Y')
            records = records.filter(month=history_date_label)
            session_entries = session_entries.filter(session__date_label=history_date_label)
    elif history_search_type == 'month':
        history_month_label = f'{history_month} {history_year}'
        month_number = _month_number(history_month)
        records = records.filter(month=history_month_label)
        if month_number:
            session_entries = session_entries.filter(
                session__date_label__contains=f'/{month_number}/{history_year}'
            )

    history_month_options = list(MONTH_DAYS.keys())
    year_options = [str(y) for y in range(date.today().year - 3, date.today().year + 3)]

    return render(request, 'academy/student_attendance.html', {
        'student': student,
        'academy': academy,
        'readonly': readonly,
        'grade': student.class_level,
        'gender': student.gender,
        'session_entries': session_entries,
        'history_month_options': history_month_options,
        'history_search_type': history_search_type,
        'history_date_input': history_date_input,
        'history_month': history_month,
        'history_year': history_year,
        'year_options': year_options,
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
            # Save this class session as a Session object and create per-student entries
            session, created = AttendanceSession.objects.get_or_create(
                academy=academy,
                grade=grade,
                gender=gender,
                date_label=record_label,
            )

            # Remove any existing entries for this session so saving is idempotent
            # (prevents duplicate rows when saving multiple times).
            session.entries.all().delete()

            for student in students:
                status = request.POST.get(f'status_{student.pk}', '').strip()
                # Only create entries for students who were explicitly marked
                if status in ('P', 'A'):
                    AttendanceSessionEntry.objects.create(
                        session=session,
                        student=student,
                        status=status,
                    )

            messages.success(request, 'Session attendance saved.')
            query_string = urlencode({
                'attendance_date_input': attendance_date,
            })
            return redirect(f'{reverse("class_students", kwargs={"grade": grade, "gender": gender})}?{query_string}')

        if request.POST.get('fee_action') == 'save_fees':
            month_label = date.today().strftime('%B %Y')
            from decimal import Decimal
            for student in students:
                status = request.POST.get(f'fee_status_{student.pk}', '').strip()
                amount_raw = request.POST.get(f'fee_amount_{student.pk}', '').strip()
                if not status:
                    continue

                amount_paid = Decimal(amount_raw) if amount_raw else Decimal('0')
                amount_due = amount_paid if status == 'collect' else Decimal('0')
                FeeRecord.objects.update_or_create(
                    student=student,
                    month=month_label,
                    defaults={
                        'status': status,
                        'amount_due': amount_due,
                        'amount_paid': amount_paid,
                        'note': '',
                    }
                )

            messages.success(request, 'Fee panel data saved.')
            return redirect('class_students', grade=grade, gender=gender)

        if request.POST.get('result_action') == 'save_results':
            from decimal import Decimal, InvalidOperation
            date_from_raw = request.POST.get('result_from_date', '').strip()
            date_to_raw = request.POST.get('result_to_date', '').strip()
            # Require at least one date field (From/To) to be provided so batches are identifiable
            if not date_from_raw and not date_to_raw:
                messages.error(request, 'Please enter From and To dates for the result batch.')
                return redirect('class_students', grade=grade, gender=gender)
            # Parse input mm/dd/YYYY into date objects and store display labels as dd/mm/YYYY
            def _parse_input(dstr):
                if not dstr:
                    return None
                for fmt in ('%m/%d/%Y', '%Y-%m-%d'):
                    try:
                        return datetime.strptime(dstr, fmt).date()
                    except (TypeError, ValueError):
                        continue
                return None

            date_from_obj = _parse_input(date_from_raw)
            date_to_obj = _parse_input(date_to_raw)
            from_label = date_from_obj.strftime('%d/%m/%Y') if date_from_obj else ('')
            to_label = date_to_obj.strftime('%d/%m/%Y') if date_to_obj else ('')
            exam_date = date_to_obj

            # Preserve column positions so marks_<studentid>_<col> maps correctly.
            selected_subjects = [None] * 8
            for idx in range(1, 9):
                subject = request.POST.get(f'subject_{idx}', '').strip()
                total_raw = request.POST.get(f'total_marks_{idx}', '').strip()
                try:
                    total_marks = Decimal(total_raw)
                except (TypeError, ValueError, InvalidOperation):
                    total_marks = Decimal('0')
                # Accept a selected subject even if total_marks is empty/0.
                if subject:
                    selected_subjects[idx - 1] = {
                        'subject': subject,
                        'total_marks': total_marks,
                    }

            if not any(selected_subjects):
                messages.error(request, 'Please select at least one subject and total marks to save results.')
                return redirect('class_students', grade=grade, gender=gender)

            saved_count = 0
            for student in students:
                for col_idx, subject_info in enumerate(selected_subjects, 1):
                    if not subject_info:
                        continue
                    marks_raw = request.POST.get(f'marks_{student.pk}_{col_idx}', '').strip()
                    if marks_raw == '':
                        continue
                    try:
                        marks_obtained = Decimal(marks_raw)
                    except (TypeError, ValueError, InvalidOperation):
                        continue
                    if marks_obtained < 0:
                        continue

                    # Always create a new ResultRecord so previous results are retained.
                    ResultRecord.objects.create(
                        student=student,
                        subject=subject_info['subject'],
                        exam_date=exam_date,
                        marks_obtained=marks_obtained,
                        total_marks=subject_info['total_marks'],
                        term='monthly',
                        note=f'{from_label} to {to_label}' if from_label or to_label else '',
                    )
                    saved_count += 1

            if saved_count:
                messages.success(request, f'Saved {saved_count} student result values.')
            else:
                messages.warning(request, 'No student result values were provided.')
            return redirect('class_students', grade=grade, gender=gender)

        if request.POST.get('result_action') == 'edit_result':
            from decimal import Decimal, InvalidOperation
            record_id = request.POST.get('result_id')
            marks_raw = request.POST.get('edit_marks_obtained', '').strip()
            if record_id and marks_raw:
                try:
                    record = ResultRecord.objects.select_related('student').get(pk=record_id)
                    if record.student.academy == academy and record.student.class_level == grade and record.student.gender == gender:
                        record.marks_obtained = Decimal(marks_raw)
                        total_raw = request.POST.get('edit_total_marks', '').strip()
                        try:
                            record.total_marks = Decimal(total_raw)
                        except (TypeError, ValueError):
                            pass
                        # Allow updating the subject if provided
                        edit_subject = request.POST.get('edit_subject', '').strip()
                        if edit_subject:
                            record.subject = edit_subject
                        record.save()
                        messages.success(request, 'Result updated.')
                except (ResultRecord.DoesNotExist, InvalidOperation):
                    messages.error(request, 'Unable to update the result record.')
            return redirect('class_students', grade=grade, gender=gender)

        if request.POST.get('result_action') == 'delete_result':
            record_id = request.POST.get('result_id')
            if record_id:
                try:
                    record = ResultRecord.objects.select_related('student').get(pk=record_id)
                    if record.student.academy == academy and record.student.class_level == grade and record.student.gender == gender:
                        record.delete()
                        messages.success(request, 'Result record removed.')
                except ResultRecord.DoesNotExist:
                    messages.error(request, 'Result record not found.')
            return redirect('class_students', grade=grade, gender=gender)
        if request.POST.get('result_action') == 'delete_student_results':
            student_id_post = request.POST.get('student_id')
            if student_id_post:
                try:
                    student_obj = Student.objects.get(pk=student_id_post, academy=academy, class_level=grade, gender=gender)
                    ResultRecord.objects.filter(student=student_obj).delete()
                    messages.success(request, f'All result records removed for {student_obj.name}.')
                except Student.DoesNotExist:
                    messages.error(request, 'Student not found.')
            return redirect('class_students', grade=grade, gender=gender)

        if request.POST.get('result_action') == 'delete_all_results':
            # Delete all result records for this class (students queryset)
            ResultRecord.objects.filter(student__in=students).delete()
            messages.success(request, 'All result records removed for this class.')
            return redirect('class_students', grade=grade, gender=gender)

        if request.POST.get('result_action') == 'delete_batch':
            batch_label = request.POST.get('batch_label', '').strip()
            if batch_label:
                # delete records for this class with this note/label
                ResultRecord.objects.filter(student__in=students, note=batch_label).delete()
                messages.success(request, f'Result batch "{batch_label}" removed.')
            return redirect('class_students', grade=grade, gender=gender)

        if request.POST.get('result_action') == 'edit_bulk':
            from decimal import Decimal, InvalidOperation
            edited = 0
            updated_ids = set()

            subject_updates = {}
            for key, val in request.POST.items():
                if key.startswith('record_subject_'):
                    try:
                        rec_id = int(key.replace('record_subject_', '', 1))
                    except (TypeError, ValueError):
                        continue
                    subject_value = val.strip()
                    if subject_value:
                        subject_updates[rec_id] = subject_value

            marks_updates = {}
            for key, val in request.POST.items():
                if key.startswith('record_marks_'):
                    try:
                        rec_id = int(key.replace('record_marks_', '', 1))
                    except (TypeError, ValueError):
                        continue
                    marks_updates[rec_id] = val.strip()

            for key, val in request.POST.items():
                if key.startswith('record_') and not key.startswith('record_subject_') and not key.startswith('record_marks_'):
                    try:
                        rec_id = int(key.replace('record_', '', 1))
                    except (TypeError, ValueError):
                        continue
                    marks_updates.setdefault(rec_id, val.strip())

            for key, val in request.POST.items():
                if key.startswith('record_subject_'):
                    try:
                        rec_id = int(key.replace('record_subject_', '', 1))
                    except (TypeError, ValueError):
                        continue
                    subject_updates.setdefault(rec_id, val.strip())

            for rec_id, subject_value in subject_updates.items():
                try:
                    record = ResultRecord.objects.select_related('student').get(pk=rec_id)
                except ResultRecord.DoesNotExist:
                    continue
                if record.student.academy != academy or record.student.class_level != grade or record.student.gender != gender:
                    continue
                record.subject = subject_value
                updated_ids.add(rec_id)
                record.save()

            for rec_id, marks_raw in marks_updates.items():
                if marks_raw == '':
                    continue
                try:
                    record = ResultRecord.objects.select_related('student').get(pk=rec_id)
                except ResultRecord.DoesNotExist:
                    continue
                if record.student.academy != academy or record.student.class_level != grade or record.student.gender != gender:
                    continue
                try:
                    record.marks_obtained = Decimal(marks_raw)
                    updated_ids.add(rec_id)
                    record.save()
                except (InvalidOperation, TypeError, ValueError):
                    continue

            edited = len(updated_ids)

            if edited:
                messages.success(request, f'Updated {edited} result records.')
            else:
                messages.info(request, 'No result records were changed.')
            return redirect('class_students', grade=grade, gender=gender)

        form = StudentForm(
            request.POST,
            class_level=grade,
            gender=gender,
            academy=academy,
        )
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
        form = StudentForm(
            class_level=grade,
            gender=gender,
            academy=academy,
        )

    attendance_values = _get_attendance_values(
        students,
        'daily',
        None,
        attendance_date_input,
    )

    result_records = ResultRecord.objects.filter(student__in=students).select_related('student').order_by('id')
    subject_choices = [
        'English',
        'Urdu',
        'Math',
        'Chemistry',
        'Islamiat',
        'T Quran',
        'Physics',
        'Computer',
        'Economics',
    ]
    result_columns = range(1, 9)

    from decimal import Decimal
    # Group result records into batches by their note (From-To) or exam_date
    from collections import OrderedDict
    batches = OrderedDict()
    for record in result_records:
        label = record.note if record.note else (record.exam_date.strftime('%d/%m/%Y') if record.exam_date else 'No date')
        batches.setdefault(label, []).append(record)

    result_batches = []
    for label, records in batches.items():
        # distinct subjects in this batch, preserving order
        subjects = []
        for r in records:
            if r.subject not in subjects:
                subjects.append(r.subject)

        # build a map student_id -> records for this batch
        records_by_student = {}
        for r in records:
            records_by_student.setdefault(r.student_id, []).append(r)

        rows = []
        for student in students:
            recs = records_by_student.get(student.pk, [])
            if not recs:
                # include students with no records for completeness (empty values)
                subject_values = ['' for _ in subjects]
                subject_entries = [
                    {'subject': sub, 'record_id': None, 'marks_obtained': '', 'total_marks': 0}
                    for sub in subjects
                ]
                total_obtained = Decimal('0')
                total_marks = Decimal('0')
                percentage = 0
                note = ''
            else:
                recs_by_subject = {r.subject: r for r in recs}
                subject_values = [recs_by_subject.get(sub).marks_obtained if recs_by_subject.get(sub) is not None else '' for sub in subjects]
                subject_entries = []
                for sub in subjects:
                    record = recs_by_subject.get(sub)
                    subject_entries.append({
                        'subject': sub,
                        'record_id': record.pk if record else None,
                        'marks_obtained': record.marks_obtained if record else '',
                        'total_marks': record.total_marks if record else 0,
                    })
                total_obtained = sum((r.marks_obtained for r in recs), Decimal('0'))
                total_marks = sum((r.total_marks for r in recs), Decimal('0'))
                percentage = round(float(total_obtained) / float(total_marks) * 100, 1) if total_marks else 0
                note = next((r.note for r in recs if getattr(r, 'note', None)), '')

            rows.append({
                'student': student,
                'subject_values': subject_values,
                'subject_entries': subject_entries,
                'total_obtained': total_obtained,
                'total_marks': total_marks,
                'percentage': percentage,
                'note': note,
            })

        result_batches.append({
            'label': label,
            'subjects': subjects,
            'rows': rows,
        })

    # Compute maximum total marks across all records (for potential JS usage)
    max_total_by_subject = {}
    for r in result_records:
        max_total_by_subject.setdefault(r.subject, 0)
        try:
            if r.total_marks and r.total_marks > max_total_by_subject[r.subject]:
                max_total_by_subject[r.subject] = r.total_marks
        except Exception:
            pass
    max_result_total = int(max(max_total_by_subject.values()) if max_total_by_subject else 0)

    # class page should not display saved session entries; sessions are
    # displayed on the individual student's attendance page instead.
    session_entries = None

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
        'session_entries': session_entries,
        'result_records': result_records,
        'result_subject_choices': subject_choices,
        'result_columns': result_columns,
        'result_batches': result_batches,
        'results_date_range': result_batches[-1]['label'] if result_batches else '',
        'max_total_by_subject': max_total_by_subject,
        'max_result_total': int(max_result_total),
    })


@login_required
def student_edit(request, student_id):
    academy, student = _get_student_for_principal(request.user, student_id)
    if not student:
        return redirect('home')

    if request.method == 'POST':
        form = StudentForm(
            request.POST,
            instance=student,
            class_level=student.class_level,
            gender=student.gender,
            academy=academy,
        )
        if form.is_valid():
            form.save()
            messages.success(request, f'Student {student.roll_no} updated.')
            return redirect(
                'class_students',
                grade=student.class_level,
                gender=student.gender,
            )
    else:
        form = StudentForm(
            instance=student,
            class_level=student.class_level,
            gender=student.gender,
            academy=academy,
        )

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
        request,
        student_id,
        FeeRecordForm,
        'fee_records',
        'academy/student_fees.html',
        redirect_name='student_fees',
        date_filter_field='due_date',
        date_filter_input_name='fee_due_date_input',
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


@login_required
@require_POST
def class_session_entry_delete(request, grade, gender, entry_id):
    try:
        entry = AttendanceSessionEntry.objects.select_related('session', 'student').get(pk=entry_id)
    except AttendanceSessionEntry.DoesNotExist:
        messages.error(request, 'Session entry not found.')
        return redirect('class_students', grade=grade, gender=gender)

    academy = _get_principal_academy(request.user)
    if not academy or entry.session.academy != academy:
        return redirect('home')

    entry.delete()
    messages.success(request, 'Session attendance entry removed.')
    attendance_date_input = request.POST.get('attendance_date_input', '')
    if attendance_date_input:
        query_string = urlencode({'attendance_date_input': attendance_date_input})
        return redirect(f'{reverse("class_students", kwargs={"grade": grade, "gender": gender})}?{query_string}')
    return redirect('class_students', grade=grade, gender=gender)


@login_required
@require_POST
def student_session_entry_delete(request, student_id, entry_id):
    # Delete a session attendance entry from the student attendance page.
    academy, student = _get_student_for_principal(request.user, student_id)
    if not student:
        return redirect('home')

    try:
        entry = AttendanceSessionEntry.objects.get(pk=entry_id, student=student)
    except AttendanceSessionEntry.DoesNotExist:
        messages.error(request, 'Session entry not found.')
        return redirect('student_attendance', student_id=student_id)

    # Ensure the session belongs to this academy
    if entry.session.academy != academy:
        return redirect('home')

    entry.delete()
    messages.success(request, 'Session attendance entry removed.')
    attendance_date_input = request.POST.get('attendance_date_input', '')
    if attendance_date_input:
        query_string = urlencode({'attendance_date_input': attendance_date_input})
        return redirect(f'{reverse("student_attendance", kwargs={"student_id": student_id})}?{query_string}')
    return redirect('student_attendance', student_id=student_id)


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
