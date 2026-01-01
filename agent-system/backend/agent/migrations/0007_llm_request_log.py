from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('agent', '0006_llm_provider_models'),
    ]

    operations = [
        migrations.CreateModel(
            name='LLMRequestLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('provider', models.CharField(blank=True, max_length=50)),
                ('model', models.CharField(blank=True, max_length=200)),
                ('request_type', models.CharField(choices=[('chat', 'Chat'), ('stream', 'Stream')], max_length=20)),
                ('status', models.CharField(choices=[('success', 'Success'), ('error', 'Error')], max_length=20)),
                ('latency_ms', models.IntegerField(blank=True, null=True)),
                ('prompt_tokens', models.IntegerField(blank=True, null=True)),
                ('completion_tokens', models.IntegerField(blank=True, null=True)),
                ('total_tokens', models.IntegerField(blank=True, null=True)),
                ('error', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('conversation', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='llm_request_logs', to='agent.chatconversation')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='llm_request_logs', to='agent.user')),
            ],
            options={
                'db_table': 'llm_request_logs',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='llmrequestlog',
            index=models.Index(fields=['user', 'created_at'], name='llm_reques_user_id_fbd3bb_idx'),
        ),
        migrations.AddIndex(
            model_name='llmrequestlog',
            index=models.Index(fields=['provider', 'model'], name='llm_reques_provide_1b6e95_idx'),
        ),
        migrations.AddIndex(
            model_name='llmrequestlog',
            index=models.Index(fields=['status'], name='llm_reques_status_78c042_idx'),
        ),
    ]
