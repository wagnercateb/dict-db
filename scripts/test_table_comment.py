import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'db_metadata_crawler.settings')
import django
django.setup()
from metadata_crawler.models import MetadataComment, TableMetadata
from django.contrib.auth import get_user_model
User = get_user_model()
user = User.objects.first()
if not user:
    print('No user found')
    raise SystemExit(1)
try:
    table = TableMetadata.objects.get(pk=8966)
except TableMetadata.DoesNotExist:
    print('Table 8966 not found; skipping save test')
    raise SystemExit(0)
mc = MetadataComment(comment_type='TABLE', comment='Test comment', user=user, table=table)
mc.save()
print('Saved comment id:', mc.id)