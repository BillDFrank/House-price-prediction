import os
import psycopg2
import pandas as pd
import re
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def connect_to_database():
    """
    Establishes a connection to the Neon PostgreSQL Database using the provided credentials.
    Returns:
        conn (psycopg2.extensions.connection): The database connection object.
    """
    try:
        conn = psycopg2.connect(
            host=os.getenv("PGHOST"),
            database=os.getenv("PGDATABASE"),
            user=os.getenv("PGUSER"),
            password=os.getenv("PGPASSWORD")
        )
        print("✅ Connected to Neon PostgreSQL Database successfully!")
        return conn
    except Exception as e:
        print("❌ Failed to connect:", e)
        return None


def get_last_scraped_page_today(conn, today_str):
    """
    Retrieve the last scraped page for today's date from the advertisings table.

    Args:
        conn (psycopg2.extensions.connection): The database connection object.
        today_str (str): Today's date as a string (e.g., "2025-02-02").

    Returns:
        int: The last scraped page number for today, or 0 if no records exist.
    """
    query = "SELECT MAX(page) FROM advertisings WHERE date_scraped = %s;"
    cursor = conn.cursor()
    cursor.execute(query, (today_str,))
    result = cursor.fetchone()[0]
    return result if result is not None else 0


def save_data_to_db(conn, df):
    cursor = conn.cursor()

    for _, row in df.iterrows():
        # Convert the Area field to float if possible.
        try:
            area_val = float(row['Area']) if row['Area'] else None
        except Exception as e:
            print(f"❌ Error converting area value: {row['Area']} - {e}")
            area_val = None

        # Handle NaN values in the Location column
        location_val = row['Location'] if pd.notna(row['Location']) else None

        cursor.execute("""
            INSERT INTO advertisings 
                (page, url, title, price, location, rooms, area, bathrooms, construction_year, energetic_certificate, date_scraped) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
                       row['Page'],
                       row['URL'],
                       row['Title'],
                       row['Price'],
                       location_val,
                       row['Rooms'],
                       area_val,        # Now using the converted area value
                       None,            # Bathrooms (to be filled later)
                       # Construction year (to be filled later)
                       None,
                       # Energetic certificate (to be filled later)
                       None,
                       row['ScrapeDate']
                       )
    conn.commit()
    print(f"✅ {len(df)} rows inserted successfully!")


def convert_to_int(val):
    """
    Attempts to extract the first integer from a string.
    Returns:
        int if conversion is possible; otherwise, None.
    """
    if not isinstance(val, str):
        return None
    # Try direct conversion
    try:
        return int(val)
    except:
        pass
    # Otherwise, extract digits using regex
    match = re.search(r'\d+', val)
    if match:
        return int(match.group())
    return None


def update_details_in_db(conn, record_id, bathrooms, construction_year, energetic_certificate):
    """
    Update additional detail fields for a given advertising record.

    Args:
        conn (psycopg2.extensions.connection): The database connection object.
        record_id (int): The ID of the record to update.
        bathrooms (str): The scraped bathroom information.
        construction_year (str): The scraped construction year.
        energetic_certificate (str): The scraped energetic certificate.
    """
    # Convert bathrooms and construction_year to integers, if possible
    b_val = convert_to_int(
        bathrooms) if bathrooms and bathrooms.upper() != "N/A" else None
    cy_val = convert_to_int(
        construction_year) if construction_year and construction_year.upper() != "N/A" else None

    # For energetic_certificate, if the value is "N/A", set to None;
    # otherwise, truncate to 10 characters (adjust max length as needed).
    ec_val = energetic_certificate if energetic_certificate and energetic_certificate.upper() != "N/A" else None
    if ec_val and len(ec_val) > 10:
        ec_val = ec_val[:10]

    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE advertisings
            SET bathrooms = %s, construction_year = %s, energetic_certificate = %s
            WHERE id = %s
        """, (b_val, cy_val, ec_val, record_id))
        conn.commit()
    except Exception as e:
        print(f"❌ Error updating record {record_id}: {e}")


