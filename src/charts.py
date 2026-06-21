import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import pandas as pd
from typing import Dict, List

CHART_COLORS = ['#636EFA', '#EF553B', '#00CC96', '#AB63FA', '#FFA15A',
                '#19D3F3', '#FF6692', '#B6E880', '#FF97FF', '#FECB52']

TEMPLATE = 'plotly_white'


def _empty_fig(title: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        title=title,
        template=TEMPLATE,
        xaxis=dict(showgrid=False, zeroline=False),
        yaxis=dict(showgrid=False, zeroline=False),
        annotations=[dict(
            text='暂无数据',
            xref='paper', yref='paper',
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(size=20, color='#aaa')
        )]
    )
    return fig


def create_pick_time_distribution(dist_df: pd.DataFrame) -> go.Figure:
    if len(dist_df) == 0 or dist_df['count'].sum() == 0:
        return _empty_fig('拣货耗时分布')
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=dist_df['pick_bins'],
        y=dist_df['count'],
        text=dist_df['percentage'].astype(str) + '%',
        textposition='outside',
        marker=dict(color=CHART_COLORS[0], line=dict(width=0)),
        hovertemplate='<b>%{x}</b><br>波次数: %{y}<br>占比: %{text}<extra></extra>',
    ))
    fig.update_layout(
        title=dict(text='拣货耗时分布', font=dict(size=16)),
        template=TEMPLATE,
        bargap=0.3,
        xaxis=dict(title='耗时区间', showgrid=False),
        yaxis=dict(title='波次数', showgrid=True, gridcolor='#f0f0f0'),
        height=380,
    )
    return fig


def create_error_rate_pie(error_stats: Dict) -> go.Figure:
    if error_stats.get('with_error', 0) + error_stats.get('no_error', 0) == 0:
        return _empty_fig('复核差异率统计')
    labels = ['无差异波次', '有差异波次']
    values = [error_stats.get('no_error', 0), error_stats.get('with_error', 0)]
    colors = ['#00CC96', '#EF553B']
    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        hole=0.55,
        marker=dict(colors=colors, line=dict(color='white', width=3)),
        textinfo='label+percent',
        textfont=dict(size=12),
        hovertemplate='<b>%{label}</b><br>数量: %{value}<br>占比: %{percent}<extra></extra>',
    )])
    fig.update_layout(
        title=dict(
            text=f'复核差异率统计<Br><span style="font-size:12px;color:#666">差异率: {error_stats.get("error_rate_wave", 0)}%</span>',
            font=dict(size=16),
            x=0.5,
        ),
        template=TEMPLATE,
        showlegend=True,
        legend=dict(orientation='h', y=-0.1),
        height=380,
    )
    return fig


def create_area_efficiency_ranking(rank_df: pd.DataFrame) -> go.Figure:
    if len(rank_df) == 0:
        return _empty_fig('仓区效率排行榜')
    fig = make_subplots(
        rows=1, cols=2,
        column_widths=[0.6, 0.4],
        specs=[[dict(type='bar'), dict(type='table')]],
        horizontal_spacing=0.05,
    )
    colors = [CHART_COLORS[i % len(CHART_COLORS)] for i in range(len(rank_df))]
    fig.add_trace(go.Bar(
        y=rank_df['warehouse_area'],
        x=rank_df['avg_sku_per_min'],
        orientation='h',
        marker=dict(color=colors, line=dict(width=0)),
        text=rank_df['avg_sku_per_min'].astype(str),
        textposition='outside',
        hovertemplate='<b>%{y}</b><br>效率(SKU/分钟): %{x}<extra></extra>',
        name='拣货效率',
    ), row=1, col=1)
    table_data = [
        rank_df['rank'].tolist(),
        rank_df['warehouse_area'].tolist(),
        rank_df['score'].astype(str).tolist(),
        rank_df['error_rate'].astype(str).tolist(),
    ]
    fig.add_trace(go.Table(
        header=dict(
            values=['排名', '仓区', '综合得分', '差异率%'],
            fill_color='#f5f5f5',
            align='center',
            font=dict(size=11),
            height=30,
        ),
        cells=dict(
            values=table_data,
            fill_color=[
                ['#fff' if i % 2 == 0 else '#fafafa' for i in range(len(rank_df))]
            ],
            align='center',
            font=dict(size=11),
            height=28,
        ),
    ), row=1, col=2)
    fig.update_layout(
        title=dict(text='仓区效率排行榜', font=dict(size=16)),
        template=TEMPLATE,
        height=420,
        showlegend=False,
        xaxis=dict(title='SKU/分钟', showgrid=True, gridcolor='#f0f0f0'),
        yaxis=dict(title='', autorange='reversed', showgrid=False),
    )
    return fig


