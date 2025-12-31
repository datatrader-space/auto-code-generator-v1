from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('agent', '0005_chatconversation_alter_githuboauthconfig_id_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='LLMProvider',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('provider_type', models.CharField(choices=[('ollama', 'Ollama'), ('anthropic', 'Anthropic'), ('openai', 'OpenAI'), ('gemini', 'Google Gemini'), ('custom', 'Custom')], max_length=50)),
                ('base_url', models.URLField(blank=True)),
                ('api_key', models.CharField(blank=True, max_length=500)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='llm_providers', to='agent.user')),
            ],
            options={
                'db_table': 'llm_providers',
                'ordering': ['-created_at'],
                'unique_together': {('user', 'name')},
            },
        ),
        migrations.CreateModel(
            name='LLMModel',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('model_id', models.CharField(max_length=200)),
                ('context_window', models.IntegerField(default=0)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('provider', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='models', to='agent.llmprovider')),
            ],
            options={
                'db_table': 'llm_models',
                'ordering': ['name'],
                'unique_together': {('provider', 'model_id')},
            },
        ),
        migrations.AddField(
            model_name='chatconversation',
            name='llm_model',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='chat_conversations', to='agent.llmmodel'),
        ),
        migrations.CreateModel(
            name='LLMRequestLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('provider_type', models.CharField(blank=True, max_length=50)),
                ('model_id', models.CharField(blank=True, max_length=200)),
                ('request_type', models.CharField(choices=[('chat', 'Chat'), ('stream', 'Stream')], default='chat', max_length=20)),
                ('status', models.CharField(choices=[('success', 'Success'), ('error', 'Error')], max_length=20)),
                ('latency_ms', models.IntegerField(blank=True, null=True)),
                ('prompt_tokens', models.IntegerField(blank=True, null=True)),
                ('completion_tokens', models.IntegerField(blank=True, null=True)),
                ('total_tokens', models.IntegerField(blank=True, null=True)),
                ('error_message', models.TextField(blank=True)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('conversation', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='llm_request_logs', to='agent.chatconversation')),
                ('llm_model', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='request_logs', to='agent.llmmodel')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='llm_request_logs', to='agent.user')),
            ],
            options={
                'db_table': 'llm_request_logs',
                'ordering': ['-created_at'],
            },
        ),
    ]
