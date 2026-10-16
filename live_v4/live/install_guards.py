"""Protect confirmed live forecasts from the legacy morning INSERT path."""
import json,sqlite3
from pathlib import Path

def install(db):
    assert db.exists()
    with sqlite3.connect(db) as c:
        for table,column in [('predictions','analysis'),('race_grades','reason')]:
            c.execute(f"""CREATE TRIGGER IF NOT EXISTS protect_v4_{table} BEFORE INSERT ON {table}
            WHEN NEW.{column} NOT LIKE '[v4-live]%' AND EXISTS (
              SELECT 1 FROM {table} old WHERE old.race_date=NEW.race_date
              AND old.stadium_number=NEW.stadium_number AND old.race_number=NEW.race_number
              AND old.{column} LIKE '[v4-live]%')
            BEGIN SELECT RAISE(IGNORE); END""")
        return c.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'protect_v4_%'").fetchall()
if __name__=='__main__':
    config=json.loads((Path(__file__).resolve().parent/'config.json').read_text())
    print(install(Path(config['primary_db'])))