def create_picker_workload_heatmap(workload_df: pd.DataFrame) -> go.Figure:
    if len(workload_df) == 0:
        return _empty_fig('人员负载变化趋势')
    pivot_df = workload_df.pivot_table(
        index='picker_name',
        columns='date_only',
        values='total_minutes',
        aggfunc='sum',
        fill_value=0
    )
    if len(pivot_df) == 0 or len(pivot_df.columns) == 0:
        return _empty_fig('人员负载变化趋势')
    dates = [str(d) for d in pivot_df.columns.tolist()]
    pickers = pivot_df.index.tolist()
    values = pivot_df.values.tolist()
    wave_pivot = workload_df.pivot_table(
        index='picker_name',
        columns='date_only',
        values='waves',
        aggfunc='sum',
        fill_value=0
    )
    customdata = wave_pivot.values.tolist()
    fig = go.Figure(data=go.Heatmap(
        z=values,
        x=dates,
        y=pickers,
        colorscale='Blues',
        showscale=True,
        colorbar=dict(title='总耗时(分钟)', titleside='right'),
        customdata=customdata,
        hovertemplate='<b>%{y}</b><br>日期: %{x}<br>总耗时: %{z:.1f}分钟<br>波次数: %{customdata}<extra></extra>',
    ))
    fig.update_layout(
        title=dict(text='人员负载变化趋势（按日耗时热力图）', font=dict(size=16)),
        template=TEMPLATE,
        height=400,
        xaxis=dict(title='日期', showgrid=False, tickangle=-30),
        yaxis=dict(title='拣货员', showgrid=False),
    )
    return fig


def create_pack_wait_trend(trend_df: pd.DataFrame) -> go.Figure:
    if len(trend_df) == 0:
        return _empty_fig('包装等待趋势')
    dates = [str(d) for d in trend_df['date_only'].tolist()]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates,
        y=trend_df['avg_wait'],
        mode='lines+markers',
        name='平均等待',
        line=dict(color=CHART_COLORS[0], width=3),
        marker=dict(size=8),
        yaxis='y1',
        hovertemplate='<b>%{x}</b><br>平均等待: %{y:.2f}分钟<extra></extra>',
    ))
    fig.add_trace(go.Scatter(
        x=dates,
        y=trend_df['max_wait'],
        mode='lines',
        name='最大等待',
        line=dict(color=CHART_COLORS[1], width=2, dash='dash'),
        marker=dict(size=6),
        yaxis='y1',
        hovertemplate='<b>%{x}</b><br>最大等待: %{y:.2f}分钟<extra></extra>',
    ))
    fig.add_trace(go.Bar(
        x=dates,
        y=trend_df['anomalous_count'],
        name='异常数量',
        marker=dict(color=CHART_COLORS[9], opacity=0.6),
        yaxis='y2',
        hovertemplate='<b>%{x}</b><br>异常等待数: %{y}<extra></extra>',
    ))
    fig.update_layout(
        title=dict(text='包装等待趋势分析', font=dict(size=16)),
        template=TEMPLATE,
        height=400,
        showlegend=True,
        legend=dict(orientation='h', y=1.1, x=0),
        xaxis=dict(title='日期', showgrid=False),
        yaxis=dict(
            title='等待时长(分钟)',
            showgrid=True, gridcolor='#f0f0f0',
            side='left',
        ),
        yaxis2=dict(
            title='异常等待数(次)',
            showgrid=False,
            overlaying='y',
            side='right',
        ),
    )
    return fig


LABEL_COLORS = {
    '表现优秀': '#00CC96',
    '效率偏低': '#FFA15A',
    '差异偏高': '#EF553B',
    '等待异常': '#AB63FA',
    '表现正常': '#636EFA',
}


