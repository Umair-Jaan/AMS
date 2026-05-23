from django.db import migrations, models
from django.utils.text import slugify


def assign_academy_codes(apps, schema_editor):
    Academy = apps.get_model('academy', 'Academy')
    for academy in Academy.objects.all():
        if academy.code:
            continue
        base = slugify(academy.name).replace('-', '')[:12] or f'academy{academy.pk}'
        candidate = base.upper()
        n = 1
        while Academy.objects.filter(code__iexact=candidate).exclude(pk=academy.pk).exists():
            candidate = f'{base}{n}'.upper()[:20]
            n += 1
        academy.code = candidate
        academy.save(update_fields=['code'])


class Migration(migrations.Migration):

    dependencies = [
        ('academy', '0004_resultrecord_exam_date'),
    ]

    operations = [
        migrations.AddField(
            model_name='academy',
            name='code',
            field=models.SlugField(
                max_length=20,
                null=True,
                help_text='Unique code students use with roll number (e.g. GPS2026)',
            ),
        ),
        migrations.RunPython(assign_academy_codes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='academy',
            name='code',
            field=models.SlugField(
                max_length=20,
                unique=True,
                help_text='Unique code students use with roll number (e.g. GPS2026)',
            ),
        ),
    ]
