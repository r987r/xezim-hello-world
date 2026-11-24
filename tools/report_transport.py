"""Lossless transport for large static report assets, not a change to evidence."""
import gzip
from html import escape
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
CAPTURE_READER = '__CAPTURE_READER__'
GZIP_THRESHOLD = 1024**2
BULKY_EVIDENCE = frozenset({
    'axi-events.jsonl', 'axi-transactions.json', 'protocol-events.jsonl',
    'protocol-transactions.json', 'protocol-transactions-decoded.json',
})


def reader(template):
    return template.replace(CAPTURE_READER, (ROOT/'templates/report_capture.js').read_text())


def capture_template(template, filename):
    """Set a trusted browser path for external capture; offline stays inline."""
    if filename and filename not in {name+'.gz' for name in BULKY_EVIDENCE}:
        raise ValueError('unexpected external report capture filename')
    attr=f' data-capture-source="{escape(filename, quote=True)}"' if filename else ''
    return reader(template).replace('__CAPTURE_SOURCE_ATTR__',attr)


def compressed_assets(folder, names):
    return {name: name+'.gz' for name in names if name in BULKY_EVIDENCE
            and (folder/name).stat().st_size >= GZIP_THRESHOLD}


def compress_originals(output, entries):
    """Apply storage encoding only after all provenance readers have finished."""
    for entry in entries:
        folder = output/Path(entry['path']).parent
        for name, archive in entry.get('compressed_assets', {}).items():
            source = folder/name
            with source.open('rb') as original, (folder/archive).open('xb') as target:
                with gzip.GzipFile(filename='', fileobj=target, mode='wb',
                                   compresslevel=1, mtime=0) as encoded:
                    shutil.copyfileobj(original, encoded, length=1024**2)
            source.unlink()


def asset_link(name, compressed):
    href = compressed.get(name, name)
    label = name+(' (lossless gzip)' if href!=name else '')
    return f'<a href="{escape(href, quote=True)}">{escape(label)}</a>'
