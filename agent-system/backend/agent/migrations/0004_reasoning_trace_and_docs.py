from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('agent', '0003_github_oauth_config'),
    ]

    operations = [
        migrations.CreateModel(
            name='RepositoryReasoningTrace',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('stage', models.CharField(max_length=100)),
                ('payload', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('repository', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reasoning_traces', to='agent.repository')),
            ],
            options={
                'db_table': 'agent_repository_reasoning_traces',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='SystemDocumentation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('doc_type', models.CharField(default='overview', max_length=100)),
                ('content', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('system', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='documentation', to='agent.system')),
            ],
            options={
                'db_table': 'agent_system_documentation',
                'ordering': ['doc_type'],
                'unique_together': {('system', 'doc_type')},
            },
        ),
    ]
