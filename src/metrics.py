import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from datetime import timedelta


def compute_base_metrics(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['date_only'] = pd.to_datetime(df['record_date']).dt.date
    df['sku_per_minute'] = np.where(df['pick_minutes'] > 0, df['sku_count'] / df['pick_minutes'], 0)
    df['has_error'] = df['error_count'] > 0
    df['error_rate'] = np.where(df['sku_count'] > 0, df['error_count'] / df['sku_count'] * 100, 0)
    df['pick_bins'] = pd.cut(
        df['pick_minutes'],
        bins=[0, 15, 30, 45, 60, 90, 120, float('inf')],
        labels=['0-15分钟', '15-30分钟', '30-45分钟', '45-60分钟', '60-90分钟', '90-120分钟', '120分钟以上']
    )
    df['sku_bins'] = pd.cut(
        df['sku_count'],
        bins=[0, 20, 50, 100, 200, 500, float('inf')],
        labels=['0-20', '20-50', '50-100', '100-200', '200-500', '500以上']
    )
    df['wait_bins'] = pd.cut(
        df['pack_wait_minutes'],
        bins=[0, 10, 30, 60, 120, float('inf')],
        labels=['0-10分钟', '10-30分钟', '30-60分钟', '60-120分钟', '120分钟以上']
    )
    return df


def filter_dataframe(df: pd.DataFrame,
                     date_range: Tuple = None,
                     warehouse_areas: List[str] = None,
                     picker_names: List[str] = None,
                     sku_range: Tuple = None,
                     error_status: str = 'all',
                     wait_range: Tuple = None) -> pd.DataFrame:
    filtered = df.copy()
    if date_range and len(date_range) == 2:
        start_date, end_date = date_range
        if start_date:
            filtered = filtered[filtered['date_only'] >= pd.to_datetime(start_date).date()]
        if end_date:
            filtered = filtered[filtered['date_only'] <= pd.to_datetime(end_date).date()]
    if warehouse_areas and len(warehouse_areas) > 0:
        filtered = filtered[filtered['warehouse_area'].isin(warehouse_areas)]
    if picker_names and len(picker_names) > 0:
        filtered = filtered[filtered['picker_name'].isin(picker_names)]
    if sku_range and len(sku_range) == 2:
        min_sku, max_sku = sku_range
        filtered = filtered[(filtered['sku_count'] >= min_sku) & (filtered['sku_count'] <= max_sku)]
    if error_status == 'with_error':
        filtered = filtered[filtered['has_error']]
    elif error_status == 'no_error':
        filtered = filtered[~filtered['has_error']]
    if wait_range and len(wait_range) == 2:
        min_wait, max_wait = wait_range
        filtered = filtered[(filtered['pack_wait_minutes'] >= min_wait) & (filtered['pack_wait_minutes'] <= max_wait)]
    return filtered


def compute_overall_summary(df: pd.DataFrame) -> Dict:
    if len(df) == 0:
        return {'total_waves': 0, 'total_sku': 0, 'total_pick_minutes': 0,
                'avg_sku_per_min': 0, 'error_rate': 0, 'avg_wait': 0, 'anomalous_count': 0}
    return {
        'total_waves': len(df),
        'total_sku': int(df['sku_count'].sum()),
        'total_pick_minutes': round(df['pick_minutes'].sum(), 2),
        'avg_sku_per_min': round(df['sku_per_minute'].mean(), 3),
        'error_rate': round(df['error_rate'].mean(), 2),
        'avg_wait': round(df['pack_wait_minutes'].mean(), 2),
        'anomalous_count': int(df.get('_is_anomalous_wait', pd.Series([False])).sum()),
    }


def compute_pick_time_distribution(df: pd.DataFrame) -> pd.DataFrame:
    if len(df) == 0:
        return pd.DataFrame(columns=['pick_bins', 'count', 'percentage'])
    dist = df.groupby('pick_bins', observed=True).size().reset_index(name='count')
    dist['percentage'] = round(dist['count'] / dist['count'].sum() * 100, 2)
    return dist


def compute_error_stats(df: pd.DataFrame) -> Dict:
    if len(df) == 0:
        return {'with_error': 0, 'no_error': 0, 'error_rate_wave': 0}
    with_error = int(df['has_error'].sum())
    no_error = len(df) - with_error
    return {
        'with_error': with_error,
        'no_error': no_error,
        'error_rate_wave': round(with_error / len(df) * 100, 2),
    }


def compute_area_ranking(df: pd.DataFrame) -> pd.DataFrame:
    if len(df) == 0:
        return pd.DataFrame(columns=['warehouse_area', 'waves', 'total_sku', 'avg_sku_per_min',
                                     'error_rate', 'avg_wait', 'score'])
    grouped = df.groupby('warehouse_area').agg(
        waves=('warehouse_area', 'size'),
        total_sku=('sku_count', 'sum'),
        avg_sku_per_min=('sku_per_minute', 'mean'),
        error_rate=('error_rate', 'mean'),
        avg_wait=('pack_wait_minutes', 'mean'),
    ).reset_index()
    grouped['avg_sku_per_min'] = grouped['avg_sku_per_min'].round(3)
    grouped['error_rate'] = grouped['error_rate'].round(2)
    grouped['avg_wait'] = grouped['avg_wait'].round(2)
    max_eff = grouped['avg_sku_per_min'].max() if grouped['avg_sku_per_min'].max() > 0 else 1
    max_err = grouped['error_rate'].max() if grouped['error_rate'].max() > 0 else 1
    max_wait = grouped['avg_wait'].max() if grouped['avg_wait'].max() > 0 else 1
    grouped['score'] = (
        (grouped['avg_sku_per_min'] / max_eff) * 0.5
        + (1 - grouped['error_rate'] / max_err) * 0.3
        + (1 - grouped['avg_wait'] / max_wait) * 0.2
    ).round(3) * 100
    grouped = grouped.sort_values('score', ascending=False).reset_index(drop=True)
    grouped['rank'] = grouped.index + 1
    return grouped


def compute_picker_workload(df: pd.DataFrame) -> pd.DataFrame:
    if len(df) == 0:
        return pd.DataFrame(columns=['date_only', 'picker_name', 'waves', 'total_sku', 'total_minutes'])
    grouped = df.groupby(['date_only', 'picker_name']).agg(
        waves=('picker_name', 'size'),
        total_sku=('sku_count', 'sum'),
        total_minutes=('pick_minutes', 'sum'),
    ).reset_index()
    return grouped


def compute_pack_wait_trend(df: pd.DataFrame) -> pd.DataFrame:
    if len(df) == 0:
        return pd.DataFrame(columns=['date_only', 'avg_wait', 'max_wait', 'anomalous_count'])
    grouped = df.groupby('date_only').agg(
        avg_wait=('pack_wait_minutes', 'mean'),
        max_wait=('pack_wait_minutes', 'max'),
        anomalous_count=('_is_anomalous_wait', 'sum') if '_is_anomalous_wait' in df.columns else ('sku_count', lambda x: 0),
    ).reset_index()
    grouped['avg_wait'] = grouped['avg_wait'].round(2)
    grouped['max_wait'] = grouped['max_wait'].round(2)
    grouped['anomalous_count'] = grouped['anomalous_count'].astype(int)
    return grouped


def get_anomaly_details(df: pd.DataFrame) -> pd.DataFrame:
    cols = ['record_date', 'warehouse_area', 'picker_name', 'sku_count',
            'pick_minutes', 'error_count', 'pack_wait_minutes', 'note',
            '_is_anomalous_wait', '_is_duplicate_wave']
    available_cols = [c for c in cols if c in df.columns]
    anomaly_df = df[(df.get('_is_anomalous_wait', False)) | (df.get('_is_duplicate_wave', False))][available_cols].copy()
    anomaly_df = anomaly_df.rename(columns={
        '_is_anomalous_wait': '异常等待',
        '_is_duplicate_wave': '重复波次'
    })
    return anomaly_df


def get_sku_bins(df: pd.DataFrame) -> List[str]:
    if len(df) == 0:
        return []
    return sorted(df['sku_bins'].dropna().astype(str).unique().tolist())


def get_date_range(df: pd.DataFrame) -> Tuple:
    if len(df) == 0:
        return (None, None)
    dates = sorted(df['date_only'].unique())
    return (dates[0], dates[-1])


def compute_picker_diagnosis(df: pd.DataFrame) -> Dict:
    if len(df) == 0:
        return {'pickers': [], 'warnings': ['筛选后无数据，无法进行绩效诊断']}
    picker_stats = df.groupby('picker_name').agg(
        waves=('picker_name', 'size'),
        total_sku=('sku_count', 'sum'),
        avg_eff=('sku_per_minute', 'mean'),
        avg_error_rate=('error_rate', 'mean'),
        avg_wait=('pack_wait_minutes', 'mean'),
        total_error_count=('error_count', 'sum'),
    ).reset_index()
    picker_stats['avg_eff'] = picker_stats['avg_eff'].round(3)
    picker_stats['avg_error_rate'] = picker_stats['avg_error_rate'].round(2)
    picker_stats['avg_wait'] = picker_stats['avg_wait'].round(2)
    picker_stats['total_sku'] = picker_stats['total_sku'].astype(int)
    overall_eff = df['sku_per_minute'].mean()
    overall_error = df['error_rate'].mean()
    overall_wait = df['pack_wait_minutes'].mean()
    eff_q25 = picker_stats['avg_eff'].quantile(0.25) if len(picker_stats) >= 4 else overall_eff * 0.8
    error_q75 = picker_stats['avg_error_rate'].quantile(0.75) if len(picker_stats) >= 4 else overall_error * 1.3
    wait_q75 = picker_stats['avg_wait'].quantile(0.75) if len(picker_stats) >= 4 else overall_wait * 1.5
    wait_iqr_q3 = picker_stats['avg_wait'].quantile(0.75) if len(picker_stats) >= 4 else 30
    wait_iqr_q1 = picker_stats['avg_wait'].quantile(0.25) if len(picker_stats) >= 4 else 10
    wait_upper = wait_iqr_q3 + 1.5 * (wait_iqr_q3 - wait_iqr_q1)
    wait_threshold = max(wait_upper, 30)

    error_record_threshold = max(error_q75, 0.5) if overall_error > 0 else 0.5
    wait_record_threshold = max(wait_threshold, 30)
    eff_record_threshold = eff_q25

    labels_list = []
    for _, row in picker_stats.iterrows():
        labels = []
        if row['avg_eff'] >= picker_stats['avg_eff'].quantile(0.75):
            labels.append('表现优秀')
        if row['avg_eff'] < eff_q25 and row['waves'] >= 3:
            labels.append('效率偏低')
        if row['avg_error_rate'] > error_q75 and row['total_error_count'] >= 1:
            labels.append('差异偏高')
        if row['avg_wait'] > wait_threshold and row['waves'] >= 3:
            labels.append('等待异常')
        if not labels:
            labels.append('表现正常')
        labels_list.append(labels)
    picker_stats['labels'] = labels_list
    warnings = []
    if len(picker_stats) < 3:
        warnings.append(f'当前仅 {len(picker_stats)} 位拣货员，样本量过少，标签判定参考价值有限，建议扩大筛选范围')
    if len(picker_stats) >= 3 and picker_stats['waves'].max() < 5:
        warnings.append('所有拣货员波次数均不足 5 次，统计数据稳定性较差，建议增加日期范围')

    daily_trend = df.groupby(['date_only', 'picker_name']).agg(
        waves=('picker_name', 'size'),
        total_sku=('sku_count', 'sum'),
        avg_eff=('sku_per_minute', 'mean'),
        avg_error_rate=('error_rate', 'mean'),
        avg_wait=('pack_wait_minutes', 'mean'),
        total_error_count=('error_count', 'sum'),
    ).reset_index()
    daily_trend['avg_eff'] = daily_trend['avg_eff'].round(3)
    daily_trend['avg_error_rate'] = daily_trend['avg_error_rate'].round(2)
    daily_trend['avg_wait'] = daily_trend['avg_wait'].round(2)

    all_dates_sorted = sorted(df['date_only'].dropna().unique().tolist())
    recent_cutoff_date = None
    if all_dates_sorted:
        from datetime import timedelta
        latest_date = all_dates_sorted[-1]
        if hasattr(latest_date, 'to_pydatetime'):
            latest_date = latest_date.to_pydatetime().date() if hasattr(latest_date, 'to_pydatetime') else latest_date
        recent_cutoff_date = latest_date - timedelta(days=6)

    picker_records = []
    for _, row in picker_stats.iterrows():
        name = row['picker_name']
        person_daily = daily_trend[daily_trend['picker_name'] == name].copy()
        person_daily = person_daily.sort_values('date_only')

        if recent_cutoff_date is not None and len(person_daily) > 0:
            date_series = pd.to_datetime(person_daily['date_only']).dt.date
            person_daily_recent = person_daily[date_series >= recent_cutoff_date].copy()
            if len(person_daily_recent) == 0:
                person_daily_recent = person_daily.tail(7).copy()
        else:
            person_daily_recent = person_daily.tail(7).copy()

        person_daily_all = person_daily.copy()
        person_daily_recent_sorted = person_daily_recent.sort_values('date_only')

        person_df = df[df['picker_name'] == name].copy()
        anomaly_records_mask = pd.Series(False, index=person_df.index)
        if '_is_anomalous_wait' in person_df.columns:
            anomaly_records_mask = anomaly_records_mask | person_df['_is_anomalous_wait']
        if '_is_duplicate_wave' in person_df.columns:
            anomaly_records_mask = anomaly_records_mask | person_df['_is_duplicate_wave']
        anomaly_records_mask = anomaly_records_mask | (person_df['error_count'] >= 1)
        if '效率偏低' in row['labels']:
            anomaly_records_mask = anomaly_records_mask | (person_df['sku_per_minute'] < eff_record_threshold)
        if '等待异常' in row['labels']:
            anomaly_records_mask = anomaly_records_mask | (person_df['pack_wait_minutes'] >= wait_record_threshold)
        if '差异偏高' in row['labels']:
            anomaly_records_mask = anomaly_records_mask | (person_df['error_rate'] >= error_record_threshold)

        person_anomalies = person_df[anomaly_records_mask].copy()
        if len(person_anomalies) > 0 and len(person_anomalies) > 20:
            person_anomalies = person_anomalies.nlargest(20, ['error_count', 'pack_wait_minutes'])

        anomaly_list = []
        if len(person_anomalies) > 0:
            for _, ar in person_anomalies.iterrows():
                reasons = []
                if ar.get('_is_anomalous_wait', False):
                    reasons.append(f"异常等待({ar.get('pack_wait_minutes', 0):.1f}分)")
                if ar.get('_is_duplicate_wave', False):
                    reasons.append('重复波次')
                if ar.get('error_count', 0) >= 1:
                    reasons.append(f"差异{int(ar.get('error_count', 0))}件")
                if '效率偏低' in row['labels'] and ar.get('sku_per_minute', 0) < eff_record_threshold:
                    reasons.append(f"低效({ar.get('sku_per_minute', 0):.2f}SKU/分)")
                if '等待异常' in row['labels'] and not ar.get('_is_anomalous_wait', False) and ar.get('pack_wait_minutes', 0) >= wait_record_threshold:
                    reasons.append(f"等待过长({ar.get('pack_wait_minutes', 0):.1f}分)")
                if not reasons:
                    if ar.get('error_count', 0) >= 1:
                        reasons.append(f"差异{int(ar.get('error_count', 0))}件")
                    else:
                        continue
                anomaly_list.append({
                    'date': str(ar.get('date_only', '')),
                    'area': str(ar.get('warehouse_area', '')),
                    'sku_count': int(ar.get('sku_count', 0)),
                    'pick_minutes': float(ar.get('pick_minutes', 0)),
                    'error_count': int(ar.get('error_count', 0)),
                    'pack_wait_minutes': float(ar.get('pack_wait_minutes', 0)),
                    'note': str(ar.get('note', '')),
                    'reasons': '、'.join(reasons),
                })

        if len(anomaly_list) == 0 and any(l in row['labels'] for l in ['效率偏低', '差异偏高', '等待异常']):
            top_low = person_df.nsmallest(3, 'sku_per_minute')
            for _, ar in top_low.iterrows():
                reasons = []
                if ar.get('sku_per_minute', 0) < eff_record_threshold:
                    reasons.append(f"低效({ar.get('sku_per_minute', 0):.2f}SKU/分)")
                if reasons:
                    anomaly_list.append({
                        'date': str(ar.get('date_only', '')),
                        'area': str(ar.get('warehouse_area', '')),
                        'sku_count': int(ar.get('sku_count', 0)),
                        'pick_minutes': float(ar.get('pick_minutes', 0)),
                        'error_count': int(ar.get('error_count', 0)),
                        'pack_wait_minutes': float(ar.get('pack_wait_minutes', 0)),
                        'note': str(ar.get('note', '')),
                        'reasons': '、'.join(reasons),
                    })

        picker_records.append({
            'picker_name': name,
            'waves': int(row['waves']),
            'total_sku': int(row['total_sku']),
            'avg_eff': float(row['avg_eff']),
            'avg_error_rate': float(row['avg_error_rate']),
            'avg_wait': float(row['avg_wait']),
            'total_error_count': int(row['total_error_count']),
            'labels': row['labels'],
            'daily_trend': person_daily_recent_sorted[['date_only', 'waves', 'total_sku', 'avg_eff', 'avg_error_rate', 'avg_wait']].to_dict('records'),
            'daily_trend_all': person_daily_all[['date_only', 'waves', 'total_sku', 'avg_eff', 'avg_error_rate', 'avg_wait']].to_dict('records'),
            'anomaly_details': anomaly_list,
        })
    return {
        'pickers': picker_records,
        'warnings': warnings,
        'thresholds': {
            'eff_low': round(float(eff_q25), 3),
            'error_high': round(float(error_q75), 2),
            'wait_abnormal': round(float(wait_threshold), 2),
        },
    }


def generate_picker_improvement_suggestions(diagnosis: Dict) -> List[Dict]:
    suggestions = []
    if not diagnosis or not diagnosis.get('pickers'):
        return suggestions
    for p in diagnosis['pickers']:
        labels = p.get('labels', [])
        if '表现正常' in labels or '表现优秀' in labels:
            continue
        reasons = []
        advice = []
        thresholds = diagnosis.get('thresholds', {})
        if '效率偏低' in labels:
            reasons.append(f"效率 {p['avg_eff']:.2f} SKU/分（低于阈值 {thresholds.get('eff_low', 0):.2f}）")
            advice.append('建议观察其波次SKU构成是否偏大或仓区路径偏长，安排老带新跟班指导')
        if '差异偏高' in labels:
            reasons.append(f"差异率 {p['avg_error_rate']:.2f}%（高于阈值 {thresholds.get('error_high', 0):.2f}%），累计差异 {p['total_error_count']} 件")
            advice.append('建议安排复核辅助或技能再培训，关注易错SKU拣货规范')
        if '等待异常' in labels:
            reasons.append(f"包装等待 {p['avg_wait']:.1f} 分（高于阈值 {thresholds.get('wait_abnormal', 0):.1f} 分）")
            advice.append('建议检查其波次释放时序与包装工位配合，优化交接流程')
        if reasons:
            suggestions.append({
                'picker': p['picker_name'],
                'labels': labels,
                'reason': '；'.join(reasons),
                'advice': '；'.join(advice),
            })
    suggestions.sort(key=lambda x: len(x['labels']), reverse=True)
    return suggestions


def get_filter_options(df: pd.DataFrame) -> Dict:
    return {
        'warehouse_areas': sorted(df['warehouse_area'].dropna().astype(str).unique().tolist()),
        'picker_names': sorted(df['picker_name'].dropna().astype(str).unique().tolist()),
        'sku_min': int(df['sku_count'].min()) if len(df) > 0 else 0,
        'sku_max': int(df['sku_count'].max()) if len(df) > 0 else 1000,
        'wait_min': float(df['pack_wait_minutes'].min()) if len(df) > 0 else 0,
        'wait_max': float(df['pack_wait_minutes'].max()) if len(df) > 0 else 500,
        'date_range': get_date_range(df),
    }
