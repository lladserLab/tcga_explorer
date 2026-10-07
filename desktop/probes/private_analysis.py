"""Probe the isolated loopback API with TRACE's synthetic teaching data."""
import io
import csv
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import urllib.request
import urllib.error
import zipfile

BASE = os.environ.get('TRACE_PROBE_BASE', 'http://127.0.0.1:3100/tcga_explorer/api/v1')
OUT = Path(os.environ['TRACE_PROBE_OUTPUT']) if 'TRACE_PROBE_OUTPUT' in os.environ else Path(__file__).resolve().parents[1] / 'runtime' / 'probe'
OUT.mkdir(parents=True, exist_ok=True)

def request(path, data=None, headers=None):
    req = urllib.request.Request(BASE + path, data=data, headers=headers or {})
    opener = urllib.request.OpenerDirector()
    for handler in (urllib.request.HTTPHandler(), urllib.request.HTTPDefaultErrorHandler(), urllib.request.HTTPErrorProcessor()):
        opener.add_handler(handler)
    with opener.open(req, timeout=60) as response:
        return response.read()

report = {'synthetic_only': True, 'base_url': BASE}
try:
    if '--resume' in sys.argv:
        session = json.loads((OUT / 'session.json').read_text())
        headers = {'X-TRACE-Dataset-Token': session['token']}
        dataset = json.loads(request('/user-datasets/' + session['dataset_id'], headers=headers))
        job = json.loads(request('/jobs/' + session['job_id'], headers=headers))
        assert dataset['patient_count'] == 48
        assert job['status'] == 'completed'
        assert job['result']['metrics']['n_patients'] == 48
        print(json.dumps({'restart_recovery': True, 'patients': 48, 'job_id': job['id']}))
        (OUT / 'restart-recovery.json').write_text(json.dumps({'passed': True, 'patients': 48, 'job_id': job['id']}, indent=2))
        raise SystemExit(0)
    report['initial_catalog'] = json.loads(request('/cancer-types'))
    archive = zipfile.ZipFile(io.BytesIO(request('/tutorial-assets/private-quickstart-kirc-log2-v1')))
    mapping = {
        'name': 'Desktop synthetic feasibility probe', 'cancer_code': 'KIRC',
        'expression_orientation': 'genes_by_rows', 'expression_id_column': 'gene_symbol',
        'clinical_id_column': 'sample_id', 'has_survival_outcome': True,
        'time_column': 'os_months', 'event_column': 'os_status',
        'event_value': 'event', 'censored_value': 'censored', 'time_unit': 'months',
        'endpoint': 'OS', 'expression_unit': 'log2_tpm',
        'covariates': {'age_at_index': 'age', 'stage': 'stage', 'grade': 'grade'},
        'confirm_deidentified': True,
    }
    boundary = 'trace-desktop-synthetic-probe-boundary'
    parts = []
    for field, filename in [('expression_file', 'expression_log2_genes_by_samples.csv'), ('clinical_file', 'clinical.csv')]:
        parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{filename}"\r\nContent-Type: text/csv\r\n\r\n').encode() + archive.read(filename) + b'\r\n')
    parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="mapping"\r\n\r\n' + json.dumps(mapping) + f'\r\n--{boundary}--\r\n').encode())
    created = json.loads(request('/user-datasets', b''.join(parts), {'Content-Type': f'multipart/form-data; boundary={boundary}'}))
    token = created.pop('access_token')
    report['upload'] = created
    headers = {'X-TRACE-Dataset-Token': token, 'Content-Type': 'application/json'}
    payload = {
        'cohort': 'TCGA-KIRC', 'dataset_id': created['id'],
        'dataset_release_id': created['active_release_id'],
        'expression_layer_id': 'uploaded_expression', 'gene_symbol': 'CDC20',
        'endpoint': 'OS', 'cutpoint_method': 'median', 'show_risk_table': True,
        'adjustment_covariates': ['age_at_index'],
    }
    report['request'] = payload
    job = json.loads(request('/analyses', json.dumps(payload).encode(), headers))
    deadline = time.monotonic() + 180
    while job['status'] not in ('completed', 'failed', 'expired'):
        if time.monotonic() > deadline:
            raise RuntimeError('Local analysis did not finish within 180 seconds')
        time.sleep(1)
        job = json.loads(request('/jobs/' + job['id'], headers=headers))
    report['job'] = job
    if job['status'] != 'completed':
        raise RuntimeError('Local analysis failed')
    result = job['result']
    assert created['patient_count'] == 48 and created['event_count'] == 24
    assert result['metrics']['n_patients'] == 48
    assert result['metrics']['group_counts'] == {'Low': 24, 'High': 24}
    report['exports'] = {}
    for kind in ('csv', 'svg', 'audit_json', 'cohort_manifest', 'zip'):
        data = request('/analyses/' + result['id'] + '/download/' + kind, headers=headers)
        (OUT / ('analysis.' + kind)).write_bytes(data)
        report['exports'][kind] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    rows = list(csv.DictReader((OUT / 'analysis.csv').read_text().splitlines()))
    assert len(rows) == 48
    report['exported_patient_rows'] = len(rows)
    bundle = zipfile.ZipFile(OUT / 'analysis.zip')
    report['bundle_files'] = bundle.namelist()
    assert any(name.endswith('audit_report.json') for name in bundle.namelist())
    assert any(name.endswith('.R') for name in bundle.namelist())
    # Local capability is excluded from Git and the public verification report.
    session_path = OUT / 'session.json'
    session_path.write_text(json.dumps({'token': token, 'dataset_id': created['id'], 'job_id': job['id']}))
    os.chmod(session_path, 0o600)
    report['passed'] = True
except urllib.error.HTTPError as exc:
    report['passed'] = False
    report['http_error'] = {'status': exc.code, 'body': exc.read().decode()}
except Exception as exc:
    import traceback
    traceback.print_exc()
    report['passed'] = False
    report['error'] = str(exc)
finally:
    if '--resume' not in sys.argv:
        (OUT / 'private-analysis.json').write_text(json.dumps(report, indent=2))
        print(json.dumps({'passed': report.get('passed'), 'error': report.get('http_error', report.get('error')), 'report': str(OUT / 'private-analysis.json')}))
        if not report.get('passed'):
            raise SystemExit(1)
