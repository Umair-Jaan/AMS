from django.contrib import admin

from .models import Academy, AttendanceRecord, FeeRecord, PrincipalProfile, ResultRecord, Student


@admin.register(Academy)
class AcademyAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'phone', 'created_at')


@admin.register(PrincipalProfile)
class PrincipalProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'academy')


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('roll_no', 'name', 'academy', 'class_level', 'gender')
    list_filter = ('academy', 'class_level', 'gender')


@admin.register(FeeRecord)
class FeeRecordAdmin(admin.ModelAdmin):
    list_display = ('student', 'month', 'due_date', 'amount_due', 'amount_paid', 'status')


@admin.register(ResultRecord)
class ResultRecordAdmin(admin.ModelAdmin):
    list_display = ('student', 'subject', 'exam_date', 'marks_obtained', 'total_marks', 'term')


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ('student', 'month', 'days_present', 'days_total')
