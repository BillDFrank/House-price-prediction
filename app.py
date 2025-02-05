import os
import folium
import pandas as pd
import psycopg2
from flask import Flask, render_template
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Database connection function


def get_db_connection():
    return psycopg2.connect(
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT")
    )

# Fetch data from PostgreSQL


def fetch_advertisings():
    conn = get_db_connection()
    query = "SELECT title, price, location FROM advertisings;"
    df = pd.read_sql(query, conn)
    conn.close()
    return df

# Create map with advert locations


def generate_map():
    df = fetch_advertisings()
    m = folium.Map(location=[38.7169, -9.1399],
                   zoom_start=12)  # Default to Lisbon

    for _, row in df.iterrows():
        if row['location']:  # Ensure location exists
            folium.Marker(
                location=[float(coord)
                          for coord in row['location'].split(',')],
                popup=f"{row['title']} - €{row['price']}",
                icon=folium.Icon(color="blue")
            ).add_to(m)

    return m._repr_html_()


@app.route("/")
def index():
    map_html = generate_map()
    return render_template("index.html", map_html=map_html)


if __name__ == "__main__":
    app.run(debug=True)
