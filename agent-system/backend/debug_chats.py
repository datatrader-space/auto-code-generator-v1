import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from agent.models import ChatConversation, User

print("--- Debugging Chat Conversations ---")
repo_id = 8
conv_type = 'repository'

# 1. Check if any exist globally for these filters
count_global = ChatConversation.objects.filter(repository_id=repo_id, conversation_type=conv_type).count()
print(f"Total conversations for Repo {repo_id} / Type '{conv_type}': {count_global}")

# 2. List owners of these conversations
convs = ChatConversation.objects.filter(repository_id=repo_id, conversation_type=conv_type)
owners = set(c.user.username for c in convs)
print(f"Owners of these conversations: {owners}")

# 3. List all users to see who is available
for u in User.objects.all():
    print(f"User: {u.username} (ID: {u.id}) - Has {u.conversations.count()} total conversations")
