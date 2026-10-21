"""Decode SOS transport envelopes without logging any voter data."""
import base64
import binascii
import csv
import gzip
import hashlib
import io
import json
import re
import zipfile

MAX_BYTES = 150 * 1024 * 1024
REQUIRED = {'county', 'votername', 'idvoter', 'votingmethod', 'precinct'}
ERROR = ('Downloaded content did not contain one identifiable SOS voter CSV; '
         'existing report retained. No response contents were logged.')


def text_of(body):
    encoding = 'utf-16' if body.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig'
    return body.decode(encoding)


def csv_header(body):
    # Inspect a bounded header, never feed an entire JSON envelope to csv.reader.
    try:
        first = text_of(body[:8192]).splitlines()[0]
        fields = next(csv.reader([first]))
        names = [re.sub(r'[^a-z0-9]', '', field.lower()) for field in fields]
        return len(names) == len(set(names)) and REQUIRED.issubset(names)
    except (UnicodeError, csv.Error, IndexError, StopIteration):
        return False


def decode(body):
    """Accept CSV, ZIP, gzip, or nested JSON strings/base64/byte arrays.

    Only known CSV headers identify payloads. Never fetch URLs from envelopes.
    Distinct candidate files are ambiguous and rejected before replacement.
    """
    found = {}
    seen = set()
    budget = [0]

    def visit(value, depth=0):
        budget[0] += 1
        if depth > 12 or budget[0] > 10000:
            raise ValueError(ERROR)
        if isinstance(value, dict):
            for item in value.values():
                visit(item, depth + 1)
            return
        if isinstance(value, list):
            if value and len(value) <= MAX_BYTES and all(type(x) is int and 0 <= x <= 255 for x in value):
                visit(bytes(value), depth + 1)
            else:
                for item in value:
                    visit(item, depth + 1)
            return
        if isinstance(value, str):
            value = value.encode('utf-8')
        if not isinstance(value, bytes) or not value or len(value) > MAX_BYTES:
            return
        digest = hashlib.sha256(value).digest()
        if digest in seen:
            return
        seen.add(digest)
        if value.startswith(b'\x1f\x8b'):
            with gzip.GzipFile(fileobj=io.BytesIO(value)) as stream:
                expanded = stream.read(MAX_BYTES + 1)
            if len(expanded) > MAX_BYTES:
                raise ValueError(ERROR)
            visit(expanded, depth + 1)
            return
        if value.startswith(b'PK'):
            with zipfile.ZipFile(io.BytesIO(value)) as archive:
                entries = [entry for entry in archive.infolist() if not entry.is_dir()
                           and entry.filename.lower().endswith('.csv')
                           and not entry.filename.startswith('__MACOSX/')]
                if len(entries) != 1 or entries[0].file_size > MAX_BYTES:
                    raise ValueError(ERROR)
                with archive.open(entries[0]) as stream:
                    expanded = stream.read(MAX_BYTES + 1)
                if len(expanded) > MAX_BYTES:
                    raise ValueError(ERROR)
                visit(expanded, depth + 1)
            return
        if csv_header(value):
            found[digest] = value
            return
        try:
            text = text_of(value).strip()
        except UnicodeError:
            return
        if text.startswith(('{', '[', '"')):
            try:
                parsed = json.loads(text)
            except (ValueError, RecursionError):
                return
            visit(parsed, depth + 1)
            return
        if text.startswith('data:'):
            prefix, separator, text = text.partition(',')
            if not separator or ';base64' not in prefix:
                return
        compact = ''.join(text.split())
        if len(compact) < 16:
            return
        try:
            expanded = base64.b64decode(compact, validate=True)
        except (ValueError, binascii.Error):
            return
        visit(expanded, depth + 1)

    try:
        visit(body)
    except (OSError, EOFError, ValueError, RuntimeError, zipfile.BadZipFile, RecursionError):
        raise ValueError(ERROR) from None
    if len(found) != 1:
        raise ValueError(ERROR)
    return next(iter(found.values()))
