import json
import pandas as pd
import numpy as np
from dash import Dash, dcc, html, Input, Output, State, dash_table, no_update, callback_context, ALL
from dash.exceptions import PreventUpdate
import plotly.graph_objects as go

from src.parser import (
    parse_csv_from_contents, suggest_column_mapping, apply_column_mapping,
    parse_all_dates, get_date_format_hint, STANDARD_COLUMNS,
)
from src.validator import run_full_validation
from src.metrics import (
    compute_base_metrics, filter_dataframe, compute_overall_summary,
    compute_pick_time_distribution, compute_error_stats, compute_area_ranking,
    compute_picker_workload, compute_pack_wait_trend, get_anomaly_details,
    get_filter_options,
)
from src.charts import (
    create_pick_time_distribution, create_error_rate_pie, create_area_efficiency_ranking,
    create_picker_workload_heatmap, create_pack_wait_trend, create_kpi_cards, _empty_fig,
)
from src.exporter import build_export_workbook, generate_download_filename
from src.optimizer import generate_optimization_suggestions, get_suggestion_summary

app = Dash(__name__, suppress_callback_exceptions=True)
app.title = '电商仓运营效率分析看板'
server = app.server

PRIORITY_COLOR = {'高': '#EF553B', '中': '#FFA15A', '低': '#00CC96', '低信息': '#636EFA'}
TYPE_ICON = {'path': '🛤️', 'assist': '👥', 'split': '✂️', 'info': 'ℹ️'}


def _layout_kpi_cards(cards):
    return html.Div([
        html.Div([
            html.Div([
                html.Div(c['icon'], className='kpi-icon',
                         style={'background': c['color'] + '22', 'color': c['color']}),
                html.Div([
                    html.Div(c['label'], className='kpi-label'),
                    html.Div(c['value'], className='kpi-value', style={'color': c['color']}),
                ], className='kpi-text'),
            ], className='kpi-card-inner'),
        ], className='kpi-card')
        for c in cards
    ], className='kpi-grid')


def _build_suggestion_cards(suggestions):
    if not suggestions:
        return html.Div('暂无优化建议', style={'padding': '20px', 'color': '#999', 'textAlign': 'center'})
    return html.Div([
        html.Div([
            html.Div([
                html.Span(TYPE_ICON.get(s.get('type', 'info'), 'ℹ️'), className='sug-icon'),
                html.Div([
                    html.Div([
                        html.Strong(s.get('target', '')),
                        html.Span(f" · {s.get('priority', '低')}优先",
                                  style={'color': PRIORITY_COLOR.get(s.get('priority', '低'), '#666'),
                                         'marginLeft': '8px', 'fontSize': '12px', 'fontWeight': 'bold'}),
                    ], className='sug-header'),
                    html.Div(s.get('suggestion', ''), className='sug-text'),
                    html.Div([
                        html.Span('判定依据: ', style={'color': '#888', 'fontSize': '12px'}),
                        html.Span(s.get('reason', ''), style={'fontSize': '12px', 'color': '#555'}),
                    ], style={'marginTop': '8px', 'borderTop': '1px solid #eee', 'paddingTop': '8px'}),
                ], style={'flex': 1, 'minWidth': 0}),
            ], className='sug-card-inner'),
        ], className='sug-card', style={'borderLeft': f'4px solid {PRIORITY_COLOR.get(s.get("priority", "低"), "#636EFA")}'})
        for s in suggestions
    ], className='sug-grid')


def build_mapping_options(df_columns):
    options = [{'label': '— 不映射 —', 'value': '__none__'}]
    options += [{'label': col, 'value': col} for col in df_columns]
    return options


