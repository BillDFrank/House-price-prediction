# app.py
from flask import Flask, render_template, flash, request
import os
import json
import datetime
import pandas as pd
import plotly.express as px
import plotly.offline as pyo

# Import your custom database connector function
from ConnectDB import get_data

app = Flask(__name__)
app.secret_key = 'your_generated_secret_key'  # Replace with your secret key

# ----------------------
# Helper: Clean the DataFrame
# ----------------------


def clean_data(df):
    # 1. Remove rows where price is "Preço sob consulta"
    df = df[~df["price"].str.contains("Preço sob consulta", na=False)]
    # 2. Clean the price column (remove non-breaking spaces, euro symbol, and thousand separators)
    df["price"] = (df["price"]
                   .str.replace("\xa0", "", regex=True)
                   .str.replace("€", "", regex=True)
                   .str.replace(",", "", regex=True)
                   .astype(float))
    # 3. Split location into parts
    df["location"] = df["location"].fillna("")
    df["location_parts"] = df["location"].str.split(",")
    # Assume the last element is the state, the second-to-last is the city,
    # and the remaining (if any) form the neighborhood.
    df["state"] = df["location_parts"].str[-1].str.strip()
    df["city"] = df["location_parts"].str[-2].str.strip()
    df["neighborhood"] = df["location_parts"].apply(
        lambda x: ", ".join(x[:-2]) if len(x) > 2 else "")
    df.drop(columns=["location_parts", "location", "page"],
            inplace=True, errors='ignore')
    # 4. Clean the rooms column (extract numeric value)
    df["rooms"] = df["rooms"].astype(str).str.extract("(\d+)")[0].astype(float)
    # 5. Convert date_scraped to datetime
    df['date_scraped'] = pd.to_datetime(df['date_scraped'], errors='coerce')
    return df

# ----------------------
# Route for the Choropleth Map
# ----------------------


@app.route('/')
def index():
    # 1. Retrieve data using your custom module.
    try:
        df = get_data()  # Should return a DataFrame from your database.
    except Exception as e:
        flash("Error retrieving data from the database: " + str(e))
        df = pd.DataFrame()

    if df.empty:
        flash("No data found in the database.")
        data = []
    else:
        # Clean the data
        df = clean_data(df)
        # 2. Select data with the latest scraped date.
        latest_date = df['date_scraped'].max()
        df_latest = df[df['date_scraped'] == latest_date].copy()

        # 3. Group data according to the selected level.
        level = request.args.get('level', '1')
        if level not in ['1', '2', '3']:
            level = '1'
        if level == '1':
            group_col = 'state'
            feature_key = 'properties.NAME_1'
            group_label = "State"
        elif level == '2':
            group_col = 'city'
            feature_key = 'properties.NAME_2'
            group_label = "City"
        elif level == '3':
            group_col = 'neighborhood'
            feature_key = 'properties.NAME_3'
            group_label = "Neighborhood"

        # Remove rows with missing group data (if any)
        df_latest = df_latest[df_latest[group_col].notna()]
        # Group by the selected column and compute average price.
        grouped = df_latest.groupby(group_col)['price'].mean().reset_index()
        grouped.rename(columns={'price': 'avg_price'}, inplace=True)
        grouped['avg_price'] = grouped['avg_price'].round(2)
        data = grouped.to_dict(orient='records')

    # 4. Determine which GeoJSON file to use based on level.
    geo_filename = f"gadm41_PRT_{level}.json"
    geojson_path = os.path.join(app.static_folder, 'geo', geo_filename)
    try:
        with open(geojson_path, 'r', encoding='utf-8') as f:
            geojson_data = json.load(f)
    except Exception as e:
        flash("Error loading GeoJSON file: " + str(e))
        geojson_data = {}

    # 5. Create the choropleth map using Plotly Express.
    # Change the color scale to "Plasma" (or choose another free scale).
    title = f"Average Apartment Prices by {group_label} (Data as of {latest_date.strftime('%Y-%m-%d')})"
    fig = px.choropleth(
        data_frame=grouped,
        geojson=geojson_data,
        locations=group_col,
        featureidkey=feature_key,
        color='avg_price',
        color_continuous_scale="Plasma",
        labels={'avg_price': 'Avg Price (€)'},
        title=title
    )
    fig.update_geos(fitbounds="locations", visible=False)
    fig.update_layout(margin={"r": 0, "t": 30, "l": 0, "b": 0})
    map_div = pyo.plot(fig, output_type='div', include_plotlyjs='cdn')

    return render_template('index.html', map_div=map_div)


if __name__ == '__main__':
    app.run(debug=True)
