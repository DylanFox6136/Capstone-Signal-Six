"""
Mars Hard Lander Payload — Ground Telemetry Console
Signal Six · CU Boulder ECE Capstone · JPL sponsor

The payload sends one packet every 10 minutes. Every packet is also appended
to telemetry_log.csv and reloaded on startup, so restarting the app doesn't
wipe the charts.

Run with the receiver plugged in:   python mars_lander_telemetry.py
Run without hardware (fake data):   python mars_lander_telemetry.py --demo
"""

import csv
import json
import math
import os
import random
import sys
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone
import plotly.graph_objects as go
import serial
from dash import Dash, Input, Output, dcc, html, no_update

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SERIAL_PORT = 'COM8'             # Update to your receiver port
BAUDRATE = 115200
PACKET_INTERVAL_S = 600          # Payload transmits every 10 minutes
LATE_AFTER_S = PACKET_INTERVAL_S + 60        # Grace period before a packet counts as late
LOS_AFTER_S = 2 * PACKET_INTERVAL_S          # Two missed packets -> loss of signal
GAP_AFTER_S = 1.5 * PACKET_INTERVAL_S        # Break the line if packets are further apart than this
MIN_VIEW_S = 3600                # Charts always show at least the last hour
MAX_VIEW_S = 24 * 3600           # ...and at most the last 24 hours
MAX_LEN = 1000                   # Packets kept in memory (~7 days)
REFRESH_MS = 1000                # Clock/countdown refresh rate
CSV_PATH = 'telemetry_log.csv'
DEMO_MODE = '--demo' in sys.argv
if DEMO_MODE:
    CSV_PATH = 'telemetry_log_demo.csv'


# Channel definitions. min_span keeps near-constant signals (pressure, temp)
# from being zoomed so far in that sensor noise looks like a cliff.
CHANNELS = [
    {'id': 'rssi',     'label': '6 DOF / RSSI', 'unit': 'dBm',    'color': '#4FD1FF', 'dp': 0, 'min_span': 10},
    {'id': 'alt',      'label': 'ALTITUDE',     'unit': 'm',      'color': '#FF8C42', 'dp': 1, 'min_span': 5},
    {'id': 'co2',      'label': 'CO₂',     'unit': 'ppm',    'color': '#7EE787', 'dp': 0, 'min_span': 100},
    {'id': 'pressure', 'label': 'AIR PRESSURE', 'unit': 'hPa',    'color': '#FFCC4D', 'dp': 2, 'min_span': 0.2},
    {'id': 'temp',     'label': 'TEMPERATURE',  'unit': '°C', 'color': '#FF6AD5', 'dp': 2, 'min_span': 0.5},
    {'id': 'humidity', 'label': 'HUMIDITY',     'unit': '%RH',    'color': '#5EEAD4', 'dp': 1, 'min_span': 2.0},
]
CSV_FIELDS = ['utc', 'packet'] + [ch['id'] for ch in CHANNELS]

# ---------------------------------------------------------------------------
# Shared state (guarded by data_lock)
# ---------------------------------------------------------------------------
data_lock = threading.Lock()
rx_times = deque(maxlen=MAX_LEN)            # UTC arrival time of each packet (x axis)
packet_ids = deque(maxlen=MAX_LEN)
series = {ch['id']: deque(maxlen=MAX_LEN) for ch in CHANNELS}
raw_log = deque(maxlen=8)
state = {'connected': False, 'last_rx': None, 'packets': 0, 'start': time.time(), 'version': 0}


def _store(now, row, raw=None):
    """Append one packet to the in-memory buffers. Caller holds data_lock."""
    rx_times.append(now)
    packet_ids.append(row['packet'])
    for ch in CHANNELS:
        series[ch['id']].append(row[ch['id']])
    state['last_rx'] = now.timestamp()
    state['packets'] += 1
    state['version'] += 1
    if raw is not None:
        raw_log.appendleft(f'{now:%Y-%m-%d %H:%M:%S}Z  RX  {raw}')


def ingest(data, now=None):
    """Decode one packet, buffer it, and append it to the CSV log."""
    now = now or datetime.now(timezone.utc)
    packet_id = data.get('packet', 0)
    row = {
        'packet': packet_id,
        'rssi': data.get('rssi', 0),
        'alt': data.get('alt', packet_id),     # Falls back to packet idx until altimeter is wired
        'co2': data.get('co2', 0),
        'pressure': data.get('pressure', 0),
        'temp': data.get('temp', 0),
        'humidity': data.get('humidity', 0),
    }
    with data_lock:
        _store(now, row, json.dumps(data, separators=(',', ':')))
    try:
        new_file = not os.path.exists(CSV_PATH)
        with open(CSV_PATH, 'a', newline='') as f:
            w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            if new_file:
                w.writeheader()
            w.writerow({'utc': now.isoformat(), **row})
    except OSError as e:
        print(f'CSV write failed: {e}')


