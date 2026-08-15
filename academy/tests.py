from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Academy, PrincipalProfile, ResultRecord, Student

User = get_user_model()


class ResultSavingTests(TestCase):
    def setUp(self):
        self.academy = Academy.objects.create(
            name='Test Academy',
            code='TEST',
            address='Somewhere',
            phone='123',
        )
        self.user = User.objects.create_user(username='principal', password='secret123')
        PrincipalProfile.objects.create(user=self.user, academy=self.academy)
        self.student = Student.objects.create(
            academy=self.academy,
            roll_no='B91',
            name='Ali Khan',
            father_name='Khan',
            class_level=9,
            gender='boys',
            section='Science - Biology',
        )

    def test_save_results_creates_student_records_without_debug_messages(self):
        self.client.login(username='principal', password='secret123')

        post_data = {
            'result_action': 'save_results',
            'result_from_date': '01/01/2026',
            'result_to_date': '01/15/2026',
            'subject_1': 'Math',
            'total_marks_1': '100',
            f'marks_{self.student.pk}_1': '85',
        }

        response = self.client.post(
            reverse('class_students', args=[9, 'boys']),
            data=post_data,
            follow=True,
        )

        self.assertEqual(ResultRecord.objects.filter(student=self.student).count(), 1)
        self.assertContains(response, 'Saved 1 student result values.')
        self.assertNotContains(response, 'DEBUG selected_subjects')
        self.assertNotContains(response, 'DEBUG marks for first student')

        saved_record = ResultRecord.objects.get(student=self.student)
        self.assertEqual(saved_record.subject, 'Math')
        self.assertEqual(saved_record.marks_obtained, Decimal('85'))
        self.assertEqual(saved_record.total_marks, Decimal('100'))
        self.assertEqual(saved_record.note, '01/01/2026 to 01/15/2026')
