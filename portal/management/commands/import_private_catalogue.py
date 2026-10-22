"""Validate by default. --apply inserts an unpublished immutable draft only."""
import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError
from django.db import transaction
from portal.models import PrivateCatalogueRelease
from portal.private_catalogue import validate_payload, digest


class Command(BaseCommand):
    help = 'Validate a confidential JSON catalogue; optionally insert a private draft. Never publishes.'

    def add_arguments(self, parser):
        parser.add_argument('file')
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        try:
            path = Path(options['file'])
            if path.stat().st_size > 2_000_000:
                raise ValueError()
            payload = validate_payload(json.loads(path.read_text(encoding='utf-8-sig')))
        except (OSError, ValueError, TypeError, KeyError, ValidationError):
            # Never print wholesale values, filenames, signed URLs or raw input.
            raise CommandError('Private catalogue validation failed; no records changed.') from None
        if options['apply']:
            with transaction.atomic():
                _, created = PrivateCatalogueRelease.objects.get_or_create(
                    checksum=digest(payload), defaults={'payload': payload})
            self.stdout.write('Private draft created.' if created else 'Identical draft already exists; no changes.')
        else:
            self.stdout.write(f'Validated {len(payload)} complete service definitions. Dry run; nothing imported or published.')
