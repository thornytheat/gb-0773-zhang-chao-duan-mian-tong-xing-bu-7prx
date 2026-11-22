from concurrent.futures import ThreadPoolExecutor

from app.main import create_app
from app.modules.journal.service import record
from app.modules.journal.store import Journal


def test_receipt(client):
    response = client.post('/api/journal',json={'sample':'dirty'})
    assert response.status_code == 201 and response.json['manifest']['rule_version']=='tide-1.0'


def test_replay(client):
    first=client.post('/api/journal',json={'sample':'dirty'}).json
    second=client.post(f"/api/journal/{first['run_id']}/rerun").json
    assert second == {**first,'reused':True}
    assert len(client.get('/api/journal').json['runs'])==1


def test_rollback(client,sources):
    sources['stations'] += 'duplicate\n'
    assert client.post('/api/journal',json={'sources':sources}).status_code==422
    assert client.get('/api/journal').json['runs']==[]


def test_concurrent(tmp_path,sources):
    journal=Journal(tmp_path/'overlap.db')
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _: record(journal,sources),range(4)))
    assert sum(not row['reused'] for row in results)==1
    assert len({r['run_id'] for r in results})==1


def test_reopen(tmp_path):
    path=tmp_path/'saved.db'
    first=create_app(path).test_client().post('/api/journal',json={'sample':'dirty'}).json
    second=create_app(path).test_client().get(f"/api/journal/{first['run_id']}").json
    assert second['manifest']==first['manifest']
    assert second['coverage']['ships']['海棠17']['seconds']['unknown']=='600'


def test_missing_run(client):
    result=client.post('/api/journal/absent/rerun')
    assert (result.status_code,result.json['code'])==(404,'NO_RUN')


def shifted_sources(sources):
    lines=sources['observations'].splitlines(keepends=True)
    return dict(sources,observations=lines[0]+lines[0].lstrip('\ufeff')+''.join(lines[1:]))


def test_extra_header_same_ledger(client,sources):
    first=client.post('/api/journal',json={'sources':sources}).json
    second=client.post('/api/journal',json={'sources':shifted_sources(sources)})
    assert second.status_code==201
    assert second.json['run_id']==first['run_id']
    assert second.json['intake_id']!=first['intake_id']
    runs=client.get('/api/journal').json['runs']
    assert len(runs)==1 and runs[0]['filings']==2
    detail=client.get(f"/api/journal/{first['run_id']}").json
    assert {row['intake_id'] for row in detail['intakes']}=={first['intake_id'],second.json['intake_id']}


def test_retry_same_original_no_new_filing(client,sources):
    first=client.post('/api/journal',json={'sources':sources}).json
    again=client.post('/api/journal',json={'sources':sources})
    assert again.status_code==200 and again.json['reused'] is True
    assert again.json['intake_id']==first['intake_id']
    assert client.get('/api/journal').json['runs'][0]['filings']==1


def test_changed_readings_new_ledger(client,sources):
    first=client.post('/api/journal',json={'sources':sources}).json
    altered=dict(sources,observations=sources['observations'].replace(',100,cm,OK',',101,cm,OK',1))
    second=client.post('/api/journal',json={'sources':altered}).json
    assert second['run_id']!=first['run_id']
    assert len(client.get('/api/journal').json['runs'])==2


def test_rerun_uses_selected_intake(client,sources):
    first=client.post('/api/journal',json={'sources':sources}).json
    second=client.post('/api/journal',json={'sources':shifted_sources(sources)}).json
    rerun=client.post(f"/api/journal/{first['run_id']}/rerun",json={'intake':second['intake_id']})
    assert rerun.status_code==200 and rerun.json['intake_id']==second['intake_id']
    assert rerun.json['manifest']['inputs']['observations']!=first['manifest']['inputs']['observations']


def test_intake_of_other_ledger_rejected(client,sources):
    first=client.post('/api/journal',json={'sources':sources}).json
    other=client.post('/api/journal',json={'sample':'clean'}).json
    result=client.post(f"/api/journal/{first['run_id']}/rerun",json={'intake':other['intake_id']})
    assert (result.status_code,result.json['code'])==(404,'NO_INTAKE')


def test_export_marks_selected_intake(client,sources):
    first=client.post('/api/journal',json={'sources':sources}).json
    shifted=shifted_sources(sources)
    second=client.post('/api/journal',json={'sources':shifted}).json
    one=client.get(f"/api/export/{first['run_id']}").json
    two=client.get(f"/api/export/{first['run_id']}?intake={second['intake_id']}").json
    assert one['manifest']['intake_id']==first['intake_id']
    assert two['manifest']['intake_id']==second['intake_id']
    assert two['originals']['observations']==shifted['observations']
    first_rows=one['reports']['readings']['tables']['observations']
    second_rows=two['reports']['readings']['tables']['observations']
    assert [row['raw'] for row in first_rows]==[row['raw'] for row in second_rows]
    assert [row['line'] for row in first_rows]!=[row['line'] for row in second_rows]
