import datetime as dt,hashlib,json,shutil,sqlite3
from pathlib import Path
root=Path(__file__).resolve().parent
config=json.loads((root/'config.json').read_text());src=Path(config['primary_db'])
folder=root/'backups'/dt.datetime.now().strftime('%Y%m%dT%H%M%S');folder.mkdir(parents=True)
dest=folder/src.name
with sqlite3.connect(str(src)) as c,sqlite3.connect(dest) as out:
    c.execute('PRAGMA query_only=ON')
    c.execute('BEGIN')
    tables=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    counts={t:c.execute('SELECT count(*) FROM "'+t+'"').fetchone()[0] for t in tables}
    c.backup(out)
    verified={t:out.execute('SELECT count(*) FROM "'+t+'"').fetchone()[0] for t in tables}
    assert counts==verified
    assert out.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    c.commit()
for name in ['model.lgb','model.meta.json','model.calibrator.pkl']:
    file=src.parent/name
    if file.exists():shutil.copy2(file,folder/name)
manifest={'source':str(src),'backup':str(dest),'counts':counts,'verified_counts':verified,'files':{f.name:{'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in folder.iterdir() if f.is_file()}}
(folder/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest))
