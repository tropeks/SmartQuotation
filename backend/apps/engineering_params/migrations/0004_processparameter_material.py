# Generated manually to avoid bootstrap issues in this environment.

from django.db import migrations, models


def remove_alargar_espelho_cnc(apps, schema_editor):
    ProcessParameter = apps.get_model('engineering_params', 'ProcessParameter')
    ProcessParameter.objects.filter(operacao='ALARGAR_ESPELHO', metodo='cnc').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('engineering_params', '0003_ratesuggestion'),
    ]

    operations = [
        migrations.AddField(
            model_name='processparameter',
            name='material',
            field=models.CharField(blank=True, db_index=True, max_length=100, null=True),
        ),
        migrations.RunPython(remove_alargar_espelho_cnc, migrations.RunPython.noop),
        migrations.AlterModelOptions(
            name='processparameter',
            options={'ordering': ['operacao', 'metodo', 'material', '-valid_from']},
        ),
        migrations.RemoveConstraint(
            model_name='processparameter',
            name='uniq_processparam_op_metodo_valid_from',
        ),
        migrations.RemoveIndex(
            model_name='processparameter',
            name='engineering_operaca_c5e797_idx',
        ),
        migrations.AddIndex(
            model_name='processparameter',
            index=models.Index(fields=['operacao', 'metodo', 'material', 'valid_from'], name='engineering_operaca_966ad8_idx'),
        ),
        migrations.AddConstraint(
            model_name='processparameter',
            constraint=models.CheckConstraint(
                condition=~models.Q(('metodo', 'cnc'), ('operacao', 'ALARGAR_ESPELHO')),
                name='ck_processparam_sem_alargar_espelho_cnc',
            ),
        ),
        migrations.AddConstraint(
            model_name='processparameter',
            constraint=models.UniqueConstraint(
                condition=models.Q(material__isnull=True),
                fields=('operacao', 'metodo', 'valid_from'),
                name='uniq_processparam_op_metodo_valid_from_null_material',
            ),
        ),
        migrations.AddConstraint(
            model_name='processparameter',
            constraint=models.UniqueConstraint(
                condition=models.Q(material__isnull=False),
                fields=('operacao', 'metodo', 'material', 'valid_from'),
                name='uniq_processparam_op_metodo_material_valid_from',
            ),
        ),
    ]
