"""Owner-only, fail-closed CSV import into private DRAFT wholesale catalogue.

Does not call Vetta, order a service, modify a verified plan or publish prices.
CSV source files are processed in memory. Never persist raw upload or its name.
"""
import csv
import io
import re
from datetime import date
from decimal import Decimal
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpResponse, HttpResponseNotAllowed
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect

from .models import DraftPlan, AuditEvent
from .owner_admin import owner_session
from .wholesale import price_breakdown

FIELDS = (
    'name', 'download_mbps', 'upload_mbps', 'network', 'wholesale_ex_gst',
    'setup_ex_gst', 'retail_ex_gst', 'retail_setup_ex_gst', 'source_reference',
)
MAX_FILE_BYTES = 100_000
MAX_ROWS = 50
SECRETS = re.compile(r'(?:sk_(?:test|live)_|rk_(?:test|live)_|whsec_|bearer\s|'
                     r'password=|api[_-]?key=|token=)', re.IGNORECASE)


class QuoteImportError(Exception):
    def __init__(self, message, status=400):
        self.status = status
        super().__init__(message)


def private_decimal(value, number, field, required=False):
    value = (value or '').strip()
    if not value:
        if required:
            raise QuoteImportError(f'Row {number}: {field} is required (a missing price is not zero).')
        return None
    # No floating point rounding, currency symbols, thousands separators or guesses.
    try:
        return Decimal(price_breakdown(value)['ex_gst'])
    except (TypeError, ValueError, KeyError):
        raise QuoteImportError(f'Row {number}: {field} needs nonnegative NZD with at most two decimals.') from None


def parse_private_quotes(raw):
    if not raw or len(raw) > MAX_FILE_BYTES:
        raise QuoteImportError('Choose a nonempty CSV file no larger than 100 KB.', 413 if len(raw) > MAX_FILE_BYTES else 400)
    try:
        decoded = raw.decode('utf-8-sig')
        if '\x00' in decoded or any(0xD800 <= ord(c) <= 0xDFFF for c in decoded):
            raise UnicodeError
        reader = csv.DictReader(io.StringIO(decoded, newline=''), strict=True)
        columns = reader.fieldnames or []
        if len(columns) != len(FIELDS) or set(columns) != set(FIELDS):
            raise QuoteImportError('CSV columns must match the private template exactly; extra columns are not accepted.')
        rows = []
        names = set()
        for index, values in enumerate(reader, start=2):
            if len(rows) >= MAX_ROWS:
                raise QuoteImportError('Limit each import to 50 private draft plans.', 413)
            if None in values or any(value is None for value in values.values()):
                raise QuoteImportError(f'Row {index}: number of columns does not match the template.')
            if not any((value or '').strip() for value in values.values()):
                continue
            name = values['name'].strip()
            network = values['network'].strip()
            source_reference = values['source_reference'].strip()
            if (not name or len(name) > 100 or name[0] in '=+-@' or
                    any(ord(c) < 32 for c in name)):
                raise QuoteImportError(f'Row {index}: enter a safe private plan name under 100 characters.')
            if (not source_reference or len(source_reference) > 160 or
                    len(network) > 100 or SECRETS.search(source_reference) or
                    SECRETS.search(network)):
                raise QuoteImportError(f'Row {index}: a short private quote reference is required. Never enter credentials.')
            if any(ord(c) < 32 for c in network + source_reference):
                raise QuoteImportError(f'Row {index}: remove control characters from source/network.')
            if name.casefold() in names:
                raise QuoteImportError(f'Row {index}: duplicate plan name in CSV.')
            names.add(name.casefold())
            speeds = []
            for field in ('download_mbps', 'upload_mbps'):
                txt = values[field].strip()
                if not re.fullmatch(r'[1-9][0-9]{0,4}', txt) or int(txt) > 10000:
                    raise QuoteImportError(f'Row {index}: {field} must be an integer from 1 to 10000.')
                speeds.append(int(txt))
            wholesale = private_decimal(values['wholesale_ex_gst'], index, 'wholesale_ex_gst', required=True)
            setup = private_decimal(values['setup_ex_gst'], index, 'setup_ex_gst')
            retail = private_decimal(values['retail_ex_gst'], index, 'retail_ex_gst')
            retail_setup = private_decimal(values['retail_setup_ex_gst'], index, 'retail_setup_ex_gst')
            # Keep missing setup cost UNKNOWN. Do not invent free installation.
            obj = DraftPlan(
                name=name, download_mbps=speeds[0], upload_mbps=speeds[1],
                network=network, source_reference=source_reference,
                wholesale_ex_gst=wholesale,
                wholesale_inc_gst=Decimal(price_breakdown(wholesale)['inc_gst']),
                setup_ex_gst=setup,
                setup_inc_gst=(Decimal(price_breakdown(setup)['inc_gst']) if setup is not None else None),
                retail_ex_gst=retail, retail_setup_ex_gst=retail_setup,
                address_specific=True, review_status='draft',
                verified_at=None, valid_until=None, approved_by=None, approved_at=None,
            )
            try:
                obj.full_clean(validate_unique=False)
            except (ValidationError, ValueError, TypeError):
                raise QuoteImportError(f'Row {index}: invalid plan fields; review private quote and GST.') from None
            rows.append(obj)
        if not rows:
            raise QuoteImportError('The file contains no private price rows.')
        return rows
    except (UnicodeError, UnicodeDecodeError, csv.Error):
        raise QuoteImportError('Upload a valid UTF-8 comma-separated CSV matching the template.') from None


