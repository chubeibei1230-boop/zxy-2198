import pandas as pd
import numpy as np
from typing import List, Dict, Tuple
from datetime import datetime, timedelta


def _get_recent_days_data(df: pd.DataFrame, days: int = 7) -> pd.DataFrame:
    if len(df) == 0:
        return df
    df = df.copy()
    if 'date_only' not in df.columns:
        df['date_only'] = pd.to_datetime(df['record_date']).dt.date
    if df['date_only'].isna().all():
        return df
    max_date = df['date_only'].max()
    if pd.isna(max_date):
        return df
    cutoff = max_date - timedelta(days=days)
    return df[df['date_only'] >= cutoff].copy()


def analyze_path_optimization(df: pd.DataFrame,
                               overall_avg_eff: float,
                               overall_avg_error: float) -> List[Dict]:
    suggestions = []
    if len(df) == 0:
        return suggestions
    recent = _get_recent_days_data(df, days=7)
    if len(recent) == 0:
        recent = df
    grouped = recent.groupby('warehouse_area').agg(
        waves=('warehouse_area', 'size'),
        avg_eff=('sku_per_minute', 'mean'),
        avg_error=('error_rate', 'mean'),
        avg_pick_time=('pick_minutes', 'mean'),
        avg_wait=('pack_wait_minutes', 'mean'),
    ).reset_index()
    eff_threshold = max(overall_avg_eff * 0.8, 0.5)
    error_threshold = max(overall_avg_error * 1.2, 1.0)
    for _, row in grouped.iterrows():
        reasons = []
        if row['waves'] < 5:
            continue
        if row['avg_eff'] < eff_threshold:
            reasons.append(f"效率偏低 ({row['avg_eff']:.2f} SKU/分，低于整体 {overall_avg_eff:.2f})")
        if row['avg_error'] > error_threshold:
            reasons.append(f"差异率偏高 ({row['avg_error']:.2f}%，高于整体 {overall_avg_error:.2f}%)")
        if row['avg_wait'] > 30:
            reasons.append(f"包装等待较长 (平均 {row['avg_wait']:.1f} 分钟)")
        if len(reasons) >= 1:
            priority = '高' if len(reasons) >= 2 else '中'
            suggestions.append({
                'type': 'path',
                'target': f"仓区: {row['warehouse_area']}",
                'reason': '；'.join(reasons),
                'suggestion': f"建议评估「{row['warehouse_area']}」仓区拣货路径，优化SKU储位布局，减少拣货员行走距离",
                'priority': priority,
            })
    suggestions.sort(key=lambda x: {'高': 0, '中': 1, '低': 2}.get(x['priority'], 3))
    return suggestions


def analyze_review_assistance(df: pd.DataFrame,
                               overall_avg_error: float) -> List[Dict]:
    suggestions = []
    if len(df) == 0:
        return suggestions
    recent = _get_recent_days_data(df, days=7)
    if len(recent) == 0:
        recent = df
    grouped = recent.groupby('picker_name').agg(
        waves=('picker_name', 'size'),
        total_errors=('error_count', 'sum'),
        avg_error=('error_rate', 'mean'),
        total_sku=('sku_count', 'sum'),
    ).reset_index()
    error_threshold = max(overall_avg_error * 1.3, 1.5)
    for _, row in grouped.iterrows():
        reasons = []
        if row['waves'] < 10:
            continue
        if row['avg_error'] > error_threshold and row['total_errors'] >= 3:
            reasons.append(
                f"差异率 {row['avg_error']:.2f}% （高于阈值 {error_threshold:.2f}%），累计差异 {row['total_errors']} 件"
            )
        if reasons:
            priority = '高' if row['avg_error'] > error_threshold * 1.5 else '中'
            suggestions.append({
                'type': 'assist',
                'target': f"拣货员: {row['picker_name']}",
                'reason': '；'.join(reasons),
                'suggestion': f"建议为「{row['picker_name']}」安排复核辅助或技能再培训，关注易错SKU的拣货规范",
                'priority': priority,
            })
    suggestions.sort(key=lambda x: -sum(1 for r in x['reason'].split('；')))
    return suggestions


