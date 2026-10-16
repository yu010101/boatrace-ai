import json, re
from urllib.parse import urlparse,parse_qs
import pandas as pd
from bs4 import BeautifulSoup
COLS = ['date', 'st', 'r', 'grade', 'distance', 'day_number', 'closed_at', 'title', 'boat', 'racer', 'name', 'rank', 'branch', 'age', 'weight', 'f', 'l', 'avg_st', 'nat_win', 'nat_top2', 'nat_top3', 'loc_win', 'loc_top2', 'loc_top3', 'motor', 'motor_top2', 'motor_top3', 'boatno', 'boat_top2', 'boat_top3', 'pv_wind', 'pv_wind_dir', 'pv_wave', 'pv_weather', 'pv_air', 'pv_water', 'pv_course', 'pv_st', 'pv_weight', 'pv_ex_time', 'pv_tilt', 'rs_course', 'rs_st', 'place', 'technique']

def rows_from_json(obj, mask=False):
    rows=[]
    for st,sd in obj.get('programs',{}).get('stadiums',{}).items():
        for r,rc in sd.get('races',{}).items():
            pv={} if mask else (rc.get('preview') or {})
            rs={} if mask else (rc.get('result') or {})
            for b,x in (rc.get('racers') or {}).items():
                p=(pv.get('racers') or {}).get(b) or {}; q=(rs.get('racers') or {}).get(b) or {}; g=x.get
                rows.append([
                    rc.get('date'), int(st), int(r), rc.get('grade_number'), rc.get('distance'), rc.get('day_number'), rc.get('closed_at'), rc.get('title'),
                    int(b), g('number'), g('name'), g('rank_number'), g('branch_number'), g('age'), g('weight'), g('flying_count'), g('late_count'), g('average_start_timing'),
                    g('national_win_rate'), g('national_top_2_percent'), g('national_top_3_percent'), g('local_win_rate'), g('local_top_2_percent'), g('local_top_3_percent'),
                    g('motor_number'), g('motor_top_2_percent'), g('motor_top_3_percent'), g('boat_number'), g('boat_top_2_percent'), g('boat_top_3_percent'),
                    pv.get('wind_speed'), pv.get('wind_direction_number'), pv.get('wave_height'), pv.get('weather_number'), pv.get('air_temperature'), pv.get('water_temperature'),
                    p.get('course_number'), p.get('start_timing'), p.get('weight'), p.get('exhibition_time'), p.get('tilt_adjustment'),
                    q.get('course_number'), q.get('start_timing'), q.get('place_number'), rs.get('technique_number')])
    df=pd.DataFrame(rows,columns=COLS)
    df['date']=pd.to_datetime(df.date)
    return df

def number(txt):
    txt=txt.strip().replace('F','-').replace('L','')
    m=re.search(r'-?(?:\d+\.?\d*|\.\d+)',txt)
    return float(m.group()) if m else None

def identity(s,day,st,r):
    links=[a for a in s.select('a[href]') if a.get_text(strip=True)=='出走表']
    if len(links)!=1: raise ValueError('missing unambiguous race identity')
    q=parse_qs(urlparse(links[0]['href']).query)
    if q.get('hd')!=[day.replace('-','')] or int(q.get('jcd',['0'])[0])!=int(st) or int(q.get('rno',['0'])[0])!=int(r):
        raise ValueError('wrong page date/stadium/race')

def parse_preview(html,day,race_no,stadium=2):
    s=BeautifulSoup(html,'html.parser'); identity(s,day,stadium,race_no); rows={}
    for body in s.select('table.is-w748 tbody'):
        cells=body.select('tr')[0].find_all('td',recursive=False)
        if len(cells)<6: continue
        b=number(cells[0].get_text())
        if b not in range(1,7): continue
        link=cells[2].select_one('a[href*=toban]')
        if not link: continue
        racer=int(re.search(r'toban=(\d+)',link['href']).group(1))
        rows[int(b)]=dict(racer=racer,pv_weight=number(cells[3].get_text()),pv_ex_time=number(cells[4].get_text()),pv_tilt=number(cells[5].get_text()))
    for course,div in enumerate(s.select('div.table1_boatImage1'),1):
        b=int(div.select_one('.table1_boatImage1Number').get_text(strip=True))
        if b in rows: rows[b].update(pv_course=course,pv_st=number(div.select_one('.table1_boatImage1Time').get_text()))
    weather={}
    for selector,key in [('is-direction','pv_air'),('is-waterTemperature','pv_water'),('is-wave','pv_wave'),('is-wind','pv_wind')]:
        node=s.select_one(f'.weather1_bodyUnit.{selector} .weather1_bodyUnitLabelData')
        weather[key]=number(node.get_text()) if node else None
    for selector,pattern,key in [('.is-weather .weather1_bodyUnitImage',r'is-weather(\d+)','pv_weather'),('.is-windDirection .weather1_bodyUnitImage',r'is-wind(\d+)','pv_wind_dir')]:
        node=s.select_one(selector); match=re.search(pattern,' '.join(node.get('class',[]))) if node else None
        weather[key]=int(match.group(1)) if match else None
    deadline=None
    for table in s.select('table'):
        body=table.find('tbody')
        if body and '締切予定時刻' in body.get_text():
            cells=body.select('td')
            if len(cells)>=13:
                hm=cells[race_no].get_text(strip=True)
                if re.fullmatch(r'\d{2}:\d{2}',hm): deadline=f'{day}T{hm}:00+09:00'
            break
    if set(rows)!=set(range(1,7)) or deadline is None: raise ValueError('missing six preview boats/deadline')
    for row in rows.values():
        row.update(weather)
        if any(row.get(k) is None for k in ['pv_ex_time','pv_course','pv_st','pv_weight','pv_air','pv_water','pv_wave','pv_weather']):
            raise ValueError('incomplete exhibition')
        if not 5<row['pv_ex_time']<9: raise ValueError('invalid exhibition time')
    if sorted(x['pv_course'] for x in rows.values())!=list(range(1,7)): raise ValueError('invalid courses')
    return rows,deadline

def parse_win_odds(html,day=None,stadium=None,race_no=None,live=False):
    s=BeautifulSoup(html,'html.parser')
    if day is not None: identity(s,day,stadium,race_no)
    if live and any(x in s.get_text() for x in ['締切時オッズ','最終オッズ','発売中止','発売終了']): raise ValueError('closed/final odds')
    h=s.find('span',class_='title7_mainLabel',string='単勝オッズ')
    if h is None: raise ValueError('no win odds')
    table=h.find_parent('div',class_='grid_unit').find('table'); out={}
    for body in table.find_all('tbody'):
        cells=body.find('tr').find_all('td')
        if len(cells)>=3:
            b=number(cells[0].get_text()); v=number(cells[2].get_text())
            if b in range(1,7) and v and v>=1: out[int(b)]=v
    if set(out)!=set(range(1,7)): raise ValueError('incomplete six-boat win odds')
    return out
