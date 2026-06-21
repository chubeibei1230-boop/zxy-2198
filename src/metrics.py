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