app.layout = html.Div([
    dcc.Store(id='store-raw-data', data=None),
    dcc.Store(id='store-processed-data', data=None),
    dcc.Store(id='store-messages', data=None),
    dcc.Store(id='store-filter-options', data=None),
    dcc.Download(id='download-export'),

    html.Header([
        html.Div([
            html.H1('📦 电商仓运营效率分析看板', className='app-title'),
            html.Div('拣货效率 · 复核差异 · 包装等待 多维分析', className='app-subtitle'),
        ], className='header-text'),
        html.Div([
            dcc.Upload(
                id='upload-data',
                children=html.Div(['📁 上传 CSV/Excel 文件']),
                className='upload-btn',
                multiple=False,
            ),
            html.Button('📤 导出分析结果', id='btn-export',
                        className='export-btn', disabled=True, n_clicks=0),
        ], className='header-actions'),
    ], className='app-header'),

    html.Div(id='mapping-modal', className='modal-overlay hidden', children=[
        html.Div(className='modal-box', children=[
            html.Div([
                html.H3('⚙️ 列名映射配置', className='modal-title'),
                html.Button('✕', id='mapping-close', className='modal-close'),
            ], className='modal-header'),
            html.Div([
                html.P(['请将 CSV 文件中的列名映射到标准字段。系统已自动建议映射，可手动调整。',
                        html.Br(),
                        html.Span(get_date_format_hint(), style={'fontSize': '12px', 'color': '#666', 'background': '#f5f5f5', 'padding': '8px', 'borderRadius': '6px', 'display': 'inline-block', 'marginTop': '8px'}),
                ], className='modal-hint'),
                html.Div(id='mapping-fields-container', className='mapping-fields'),
            ], className='modal-body'),
            html.Div([
                html.Button('取消', id='mapping-cancel', className='btn-secondary'),
                html.Button('确认映射并继续', id='mapping-confirm', className='btn-primary'),
            ], className='modal-footer'),
        ]),
    ]),

    html.Div(id='messages-panel', className='messages-panel hidden'),
    html.Div(id='welcome-panel', className='welcome-panel', children=[
        html.Div([
            html.Div('📊', style={'fontSize': '64px', 'marginBottom': '16px'}),
            html.H2('欢迎使用电商仓运营效率分析看板'),
            html.P('请上传拣货波次 / 复核明细 / 包装记录文件，支持 CSV 或 Excel 格式',
                   className='welcome-desc'),
            html.Div([
                html.Div([
                    html.Strong('必需字段：'),
                    'record_date, warehouse_area, picker_name, sku_count, pick_minutes',
                ], className='field-hint'),
                html.Div([
                    html.Strong('可选字段：'),
                    'error_count, pack_wait_minutes, note（波次号）',
                ], className='field-hint'),
            ], style={'textAlign': 'left', 'marginTop': '16px', 'display': 'inline-block'}),
        ]),
    ]),

    html.Div(id='dashboard-container', className='dashboard-container hidden', children=[
        html.Div([
            html.Details([
                html.Summary('🎛️ 筛选器面板', style={'cursor': 'pointer', 'fontWeight': 'bold', 'padding': '12px'}),
                html.Div([
                    html.Div([
                        html.Label('📅 日期范围'),
                        dcc.DatePickerRange(
                            id='filter-date',
                            display_format='YYYY-MM-DD',
                            className='filter-control',
                        ),
                    ], className='filter-item'),
                    html.Div([
                        html.Label('🏷️ 仓区'),
                        dcc.Dropdown(id='filter-area', multi=True, placeholder='全部', className='filter-control'),
                    ], className='filter-item'),
                    html.Div([
                        html.Label('👤 拣货员'),
                        dcc.Dropdown(id='filter-picker', multi=True, placeholder='全部', className='filter-control'),
                    ], className='filter-item'),
                    html.Div([
                        html.Label('📦 SKU 数区间'),
                        dcc.RangeSlider(id='filter-sku-range', className='filter-control'),
                        html.Div(id='sku-range-display', className='range-display'),
                    ], className='filter-item filter-item-wide'),
                    html.Div([
                        html.Label('⚠️ 差异状态'),
                        dcc.Dropdown(
                            id='filter-error',
                            options=[
                                {'label': '全部', 'value': 'all'},
                                {'label': '仅含差异', 'value': 'with_error'},
                                {'label': '仅无差异', 'value': 'no_error'},
                            ],
                            value='all',
                            clearable=False,
                            className='filter-control',
                        ),
                    ], className='filter-item'),
                    html.Div([
                        html.Label('⏳ 包装等待区间(分钟)'),
                        dcc.RangeSlider(id='filter-wait-range', className='filter-control'),
                        html.Div(id='wait-range-display', className='range-display'),
                    ], className='filter-item filter-item-wide'),
                ], className='filters-grid'),
            ], open=True, className='filters-panel'),
        ], className='filters-wrapper'),

        html.Div(id='kpi-container', className='kpi-container'),
        html.Div(id='loading-indicator', className='loading hidden'),

        html.Div([
            html.Div([
                dcc.Graph(id='chart-pick-dist'),
            ], className='chart-box chart-half'),
            html.Div([
                dcc.Graph(id='chart-error-pie'),
            ], className='chart-box chart-half'),
        ], className='charts-row'),

        html.Div([
            html.Div([
                dcc.Graph(id='chart-area-rank'),
            ], className='chart-box chart-full'),
        ], className='charts-row'),

        html.Div([
            html.Div([
                dcc.Graph(id='chart-workload'),
            ], className='chart-box chart-half'),
            html.Div([
                dcc.Graph(id='chart-wait-trend'),
            ], className='chart-box chart-half'),
        ], className='charts-row'),

        html.Details([
            html.Summary('🚨 异常明细列表',
                         style={'cursor': 'pointer', 'fontWeight': 'bold', 'padding': '12px',
                                'fontSize': '16px', 'borderBottom': '1px solid #eee'}),
            html.Div([
                dash_table.DataTable(
                    id='table-anomalies',
                    style_table={'overflowX': 'auto'},
                    style_header={'backgroundColor': '#f5f5f5', 'fontWeight': 'bold'},
                    style_cell={'padding': '10px', 'textAlign': 'left', 'fontSize': '13px'},
                    style_data_conditional=[
                        {'if': {'filter_query': '{异常等待} = true'}, 'backgroundColor': '#FFE5E5'},
                        {'if': {'filter_query': '{重复波次} = true'}, 'backgroundColor': '#FFF3CD'},
                    ],
                    page_size=15,
                    sort_action='native',
                    filter_action='native',
                ),
            ]),
        ], open=True, className='table-wrapper details-panel'),

        html.Details([
            html.Summary(id='optimization-summary-title',
                         style={'cursor': 'pointer', 'fontWeight': 'bold', 'padding': '12px',
                                'fontSize': '16px', 'borderBottom': '1px solid #eee'}),
            html.Div([
                html.Div(id='optimization-summary', className='optimization-summary'),
                html.Div(id='optimization-suggestions'),
            ]),
        ], open=True, className='details-panel optimization-panel'),

    ]),

    html.Footer([
        html.Div('© 电商仓运营效率分析看板 · 数据处理使用 Pandas · 图表使用 Plotly'),
    ], className='app-footer'),
], className='app-root')


