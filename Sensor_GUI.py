from dash import Dash, dcc, html, Input, Output, callback
import plotly.express as px
import pandas as pd

app = Dash()

colors = {
    'background': "#0c0000",
    'text': "#00B7FF"
}

app.layout = html.Div(style={'backgroundColor': colors['background']}, children=[
    html.H1(
        children='Sensor Data',
        style={
            'textAlign': 'center',
            'color': colors['text']
        }
    ),
    dcc.Graph(
        id='sensor-graph',
        figure=px.line(pd.DataFrame({'x': [1, 2, 3], 'y': [4, 1, 3]}), x='x', y='y')
    )
])

if __name__ == '__main__':
    app.run(debug=True)