def analyze_wave_splitting(df: pd.DataFrame) -> List[Dict]:
    suggestions = []
    if len(df) == 0:
        return suggestions
    recent = _get_recent_days_data(df, days=7)
    if len(recent) == 0:
        recent = df
    sku_75 = recent['sku_count'].quantile(0.75) if len(recent) > 10 else 100
    time_75 = recent['pick_minutes'].quantile(0.75) if len(recent) > 10 else 60
    wait_75 = recent['pack_wait_minutes'].quantile(0.75) if len(recent) > 10 else 30
    large_waves = recent[
        (recent['sku_count'] >= sku_75)
        & (recent['pick_minutes'] >= time_75)
    ].copy()
    if len(large_waves) == 0:
        return suggestions
    area_large = large_waves.groupby('warehouse_area').agg(
        large_count=('warehouse_area', 'size'),
        avg_sku=('sku_count', 'mean'),
        avg_time=('pick_minutes', 'mean'),
        avg_wait=('pack_wait_minutes', 'mean'),
    ).reset_index()
    total_by_area = recent.groupby('warehouse_area').size().to_dict()
    for _, row in area_large.iterrows():
        total = total_by_area.get(row['warehouse_area'], 1)
        ratio = row['large_count'] / total if total > 0 else 0
        reasons = []
        if ratio >= 0.15 and row['large_count'] >= 3:
            reasons.append(
                f"该仓区 {row['large_count']} 个大波次（占比 {ratio*100:.1f}%），"
                f"平均 SKU={row['avg_sku']:.0f}，平均耗时={row['avg_time']:.1f} 分钟"
            )
        if row['avg_wait'] > wait_75:
            reasons.append(f"大波次包装等待均值 {row['avg_wait']:.1f} 分钟，超 75 分位线 {wait_75:.1f} 分钟")
        if reasons:
            priority = '高' if len(reasons) >= 2 else '中'
            suggestions.append({
                'type': 'split',
                'target': f"仓区: {row['warehouse_area']}",
                'reason': '；'.join(reasons),
                'suggestion': f"建议将「{row['warehouse_area']}」仓区 SKU>{sku_75:.0f} 的大波次拆分为 2-3 个小波次，改善流转效率",
                'priority': priority,
            })
    if len(suggestions) == 0 and len(large_waves) >= 5:
        top_large = large_waves.nlargest(3, 'sku_count')[['record_date', 'warehouse_area', 'picker_name', 'sku_count', 'pick_minutes']]
        sample_info = '；'.join(
            f"{r['warehouse_area']} {r['sku_count']:.0f}SKU/{r['pick_minutes']:.0f}分"
            for _, r in top_large.iterrows()
        )
        suggestions.append({
            'type': 'split',
            'target': '大波次（全局）',
            'reason': f"检测到 {len(large_waves)} 个高 SKU 长耗时波次，示例: {sample_info}",
            'suggestion': f"建议将 SKU>{sku_75:.0f} 或耗时>{time_75:.1f} 分钟的波次按 50-80 SKU/波次进行拆分",
            'priority': '中',
        })
    return suggestions


def generate_optimization_suggestions(df: pd.DataFrame,
                                       overall_summary: Dict,
                                       area_rank: pd.DataFrame) -> List[Dict]:
    suggestions = []
    if len(df) == 0:
        return suggestions
    avg_eff = overall_summary.get('avg_sku_per_min', 0)
    avg_error = overall_summary.get('error_rate', 0)
    path_sug = analyze_path_optimization(df, avg_eff, avg_error)
    assist_sug = analyze_review_assistance(df, avg_error)
    split_sug = analyze_wave_splitting(df)
    suggestions.extend(path_sug)
    suggestions.extend(assist_sug)
    suggestions.extend(split_sug)
    if len(suggestions) == 0:
        suggestions.append({
            'type': 'info',
            'target': '整体运营',
            'reason': f"整体效率={avg_eff:.2f} SKU/分，差异率={avg_error:.2f}%，数据表现平稳",
            'suggestion': '维持当前运营策略，持续监控关键指标；可关注异常等待明细以预防瓶颈',
            'priority': '低',
        })
    return suggestions


def get_suggestion_summary(suggestions: List[Dict]) -> Dict:
    counts = {'路径优化': 0, '复核辅助': 0, '波次拆分': 0, '信息提示': 0}
    priority_counts = {'高': 0, '中': 0, '低': 0}
    type_map = {'path': '路径优化', 'assist': '复核辅助', 'split': '波次拆分', 'info': '信息提示'}
    for s in suggestions:
        t = type_map.get(s.get('type', 'info'), '信息提示')
        counts[t] = counts.get(t, 0) + 1
        priority_counts[s.get('priority', '低')] = priority_counts.get(s.get('priority', '低'), 0) + 1
    return {
        'total': len(suggestions),
        'by_type': counts,
        'by_priority': priority_counts,
    }