# ==========================
# Callbacks
# ==========================

@app.callback(
    Output('mapping-modal', 'className'),
    Output('mapping-fields-container', 'children'),
    Output('store-raw-data', 'data'),
    Output('welcome-panel', 'className'),
    Input('upload-data', 'contents'),
    Input('mapping-close', 'n_clicks'),
    Input('mapping-cancel', 'n_clicks'),
    State('upload-data', 'filename'),
    State('mapping-modal', 'className'),
    prevent_initial_call=True,
)
def handle_upload_and_modal(contents, close_clicks, cancel_clicks, filename, modal_class):
    ctx = callback_context
    if not ctx.triggered:
        raise PreventUpdate
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

    if trigger_id in ('mapping-close', 'mapping-cancel'):
        return 'modal-overlay hidden', no_update, no_update, 'welcome-panel'

    if trigger_id == 'upload-data' and contents:
        df, msg = parse_csv_from_contents(contents, filename or '')
        if df is None or len(df) == 0:
            return (modal_class,
                    html.Div([f'❌ {msg}'], style={'color': '#EF553B', 'padding': '20px'}),
                    no_update, 'welcome-panel')
        suggested = suggest_column_mapping(df.columns.tolist())
        mapping_fields = []
        for std_col, std_label in STANDARD_COLUMNS.items():
            current_val = '__none__'
            for csv_col, mapped in suggested.items():
                if mapped == std_label:
                    current_val = csv_col
                    break
            mapping_fields.append(html.Div([
                html.Label(
                    f'{std_col}' + (' *' if std_col in ['record_date', 'warehouse_area', 'picker_name', 'sku_count', 'pick_minutes'] else ''),
                    className='mapping-label'
                ),
                dcc.Dropdown(
                    id={'type': 'mapping-dropdown', 'index': std_col},
                    options=build_mapping_options(df.columns.tolist()),
                    value=current_val,
                    clearable=False,
                    className='mapping-dropdown',
                ),
            ], className='mapping-field'))
        raw_json = df.to_json(orient='split', date_format='iso')
        return 'modal-overlay', mapping_fields, raw_json, 'welcome-panel hidden'

    raise PreventUpdate


