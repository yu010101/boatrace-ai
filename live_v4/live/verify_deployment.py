import hashlib,json,sqlite3
from pathlib import Path
root=Path(__file__).resolve().parent.parent
config=json.loads((root/'live/config.json').read_text())
assert config['active_model']=='v4'
backup=root/'live/backups/20261016T063718'
manifest=json.loads((backup/'manifest.json').read_text())
db=Path(config['primary_db'])
with sqlite3.connect(db) as c:
    counts={t:c.execute('SELECT count(*) FROM "'+t+'"').fetchone()[0] for t in manifest['counts']}
    assert counts==manifest['counts']
    triggers=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'protect_v4_%'")]
    assert len(triggers)==2
    audit=c.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='live_v4_predictions'").fetchone()[0]
    records=c.execute('SELECT count(*) FROM live_v4_predictions').fetchone()[0] if audit else 0
for name in ['boatrace.db','model.lgb','model.meta.json','model.calibrator.pkl']:
    assert hashlib.sha256((backup/name).read_bytes()).hexdigest()==manifest['files'][name]['sha256']
    if name!='boatrace.db':assert (backup/name).read_bytes()==(db.parent/name).read_bytes()
heartbeat=json.loads((root/'live/state/heartbeat.json').read_text())
assert not heartbeat['stop']
result=dict(config=config,legacy_counts=counts,triggers=triggers,live_records=records,heartbeat=heartbeat,backup=str(backup),backup_verified=True,legacy_models_unchanged=True)
print(json.dumps(result,ensure_ascii=False,indent=2))
