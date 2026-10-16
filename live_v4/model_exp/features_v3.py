# v3 の追加特徴量（第2段の 3・4・5）。土台は features.build（v2・逐次の表）。すべて当日より前の結果だけを使う。
import numpy as np, pandas as pd
from features import build, prior_cum, diff_mean


def _rate(num, den, prior, k):
    return (np.nan_to_num(num) + k * prior) / (np.nan_to_num(den) + k)


def build3(raw, kib):
    df, F = build(raw, kib)
    src = df[df['place'].notna()].copy()
    src['_n'] = 1.0
    src['_sashi'] = (src['win'] == 1) & (src['technique'] == 2)
    src['_makuri'] = (src['win'] == 1) & src['technique'].isin([3, 4])
    src[['_sashi', '_makuri']] = src[['_sashi', '_makuri']].astype(float)

    # ---- 3. 1号艇と攻め艇の対戦変数 ----
    # 全体（全選手）のコース別の率（前日まで）を事前値にして、選手×コースの率を縮約（k=20）
    g = prior_cum(src, ['_c_res'], ['_n', 'win', '_sashi', '_makuri'], df, ['cur_course'], 'muG')
    r = prior_cum(src, ['racer', '_c_res'], ['_n', 'win', '_sashi', '_makuri'], df, ['racer', 'cur_course'], 'muR')
    K = 20.0
    for v in ['win', '_sashi', '_makuri']:
        pg = (g[f'muG_{v}'] / g['muG__n']).values
        df[f'mu_{v.strip("_")}'] = _rate(r[f'muR_{v}'].values, r['muR__n'].values, np.nan_to_num(pg, nan=1 / 6), K)
    cc = df['cur_course'].values
    df['mu_attack'] = np.where(cc == 1, df['mu_win'], np.where(cc == 2, df['mu_sashi'], df['mu_makuri']))
    def race_pick(col, course):
        s = df[col].where(df['cur_course'] == course)
        return s.groupby(df['race_id']).transform('max')
    esc1 = race_pick('mu_win', 1)
    df['mu_esc1'] = esc1
    df['mu_esc1_m_sashi2'] = esc1 - race_pick('mu_sashi', 2)
    df['mu_esc1_m_makuri3'] = esc1 - race_pick('mu_makuri', 3)
    df['mu_attack_m_esc1'] = df['mu_attack'] - esc1
    # 隣（内側）の艇との展示ST差、1号艇（1コース）と最速艇の展示タイム差
    o = df.sort_values(['race_id', 'cur_course'])
    df['exst_minus_inner'] = (o['pv_st'] - o.groupby('race_id')['pv_st'].shift(1)).reindex(df.index)
    ex1 = df['pv_ex_time'].where(df['cur_course'] == 1).groupby(df['race_id']).transform('max')
    df['ex1_minus_best'] = ex1 - df.groupby('race_id')['pv_ex_time'].transform('min')
    F['s3_matchup'] = ['mu_esc1', 'mu_esc1_m_sashi2', 'mu_esc1_m_makuri3', 'mu_attack', 'mu_attack_m_esc1',
                       'exst_minus_inner', 'ex1_minus_best']

    # ---- 4. 展示タイムを場×日の中で標準化。同じ日のそのレースまで（R番号が自分以下）の展示だけを使う ----
    e = df[df['pv_ex_time'].notna()].assign(_x=lambda x: x['pv_ex_time'], _xx=lambda x: x['pv_ex_time'] ** 2, _c=1.0)
    gr = e.groupby(['st', 'date', 'r'])[['_x', '_xx', '_c']].sum().reset_index().sort_values(['st', 'date', 'r'])
    gr[['_x', '_xx', '_c']] = gr.groupby(['st', 'date'])[['_x', '_xx', '_c']].cumsum()
    m = df[['st', 'date', 'r']].merge(gr, on=['st', 'date', 'r'], how='left')
    mu = m['_x'] / m['_c']; sd = np.sqrt(np.clip(m['_xx'] / m['_c'] - mu ** 2, 1e-6, None))
    df['ex_z_day'] = ((df['pv_ex_time'].values - mu.values) / sd.values)
    df.loc[m['_c'].values < 12, 'ex_z_day'] = np.nan   # 2レース分（12艇）未満は不安定なので空
    df['ex_z_day_dm'] = diff_mean(df, 'ex_z_day')
    F['s4_exz'] = ['ex_z_day', 'ex_z_day_dm']

    # ---- 5. 少数の成績の縮約（選手×コース・選手×場・モーター）＋件数と経過日数 ----
    gc = prior_cum(src, ['_c_res'], ['_n', 'win', 'top2'], df, ['cur_course'], 'shG')
    ra = prior_cum(src, ['racer'], ['_n', 'win', 'top2'], df, ['racer'], 'shA')
    rc = prior_cum(src, ['racer', '_c_res'], ['_n', 'win', 'top2'], df, ['racer', 'cur_course'], 'shC')
    rs = prior_cum(src, ['racer', 'st'], ['_n', 'win', 'top2'], df, ['racer', 'st'], 'shS')
    mo = prior_cum(src, ['st', 'motor'], ['_n', 'win', 'top2'], df, ['st', 'motor'], 'shM')
    pall_w = _rate(ra['shA_win'].values, ra['shA__n'].values, 1 / 6, K)
    pall_t = _rate(ra['shA_top2'].values, ra['shA__n'].values, 1 / 3, K)
    pc_w = np.nan_to_num((gc['shG_win'] / gc['shG__n']).values, nan=1 / 6)
    df['sh_rc_win'] = _rate(rc['shC_win'].values, rc['shC__n'].values, pc_w, K)
    df['sh_rs_win'] = _rate(rs['shS_win'].values, rs['shS__n'].values, pall_w, K)
    df['sh_rs_top2'] = _rate(rs['shS_top2'].values, rs['shS__n'].values, pall_t, K)
    df['sh_mo_win'] = _rate(mo['shM_win'].values, mo['shM__n'].values, 1 / 6, 50.0)
    df['sh_mo_top2'] = _rate(mo['shM_top2'].values, mo['shM__n'].values, 1 / 3, 50.0)
    for nm, mm, p in [('rc', rc, 'shC'), ('rs', rs, 'shS'), ('mo', mo, 'shM')]:
        df[f'sh_{nm}_n'] = mm[f'{p}__n'].values
        df[f'sh_{nm}_days'] = (df['date'].values - mm[f'{p}_srcdate'].values) / np.timedelta64(1, 'D')
    df['sh_rc_win_dm'] = diff_mean(df, 'sh_rc_win'); df['sh_mo_top2_dm'] = diff_mean(df, 'sh_mo_top2')
    F['s5_shrink'] = ['sh_rc_win', 'sh_rs_win', 'sh_rs_top2', 'sh_mo_win', 'sh_mo_top2', 'sh_rc_n', 'sh_rs_n', 'sh_mo_n',
                      'sh_rc_days', 'sh_rs_days', 'sh_mo_days', 'sh_rc_win_dm', 'sh_mo_top2_dm']

    # ---- 上限実験用（結果側。漏れを承知・採用しない） ----
    df['LEAK_rs_course'] = df['rs_course']; df['LEAK_rs_st'] = df['rs_st']
    df['LEAK_rs_st_rank'] = df.groupby('race_id')['rs_st'].rank()
    F['LEAK_upper'] = ['LEAK_rs_course', 'LEAK_rs_st', 'LEAK_rs_st_rank']

    # ---- 開催ID（同じ場・同じ節＝同じ題名で日付が続く）: ブロック再標本化の単位 ----
    u = df[['st', 'date', 'title']].drop_duplicates().sort_values(['st', 'date'])
    gap = u.groupby('st')['date'].diff().dt.days
    new = gap.isna() | (gap > 1) | (u['title'] != u.groupby('st')['title'].shift(1))
    u['meeting'] = new.astype(int).groupby(u['st']).cumsum()
    u['meeting_id'] = u['st'].astype(str) + '_' + u['meeting'].astype(str)
    df = df.merge(u[['st', 'date', 'title', 'meeting_id']], on=['st', 'date', 'title'], how='left')
    return df, F