@app.callback(
    Output('mapping-modal', 'className', allow_duplicate=True),
    Output('store-processed-data', 'data'),
    Output('store-messages', 'data'),
    Output('store-filter-options', 'data'),
    Output('dashboard-container', 'className'),
    Output('welcome-panel', 'className', allow_duplicate=True),
    Output('messages-panel', 'children'),
    Output('messages-panel', 'className'),
    Output('btn-export', 'disabled'),
    Input('mapping-confirm', 'n_clicks'),
    State('store-raw-data', 'data'),
    State({'type': 'mapping-dropdown', 'index': ALL}, 'id'),
    State({'type': 'mapping-dropdown', 'index': ALL}, 'value'),
    prevent_initial_call=True,
)
def confirm_mapping_and_process(confirm_clicks, raw_json, mapping_ids, mapping_values):
    if not raw_json:
        raise PreventUpdate
    try:
        df = pd.read_json(raw_json, orient='split')
    except Exception:
        return (
            'modal-overlay', no_update, no_update, no_update, 'dashboard-container hidden',
            'welcome-panel', html.Div('❌ 原始数据解析失败'), 'messages-panel', True,
        )
    mapping = {}
    if isinstance(mapping_ids, list) and isinstance(mapping_values, list):
        for mid, val in zip(mapping_ids, mapping_values):
            if isinstance(mid, dict) and 'index' in mid:
                std_col = mid['index']
                if val and val != '__none__':
                    mapping[val] = std_col
    df_mapped = apply_column_mapping(df, mapping)
    df_parsed, date_msgs = parse_all_dates(df_mapped)
    df_processed, validation_msgs = run_full_validation(df_parsed)
    if len(df_processed) == 0:
        all_msgs = validation_msgs
        all_msgs['date_parse'] = date_msgs
        msg_elements = _flatten_messages(all_msgs)
        return (
            'modal-overlay hidden', None, json.dumps(all_msgs, ensure_ascii=False),
            None, 'dashboard-container hidden', 'welcome-panel',
            html.Div([html.H4('⚠️ 数据处理结果：0 条有效记录'),
                      html.Div(msg_elements)]),
            'messages-panel error', True,
        )
    df_final = compute_base_metrics(df_processed)
    processed_json = df_final.to_json(orient='split', date_format='iso')
    opts = get_filter_options(df_final)
    opts_json = json.dumps({k: (v.isoformat() if hasattr(v, 'isoformat') else v) if not isinstance(v, tuple) else
                              [x.isoformat() if hasattr(x, 'isoformat') else x for x in v]
                            for k, v in opts.items()}, ensure_ascii=False)
    all_msgs = validation_msgs
    all_msgs['date_parse'] = date_msgs
    msg_elements = _flatten_messages(all_msgs)
    return (
        'modal-overlay hidden', processed_json, json.dumps(all_msgs, ensure_ascii=False),
        opts_json, 'dashboard-container', 'welcome-panel hidden',
        html.Div([html.H4('✅ 数据处理完成'), html.Div(msg_elements)]),
        'messages-panel', False,
    )


def _flatten_messages(all_msgs: dict):
    children = []
    category_titles = {
        'required_fields': '🔍 必需字段校验',
        'numeric_clean': '🔢 数值字段清洗',
        'duplicate_check': '🔁 重复波次检查',
        'anomaly_wait': '⏳ 异常等待识别',
        'date_parse': '📅 日期解析',
        'summary': '📊 数据概览',
    }
    for cat, msgs in all_msgs.items():
        if isinstance(msgs, list) and msgs:
            children.append(html.Div([
                html.Strong(category_titles.get(cat, cat)),
                html.Ul([html.Li(m) for m in msgs], className='msg-list'),
            ], className='msg-category'))
    return children


