# app.py
from flask import Flask, render_template, flash, request
import os
import json
import datetime
import pandas as pd
import plotly.express as px
import plotly.offline as pyo

# Import your custom database connector functions
from ConnectDB import get_data, get_states_list, get_cities_list, get_neighborhoods_list

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
    # Assume: last element is state, second-to-last is city, and the rest is neighborhood.
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

    # Initialize variables.
    latest_date = None
    grouped = pd.DataFrame()

    if not df.empty:
        # Clean the data.
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

        # Remove rows with missing group data.
        df_latest = df_latest[df_latest[group_col].notna()]
        # Group scraped data and compute average price.
        grouped = df_latest.groupby(group_col)['price'].mean().reset_index()
        grouped.rename(columns={'price': 'avg_price'}, inplace=True)
        grouped['avg_price'] = grouped['avg_price'].round(2)
    else:
        flash("No data found in the database.")

    # 4. Determine which GeoJSON file to use based on level.
    level = request.args.get('level', '1')
    if level not in ['1', '2', '3']:
        level = '1'
    geo_filename = f"gadm41_PRT_{level}.json"
    geojson_path = os.path.join(app.static_folder, 'geo', geo_filename)
    try:
        with open(geojson_path, 'r', encoding='utf-8') as f:
            geojson_data = json.load(f)
    except Exception as e:
        flash("Error loading GeoJSON file: " + str(e))
        geojson_data = {}

    # 5. Build a DataFrame from the GeoJSON file features.
    # Extract the region name from each feature using the corresponding key.
    geo_features = geojson_data.get("features", [])
    geo_regions = []
    # e.g., 'NAME_1', 'NAME_2', or 'NAME_3'
    prop_key = feature_key.split(".")[-1]
    for feature in geo_features:
        props = feature.get("properties", {})
        region_name = props.get(prop_key)
        if region_name:
            geo_regions.append(region_name)
    df_geo = pd.DataFrame({group_col: geo_regions}).drop_duplicates()

    # 6. Merge the complete list from the GeoJSON with the scraped data.
    if not df_geo.empty:
        if not grouped.empty:
            merged = pd.merge(df_geo, grouped, on=group_col, how='left')
        else:
            merged = df_geo.copy()
        # Initialize missing prices with 0.
        merged['avg_price'] = merged['avg_price'].fillna(0)
    else:
        merged = pd.DataFrame({group_col: [], 'avg_price': []})

    # 7. Create the choropleth map using Plotly Express.
    if latest_date:
        title = f"Average Apartment Prices by {group_label} (Data as of {latest_date.strftime('%Y-%m-%d')})"
    else:
        title = f"Average Apartment Prices by {group_label}"
    fig = px.choropleth(
        data_frame=merged,
        geojson=geojson_data,
        locations=group_col,
        featureidkey=feature_key,
        color='avg_price',
        color_continuous_scale="Viridis",
        labels={'avg_price': 'Avg Price (€)'},
        title=title
    )
    fig.update_geos(fitbounds="locations", visible=False)
    fig.update_layout(margin={"r": 0, "t": 30, "l": 0, "b": 0})
    map_div = pyo.plot(fig, output_type='div', include_plotlyjs='cdn')

    return render_template('index.html', map_div=map_div)


if __name__ == '__main__':
    app.run(debug=True)
