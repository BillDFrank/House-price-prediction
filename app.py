# app.py
from flask import Flask, render_template, flash, request
import os
import json
import datetime
import pandas as pd
import plotly.express as px
import plotly.offline as pyo

# Import your custom database connector
from ConnectDB import get_data

app = Flask(__name__)
app.secret_key = 'your_generated_secret_key'  # Replace with your secret key

# ----------------------
# Route for the Choropleth Map
# ----------------------


@app.route('/')
def index():
    # 1. Retrieve data from the database using your custom module.
    try:
        # get_data() is assumed to return a DataFrame loaded from your CSV data in the database.
        df = get_data()
    except Exception as e:
        flash("Error retrieving data from the database: " + str(e))
        df = pd.DataFrame()

    if df.empty:
        flash("No data found in the database.")
        data = []
    else:
        # ----------------------
        # 2. Clean the data
        # ----------------------
        # Remove rows where price is "Preço sob consulta"
        df = df[~df["price"].str.contains("Preço sob consulta", na=False)]

        # Clean the price column by removing non-breaking spaces, euro symbol, and thousand separators.
        df["price"] = (
            df["price"]
            .str.replace("\xa0", "", regex=True)
            .str.replace("€", "", regex=True)
            .str.replace(",", "", regex=True)
            .astype(float)
        )

        # Split the location into parts
        df["location"] = df["location"].fillna("")
        df["location_parts"] = df["location"].str.split(",")
        # According to your instructions, we take the last element as state,
        # the second-to-last as city, and the rest as neighborhood.
        df["state"] = df["location_parts"].str[-1].str.strip()
        df["city"] = df["location_parts"].str[-2].str.strip()
        df["neighborhood"] = df["location_parts"].apply(
            lambda x: ", ".join(x[:-2]) if len(x) > 2 else "")
        df.drop(columns=["location_parts", "location",
                "page"], inplace=True, errors='ignore')

        # Clean the rooms column: extract numeric digits and convert to float.
        # (If the column is already numeric, this step might be skipped.)
        df["rooms"] = df["rooms"].astype(
            str).str.extract("(\d+)")[0].astype(float)

        # Convert date_scraped to datetime
        df['date_scraped'] = pd.to_datetime(
            df['date_scraped'], errors='coerce')

        # 3. Filter the DataFrame for the latest scraped date.
        latest_date = df['date_scraped'].max()
        df_latest = df[df['date_scraped'] == latest_date].copy()

        # 4. Group by region (state) and compute average price.
        grouped = df_latest.groupby('state')['price'].mean().reset_index()
        grouped.rename(columns={'price': 'avg_price'}, inplace=True)
        grouped['avg_price'] = grouped['avg_price'].round(2)
        data = grouped.to_dict(orient='records')

    # ----------------------
    # 5. Determine the GeoJSON level from a query parameter.
    # Default to level 1 if not provided.
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

    # ----------------------
    # 6. Create the Choropleth Map using Plotly Express.
    # Ensure the GeoJSON file has a property (here we use 'NAME_1')
    # that matches the 'state' values in our data.
    fig = px.choropleth(
        data_frame=data,
        geojson=geojson_data,
        locations='state',
        # Adjust based on your GeoJSON structure.
        featureidkey='properties.NAME_1',
        color='avg_price',
        color_continuous_scale="Viridis",
        labels={'avg_price': 'Average Price (€)'},
        title="Average Apartment Prices by Region (Data as of " +
        latest_date.strftime('%Y-%m-%d') + ")"
    )
    fig.update_geos(fitbounds="locations", visible=False)
    fig.update_layout(margin={"r": 0, "t": 30, "l": 0, "b": 0})
    map_div = pyo.plot(fig, output_type='div', include_plotlyjs='cdn')

    return render_template('index.html', map_div=map_div)


if __name__ == '__main__':
    app.run(debug=True)
