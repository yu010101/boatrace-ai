# v4（越境TTP）: 1. スピード指数（Beyer の移植）  2. 選手の強さの点数（TrueSkill の移植）。土台は features_v3.build3。
# どちらも「その日より前」の結果（強さ）／「そのレースより前」の展示（当日バリアント）だけを使う。
import numpy as np, pandas as pd, trueskill
from features_v3 import build3
from features import diff_mean


def add_speed(df, F):
    """展示タイム − パータイム（場ごと・その日より前60日の日別中央値の中央値）− 当日バリアント（同じ場・同じ日のそのレースより前のレースの平均のずれ）"""
    ex = df[df['pv_ex_time'].notna()]
    daily = ex.groupby(['st', 'date'])['pv_ex_time'].median().reset_index().sort_values(['st', 'date'])
    par = []
    for s, g in daily.groupby('st'):
        ser = g.set_index('date')['pv_ex_time']
        p = ser.rolling('60D', closed='left', min_periods=3).median()   # closed='left' で当日を含めない
        par.append(pd.DataFrame({'st': s, 'date': p.index, 'sp_par': p.values}))
    par = pd.concat(par)
    df = df.merge(par, on=['st', 'date'], how='left')
    df['sp_ex_vs_par'] = df['pv_ex_time'] - df['sp_par']
    e = df[df['sp_ex_vs_par'].notna()]
    gr = e.groupby(['st', 'date', 'r'])['sp_ex_vs_par'].agg(['sum', 'count']).reset_index().sort_values(['st', 'date', 'r'])
    cs = gr.groupby(['st', 'date'])[['sum', 'count']].cumsum()
    gr['_s'] = cs['sum'] - gr['sum']; gr['_c'] = cs['count'] - gr['count']   # そのレースより前のレースだけ
    df = df.merge(gr[['st', 'date', 'r', '_s', '_c']], on=['st', 'date', 'r'], how='left')
    df['sp_day_var_n'] = df['_c'].fillna(0)
    df['sp_day_var'] = np.where(df['sp_day_var_n'] >= 6, df['_s'] / df['_c'].replace(0, np.nan), np.nan)
    df['sp_fig'] = df['sp_ex_vs_par'] - np.nan_to_num(df['sp_day_var'])
    df['sp_fig_rank'] = df.groupby('race_id')['sp_fig'].rank()
    df['sp_fig_dm'] = diff_mean(df, 'sp_fig')
    df = df.drop(columns=['_s', '_c'])
    F['t1_speed'] = ['sp_ex_vs_par', 'sp_day_var', 'sp_day_var_n', 'sp_fig', 'sp_fig_rank', 'sp_fig_dm']
    return df


def _trueskill(df, key_upd, key_look, prefix):
    """日ごとに: その日の各行に「前日までの」μ・σ・件数を付ける → その日のレースの着順で更新。着順コード7以上は最下位タイ扱い。"""
    env = trueskill.TrueSkill(mu=25.0, sigma=25.0 / 3, beta=25.0 / 6, tau=25.0 / 300, draw_probability=0.01)
    R, N = {}, {}
    mu = np.full(len(df), np.nan); sg = np.full(len(df), np.nan); nn = np.zeros(len(df))
    d = df[['date', 'race_id', 'r', 'st', 'place'] + list(dict.fromkeys(key_upd + key_look))].copy()
    d['_i'] = np.arange(len(df))
    d = d.sort_values(['date', 'st', 'r'])
    ku = list(zip(*[d[k].values for k in key_upd])); kl = list(zip(*[d[k].values for k in key_look]))
    d['_ku'] = ku; d['_kl'] = kl
    for D, g in d.groupby('date', sort=True):
        for i, k in zip(g['_i'].values, g['_kl'].values):   # 前日までの値（当日の更新より前）
            r = R.get(k)
            if r is None: mu[i], sg[i] = env.mu, env.sigma
            else: mu[i], sg[i] = r.mu, r.sigma
            nn[i] = N.get(k, 0)
        for rid, gg in g.groupby('race_id', sort=False):
            gg = gg[gg['place'].notna()]
            if len(gg) < 2: continue
            keys = list(gg['_ku'].values); ranks = list(np.clip(gg['place'].values, 1, 6).astype(int))
            new = env.rate([(R.get(k, env.create_rating()),) for k in keys], ranks=ranks)
            for k, (nr,) in zip(keys, new):
                R[k] = nr; N[k] = N.get(k, 0) + 1
    df[f'{prefix}_mu'] = mu; df[f'{prefix}_sigma'] = sg; df[f'{prefix}_n'] = nn
    df[f'{prefix}_cons'] = df[f'{prefix}_mu'] - 3 * df[f'{prefix}_sigma']
    df[f'{prefix}_rank'] = df.groupby('race_id')[f'{prefix}_mu'].rank(ascending=False)
    df[f'{prefix}_gap_best'] = df[f'{prefix}_mu'] - df.groupby('race_id')[f'{prefix}_mu'].transform('max')
    df[f'{prefix}_dm'] = diff_mean(df, f'{prefix}_mu')
    return [f'{prefix}_{s}' for s in ['mu', 'sigma', 'n', 'cons', 'rank', 'gap_best', 'dm']]


def build4(raw, kib):
    df, F = build3(raw, kib)
    df = df.reset_index(drop=True)
    df = add_speed(df, F)
    df['_c_upd'] = df['rs_course'].fillna(df['boat']).astype(float)
    df['_c_look'] = df['cur_course'].astype(float)
    F['t2_ts'] = _trueskill(df, ['racer'], ['racer'], 'ts')
    F['t2_tsc'] = _trueskill(df, ['racer', '_c_upd'], ['racer', '_c_look'], 'tsc')
    return df, F