def load_history():
    """Reload earlier packets from the CSV so a restart keeps the charts."""
    if not os.path.exists(CSV_PATH):
        return
    with open(CSV_PATH, newline='') as f, data_lock:
        for r in csv.DictReader(f):
            try:
                now = datetime.fromisoformat(r['utc'])
                row = {'packet': int(float(r['packet']))}
                row.update({ch['id']: float(r[ch['id']]) for ch in CHANNELS})
            except (KeyError, ValueError):
                continue
            _store(now, row, json.dumps({k: v for k, v in row.items()}, separators=(',', ':')))
    print(f'Loaded {state["packets"]} packets from {CSV_PATH}')


# ---------------------------------------------------------------------------
# Background threads
# ---------------------------------------------------------------------------
def serial_reader_thread():
    print(f'Starting serial listener on {SERIAL_PORT}...')
    while True:
        try:
            with serial.Serial(SERIAL_PORT, BAUDRATE, timeout=1) as ser:
                print('Connected to ESP32-C6 receiver')
                state['connected'] = True
                while True:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if line.startswith('JSON:'):
                        try:
                            ingest(json.loads(line[5:]))
                        except json.JSONDecodeError:
                            pass
        except (serial.SerialException, OSError):
            state['connected'] = False
            time.sleep(2)


def fake_packet(pkt):
    return {
        'packet': pkt,
        'rssi': round(-34 + 3 * math.sin(pkt / 4) + random.uniform(-2, 2)),
        'co2': round(650 + 120 * math.sin(pkt / 6) + random.uniform(-40, 40)),
        'pressure': round(834.25 + 0.05 * math.sin(pkt / 10), 2),
        'temp': round(28.38 + 0.3 * math.sin(pkt / 8), 2),
        'humidity': round(37 + 0.6 * math.sin(pkt / 3) + random.uniform(-0.2, 0.2), 1),
    }


def demo_thread():
    """Fake packets on the real 10-minute schedule, with 4 hours of back-filled history."""
    state['connected'] = True
    pkt = state['packets']
    if pkt == 0:
        # Last back-filled packet lands 1 min ago, so the next live one is 9 min out
        t0 = datetime.now(timezone.utc) - timedelta(seconds=23 * PACKET_INTERVAL_S + 60)
        for i in range(24):
            if i == 15:            # one missed packet, to show how a dropout looks
                continue
            pkt += 1
            ingest(fake_packet(pkt), t0 + timedelta(seconds=i * PACKET_INTERVAL_S))
    while True:
        due = (state['last_rx'] or time.time()) + PACKET_INTERVAL_S
        time.sleep(max(1, due - time.time()))
        pkt += 1
        ingest(fake_packet(pkt))


# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------
BG = '#05080C'
PANEL = '#0A1018'
GRID = '#131D28'
AXIS = '#1E2B39'
TEXT = '#C9D6E3'
DIM = '#5B6B7C'
FONT = "Arial, 'Times New Roman', serif"
CHART_HEIGHT = 240

