"""The policy library: every reference document in the release, split into its numbered sections.

Read-only. Text comes verbatim from the release files under files/docs; the catalogue comes from
data/reference_documents.csv. A row whose file_path leaves files/docs is skipped, never read.
"""
import csv
import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path

TYPE_ORDER = ['policy', 'procedure', 'call_script', 'hardship_programme_terms', 'regulatory_summary', 'faq',
              'data_contract', 'incident_report', 'release_note']
SECTION = re.compile(r'(§[\d.]+|Q\d+)')


def _sections(text):
    # Policies and procedures use "## §5.4 Heading"; the FAQ uses "**Q2. Question?**" lines.
    if not re.search(r'^## ', text, flags=re.M) and re.search(r'^\*\*Q\d+\.', text, flags=re.M):
        text = re.sub(r'^\*\*(Q\d+\..*?)\*\*\s*$', r'## \1', text, flags=re.M)
    parts = re.split(r'(?=^## )', text, flags=re.M)
    preamble = parts[0].strip() if parts and not parts[0].startswith('## ') else ''
    sections = []
    for part in parts:
        if not part.startswith('## '):continue
        heading = part.splitlines()[0][3:].strip()
        found = SECTION.search(heading)
        body = part.split('\n', 1)[1].strip() if '\n' in part else ''
        sections.append({'id': found.group(0) if found else heading, 'heading': heading, 'text': body})
    return preamble, sections


@lru_cache(maxsize=4)
def _library(dataset_key):
    dataset = Path(dataset_key)
    catalogue = dataset/'data/reference_documents.csv'
    docs_root = (dataset/'files/docs').resolve()
    documents = []
    if catalogue.exists():
        with catalogue.open(encoding='utf-8-sig', newline='') as f:
            for row in csv.DictReader(f):
                file = (dataset/'files'/row['file_path']).resolve()
                if not file.is_relative_to(docs_root) or not file.is_file():continue
                raw = file.read_bytes()
                preamble, sections = _sections(raw.decode('utf-8'))
                documents.append({
                    'doc_id': row['doc_id'], 'title': row['title'], 'doc_type': row['doc_type'], 'language': row['language'],
                    'version': row['version'], 'effective_date': row['effective_date'] or None,
                    'superseded_by': row['superseded_by'] or None, 'owner': row['owner'] or None,
                    'file_path': file.relative_to(dataset).as_posix(), 'sha256': hashlib.sha256(raw).hexdigest(),
                    'current': not row['superseded_by'], 'preamble': preamble, 'sections': sections})
    rank = {t: i for i, t in enumerate(TYPE_ORDER)}
    documents.sort(key=lambda d: (not d['current'], rank.get(d['doc_type'], len(rank)), d['doc_id']))
    provenance = dataset.parent/'release-provenance.json'
    release = None
    if provenance.exists():
        p = json.loads(provenance.read_text(encoding='utf-8'))
        release = {'revision': p.get('revision'), 'verified_against_publisher': bool(p.get('verified_against_publisher'))}
    return {'release': release, 'documents': documents}


def library(dataset):
    return _library(str(Path(dataset).resolve()))