def matches_exact_private_draft(old, new):
    if old.review_status != 'draft' or not old.address_specific or old.verified_at or old.approved_at:
        return False
    fields = ('name', 'download_mbps', 'upload_mbps', 'network', 'source_reference',
              'wholesale_ex_gst', 'wholesale_inc_gst', 'setup_ex_gst', 'setup_inc_gst',
              'retail_ex_gst', 'retail_setup_ex_gst', 'valid_until')
    return all(getattr(old, key) == getattr(new, key) for key in fields)


def import_private_drafts(owner, parsed_rows):
    # Validate every collision before writing anything. No unapproved-to-approved
    # transition, overwrite of edited quotes or partial batch import is possible.
    try:
        with transaction.atomic():
            new_rows = []
            already = 0
            for row in parsed_rows:
                prior = DraftPlan.objects.select_for_update().filter(name__iexact=row.name).first()
                if prior:
                    if not matches_exact_private_draft(prior, row):
                        raise QuoteImportError(
                            'A private plan name already exists with different or reviewed data; resolve it in the catalogue first.',
                            409,
                        )
                    already += 1
                else:
                    new_rows.append(row)
            for row in new_rows:
                try:
                    row.full_clean()
                except (ValidationError, ValueError, TypeError):
                    raise QuoteImportError('A proposed private draft conflicts with current catalogue data.', 409) from None
                row.save(force_insert=True)
            if new_rows:
                AuditEvent.objects.create(
                    actor=owner, action='catalogue_csv_import',
                    reference=f'private_drafts:{len(new_rows)}',
                )
            return len(new_rows), already
    except IntegrityError:
        raise QuoteImportError('The private catalogue changed during import. Reload and review before trying again.', 409) from None


@never_cache
@csrf_protect
def private_catalogue_import(request):
    if not owner_session(request) or not admin.site.has_permission(request):
        return HttpResponse(status=404)
    if request.method not in ('GET', 'POST'):
        return HttpResponseNotAllowed(['GET', 'POST'])

    if request.method == 'GET' and request.GET.get('template') == '1':
        response = HttpResponse(','.join(FIELDS) + '\n', content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="kiwikind_private_quote_template.csv"'
        response['Cache-Control'] = 'no-store'
        return response

    error = ''
    status = 200
    if request.method == 'POST':
        try:
            if request.POST.get('confirm_draft_only') != 'yes':
                raise QuoteImportError('Confirm that these are PRIVATE, unverified drafts only.')
            upload = request.FILES.get('catalogue_csv')
            if not upload or not upload.name.lower().endswith('.csv') or upload.size > MAX_FILE_BYTES:
                raise QuoteImportError('Select a CSV template file up to 100 KB (not a PDF or screenshot).')
            rows = parse_private_quotes(upload.read())
            created, existing = import_private_drafts(request.user, rows)
        except QuoteImportError as exc:
            error, status = str(exc), exc.status
        else:
            messages.success(request, f'Private catalogue: {created} new unapproved draft(s); {existing} exact duplicate(s) skipped. No public plans, supplier orders or payments changed.')
            return redirect('admin:portal_draftplan_changelist')

    return TemplateResponse(request, 'admin/wholesale/catalogue_import.html', {
        **admin.site.each_context(request),
        'title': 'Private wholesale quote CSV import',
        'error': error,
        'column_names': FIELDS,
        'draft_count': DraftPlan.objects.filter(review_status='draft').count(),
    }, status=status)
