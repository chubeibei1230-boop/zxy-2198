import io
import base64
import pandas as pd
from typing import Dict, List, Tuple, Optional

STANDARD_COLUMNS = {
    'record_date': 'record_date',
    'warehouse_area': 'warehouse_area',
    'picker_name': 'picker_name',
    'sku_count': 'sku_count',
    'pick_minutes': 'pick_minutes',
    'error_count': 'error_count',
    'pack_wait_minutes': 'pack_wait_minutes',
    'note': 'note',
}

COLUMN_ALIASES = {
    'record_date': ['日期', '记录日期', 'date', 'datetime', '时间', 'wave_date', '波次日期'],
    'warehouse_area': ['区域', '仓区', '库区', 'area', 'zone', 'storage_area', '拣货区域'],
    'picker_name': ['拣货员', '拣货人员', '人员', '姓名', 'picker', 'operator', 'staff', 'name'],
    'sku_count': ['SKU数', 'sku数量', '商品数', '品种数', 'sku_total', 'items', 'qty', '数量'],
    'pick_minutes': ['拣货耗时', '拣货时长', '拣货时间', '耗时', '时长', 'pick_time', 'pick_duration', 'minutes'],
    'error_count': ['差异数', '差异数量', '错误数', '差错数', 'errors', 'difference', 'diff_count', '异常数'],
    'pack_wait_minutes': ['包装等待', '等待时长', '等待时间', '包装等待时长', 'wait_time', 'waiting', 'pack_wait', '等待分钟'],
    'note': ['备注', '说明', '波次号', '波次编号', 'wave_no', 'wave_id', 'remark', 'comment', '波次'],
}

DATE_FORMATS = [
    '%Y-%m-%d', '%Y/%m/%d', '%d-%m-%Y', '%d/%m/%Y',
    '%Y-%m-%d %H:%M:%S', '%Y/%m/%d %H:%M:%S',
    '%Y年%m月%d日', '%Y.%m.%d', '%m/%d/%Y',
]


def parse_csv_from_contents(contents: str, filename: str = '') -> Tuple[Optional[pd.DataFrame], str]:
    if contents is None:
        return None, '未上传文件'
    try:
        content_type, content_string = contents.split(',')
        decoded = base64.b64decode(content_string)
        if filename.endswith('.xlsx') or filename.endswith('.xls'):
            df = pd.read_excel(io.BytesIO(decoded))
        else:
            df = pd.read_csv(io.BytesIO(decoded))
        return df, f'成功读取 {len(df)} 行数据'
    except Exception as e:
        return None, f'文件解析失败: {str(e)}'


def suggest_column_mapping(df_columns: List[str]) -> Dict[str, str]:
    mapping = {}
    used_cols = set()
    for std_col in STANDARD_COLUMNS:
        for col in df_columns:
            if col in used_cols:
                continue
            if col.lower() == std_col.lower():
                mapping[col] = std_col
                used_cols.add(col)
                break
        if std_col in mapping.values():
            continue
        for alias in COLUMN_ALIASES.get(std_col, []):
            alias_lower = alias.lower()
            for col in df_columns:
                if col in used_cols:
                    continue
                if alias_lower in col.lower() or col.lower() in alias_lower:
                    mapping[col] = std_col
                    used_cols.add(col)
                    break
            if std_col in mapping.values():
                break
    return mapping


def apply_column_mapping(df: pd.DataFrame, mapping: Dict[str, str]) -> pd.DataFrame:
    reverse_map = {v: k for k, v in mapping.items()}
    result = pd.DataFrame()
    for std_col in STANDARD_COLUMNS:
        if std_col in reverse_map and reverse_map[std_col] in df.columns:
            result[std_col] = df[reverse_map[std_col]]
        else:
            if std_col == 'note':
                result[std_col] = ''
            elif std_col == 'error_count' or std_col == 'pack_wait_minutes':
                result[std_col] = 0
            else:
                result[std_col] = None
    return result


def try_parse_date(date_str) -> Tuple[Optional[pd.Timestamp], Optional[str]]:
    if pd.isna(date_str) or date_str == '':
        return None, '日期为空'
    if isinstance(date_str, (pd.Timestamp, pd.DatetimeTZDtype)):
        return pd.Timestamp(date_str), None
    date_str = str(date_str).strip()
    for fmt in DATE_FORMATS:
        try:
            ts = pd.to_datetime(date_str, format=fmt)
            return ts, None
        except (ValueError, TypeError):
            continue
    try:
        ts = pd.to_datetime(date_str, errors='coerce')
        if not pd.isna(ts):
            return ts, None
    except Exception:
        pass
    return None, f'无法解析日期格式: {date_str}'


def get_date_format_hint() -> str:
    hints = [
        '支持以下日期格式示例:',
        '  • 2024-01-15 或 2024/01/15',
        '  • 15-01-2024 或 15/01/2024',
        '  • 2024-01-15 14:30:00',
        '  • 2024年1月15日',
        '  • 2024.01.15',
    ]
    return '\n'.join(hints)


def parse_all_dates(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    messages = []
    parsed_dates = []
    date_errors = 0
    for idx, val in enumerate(df['record_date']):
        ts, err = try_parse_date(val)
        if err and ts is None:
            date_errors += 1
            parsed_dates.append(pd.NaT)
        else:
            parsed_dates.append(ts)
    df['record_date'] = parsed_dates
    valid_count = df['record_date'].notna().sum()
    messages.append(f'日期解析: 成功 {valid_count} 条')
    if date_errors > 0:
        messages.append(f'警告: {date_errors} 条日期无法解析，已标记为空')
    return df, messages