@app.callback(
    Output('filter-date', 'start_date'),
    Output('filter-date', 'end_date'),
    Output('filter-area', 'options'),
    Output('filter-picker', 'options'),
    Output('filter-sku-range', 'min'),
    Output('filter-sku-range', 'max'),
    Output('filter-sku-range', 'value'),
    Output('sku-range-display', 'children'),
    Output('filter-wait-range', 'min'),
    Output('filter-wait-range', 'max'),
    Output('filter-wait-range', 'value'),
    Output('wait-range-display', 'children'),
    Input('store-filter-options', 'data'),
    prevent_initial_call=True,
)
def populate_filter_options(opts_json):
    if not opts_json:
        raise PreventUpdate
    opts = json.loads(opts_json)
    date_range = opts.get('date_range') or [None, None]
    start_date = date_range[0] if date_range[0] else None
    end_date = date_range[1] if date_range[1] else None
    area_opts = [{'label': a, 'value': a} for a in opts.get('warehouse_areas', [])]
    picker_opts = [{'label': p, 'value': p} for p in opts.get('picker_names', [])]
    sku_min = int(opts.get('sku_min', 0))
    sku_max = int(opts.get('sku_max', 1000))
    wait_min = float(opts.get('wait_min', 0))
    wait_max = float(opts.get('wait_max', 500))
    return (
        start_date, end_date,
        area_opts, picker_opts,
        sku_min, sku_max, [sku_min, sku_max],
        f'SKU数范围: {sku_min} ~ {sku_max}',
        wait_min, wait_max, [wait_min, wait_max],
        f'等待范围: {wait_min:.1f} ~ {wait_max:.1f} 分钟',
    )


@app.callback(
    Output('sku-range-display', 'children', allow_duplicate=True),
    Output('wait-range-display', 'children', allow_duplicate=True),
    Input('filter-sku-range', 'value'),
    Input('filter-wait-range', 'value'),
    prevent_initial_call=True,
)
def update_range_displays(sku_val, wait_val):
    sku_msg = f'SKU数范围: {sku_val[0]} ~ {sku_val[1]}' if sku_val else ''
    wait_msg = f'等待范围: {wait_val[0]:.1f} ~ {wait_val[1]:.1f} 分钟' if wait_val else ''
    return sku_msg, wait_msg


