import json
import os
import threading
import time
from collections import deque
import plotly.graph_objects as go
import serial
from dash import Dash, Input, Output, dcc, html
from plotly.subplots import make_subplots

# --- Data Buffers & Thread Safety ---
MAX_LEN = 50
# The lock prevents Dash from trying to read the deques at the exact 
# millisecond the serial thread is writing new data to them.
data_lock = threading.Lock() 

time_data = deque(maxlen=MAX_LEN)
dof_data = deque(maxlen=MAX_LEN)  # Mapped to RSSI for now
alt_data = deque(maxlen=MAX_LEN)  # Mapped to packet progression
co2_data = deque(maxlen=MAX_LEN)
pressure_data = deque(maxlen=MAX_LEN)
temp_data = deque(maxlen=MAX_LEN)
humidity_data = deque(maxlen=MAX_LEN)

# --- Background Serial Reader Thread ---
def serial_reader_thread():
    port = 'COM8'  # Update to your receiver port
    baudrate = 115200

    print(f'Starting serial listener thread on {port}...')
    while True:
        try:
            with serial.Serial(port, baudrate, timeout=1) as ser:
                print('Connected to ESP32-C6 Receiver!')
                while True:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if line.startswith('JSON:'):
                        try:
                            data = json.loads(line[5:])
                            packet_id = data.get('packet', 0)
                            
                            # Lock the thread briefly while we update the global deques
                            with data_lock:
                                time_data.append(packet_id)
                                temp_data.append(data.get('temp', 0))
                                humidity_data.append(data.get('humidity', 0))
                                pressure_data.append(data.get('pressure', 0))
                                co2_data.append(data.get('co2', 0))
                                dof_data.append(data.get('rssi', 0))
                                alt_data.append(packet_id) 
                        except json.JSONDecodeError:
                            pass
        except (serial.SerialException, OSError):
            # Handle disconnections gracefully without crashing
            time.sleep(2)

# Start background thread (preventing duplicate threads during Dash debug reloads)
if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not os.environ.get('WERKZEUG_RUN_MAIN'):
    thread = threading.Thread(target=serial_reader_thread, daemon=True)
    thread.start()

# --- Dash App Initialization ---
app = Dash(__name__)

colors = {'background': '#0c0000', 'text': '#00B7FF'}

app.layout = html.Div(
    style={
        'backgroundColor': colors['background'],
        'padding': '20px',
        'minHeight': '100vh',
    },
    children=[
        html.H1(
            children='Mars Lander Telemetry',
            style={'textAlign': 'center', 'color': colors['text']},
        ),
        dcc.Graph(id='live-sensor-graph'),
        dcc.Interval(id='graph-update-interval', interval=1000, n_intervals=0),
    ],
)

# --- Live Graph Update Callback ---
@app.callback(
    Output('live-sensor-graph', 'figure'),
    Input('graph-update-interval', 'n_intervals'),
)
def update_live_plots(n):
    fig = make_subplots(
        rows=3, cols=2,
        subplot_titles=(
            '6 DOF / RSSI', 'Altitude',
            'CO2', 'Air Pressure',
            'Temperature', 'Humidity'
        ),
    )

    # Safely lock and copy the data to standard lists for Plotly to render
    with data_lock:
        x_vals = list(time_data)
        y_dof = list(dof_data)
        y_alt = list(alt_data)
        y_co2 = list(co2_data)
        y_pres = list(pressure_data)
        y_temp = list(temp_data)
        y_hum = list(humidity_data)

    # Build Traces
    fig.add_trace(go.Scatter(x=x_vals, y=y_dof, mode='lines+markers', name='RSSI', line=dict(color='#00B7FF')), row=1, col=1)
    fig.add_trace(go.Scatter(x=x_vals, y=y_alt, mode='lines+markers', name='Altitude', line=dict(color='#FF5733')), row=1, col=2)
    fig.add_trace(go.Scatter(x=x_vals, y=y_co2, mode='lines+markers', name='CO2', line=dict(color='#33FF57')), row=2, col=1)
    fig.add_trace(go.Scatter(x=x_vals, y=y_pres, mode='lines+markers', name='Pressure', line=dict(color='#F3FF33')), row=2, col=2)
    fig.add_trace(go.Scatter(x=x_vals, y=y_temp, mode='lines+markers', name='Temp', line=dict(color='#FF33F3')), row=3, col=1)
    fig.add_trace(go.Scatter(x=x_vals, y=y_hum, mode='lines+markers', name='Humidity', line=dict(color='#33FFFF')), row=3, col=2)

    fig.update_layout(
        height=900,
        template='plotly_dark',
        paper_bgcolor='#0c0000',
        plot_bgcolor='#0c0000',
        font=dict(color='#00B7FF'),
        transition_duration=200,  # Smooth transition animation
    )

    return fig

if __name__ == '__main__':
    # Use standard host and port settings
    app.run(debug=True, use_reloader=False)
