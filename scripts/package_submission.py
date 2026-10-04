"""Check organizer requirements and archive a committed code snapshot.

This script does not submit the form, invite collaborators or upload a video.
The final package requires the 15 extra questions as an explicit input.
"""
import argparse
import csv
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.settings import DATASET, ROOT

REQUIRED = [
    'README.md', 'config/c360-contract.yaml', 'docs/data-quality-report.md',
    'submission/benchmark_answers.csv', 'app/main.py', 'frontend/package.json',
    'requirements-lock.txt',
]


def read_csv(path):
    with Path(path).open(newline='', encoding='utf-8-sig') as stream:
        reader = csv.DictReader(stream)
        return reader.fieldnames, list(reader)


def validate_answers(extra=(), final=False):
    template, _ = read_csv(DATASET / 'labels/benchmark_answers_template.csv')
    header, answers = read_csv(ROOT / 'submission/benchmark_answers.csv')
    if header != template:
        raise ValueError(f'Benchmark columns differ from the released template: {header}')
    _, released = read_csv(DATASET / 'data/benchmark_questions.csv')
    questions = {row['question_id']: row['question_text'] for row in released}
    released_ids = set(questions)
    for path in extra:
        _, rows = read_csv(path)
        for row in rows:
            qid, text = row['question_id'], row['question_text']
            if qid in questions and questions[qid] != text:
                raise ValueError(f'Conflicting question ID: {qid}')
            questions[qid] = text
    extra_count = len(set(questions) - released_ids)
    if final and extra_count != 15:
        raise ValueError(f'Final submission requires the 15 extra questions; supplied {extra_count}.')
    ids = [row['question_id'] for row in answers]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate benchmark answer IDs.')
    if set(ids) != set(questions):
        raise ValueError(f'Question coverage differs: missing={sorted(set(questions)-set(ids))}, unexpected={sorted(set(ids)-set(questions))}')
    for row in answers:
        if row['refused'] not in ['true', 'false'] or not row['answer'].strip():
            raise ValueError(f'Invalid answer/refusal field: {row["question_id"]}')
        if row['refused'] == 'false' and not row['sql_or_sources'].strip():
            raise ValueError(f'Non-refused answer lacks evidence: {row["question_id"]}')
    status_path = ROOT / 'data/benchmark-status.json'
    if status_path.exists():
        status = json.loads(status_path.read_text())
        if status.get('unresolved'):
            raise ValueError('Benchmark generation has unresolved results; inspect data/benchmark-status.json.')
        if status.get('questions') != len(answers):
            raise ValueError('Benchmark status count is stale; regenerate answers.')
    return {'questions': len(answers), 'released': len(released), 'extra': extra_count,
            'refused': sum(row['refused'] == 'true' for row in answers),
            'final': final, 'answer_accuracy': 'Coverage/format checks only; hidden-answer correctness is unverified.'}


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def package(output, extra=(), final=False, check_only=False):
    for name in REQUIRED:
        if not (ROOT / name).is_file():
            raise ValueError(f'Missing required repository file: {name}')
    architecture = [name for name in ['docs/architecture-build.pdf', 'docs/architecture-build.png'] if (ROOT / name).is_file()]
    if not architecture:
        raise ValueError('Missing final architecture PDF/PNG.')
    result = validate_answers(extra, final)
    result.update(repository='https://github.com/pg1590/cibc-collections-copilot',
                  commit=git('rev-parse', 'HEAD').decode().strip(),
                  collaborator='Must verify cibchack26 invitation/access in GitHub Settings.',
                  demo_video='Must supply an accessible link, at most five minutes.',
                  presentation='Must upload PDF, at most ten slides.')
    if check_only:
        print(json.dumps(result, indent=2))
        return
    if git('status', '--porcelain').strip():
        raise ValueError('Commit pending repository changes before packaging; the ZIP contains HEAD only.')
    output = Path(output).resolve()
    if output.is_relative_to(ROOT):
        raise ValueError('Put the backup outside the code repo to avoid archiving backups recursively.')
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix('.tmp.zip')
    try:
        git('archive', '--format=zip', '--prefix=AddaWale/', '--output=' + str(temporary), 'HEAD')
        with zipfile.ZipFile(temporary, 'a') as archive:
            names = archive.namelist()
            for name in REQUIRED + architecture:
                if 'AddaWale/' + name not in names:
                    raise ValueError(f'Required file is not committed: {name}')
            forbidden = [name for name in names if
                         any(part in ['.git', '.venv', 'node_modules', '.next', 'data', 'logs', 'prompts'] for part in Path(name).parts) or
                         (Path(name).name.startswith('.env') and Path(name).name != '.env.example') or
                         Path(name).suffix in ['.pem', '.key', '.duckdb', '.sqlite3', '.joblib']]
            if forbidden:
                raise ValueError(f'Unexpected local data/credential/dependency files: {forbidden[:5]}')
            if archive.testzip() is not None:
                raise ValueError('ZIP integrity check failed.')
            archive.comment = json.dumps({'commit': result['commit'], 'questions': result['questions'],
                                          'final': final}, sort_keys=True).encode()
            result['archived_files'] = len([name for name in names if not name.endswith('/')])
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    result.update(zip=str(output), bytes=output.stat().st_size,
                  sha256=hashlib.sha256(output.read_bytes()).hexdigest())
    output.with_suffix('.manifest.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT.parent / 'deliverables/AddaWale-code-backup.zip')
    parser.add_argument('--extra', type=Path, action='append', default=[])
    parser.add_argument('--final', action='store_true', help='Require all 15 extra questions before creating the final package.')
    parser.add_argument('--check-only', action='store_true', help='Check current files without archiving or requiring a clean commit.')
    args = parser.parse_args()
    try:
        package(args.output, args.extra, args.final, args.check_only)
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as exc:
        parser.exit(1, str(exc) + '\n')
