# 特徴量づくり。入力は races.db の boats と racers.db の kibetsu（読み取りのみ）。
# 原則: 結果側の列（rs_*, place, technique）は「当日より前の日付」の行からしか集計しない。
import sqlite3, numpy as np, pandas as pd

BASE = '/Users/yu01/tasks/kyotei-db-20261015'
RESULT_COLS = ['rs_course', 'rs_st', 'place', 'technique']


def load_boats():
    db = sqlite3.connect(f'file:{BASE}/data/races.db?mode=ro', uri=True)
    df = pd.read_sql('select * from boats', db)
    df['date'] = pd.to_datetime(df['date'])
    return df


def load_kibetsu():
    db = sqlite3.connect(f'file:{BASE}/data/racers.db?mode=ro', uri=True)
    k = pd.read_sql('select * from kibetsu', db)
    k['racer'] = pd.to_numeric(k['toban'], errors='coerce')
    k['period_to'] = pd.to_datetime(k['period_to'])
    return k


# ---- 当日より前の累積を引く道具: (key..., date) で日ごとに集計→累積→ merge_asof(厳密に前の日) ----
def prior_cum(df_src, keys, vals, df_tgt, tgt_keys, prefix):
    """df_src の vals を (keys, date) ごとに合計→累積し、df_tgt の各行に「その行の date より前の日まで」の累積を付ける。
    合わせた元の日付を prefix+'_srcdate' に残し、あとで < date を assert する。"""
    g = df_src.groupby(keys + ['date'])[vals].sum().reset_index().sort_values('date')
    g[vals] = g.groupby(keys)[vals].cumsum()
    g = g.rename(columns={**{v: f'{prefix}_{v}' for v in vals}, 'date': f'{prefix}_srcdate'})
    g = g.rename(columns=dict(zip(keys, tgt_keys)))
    t = df_tgt[tgt_keys + ['date', '_rowid']].copy()
    for a in tgt_keys:
        t[a] = t[a].astype('float64'); g[a] = g[a].astype('float64')
    t = t.sort_values('date'); g = g.sort_values(f'{prefix}_srcdate')
    m = pd.merge_asof(t, g, left_on='date', right_on=f'{prefix}_srcdate', by=tgt_keys,
                      allow_exact_matches=False, direction='backward')
    m = m.set_index('_rowid').reindex(df_tgt['_rowid'])
    ok = m[f'{prefix}_srcdate'].isna() | (m[f'{prefix}_srcdate'].values < df_tgt['date'].values)
    assert ok.all(), f'leak in {prefix}'
    return m[[f'{prefix}_{v}' for v in vals] + [f'{prefix}_srcdate']].reset_index(drop=True)


def prior_rolling(df, key, col, n, funcs, prefix):
    """key ごとに過去 n 走の col の統計。当日分を含めないため、各 (key,date) の最初の行の値（=前日までの走）を当日全行に配る。"""
    d = df[[*key, 'date', 'r', col, '_rowid']].sort_values(['date', 'r'])
    out = {}
    sh = d.groupby(key)[col].shift(1)
    tmp = d[key + ['date']].copy(); tmp['_v'] = sh
    for f in funcs:
        roll = tmp.groupby(key)['_v'].rolling(n, min_periods=3).agg(f).reset_index(level=list(range(len(key))), drop=True)
        tmp[f'{prefix}_{f}'] = roll
        # 同じ日の 2 走目以降は同日の前の走を含むので、その日の最初の行の値に揃える
        tmp[f'{prefix}_{f}'] = tmp.groupby(key + ['date'])[f'{prefix}_{f}'].transform(lambda s: s.iloc[0])  # 'first' は欠損を飛ばすので使わない
        out[f'{prefix}_{f}'] = tmp[f'{prefix}_{f}']
    res = pd.DataFrame(out); res['_rowid'] = d['_rowid'].values
    return res.set_index('_rowid').reindex(df['_rowid']).reset_index(drop=True)


def rank_in_race(df, col, asc=True):
    return df.groupby('race_id')[col].rank(ascending=asc, method='average')


def diff_mean(df, col):
    return df[col] - df.groupby('race_id')[col].transform('mean')


