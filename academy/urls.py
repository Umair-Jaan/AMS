from django.urls import path

from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('register/', views.register_academy, name='register_academy'),
    path('principal/login/', views.principal_login, name='principal_login'),
    path('principal/logout/', views.principal_logout, name='principal_logout'),
    path('principal/dashboard/', views.principal_dashboard, name='principal_dashboard'),
    path('principal/class/<int:grade>/', views.class_gender_select, name='class_gender_select'),
    path(
        'principal/class/<int:grade>/<str:gender>/',
        views.class_students,
        name='class_students',
    ),
    path('student/', views.student_lookup, name='student_lookup'),
    path(
        'principal/student/<int:student_id>/fees/',
        views.student_fees,
        name='student_fees',
    ),
    path(
        'principal/student/<int:student_id>/results/',
        views.student_results,
        name='student_results',
    ),
    path(
        'principal/student/<int:student_id>/attendance/',
        views.student_attendance,
        name='student_attendance',
    ),
    path(
        'student/record/<int:student_id>/fees/',
        views.student_fees_readonly,
        name='student_fees_readonly',
    ),
    path(
        'student/record/<int:student_id>/results/',
        views.student_results_readonly,
        name='student_results_readonly',
    ),
    path(
        'student/record/<int:student_id>/attendance/',
        views.student_attendance_readonly,
        name='student_attendance_readonly',
    ),
]