CSS = """
:root {
  --bg: #05080C; --panel: #0A1018; --panel-2: #0C131C; --line: #1A2633;
  --text: #C9D6E3; --dim: #5B6B7C; --amber: #FFB000; --ok: #39FF88; --bad: #FF4D4D;
}
* { box-sizing: border-box; }
html, body { margin: 0; background: var(--bg); }
body {
  color: var(--text);
  font-family: Arial, 'Times New Roman', serif;
  -webkit-font-smoothing: antialiased;
  background:
    radial-gradient(1200px 500px at 50% -200px, rgba(79,209,255,0.06), transparent 70%),
    var(--bg);
  min-height: 100vh;
}
body::after {  /* faint CRT scanlines */
  content: ''; position: fixed; inset: 0; pointer-events: none; z-index: 99;
  background: repeating-linear-gradient(0deg, rgba(255,255,255,0.012) 0 1px, transparent 1px 3px);
}
.console { max-width: 1680px; margin: 0 auto; padding: 18px 22px 28px; }

/* ---- header ---- */
.hdr {
  display: flex; justify-content: space-between; align-items: stretch; gap: 16px;
  border: 1px solid var(--line); border-radius: 6px; background: var(--panel); overflow: hidden;
}
.hdr-id { display: flex; align-items: center; gap: 16px; padding: 14px 18px; min-width: 0; }
.badge {
  flex: none; width: 46px; height: 46px; border-radius: 50%; border: 2px solid var(--amber);
  display: grid; place-items: center; color: var(--amber); font-weight: 700; font-size: 13px;
  letter-spacing: 1px; box-shadow: 0 0 18px rgba(255,176,0,0.18), inset 0 0 10px rgba(255,176,0,0.12);
}
.mission { font-size: 20px; font-weight: 700; letter-spacing: 3px; color: #E8F0F8; }
.sub { font-size: 11px; letter-spacing: 2px; color: var(--dim); margin-top: 5px; }
.hdr-stats { display: flex; }
.hstat {
  padding: 12px 20px; border-left: 1px solid var(--line); min-width: 124px;
  display: flex; flex-direction: column; justify-content: center;
}
.hstat .k { font-size: 10px; letter-spacing: 2px; color: var(--dim); }
.hstat .v { font-size: 17px; font-weight: 600; margin-top: 5px; font-variant-numeric: tabular-nums; white-space: nowrap; }
.link { display: flex; align-items: center; gap: 8px; }
.dot { width: 9px; height: 9px; border-radius: 50%; flex: none; }
.ok { color: var(--ok); }
.ok .dot { background: var(--ok); box-shadow: 0 0 10px var(--ok); animation: pulse 1.6s infinite; }
.warn { color: var(--amber); }
.warn .dot { background: var(--amber); box-shadow: 0 0 10px var(--amber); }
.bad { color: var(--bad); }
.bad .dot { background: var(--bad); box-shadow: 0 0 10px var(--bad); }
@keyframes pulse { 50% { opacity: 0.35; } }

/* ---- next-packet bar ---- */
.toolbar {
  display: flex; justify-content: space-between; align-items: center; gap: 16px;
  margin: 14px 0 10px; font-size: 10px; letter-spacing: 2px; color: var(--dim);
}
.next { display: flex; align-items: center; gap: 12px; flex: 1; max-width: 520px; }
.bar { flex: 1; height: 4px; background: var(--line); border-radius: 2px; overflow: hidden; }
.bar > div { height: 100%; background: var(--amber); box-shadow: 0 0 8px var(--amber); transition: width 1s linear; }

/* ---- readout tiles ---- */
.tiles { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 10px; margin-bottom: 10px; }
.tile {
  background: linear-gradient(180deg, var(--panel-2), var(--panel));
  border: 1px solid var(--line); border-radius: 6px; padding: 12px 14px; position: relative; overflow: hidden;
}
.tile::before {
  content: ''; position: absolute; left: 0; right: 0; top: 0; height: 2px; background: var(--c);
  box-shadow: 0 0 12px var(--c);
}
.tile .k { font-size: 10px; letter-spacing: 2px; color: var(--dim); }
.tile .v {
  font-size: 28px; font-weight: 600; color: var(--c); margin-top: 6px; white-space: nowrap;
  font-variant-numeric: tabular-nums; text-shadow: 0 0 16px color-mix(in srgb, var(--c) 40%, transparent);
}
.tile .u { font-size: 12px; color: var(--dim); margin-left: 6px; text-shadow: none; }
.tile .d { font-size: 11px; color: var(--dim); margin-top: 4px; font-variant-numeric: tabular-nums; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* ---- chart panels ---- */
.grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.panel {
  min-width: 0;                          /* lets grid cells shrink: fixes resize jitter */
  background: var(--panel); border: 1px solid var(--line); border-radius: 6px; overflow: hidden;
}
.panel-h {
  display: flex; justify-content: space-between; align-items: center;
  padding: 9px 14px; border-bottom: 1px solid var(--line);
  background: linear-gradient(90deg, color-mix(in srgb, var(--c, #1A2633) 10%, var(--panel-2)), var(--panel-2) 45%);
  font-size: 11px; letter-spacing: 2px;
}
.panel-h .ch { color: var(--c, var(--dim)); margin-right: 10px; opacity: 0.8; }
.panel-h .name { color: var(--text); font-weight: 600; }
.panel-h .unit { color: var(--dim); }
.chart { width: 100%; height: """ + str(CHART_HEIGHT) + """px; }

/* ---- packet log ---- */
.log { margin-top: 10px; }
.log pre {
  margin: 0; padding: 10px 14px; font-size: 11.5px; line-height: 1.65; color: #7F93A6;
  white-space: pre; overflow-x: auto; min-height: 60px;
}
.log pre::first-line { color: var(--amber); }
.foot { margin-top: 10px; font-size: 10px; letter-spacing: 2px; color: var(--dim); display: flex; justify-content: space-between; }

@media (max-width: 1200px) {
  .tiles { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .hdr { flex-direction: column; }
  .hdr-stats { flex-wrap: wrap; border-top: 1px solid var(--line); }
  .hstat:first-child { border-left: 0; }
}
@media (max-width: 900px) {
  .grid { grid-template-columns: minmax(0, 1fr); }
  .tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .toolbar { flex-direction: column; align-items: stretch; }
}
"""

