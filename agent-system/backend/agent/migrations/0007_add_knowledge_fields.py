# Generated migration for Repository knowledge tracking fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agent', '0006_llm_provider_models'),
    ]

    operations = [
        migrations.AddField(
            model_name='repository',
            name='knowledge_status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending Extraction'),
                    ('extracting', 'Extracting Knowledge'),
                    ('ready', 'Knowledge Ready'),
                    ('error', 'Extraction Error')
                ],
                default='pending',
                max_length=50
            ),
        ),
        migrations.AddField(
            model_name='repository',
            name='knowledge_last_extracted',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='repository',
            name='knowledge_docs_count',
            field=models.IntegerField(default=0),
        ),
    ]
