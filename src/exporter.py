import io
import pandas as pd
from typing import Dict, List
from datetime import datetime


def build_export_workbook(
    raw_df: pd.DataFrame,
    filtered_df: pd.DataFrame,
    summary: Dict,
    area_rank: pd.DataFrame,
    trend_df: pd.DataFrame,
    anomaly_df: pd.DataFrame,
    suggestions: List[Dict] = None,
    picker_diagnosis: Dict = None,
    picker_suggestions: List[Dict] = None,
) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        if summary and len(summary) > 0:
            summary_df = pd.DataFrame([{
                '指标名称': {
                    'total_waves': '总波次数',
                    'total_sku': '总SKU件数',
                    'total_pick_minutes': '总拣货耗时(分钟)',
                    'avg_sku_per_min': '平均拣货效率(SKU/分钟)',
                    'error_rate': '平均差异率(%)',
                    'avg_wait': '平均包装等待(分钟)',
                    'anomalous_count': '异常等待次数',
                }.get(k, k),
                '指标值': v,
            } for k, v in summary.items()])
            summary_df.to_excel(writer, sheet_name='总体汇总', index=False)
        if filtered_df is not None and len(filtered_df) > 0:
            export_cols = ['record_date', 'warehouse_area', 'picker_name',
                           'sku_count', 'pick_minutes', 'sku_per_minute',
                           'error_count', 'error_rate', 'pack_wait_minutes', 'note']
            available_cols = [c for c in export_cols if c in filtered_df.columns]
            export_df = filtered_df[available_cols].copy()
            rename_map = {
                'record_date': '记录日期',
                'warehouse_area': '仓区',
                'picker_name': '拣货员',
                'sku_count': 'SKU数',
                'pick_minutes': '拣货耗时(分)',
                'sku_per_minute': '效率(SKU/分)',
                'error_count': '差异数',
                'error_rate': '差异率(%)',
                'pack_wait_minutes': '包装等待(分)',
                'note': '备注/波次号',
            }
            export_df = export_df.rename(columns=rename_map)
            export_df.to_excel(writer, sheet_name='明细数据', index=False)
        if area_rank is not None and len(area_rank) > 0:
            rank_export = area_rank.rename(columns={
                'warehouse_area': '仓区',
                'waves': '波次数',
                'total_sku': '总SKU',
                'avg_sku_per_min': '效率(SKU/分)',
                'error_rate': '差异率(%)',
                'avg_wait': '平均等待(分)',
                'score': '综合得分',
                'rank': '排名',
            })
            rank_export.to_excel(writer, sheet_name='区域效率排行', index=False)
        if trend_df is not None and len(trend_df) > 0:
            trend_export = trend_df.rename(columns={
                'date_only': '日期',
                'avg_wait': '平均等待(分)',
                'max_wait': '最大等待(分)',
                'anomalous_count': '异常数',
            })
            trend_export.to_excel(writer, sheet_name='包装等待趋势', index=False)
        if anomaly_df is not None and len(anomaly_df) > 0:
            rename_map2 = {
                'record_date': '记录日期',
                'warehouse_area': '仓区',
                'picker_name': '拣货员',
                'sku_count': 'SKU数',
                'pick_minutes': '拣货耗时(分)',
                'error_count': '差异数',
                'pack_wait_minutes': '包装等待(分)',
                'note': '备注/波次号',
            }
            anom_export = anomaly_df.rename(columns=rename_map2)
            anom_export.to_excel(writer, sheet_name='异常明细', index=False)
        if suggestions:
            sug_df = pd.DataFrame(suggestions)
            if 'type' in sug_df.columns:
                sug_df['type'] = sug_df['type'].map({
                    'path': '路径优化',
                    'assist': '复核辅助',
                    'split': '波次拆分',
                }).fillna(sug_df['type'])
                sug_df = sug_df.rename(columns={
                    'type': '建议类型',
                    'target': '建议对象',
                    'reason': '判定依据',
                    'suggestion': '优化建议',
                    'priority': '优先级',
                })
            sug_df.to_excel(writer, sheet_name='优化建议', index=False)
        if picker_diagnosis and picker_diagnosis.get('pickers'):
            diag_rows = []
            for p in picker_diagnosis['pickers']:
                diag_rows.append({
                    '拣货员': p['picker_name'],
                    '波次数': p['waves'],
                    '总SKU量': p['total_sku'],
                    '平均效率(SKU/分)': p['avg_eff'],
                    '平均差异率(%)': p['avg_error_rate'],
                    '平均等待(分)': p['avg_wait'],
                    '累计差异数': p['total_error_count'],
                    '诊断标签': '、'.join(p.get('labels', [])),
                })
            diag_df = pd.DataFrame(diag_rows)
            diag_df.to_excel(writer, sheet_name='拣货员绩效诊断', index=False)
            all_anomaly_rows = []
            for p in picker_diagnosis['pickers']:
                for a in p.get('anomaly_details', []):
                    all_anomaly_rows.append({
                        '拣货员': p['picker_name'],
                        '日期': a['date'],
                        '仓区': a['area'],
                        'SKU数': a['sku_count'],
                        '拣货耗时(分)': a['pick_minutes'],
                        '差异数': a['error_count'],
                        '包装等待(分)': a['pack_wait_minutes'],
                        '备注': a['note'],
                        '异常类型': a['reasons'],
                    })
            if all_anomaly_rows:
                anom_detail_df = pd.DataFrame(all_anomaly_rows)
                anom_detail_df.to_excel(writer, sheet_name='人员异常明细', index=False)
        if picker_suggestions:
            sug_imp_rows = []
            for s in picker_suggestions:
                sug_imp_rows.append({
                    '拣货员': s['picker'],
                    '诊断标签': '、'.join(s.get('labels', [])),
                    '判定依据': s['reason'],
                    '改进建议': s['advice'],
                })
            if sug_imp_rows:
                imp_df = pd.DataFrame(sug_imp_rows)
                imp_df.to_excel(writer, sheet_name='人员改进建议', index=False)
    return output.getvalue()


def generate_download_filename(prefix: str = '仓储数据分析') -> str:
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return f'{prefix}_{timestamp}.xlsx'


def build_csv_export(df: pd.DataFrame) -> str:
    if df is None or len(df) == 0:
        return ''
    rename_map = {
        'record_date': '记录日期',
        'warehouse_area': '仓区',
        'picker_name': '拣货员',
        'sku_count': 'SKU数',
        'pick_minutes': '拣货耗时(分)',
        'sku_per_minute': '效率(SKU/分)',
        'error_count': '差异数',
        'error_rate': '差异率(%)',
        'pack_wait_minutes': '包装等待(分)',
        'note': '备注/波次号',
    }
    export_cols = [c for c in rename_map.keys() if c in df.columns]
    export_df = df[export_cols].rename(columns=rename_map).copy()
    return export_df.to_csv(index=False, encoding='utf-8-sig')