def build(df, kib, train_end=None):
    """df: boats（検証日の結果列は使われない設計）。train_end: 学習期間の最終日（風向き推定・期待着順表はここまでで作る）。"""
    df = df.copy().reset_index(drop=True)
    df['_rowid'] = np.arange(len(df))
    df['race_id'] = df['date'].dt.strftime('%Y%m%d') + '_' + df['st'].astype(str) + '_' + df['r'].astype(str)
    df['win'] = (df['place'] == 1).astype(float)
    df.loc[df['place'].isna(), 'win'] = 0.0
    df['top2'] = (df['place'] <= 2).astype(float)
    df['has_res'] = df['place'].notna().astype(float)
    # place 7〜99 は失格・F・欠場などの記号。v1 はそのまま平均していた（不具合）。v2 は 6 着扱い
    df['place_f'] = df['place'].astype(float).clip(upper=6)
    df['cur_course'] = df['pv_course'].fillna(df['boat'])
    F = {}

    # ===== 基準: 出走表 35 変数 =====
    base = ['boat', 'rank', 'age', 'weight', 'f', 'l', 'avg_st', 'nat_win', 'nat_top2', 'nat_top3', 'loc_win', 'loc_top2',
            'loc_top3', 'motor_top2', 'motor_top3', 'boat_top2', 'boat_top3', 'branch', 'st', 'r', 'grade', 'distance', 'day_number']
    for c in ['nat_win', 'nat_top2', 'motor_top2', 'avg_st', 'loc_win']:
        df[f'rk_{c}'] = rank_in_race(df, c, asc=(c == 'avg_st')); df[f'dm_{c}'] = diff_mean(df, c)
        base += [f'rk_{c}', f'dm_{c}']
    df = df.sort_values(['race_id', 'boat']).reset_index(drop=True)
    df['inner_nat_win_diff'] = df['nat_win'] - df.groupby('race_id')['nat_win'].shift(1)
    # 場×艇番の1着率（当日より前のデータだけ）
    df['_one'] = 1.0
    m = prior_cum(df, ['st', 'boat'], ['win', 'has_res'], df, ['st', 'boat'], 'stb')
    df['st_boat_winrate'] = (m['stb_win'] / m['stb_has_res']).values
    base += ['inner_nat_win_diff', 'st_boat_winrate']
    F['base'] = base

    # ===== 展示タイム =====
    df['ex_rank'] = rank_in_race(df, 'pv_ex_time'); df['ex_dm'] = diff_mean(df, 'pv_ex_time')
    df['ex_dbest'] = df['pv_ex_time'] - df.groupby('race_id')['pv_ex_time'].transform('min')
    F['ex_time'] = ['pv_ex_time', 'ex_rank', 'ex_dm', 'ex_dbest']

    # ===== 進入コース =====
    df['course_shift'] = df['pv_course'] - df['boat']; df['course_changed'] = (df['course_shift'] != 0).astype(float)
    df.loc[df['pv_course'].isna(), 'course_changed'] = np.nan
    df['race_n_changed'] = df.groupby('race_id')['course_changed'].transform('sum')
    F['course'] = ['pv_course', 'course_shift', 'course_changed', 'race_n_changed']

    # ===== 展示ST =====
    df['exst_rank'] = rank_in_race(df, 'pv_st'); df['exst_dm'] = diff_mean(df, 'pv_st')
    F['ex_st'] = ['pv_st', 'exst_rank', 'exst_dm']

    # ===== 風 =====
    calm = (df['pv_wind_dir'] == 17) | (df['pv_wind'] == 0)
    ang = np.deg2rad((df['pv_wind_dir'] - 1) * 22.5)
    sp = df['pv_wind'].where(~calm, 0.0)
    df['wind_x'] = sp * np.sin(ang); df['wind_y'] = sp * np.cos(ang)
    df.loc[calm, ['wind_x', 'wind_y']] = 0.0
    # v2: 向きは「その日より前の日」の1号艇の結果だけで逐次に推定（場ごと・16方位で相関が最大の向き）
    src = df[(df['boat'] == 1) & df['place'].notna() & ~calm & (df['pv_wind'] >= 1)].copy()
    a1 = np.deg2rad((src['pv_wind_dir'] - 1) * 22.5); src['_n'] = 1.0; src['_y'] = src['win']
    vals = ['_n', '_y']
    for k in range(16):
        x = src['pv_wind'] * np.cos(a1 - np.deg2rad(k * 22.5))
        src[f'_x{k}'] = x; src[f'_xx{k}'] = x * x; src[f'_xy{k}'] = x * src['win']; vals += [f'_x{k}', f'_xx{k}', f'_xy{k}']
    m = prior_cum(src, ['st'], vals, df, ['st'], 'wa')
    n, sy = m['wa__n'].values, m['wa__y'].values
    cor = np.full((len(df), 16), -np.inf)
    for k in range(16):
        sx, sxx, sxy = m[f'wa__x{k}'].values, m[f'wa__xx{k}'].values, m[f'wa__xy{k}'].values
        den = np.sqrt(np.clip((n * sxx - sx ** 2) * (n * sy - sy ** 2), 1e-12, None))
        c = (n * sxy - sx * sy) / den
        cor[:, k] = np.where(np.isfinite(c) & (n > 30), c, -np.inf)
    ok = np.isfinite(cor.max(1))
    th = np.where(ok, np.deg2rad(cor.argmax(1) * 22.5), np.nan)
    df['wind_along'] = sp * np.cos(ang - th); df['wind_cross'] = (sp * np.sin(ang - th)).abs()
    df.loc[calm & ok, ['wind_along', 'wind_cross']] = 0.0
    # v2 (b): 場×風速帯 / 場×風向 の「過去の1号艇勝率 − その場の過去の1号艇勝率」（縮約 k=30・その日より前だけ）
    df['wind_band'] = pd.cut(sp.fillna(-1), [-2, -0.5, 0.5, 2.5, 4.5, 6.5, 99], labels=False).astype(float)
    df.loc[df['pv_wind'].isna(), 'wind_band'] = np.nan
    b1 = df[(df['boat'] == 1) & df['place'].notna()]
    mo = prior_cum(b1, ['st'], ['win', 'has_res'], df, ['st'], 'w1o')
    base_rate = (mo['w1o_win'] / mo['w1o_has_res']).values
    mb = prior_cum(b1.dropna(subset=['wind_band']), ['st', 'wind_band'], ['win', 'has_res'], df, ['st', 'wind_band'], 'w1b')
    K = 30.0
    df['wind_band_dev'] = (mb['w1b_win'].fillna(0).values + K * base_rate) / (mb['w1b_has_res'].fillna(0).values + K) - base_rate
    b1d = b1[(b1['pv_wind'] >= 2) & (b1['pv_wind_dir'] != 17)]
    df['_dir2'] = df['pv_wind_dir'].where(df['pv_wind'] >= 2)
    md = prior_cum(b1d.assign(_dir2=b1d['pv_wind_dir']), ['st', '_dir2'], ['win', 'has_res'], df, ['st', '_dir2'], 'w1d')
    dd_ = (md['w1d_win'].fillna(0).values + K * base_rate) / (md['w1d_has_res'].fillna(0).values + K) - base_rate
    df['wind_dir_dev'] = np.where(df['_dir2'].notna(), dd_, 0.0)
    df.loc[df['pv_wind'].isna(), 'wind_dir_dev'] = np.nan
    df['st_winddir'] = df['st'] * 20 + df['pv_wind_dir'].fillna(0)
    F['wind_v1'] = ['pv_wind', 'wind_x', 'wind_y', 'st_winddir']
    F['wind_a'] = ['pv_wind', 'wind_along', 'wind_cross']
    F['wind_b'] = ['pv_wind', 'wind_band_dev', 'wind_dir_dev']

    # ===== 波・水温・気温・天候 =====
    df['water_air'] = df['pv_water'] - df['pv_air']
    F['wave_temp'] = ['pv_wave', 'pv_water', 'pv_air', 'pv_weather', 'water_air']

    # ===== 今節成績（同じ選手・同じ場・連続した開催の前の日まで） =====
    d2 = df.sort_values(['racer', 'st', 'date'])
    gap = d2.groupby(['racer', 'st'])['date'].diff().dt.days
    newser = (gap.isna() | (gap > 2) | (d2['title'] != d2.groupby(['racer', 'st'])['title'].shift(1))).astype(int)
    d2['series'] = newser.groupby([d2['racer'], d2['st']]).cumsum()
    df['series'] = d2['series'].reindex(df.index)
    m = prior_cum(df, ['racer', 'st', 'series'], ['place_f', 'has_res', 'win', 'top2'], df, ['racer', 'st', 'series'], 'ser')
    df['ser_n'] = m['ser_has_res'].values; df['ser_avg_place'] = (m['ser_place_f'] / m['ser_has_res']).values
    df['ser_wins'] = m['ser_win'].values; df['ser_top2'] = (m['ser_top2'] / m['ser_has_res']).values
    df['ser_avg_place_dm'] = diff_mean(df, 'ser_avg_place')
    F['series'] = ['ser_n', 'ser_avg_place', 'ser_wins', 'ser_top2', 'ser_avg_place_dm']

    # ===== データ内の過去成績（当地・コース別。当日より前） =====
    src = df[df['place'].notna()].copy(); src['c'] = src['rs_course'].fillna(src['boat'])
    m1 = prior_cum(df, ['racer'], ['win', 'top2', 'has_res'], df, ['racer'], 'h_all')
    m2 = prior_cum(df, ['racer', 'st'], ['win', 'top2', 'has_res'], df, ['racer', 'st'], 'h_st')
    m3 = prior_cum(src, ['racer', 'c'], ['win', 'top2', 'has_res'], df, ['racer', 'cur_course'], 'h_c')
    for p, mm in [('h_all', m1), ('h_st', m2), ('h_c', m3)]:
        df[f'{p}_n'] = mm[f'{p}_has_res'].values
        df[f'{p}_win'] = (mm[f'{p}_win'] / mm[f'{p}_has_res']).values
        df[f'{p}_top2'] = (mm[f'{p}_top2'] / mm[f'{p}_has_res']).values
    F['hist'] = [f'{p}_{s}' for p in ['h_all', 'h_st', 'h_c'] for s in ['n', 'win', 'top2']]

    # ===== 期別成績（算出期間の終わり+60日 < レース日 の最新期だけ） =====
    kk = kib.dropna(subset=['racer']).copy()
    kk['usable_from'] = kk['period_to'] + pd.Timedelta(days=61)
    kk = kk.sort_values('usable_from')
    t = df[['_rowid', 'racer', 'date', 'cur_course']].sort_values('date')
    t['racer'] = t['racer'].astype('float64'); kk['racer'] = kk['racer'].astype('float64')
    mk = pd.merge_asof(t, kk, left_on='date', right_on='usable_from', by='racer', direction='backward')
    assert (mk['period_to'].isna() | (mk['period_to'] < mk['date'])).all()
    mk = mk.set_index('_rowid').reindex(df['_rowid']).reset_index(drop=True)
    c = df['cur_course'].clip(1, 6).astype(int).values
    def pick(fmt):
        arr = np.full(len(df), np.nan)
        for k in range(1, 7):
            sel = c == k; arr[sel] = mk[fmt.format(k)].values[sel]
        return arr
    df['kb_c_top2'] = pick('c{}_top2_rate'); df['kb_c_avgst'] = pick('c{}_avg_st'); df['kb_c_entries'] = pick('c{}_entries')
    df['kb_c_p1'] = pick('c{}_p1') / df['kb_c_entries'].replace(0, np.nan)
    df['kb_ability'] = mk['ability'].values
    df['kb_c_top2_dm'] = diff_mean(df, 'kb_c_top2')
    F['kibetsu'] = ['kb_c_top2', 'kb_c_avgst', 'kb_c_entries', 'kb_c_p1', 'kb_ability', 'kb_c_top2_dm']
    tot = sum(mk[f'c{k}_entries'].fillna(0) for k in range(1, 7)).replace(0, np.nan)
    df['sol_course_familiar'] = df['kb_c_entries'] / tot.values

    # ===== gpt-6-sol 案 =====
    # (5) モーター近況: 同じ場の同じモーターの過去10走の (着順 - 期待着順)。期待着順は学習期間だけで作った (進入コース×級) の平均着順
    # v2: 期待着順は (進入コース×級) の平均着順を「その行の日付より前の日」のデータだけで逐次に作る
    df['_c_res'] = df['rs_course'].fillna(df['boat']).astype(float)
    srcp = df[df['place'].notna()]
    me = prior_cum(srcp, ['_c_res', 'rank'], ['place_f', 'has_res'], df, ['_c_res', 'rank'], 'ep')
    df['_resid'] = df['place_f'].values - (me['ep_place_f'] / me['ep_has_res']).values
    mr = prior_rolling(df, ['st', 'motor'], '_resid', 10, ['mean'], 'sol_motor')
    df['sol_motor_resid'] = mr['sol_motor_mean'].values
    # (4) 直近STのばらつき: 過去10走の本番ST の標準偏差・平均と出走表平均STとの差
    ms = prior_rolling(df, ['racer'], 'rs_st', 10, ['std', 'mean'], 'sol_st')
    df['sol_st_std'] = ms['sol_st_std'].values; df['sol_st_recent_minus_avg'] = ms['sol_st_mean'].values - df['avg_st']
    # (6) 前走からの日数・同日何走目（出走表で分かる）
    dd = df.sort_values(['racer', 'date', 'r'])
    prevdate = dd.groupby('racer')['date'].shift(1)
    sameday = prevdate == dd['date']
    lastprev = prevdate.where(~sameday)
    lastprev = lastprev.groupby([dd['racer'], dd['date']]).transform(lambda s: s.iloc[0])
    df['sol_days_since'] = (dd['date'] - lastprev).dt.days.reindex(df.index)
    df['sol_nth_today'] = (dd.groupby(['racer', 'date']).cumcount() + 1).reindex(df.index)
    # (7) 本人比の体重変化: 直前体重 - 過去10走の出走表体重の中央値
    mw = prior_rolling(df, ['racer'], 'weight', 10, ['median'], 'sol_w')
    df['sol_weight_delta'] = df['pv_weight'].fillna(df['weight']) - mw['sol_w_median'].values
    F['sol_motor'] = ['sol_motor_resid']; F['sol_st_var'] = ['sol_st_std', 'sol_st_recent_minus_avg']
    F['sol_interval'] = ['sol_days_since', 'sol_nth_today']; F['sol_weight'] = ['sol_weight_delta']
    F['sol_familiar'] = ['sol_course_familiar']
    return df, F
