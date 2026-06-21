import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from collections import Counter

NUMERIC_COLUMNS = ['sku_count', 'pick_minutes', 'error_count', 'pack_wait_minutes']


def clean_numeric_value(val):
    if pd.isna(val):
        return np.nan
    if isinstance(val, (int, float, np.integer, np.floating)):
        return float(val)
    s = str(val).strip()
    if s == '' or s == '-' or s.lower() == 'nan' or s.lower() == 'null':
        return np.nan
    s = s.replace(',', '').replace('，', '')
    for unit in ['分钟', 'min', 'mins', '小时', 'h', '件', '个', '条']:
        if s.endswith(unit):
            s = s[:-len(unit)]
            break
    try:
        return float(s)
    except ValueError:
        return np.nan


def clean_numeric_columns(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    messages = []
    for col in NUMERIC_COLUMNS:
        if col in df.columns:
            original_vals = df[col].copy()
            df[col] = df[col].apply(clean_numeric_value)
            na_count = df[col].isna().sum()
            if na_count > 0:
                messages.append(f'字段 {col}: {na_count} 条非数值数据已转为空值')
                df[col] = df[col].fillna(0)
            neg_count = (df[col] < 0).sum()
            if neg_count > 0:
                messages.append(f'字段 {col}: {neg_count} 条负数已修正为 0')
                df.loc[df[col] < 0, col] = 0
            if col in ['sku_count', 'error_count']:
                df[col] = df[col].round().astype(int)
            else:
                df[col] = df[col].round(2)
            valid = original_vals.notna().sum()
            messages.append(f'字段 {col}: 已清洗 {valid} 条数据，范围 [{df[col].min()}, {df[col].max()}]')
    return df, messages


def check_duplicate_waves(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str], List[int]]:
    messages = []
    df['_wave_key'] = df.apply(
        lambda r: f"{r.get('record_date', '')}|{r.get('warehouse_area', '')}|{r.get('note', '')}",
        axis=1
    )
    key_counts = Counter(df['_wave_key'].tolist())
    duplicate_indices = []
    dup_keys = [k for k, c in key_counts.items() if c > 1 and k != '||']
    if dup_keys:
        for idx, row in df.iterrows():
            if row['_wave_key'] in dup_keys:
                duplicate_indices.append(idx)
        messages.append(f'检测到 {len(dup_keys)} 个重复波次组合，共涉及 {len(duplicate_indices)} 条记录')
        df['_is_duplicate_wave'] = df.index.isin(duplicate_indices)
    else:
        df['_is_duplicate_wave'] = False
        messages.append('未检测到重复波次')
    df = df.drop(columns=['_wave_key'])
    return df, messages, duplicate_indices


def identify_anomalous_waits(df: pd.DataFrame,
                              wait_col: str = 'pack_wait_minutes',
                              threshold_method: str = 'iqr') -> Tuple[pd.DataFrame, List[str]]:
    messages = []
    if wait_col not in df.columns:
        return df, ['包装等待列不存在，跳过异常识别']
    wait_data = df[wait_col].dropna()
    if len(wait_data) == 0:
        return df, ['包装等待数据为空，跳过异常识别']
    if threshold_method == 'iqr':
        q1 = wait_data.quantile(0.25)
        q3 = wait_data.quantile(0.75)
        iqr = q3 - q1
        upper_bound = q3 + 1.5 * iqr
        threshold = max(upper_bound, 30)
    else:
        mean = wait_data.mean()
        std = wait_data.std()
        threshold = max(mean + 2 * std, 30)
    anomalous_mask = df[wait_col] > threshold
    anomalous_count = anomalous_mask.sum()
    df['_is_anomalous_wait'] = anomalous_mask
    df['_wait_threshold'] = round(threshold, 2)
    if anomalous_count > 0:
        messages.append(
            f'异常等待识别: 阈值={round(threshold, 2)}分钟，共 {anomalous_count} 条异常记录'
        )
    else:
        messages.append(f'异常等待识别: 阈值={round(threshold, 2)}分钟，未发现异常等待')
    return df, messages


def validate_required_fields(df: pd.DataFrame) -> Tuple[bool, List[str]]:
    messages = []
    is_valid = True
    required = ['record_date', 'warehouse_area', 'picker_name', 'sku_count', 'pick_minutes']
    for col in required:
        if col not in df.columns:
            messages.append(f'缺失必需字段: {col}')
            is_valid = False
            continue
        na_count = df[col].isna().sum()
        if col == 'record_date':
            na_count = df[col].isna().sum()
        if na_count == len(df):
            messages.append(f'字段 {col}: 所有数据为空，请检查列名映射')
            is_valid = False
        elif na_count > 0:
            messages.append(f'字段 {col}: {na_count} 条数据为空')
    if 'warehouse_area' in df.columns:
        df['warehouse_area'] = df['warehouse_area'].fillna('未分配').astype(str).str.strip()
    if 'picker_name' in df.columns:
        df['picker_name'] = df['picker_name'].fillna('未知').astype(str).str.strip()
    if 'note' in df.columns:
        df['note'] = df['note'].fillna('').astype(str).str.strip()
    return is_valid, messages


def run_full_validation(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict]:
    all_messages = {}
    is_valid, req_msgs = validate_required_fields(df)
    all_messages['required_fields'] = req_msgs
    df, num_msgs = clean_numeric_columns(df)
    all_messages['numeric_clean'] = num_msgs
    df, dup_msgs, dup_indices = check_duplicate_waves(df)
    all_messages['duplicate_check'] = dup_msgs
    all_messages['duplicate_indices'] = dup_indices
    df, anom_msgs = identify_anomalous_waits(df)
    all_messages['anomaly_wait'] = anom_msgs
    valid_rows = df['record_date'].notna() & df['sku_count'].notna() & (df['sku_count'] > 0)
    df_valid = df[valid_rows].copy()
    excluded = len(df) - len(df_valid)
    all_messages['summary'] = [
        f'原始数据: {len(df)} 行',
        f'有效数据: {len(df_valid)} 行',
        f'排除无效: {excluded} 行（无日期或 SKU 数为 0）',
    ]
    return df_valid, all_messages
