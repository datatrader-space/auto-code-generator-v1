from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agent', '0002_system_intent_constraints'),
    ]

    operations = [
        migrations.CreateModel(
            name='GitHubOAuthConfig',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('client_id', models.CharField(max_length=200)),
                ('client_secret', models.CharField(max_length=200)),
                ('callback_url', models.URLField(default='http://localhost:8000/api/auth/github/callback')),
                ('scope', models.CharField(default='repo,user', max_length=200)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'agent_github_oauth_config',
                'ordering': ['-created_at'],
            },
        ),
    ]
