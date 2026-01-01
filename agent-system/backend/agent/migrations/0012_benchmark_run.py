from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('agent', '0011_alter_llmrequestlog_latency_ms_alter_task_task_id'),
    ]

    operations = [
        migrations.CreateModel(
            name='BenchmarkRun',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('run_id', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True)),
                ('selected_models', models.JSONField(blank=True, default=list)),
                ('agent_modes', models.JSONField(blank=True, default=list)),
                ('suite_definition', models.JSONField(blank=True, default=dict)),
                ('run_jsonl_path', models.CharField(blank=True, max_length=500)),
                ('context_trace_path', models.CharField(blank=True, max_length=500)),
                ('report_output_path', models.CharField(blank=True, max_length=500)),
                ('status', models.CharField(choices=[('queued', 'Queued'), ('running', 'Running'), ('completed', 'Completed'), ('failed', 'Failed')], default='queued', max_length=20)),
                ('current_phase', models.CharField(blank=True, max_length=200)),
                ('progress', models.IntegerField(default=0, help_text='Progress percent 0-100')),
                ('report_metrics', models.JSONField(blank=True, default=dict)),
                ('report_artifacts', models.JSONField(blank=True, default=list)),
                ('error_message', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('system', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='benchmark_runs', to='agent.system')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='benchmark_runs', to='agent.user')),
            ],
            options={
                'db_table': 'benchmark_runs',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='benchmarkrun',
            index=models.Index(fields=['user', '-created_at'], name='benchmark_runs_user_id_b6757d_idx'),
        ),
        migrations.AddIndex(
            model_name='benchmarkrun',
            index=models.Index(fields=['status', '-created_at'], name='benchmark_runs_status_6bf5ad_idx'),
        ),
    ]