@app.callback(
    Output('kpi-container', 'children'),
    Output('chart-pick-dist', 'figure'),
    Output('chart-error-pie', 'figure'),
    Output('chart-area-rank', 'figure'),
    Output('chart-workload', 'figure'),
    Output('chart-wait-trend', 'figure'),
    Output('table-anomalies', 'data'),
    Output('table-anomalies', 'columns'),
    Output('optimization-summary', 'children'),
    Output('optimization-summary-title', 'children'),
    Output('optimization-suggestions', 'children'),
    Input('store-processed-data', 'data'),
    Input('filter-date', 'start_date'),
    Input('filter-date', 'end_date'),
    Input('filter-area', 'value'),
    Input('filter-picker', 'value'),
    Input('filter-sku-range', 'value'),
    Input('filter-error', 'value'),
    Input('filter-wait-range', 'value'),
    prevent_initial_call=True,
)
def render_all_dashboard(
    processed_json, start_date, end_date, areas, pickers, sku_range, error_status, wait_range
):
    if not processed_json:
        raise PreventUpdate
    try:
        df_full = pd.read_json(processed_json, orient='split')
        if 'date_only' in df_full.columns and df_full['date_only'].iloc[0] is not None:
            try:
                df_full['date_only'] = pd.to_datetime(df_full['date_only']).dt.date
            except Exception:
                pass
    except Exception:
        return [], _empty_fig(''), _empty_fig(''), _empty_fig(''), _empty_fig(''), _empty_fig(''), [], [], [], '', ''

    date_r = (start_date, end_date) if start_date or end_date else None
    df = filter_dataframe(df_full, date_range=date_r, warehouse_areas=areas,
                          picker_names=pickers, sku_range=sku_range,
                          error_status=error_status or 'all', wait_range=wait_range)

    summary = compute_overall_summary(df)
    kpi_cards = create_kpi_cards(summary)
    kpi_component = _layout_kpi_cards(kpi_cards)

    dist_df = compute_pick_time_distribution(df)
    fig_dist = create_pick_time_distribution(dist_df)

    err_stats = compute_error_stats(df)
    fig_error = create_error_rate_pie(err_stats)

    rank_df = compute_area_ranking(df)
    fig_rank = create_area_efficiency_ranking(rank_df)

    workload_df = compute_picker_workload(df)
    fig_work = create_picker_workload_heatmap(workload_df)

    trend_df = compute_pack_wait_trend(df)
    fig_trend = create_pack_wait_trend(trend_df)

    anomaly_df = get_anomaly_details(df)
    if len(anomaly_df) > 0:
        table_data = anomaly_df.to_dict('records')
        table_cols = [{'name': c, 'id': c} for c in anomaly_df.columns]
    else:
        table_data = []
        table_cols = []

    suggestions = generate_optimization_suggestions(df, summary, rank_df)
    sug_summary = get_suggestion_summary(suggestions)
    summary_chips = html.Div([
        html.Span(f'共 {sug_summary["total"]} 条建议', className='chip chip-primary'),
    ] + [
        html.Span(f'{t} {c}条', className='chip')
        for t, c in sug_summary['by_type'].items() if c > 0
    ] + [
        html.Span(f'{p}优先级 {c}条',
                  className='chip',
                  style={'borderColor': PRIORITY_COLOR.get(p, '#ccc'),
                         'color': PRIORITY_COLOR.get(p, '#666')})
        for p, c in sug_summary['by_priority'].items() if c > 0
    ], className='chips-row')
    sug_title = f'💡 流程优化建议 ({sug_summary["total"]} 条) - 点击展开'
    sug_cards = _build_suggestion_cards(suggestions[:15])

    return (
        kpi_component,
        fig_dist, fig_error, fig_rank, fig_work, fig_trend,
        table_data, table_cols,
        summary_chips, sug_title, sug_cards,
    )


@app.callback(
    Output('download-export', 'data'),
    Input('btn-export', 'n_clicks'),
    State('store-processed-data', 'data'),
    State('filter-date', 'start_date'),
    State('filter-date', 'end_date'),
    State('filter-area', 'value'),
    State('filter-picker', 'value'),
    State('filter-sku-range', 'value'),
    State('filter-error', 'value'),
    State('filter-wait-range', 'value'),
    prevent_initial_call=True,
)
def export_results(n_clicks, processed_json, start_date, end_date, areas, pickers, sku_range, error_status, wait_range):
    if not processed_json or not n_clicks:
        raise PreventUpdate
    try:
        df_full = pd.read_json(processed_json, orient='split')
        if 'date_only' in df_full.columns:
            try:
                df_full['date_only'] = pd.to_datetime(df_full['date_only']).dt.date
            except Exception:
                pass
    except Exception:
        raise PreventUpdate

    date_r = (start_date, end_date) if start_date or end_date else None
    df_filtered = filter_dataframe(df_full, date_range=date_r, warehouse_areas=areas,
                                   picker_names=pickers, sku_range=sku_range,
                                   error_status=error_status or 'all', wait_range=wait_range)

    summary = compute_overall_summary(df_filtered)
    rank_df = compute_area_ranking(df_filtered)
    trend_df = compute_pack_wait_trend(df_filtered)
    anomaly_df = get_anomaly_details(df_filtered)
    suggestions = generate_optimization_suggestions(df_filtered, summary, rank_df)

    workbook_bytes = build_export_workbook(
        raw_df=df_full, filtered_df=df_filtered, summary=summary,
        area_rank=rank_df, trend_df=trend_df, anomaly_df=anomaly_df,
        suggestions=suggestions,
    )
    fname = generate_download_filename('仓储数据分析')
    return dcc.send_bytes(workbook_bytes, filename=fname)


if __name__ == '__main__':
    print('🚀 启动电商仓运营效率分析看板...')
    print('📌 访问: http://127.0.0.1:8050')
    app.run(debug=True, host='0.0.0.0', port=8050)