INDEX = """<!DOCTYPE html>
<html>
<head>
  {%metas%}
  <title>Mars Lander Telemetry</title>
  {%favicon%}
  {%css%}
  <style>""" + CSS + """</style>
</head>
<body>
  {%app_entry%}
  <footer>{%config%}{%scripts%}{%renderer%}</footer>
</body>
</html>"""


def hex_to_rgba(hex_color, alpha):
    h = hex_color.lstrip('#')
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f'rgba({r},{g},{b},{alpha})'


def y_range(ys, min_span):
    lo, hi = min(ys), max(ys)
    span = max(hi - lo, min_span)
    mid = (hi + lo) / 2
    pad = span * 0.15
    return [mid - span / 2 - pad, mid + span / 2 + pad]


def fmt_dur(s):
    s = int(abs(s))
    return f'{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}' if s >= 3600 else f'{s // 60:02d}:{s % 60:02d}'


def view_range(xs, now):
    """Whole session, at least the last hour, at most the last day, plus room for the next packet."""
    x_hi = now + timedelta(seconds=PACKET_INTERVAL_S)
    x_lo = xs[0] if xs else now
    x_lo = min(x_lo, now - timedelta(seconds=MIN_VIEW_S))
    x_lo = max(x_lo, now - timedelta(seconds=MAX_VIEW_S))
    return x_lo - timedelta(seconds=PACKET_INTERVAL_S / 4), x_hi


def build_figure(ch, xs, ys, now):
    color = ch['color']
    x_lo, x_hi = view_range(xs, now)
    fig = go.Figure()

    keep = [i for i, x in enumerate(xs) if x >= x_lo]
    xs, ys = [xs[i] for i in keep], [ys[i] for i in keep]

    if ys:
        rng = y_range(ys, ch['min_span'])
        # Split into continuous runs so a missed packet shows as a break in the line
        runs, run = [], ([], [])
        for i, (x, y) in enumerate(zip(xs, ys)):
            if i and (x - xs[i - 1]).total_seconds() > GAP_AFTER_S:
                runs.append(run)
                run = ([], [])
            run[0].append(x)
            run[1].append(y)
        runs.append(run)

        for rx, ry in runs:
            # Filled area down to the bottom of the plot
            fig.add_trace(go.Scatter(x=rx, y=[rng[0]] * len(rx), mode='lines', hoverinfo='skip',
                                     showlegend=False, line=dict(width=0)))
            fig.add_trace(go.Scatter(x=rx, y=ry, mode='lines', hoverinfo='skip', showlegend=False,
                                     line=dict(width=0), fill='tonexty',
                                     fillcolor=hex_to_rgba(color, 0.07)))
            # Glow underlay
            fig.add_trace(go.Scatter(x=rx, y=ry, mode='lines', hoverinfo='skip', showlegend=False,
                                     line=dict(color=hex_to_rgba(color, 0.15), width=6)))
            # Main trace; each dot is one real packet
            fig.add_trace(go.Scatter(
                x=rx, y=ry, mode='lines+markers', showlegend=False, name=ch['label'],
                line=dict(color=color, width=2),
                marker=dict(size=5, color=color),
                hovertemplate=f'%{{x|%H:%M}} UTC<br><b>%{{y:.{ch["dp"]}f}} {ch["unit"]}</b><extra></extra>',
            ))
        # Latest-sample marker
        fig.add_trace(go.Scatter(
            x=[xs[-1]], y=[ys[-1]], mode='markers', hoverinfo='skip', showlegend=False,
            marker=dict(size=11, color=PANEL, line=dict(color=color, width=2)),
        ))
        # Shaded slot where the next packet is expected
        nxt = xs[-1] + timedelta(seconds=PACKET_INTERVAL_S)
        fig.add_vrect(x0=nxt - timedelta(seconds=60), x1=nxt + timedelta(seconds=60),
                      fillcolor=hex_to_rgba(color, 0.08), line_width=0)
        # Session mean
        mean = sum(ys) / len(ys)
        fig.add_hline(y=mean, line=dict(color=DIM, width=1, dash='dot'), opacity=0.5,
                      annotation_text=f'AVG {mean:.{ch["dp"]}f}', annotation_position='top left',
                      annotation_font=dict(size=9, color=DIM, family=FONT))
    else:
        rng = None
        fig.add_annotation(text='AWAITING FIRST PACKET', showarrow=False, x=0.5, y=0.5,
                           xref='paper', yref='paper', font=dict(color=DIM, size=12, family=FONT))

    axis = dict(
        gridcolor=GRID, zeroline=False, showline=True, linecolor=AXIS, mirror=False,
        tickfont=dict(color=DIM, size=10, family=FONT), ticks='outside', tickcolor=AXIS, ticklen=4,
        fixedrange=True,
    )
    fig.update_layout(
        autosize=True,
        margin=dict(l=62, r=18, t=14, b=30),
        paper_bgcolor=PANEL, plot_bgcolor=PANEL,
        font=dict(family=FONT, color=TEXT),
        xaxis=dict(**axis, type='date', range=[x_lo, x_hi], tickformat='%H:%M', nticks=8),
        yaxis=dict(**axis, range=rng, tickformat=f'.{ch["dp"]}f', nticks=6),
        hovermode='closest',
        hoverlabel=dict(bgcolor='#0D1520', bordercolor=color, font=dict(family=FONT, size=11, color=TEXT)),
    )
    return fig


# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------
def panel(idx, ch):
    return html.Div(className='panel', style={'--c': ch['color']}, children=[
        html.Div(className='panel-h', children=[
            html.Div([html.Span(f'CH-{idx:02d}', className='ch'),
                      html.Span(ch['label'], className='name')]),
            html.Span(f'[{ch["unit"]}]', className='unit'),
        ]),
        dcc.Graph(
            id=f'g-{ch["id"]}', className='chart', responsive=True,
            style={'height': f'{CHART_HEIGHT}px', 'width': '100%'},
            config={'displayModeBar': False},
            figure=build_figure(ch, [], [], datetime.now(timezone.utc)),
        ),
    ])


def tile(ch):
    return html.Div(className='tile', style={'--c': ch['color']}, children=[
        html.Div(ch['label'], className='k'),
        html.Div([html.Span('---', id=f'v-{ch["id"]}'), html.Span(ch['unit'], className='u')], className='v'),
        html.Div('Δ ---', id=f'd-{ch["id"]}', className='d'),
    ])


def hstat(label, id_):
    return html.Div(className='hstat', children=[
        html.Div(label, className='k'), html.Div('---', id=id_, className='v'),
    ])


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = Dash(__name__, title='Mars Lander Telemetry')
app.index_string = INDEX

app.layout = html.Div(className='console', children=[
    html.Div(className='hdr', children=[
        html.Div(className='hdr-id', children=[
            html.Div('JPL', className='badge'),
            html.Div([
                html.Div('MARS HARD LANDER PAYLOAD', className='mission'),
                html.Div('GROUND TELEMETRY CONSOLE · SIGNAL SIX · CU BOULDER', className='sub'),
            ]),
        ]),
        html.Div(className='hdr-stats', children=[
            hstat('LINK', 'h-link'), hstat('UTC', 'h-utc'), hstat('MET', 'h-met'),
            hstat('PACKETS', 'h-pkts'), hstat('LAST RX', 'h-age'), hstat('NEXT PKT', 'h-next'),
        ]),
    ]),
    html.Div(className='toolbar', children=[
        html.Span(f'LIVE SENSOR CHANNELS · 1 PACKET / {PACKET_INTERVAL_S // 60} MIN'),
        html.Div(className='next', children=[
            html.Span('NEXT PACKET'),
            html.Div(className='bar', children=html.Div(id='next-bar', style={'width': '0%'})),
        ]),
    ]),
    html.Div(className='tiles', children=[tile(ch) for ch in CHANNELS]),
    html.Div(className='grid', children=[panel(i + 1, ch) for i, ch in enumerate(CHANNELS)]),
    html.Div(className='panel log', children=[
        html.Div(className='panel-h', children=[
            html.Div([html.Span('LOG', className='ch'), html.Span('PACKET STREAM', className='name')]),
            html.Span(f'{"DEMO" if DEMO_MODE else SERIAL_PORT} @ {BAUDRATE} · {CSV_PATH}', className='unit'),
        ]),
        html.Pre(id='raw-log', children='-- no packets received --'),
    ]),
    html.Div(className='foot', children=[
        html.Span('ESP32-C6 RX → SERIAL → DASH'),
        html.Span(f'CADENCE {PACKET_INTERVAL_S // 60} MIN · LOS AFTER {LOS_AFTER_S // 60} MIN'),
    ]),
    dcc.Interval(id='tick', interval=REFRESH_MS, n_intervals=0),
])

