from dash import Dash, html, dcc
import plotly.graph_objects as go
from plotly.subplots import make_subplots

app = Dash()

fig = make_subplots(
    rows=3, 
    cols=2, 
    subplot_titles=("6 DOF", "Altitude", "CO2", "Air Pressure", "Temperature", "Humidity")
)

fig.add_trace(go.Scatter(x=[1, 2, 3], y=[4, 5, 6], mode='lines', name='6 DOF'), row=1, col=1)
fig.add_trace(go.Scatter(x=[1, 2, 3], y=[7, 8, 9], mode='lines', name='Altitude'), row=1, col=2)
fig.add_trace(go.Scatter(x=[1, 2, 3], y=[10, 11, 12], mode='lines', name='CO2'), row=2, col=1)
fig.add_trace(go.Scatter(x=[1, 2, 3], y=[13, 14, 15], mode='lines', name='Air Pressure'), row=2, col=2)
fig.add_trace(go.Scatter(x=[1, 2, 3], y=[16, 17, 18], mode='lines', name='Temperature'), row=3, col=1)
fig.add_trace(go.Scatter(x=[1, 2, 3], y=[19, 20, 21], mode='lines', name='Humidity'), row=3, col=2)


fig.update_layout(
    height=900, 
    template="plotly_dark", 
    paper_bgcolor="#0c0000", 
    plot_bgcolor="#0c0000",
    font=dict(color="#00B7FF")
)

colors = {
    'background': "#0c0000",
    'text': "#00B7FF"
}

app.layout = html.Div(
    style={'backgroundColor': colors['background'], 'padding': '20px', 'minHeight': '100vh'}, 
    children=[
        html.H1(
            children='Sensor Data',
            style={
                'textAlign': 'center',
                'color': colors['text']
            }
        ),
        
        dcc.Graph(figure=fig)
    ]
)

if __name__ == '__main__':
    app.run(debug=True)
