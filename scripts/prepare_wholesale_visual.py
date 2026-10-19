"""Create a synthetic owner session ONLY in the named disposable SQLite fixture."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client

expected = (settings.BASE_DIR / 'test-results' / 'visual.sqlite3').resolve()
database = settings.DATABASES['default']
if not settings.DEBUG or database['ENGINE'] != 'django.db.backends.sqlite3' or Path(database['NAME']).resolve() != expected:
    raise SystemExit('Refusing to seed outside the disposable local visual database.')
expected.parent.mkdir(parents=True, exist_ok=True)
call_command('migrate', interactive=False, verbosity=0)
User = get_user_model()
if User.objects.exists():
    raise SystemExit('Use a fresh visual fixture database; existing accounts are never changed.')
user = User.objects.create_user('kiwikind-owner-admin', 'kiwikindbroadband@gmail.com', is_staff=True, is_superuser=True)
client = Client(); client.force_login(user)
target = expected.parent / 'local-session.json'
target.write_text(json.dumps({'sessionid': client.cookies['sessionid'].value}), encoding='utf-8')
print('Synthetic local visual fixture prepared.')
