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