outputs = (
    [Output(f'g-{ch["id"]}', 'figure') for ch in CHANNELS]
    + [Output(f'v-{ch["id"]}', 'children') for ch in CHANNELS]
    + [Output(f'd-{ch["id"]}', 'children') for ch in CHANNELS]
    + [Output('h-link', 'children'), Output('h-link', 'className'),
       Output('h-utc', 'children'), Output('h-met', 'children'),
       Output('h-pkts', 'children'), Output('h-age', 'children'),
       Output('h-next', 'children'), Output('h-next', 'className'),
       Output('next-bar', 'style'), Output('raw-log', 'children')]
)

_drawn = {'version': -1, 'minute': None}


@app.callback(outputs, Input('tick', 'n_intervals'))
def refresh(n):
    with data_lock:
        xs = list(rx_times)
        ys_all = {k: list(v) for k, v in series.items()}
        log = list(raw_log)
        last_rx, pkts, connected, version = (state['last_rx'], state['packets'],
                                             state['connected'], state['version'])

    now = datetime.now(timezone.utc)
    t = now.timestamp()

    # Charts only need redrawing when a packet lands or the axis should slide (once a minute).
    # The first tick after a page load always redraws.
    minute = now.replace(second=0, microsecond=0)
    redraw = n == 0 or version != _drawn['version'] or minute != _drawn['minute']
    _drawn.update(version=version, minute=minute)

    figs, vals, deltas = [], [], []
    for ch in CHANNELS:
        ys = ys_all[ch['id']]
        figs.append(build_figure(ch, xs, ys, now) if redraw else no_update)
        dp = ch['dp']
        if ys:
            d = ys[-1] - ys[-2] if len(ys) > 1 else 0
            vals.append(f'{ys[-1]:.{dp}f}')
            deltas.append(f'Δ{d:+.{dp}f} vs last  ↓{min(ys):.{dp}f}  ↑{max(ys):.{dp}f}')
        else:
            vals.append('---')
            deltas.append('Δ ---')

    age = t - last_rx if last_rx else None
    if not connected:
        link, link_cls = [html.Span(className='dot'), 'NO PORT'], 'v link bad'
    elif age is None:
        link, link_cls = [html.Span(className='dot'), 'WAITING'], 'v link warn'
    elif age < LATE_AFTER_S:
        link, link_cls = [html.Span(className='dot'), 'NOMINAL'], 'v link ok'
    elif age < LOS_AFTER_S:
        link, link_cls = [html.Span(className='dot'), 'LATE'], 'v link warn'
    else:
        link, link_cls = [html.Span(className='dot'), 'LOS'], 'v link bad'

    if age is None:
        next_txt, next_cls, pct = '---', 'v', 0
    elif age <= PACKET_INTERVAL_S:
        next_txt, next_cls = f'T-{fmt_dur(PACKET_INTERVAL_S - age)}', 'v'
        pct = 100 * age / PACKET_INTERVAL_S
    else:
        next_txt, next_cls, pct = f'LATE +{fmt_dur(age - PACKET_INTERVAL_S)}', 'v warn', 100

    met = int(t - state['start'])
    met_str = f'T+{met // 3600:02d}:{met % 3600 // 60:02d}:{met % 60:02d}'
    age_str = f'{fmt_dur(age)} ago' if age is not None else '---'

    return (figs + vals + deltas
            + [link, link_cls, f'{now:%H:%M:%S}', met_str, f'{pkts:,}', age_str,
               next_txt, next_cls, {'width': f'{pct:.1f}%'},
               '\n'.join(log) if log else '-- no packets received --'])


if __name__ == '__main__':
    load_history()
    target = demo_thread if DEMO_MODE else serial_reader_thread
    threading.Thread(target=target, daemon=True).start()
    app.run(debug=True, use_reloader=False, dev_tools_ui=False)
