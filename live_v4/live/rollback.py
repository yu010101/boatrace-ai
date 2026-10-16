"""Stop v4 and restore only v4 rows from their transaction-local backups."""
import json,sqlite3
from pathlib import Path
import runner
root=Path(__file__).resolve().parent
(root/'state/STOP').touch()
config=json.loads((root/'config.json').read_text());config['active_model']='shadow'
(root/'config.json').write_text(json.dumps(config,indent=2))
with runner.primary_connection(Path(config['primary_db'])) as c:
    c.execute('BEGIN IMMEDIATE')
    for row in c.execute('SELECT record FROM live_v4_predictions').fetchall():
        record=json.loads(row[0]);conflicts=runner.restore_primary(c,record)
        if conflicts:print('concurrent changes preserved',record['day'],record['st'],record['r'],conflicts)
    for table in ['predictions','race_grades']:c.execute(f'DROP TRIGGER IF EXISTS protect_v4_{table}')
print('v4 stopped; legacy predictions restored; original model files were never replaced')