def create_picker_diagnosis_overview(diagnosis: Dict) -> go.Figure:
    pickers = diagnosis.get('pickers', [])
    if not pickers:
        return _empty_fig('拣货员绩效诊断概览')
    names = [p['picker_name'] for p in pickers]
    effs = [p['avg_eff'] for p in pickers]
    errors = [p['avg_error_rate'] for p in pickers]
    waits = [p['avg_wait'] for p in pickers]
    fig = make_subplots(
        rows=1, cols=3,
        column_widths=[0.35, 0.35, 0.3],
        specs=[[dict(type='bar'), dict(type='bar'), dict(type='bar')]],
        horizontal_spacing=0.08,
        subplot_titles=['平均效率 (SKU/分)', '平均差异率 (%)', '平均等待 (分)'],
    )
    eff_colors = []
    for p in pickers:
        if '表现优秀' in p['labels']:
            eff_colors.append(LABEL_COLORS['表现优秀'])
        elif '效率偏低' in p['labels']:
            eff_colors.append(LABEL_COLORS['效率偏低'])
        else:
            eff_colors.append('#636EFA')
    fig.add_trace(go.Bar(
        x=names, y=effs,
        marker=dict(color=eff_colors, line=dict(width=0)),
        text=[f'{e:.2f}' for e in effs],
        textposition='outside',
        hovertemplate='<b>%{x}</b><br>效率: %{y:.3f} SKU/分<extra></extra>',
        name='效率',
        showlegend=False,
    ), row=1, col=1)
    err_colors = [LABEL_COLORS['差异偏高'] if '差异偏高' in p['labels'] else '#636EFA' for p in pickers]
    fig.add_trace(go.Bar(
        x=names, y=errors,
        marker=dict(color=err_colors, line=dict(width=0)),
        text=[f'{e:.2f}' for e in errors],
        textposition='outside',
        hovertemplate='<b>%{x}</b><br>差异率: %{y:.2f}%<extra></extra>',
        name='差异率',
        showlegend=False,
    ), row=1, col=2)
    wait_colors = [LABEL_COLORS['等待异常'] if '等待异常' in p['labels'] else '#636EFA' for p in pickers]
    fig.add_trace(go.Bar(
        x=names, y=waits,
        marker=dict(color=wait_colors, line=dict(width=0)),
        text=[f'{w:.1f}' for w in waits],
        textposition='outside',
        hovertemplate='<b>%{x}</b><br>等待: %{y:.1f} 分<extra></extra>',
        name='等待',
        showlegend=False,
    ), row=1, col=3)
    thresholds = diagnosis.get('thresholds', {})
    if thresholds.get('eff_low'):
        fig.add_hline(y=thresholds['eff_low'], line_dash='dash', line_color='#FFA15A',
                      row=1, col=1, annotation_text=f"效率阈值 {thresholds['eff_low']:.2f}")
    if thresholds.get('error_high'):
        fig.add_hline(y=thresholds['error_high'], line_dash='dash', line_color='#EF553B',
                      row=1, col=2, annotation_text=f"差异阈值 {thresholds['error_high']:.2f}%")
    if thresholds.get('wait_abnormal'):
        fig.add_hline(y=thresholds['wait_abnormal'], line_dash='dash', line_color='#AB63FA',
                      row=1, col=3, annotation_text=f"等待阈值 {thresholds['wait_abnormal']:.1f}分")
    fig.update_layout(
        title=dict(text='拣货员绩效诊断概览', font=dict(size=16)),
        template=TEMPLATE,
        height=400,
        showlegend=False,
        margin=dict(t=80),
    )
    for i in range(1, 4):
        fig.update_xaxes(tickangle=-30, row=1, col=i)
        fig.update_yaxes(showgrid=True, gridcolor='#f0f0f0', row=1, col=i)
    return fig


def create_picker_trend_chart(picker_record: Dict) -> go.Figure:
    daily = picker_record.get('daily_trend', [])
    if not daily:
        return _empty_fig(f'{picker_record.get("picker_name", "")} 趋势')
    dates = [str(d.get('date_only', '')) for d in daily]
    effs = [d.get('avg_eff', 0) for d in daily]
    errors = [d.get('avg_error_rate', 0) for d in daily]
    waits = [d.get('avg_wait', 0) for d in daily]
    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        subplot_titles=['效率趋势 (SKU/分)', '差异率趋势 (%)', '包装等待趋势 (分)'],
    )
    fig.add_trace(go.Scatter(
        x=dates, y=effs, mode='lines+markers',
        line=dict(color='#636EFA', width=2.5),
        marker=dict(size=7),
        name='效率',
        hovertemplate='%{x}<br>效率: %{y:.3f}<extra></extra>',
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=dates, y=errors, mode='lines+markers',
        line=dict(color='#EF553B', width=2.5),
        marker=dict(size=7),
        name='差异率',
        hovertemplate='%{x}<br>差异率: %{y:.2f}%<extra></extra>',
    ), row=2, col=1)
    fig.add_trace(go.Scatter(
        x=dates, y=waits, mode='lines+markers',
        line=dict(color='#AB63FA', width=2.5),
        marker=dict(size=7),
        name='等待',
        hovertemplate='%{x}<br>等待: %{y:.1f}分<extra></extra>',
    ), row=3, col=1)
    name = picker_record.get('picker_name', '')
    fig.update_layout(
        title=dict(text=f'📋 {name} 最近记录趋势', font=dict(size=16)),
        template=TEMPLATE,
        height=600,
        showlegend=False,
        margin=dict(t=60),
    )
    for i in range(1, 4):
        fig.update_yaxes(showgrid=True, gridcolor='#f0f0f0', row=i, col=1)
    fig.update_xaxes(title='日期', row=3, col=1)
    return fig


def create_kpi_cards(summary: Dict) -> List[Dict]:
    cards = [
        {
            'label': '总波次数',
            'value': f"{summary.get('total_waves', 0):,}",
            'color': '#636EFA',
            'icon': '📦',
        },
        {
            'label': '总SKU件数',
            'value': f"{summary.get('total_sku', 0):,}",
            'color': '#00CC96',
            'icon': '🛒',
        },
        {
            'label': '平均拣货效率',
            'value': f"{summary.get('avg_sku_per_min', 0)} SKU/分",
            'color': '#FFA15A',
            'icon': '⚡',
        },
        {
            'label': '平均差异率',
            'value': f"{summary.get('error_rate', 0)}%",
            'color': '#EF553B',
            'icon': '⚠️',
        },
        {
            'label': '平均包装等待',
            'value': f"{summary.get('avg_wait', 0)} 分",
            'color': '#AB63FA',
            'icon': '⏳',
        },
        {
            'label': '异常等待数',
            'value': f"{summary.get('anomalous_count', 0)} 次",
            'color': '#FF6692',
            'icon': '🚨',
        },
    ]
    return cards