def get_data(date_str=None):
    """
    Retrieve data from the advertisings table. If a date is provided, filter by date_scraped.

    Args:
        date_str (str, optional): The date (format: "YYYY-MM-DD") to filter the records. Defaults to None.

    Returns:
        pd.DataFrame: A DataFrame containing the retrieved records.
    """
    conn = connect_to_database()
    if conn is None:
        print("❌ Database connection failed. Exiting.")
        return pd.DataFrame()

    query = "SELECT * FROM advertisings"
    params = []

    if date_str:
        query += " WHERE date_scraped = %s"
        params.append(date_str)

    try:
        df = pd.read_sql(query, conn, params=params)
        print(
            f"✅ Retrieved {len(df)} records{' for date ' + date_str if date_str else ''}.")
    except Exception as e:
        print(f"❌ Error retrieving data: {e}")
        df = pd.DataFrame()
    finally:
        conn.close()

    return df


def send_dataframe_to_sql(df):
    """
    Sends the entire DataFrame to the PostgreSQL database in bulk.

    Args:
        df (pd.DataFrame): The DataFrame containing the data to be inserted.
    """
    from sqlalchemy import create_engine
    try:
        # Create SQLAlchemy engine using environment variables
        engine = create_engine(
            f'postgresql+psycopg2://{os.getenv("PGUSER")}:{os.getenv("PGPASSWORD")}'
            f'@{os.getenv("PGHOST")}/{os.getenv("PGDATABASE")}'
        )

        # Prepare DataFrame: Drop 'id' column and handle data types
        df_to_insert = df.drop(columns=['id']).copy()

        # Convert date_scraped to datetime
        df_to_insert['date_scraped'] = pd.to_datetime(
            df_to_insert['date_scraped'])

        # Convert float columns to nullable integers where appropriate
        for col in ['bathrooms', 'construction_year']:
            df_to_insert[col] = df_to_insert[col].astype(pd.Int64Dtype())

        # Truncate energetic_certificate to 10 characters
        df_to_insert['energetic_certificate'] = df_to_insert['energetic_certificate'].str[:10]

        # Insert data
        df_to_insert.to_sql(
            name='advertisings',
            con=engine,
            if_exists='append',
            index=False,
            method='multi'
        )
        print(
            f"✅ Successfully inserted {len(df_to_insert)} rows into the database.")
    except Exception as e:
        print(f"❌ Error inserting data: {e}")
    finally:
        if 'engine' in locals():
            engine.dispose()


def get_states_list():
    """
    Retrieve a DataFrame with all states from the 'state' table.
    Expected columns: id, state_name
    """
    conn = connect_to_database()
    if conn is None:
        return pd.DataFrame()
    query = "SELECT id, state_name FROM state"
    try:
        df_states = pd.read_sql(query, conn)
    except Exception as e:
        print("❌ Error retrieving states:", e)
        df_states = pd.DataFrame()
    finally:
        conn.close()
    return df_states


def get_cities_list():
    """
    Retrieve a DataFrame with all cities from the 'city' table.
    Expected columns: id, id_state, city_name
    """
    conn = connect_to_database()
    if conn is None:
        return pd.DataFrame()
    query = "SELECT id, id_state, city_name FROM city"
    try:
        df_cities = pd.read_sql(query, conn)
    except Exception as e:
        print("❌ Error retrieving cities:", e)
        df_cities = pd.DataFrame()
    finally:
        conn.close()
    return df_cities


def get_neighborhoods_list():
    """
    Retrieve a DataFrame with all neighborhoods from the 'neighborhood' table.
    Expected columns: id, id_city, neighborhood_name
    """
    conn = connect_to_database()
    if conn is None:
        return pd.DataFrame()
    query = "SELECT id, id_city, neighborhood_name FROM neighborhood"
    try:
        df_neighborhoods = pd.read_sql(query, conn)
    except Exception as e:
        print("❌ Error retrieving neighborhoods:", e)
        df_neighborhoods = pd.DataFrame()
    finally:
        conn.close()
    return df_neighborhoods
