import os
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
import sys

def clean_data(file_path):
    print(f"Loading data from {file_path}...")
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found. Please run generate_mock_data.py first.")
        sys.exit(1)
        
    df = pd.read_csv(file_path)
    initial_rows = len(df)
    print(f"Initial row count: {initial_rows}")

    # 1. Remove duplicate rows
    df = df.drop_duplicates()
    dedup_rows = len(df)
    print(f"Removed {initial_rows - dedup_rows} duplicate rows. Remaining: {dedup_rows}")

    # Parse with explicit formats sequentially to prevent Day/Month swapping in mixed formats
    print("Standardizing timestamps...")
    ts_cleaned = pd.to_datetime(df['timestamp'], format='%Y-%m-%d %H:%M:%S', errors='coerce')
    
    mask_nat = ts_cleaned.isna()
    if mask_nat.any():
        ts_cleaned.loc[mask_nat] = pd.to_datetime(df.loc[mask_nat, 'timestamp'], format='%d/%m/%Y %H:%M:%S', errors='coerce')
        
    mask_nat = ts_cleaned.isna()
    if mask_nat.any():
        ts_cleaned.loc[mask_nat] = pd.to_datetime(df.loc[mask_nat, 'timestamp'], format='%Y-%m-%dT%H:%M:%SZ', errors='coerce', utc=True).dt.tz_localize(None)
        
    df['timestamp'] = ts_cleaned
    
    # Check for any unparseable timestamps
    null_ts = df['timestamp'].isnull().sum()
    if null_ts > 0:
        print(f"Warning: {null_ts} timestamps could not be parsed and were set to NaT.")
        # Drop rows with invalid timestamps
        df = df.dropna(subset=['timestamp'])
        print(f"Dropped rows with invalid timestamps. Remaining: {len(df)}")

    # 3. Handle missing values in purchase_amount
    print("Handling missing values in purchase_amount...")
    
    # If funnel stage is not '4_Purchase', set purchase_amount to 0.0
    non_purchase_mask = df['funnel_stage'] != '4_Purchase'
    df.loc[non_purchase_mask, 'purchase_amount'] = 0.0
    
    # If funnel stage is '4_Purchase' and purchase_amount is missing, impute with category mean purchase amount
    purchase_mask = df['funnel_stage'] == '4_Purchase'
    missing_purchase_mask = purchase_mask & df['purchase_amount'].isnull()
    missing_purchase_count = missing_purchase_mask.sum()
    
    if missing_purchase_count > 0:
        print(f"Found {missing_purchase_count} purchases with missing amounts. Imputing using category means...")
        # Calculate mean purchase amount for each category
        category_means = df[purchase_mask].groupby('category')['purchase_amount'].mean()
        print("Category mean purchase amounts for imputation:")
        print(category_means)
        
        # Fill missing values
        for category, mean_val in category_means.items():
            cat_missing_mask = missing_purchase_mask & (df['category'] == category)
            df.loc[cat_missing_mask, 'purchase_amount'] = mean_val
            
    # Final check for missing values
    remaining_missing = df.isnull().sum()
    print("Remaining missing values per column:")
    print(remaining_missing)

    return df

def ingest_to_mysql(df, host, port, user, password, database):
    # Create connection string
    # We use mysql+mysqlconnector dialect
    connection_str = f"mysql+mysqlconnector://{user}:{password}@{host}:{port}/{database}"
    
    # Setup connection engine
    try:
        # First, try to connect to server without specifying the database to create it if it doesn't exist
        temp_engine = create_engine(f"mysql+mysqlconnector://{user}:{password}@{host}:{port}")
        with temp_engine.connect() as conn:
            conn.execute(text(f"CREATE DATABASE IF NOT EXISTS {database}"))
            conn.commit()
        print(f"Database '{database}' verified/created.")
        
        # Now connect to the database itself
        engine = create_engine(connection_str)
        
        print("Ingesting cleaned data into MySQL table 'ecommerce_funnel'...")
        df.to_sql(name='ecommerce_funnel', con=engine, if_exists='replace', index=False)
        print("Data ingestion completed successfully!")
        
    except Exception as e:
        print("\n" + "="*60)
        print("DATABASE INGESTION ERROR:")
        print(e)
        print("="*60)
        print("\nTroubleshooting tips:")
        print("1. Is the MySQL service running? If not, run standard admin command or start it from Windows Services.")
        print("2. Are the connection details correct?")
        print("3. Does the user have permissions to create database/tables?")
        print("\nWriting data to fallback SQLite database 'ecommerce.db' so you can test locally...")
        sqlite_engine = create_engine("sqlite:///ecommerce.db")
        df.to_sql(name='ecommerce_funnel', con=sqlite_engine, if_exists='replace', index=False)
        print("Saved to fallback SQLite database successfully as 'ecommerce.db'.")

if __name__ == "__main__":
    # Load configuration from environment variables or use defaults
    MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_PORT = os.getenv("MYSQL_PORT", "3306")
    MYSQL_USER = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "Rithesh_2512")  # Adjust as necessary
    MYSQL_DB = os.getenv("MYSQL_DB", "ecommerce_analytics")
    
    raw_file = "raw_ecommerce_data.csv"
    
    cleaned_df = clean_data(raw_file)
    
    print("\nAttempting to ingest to MySQL...")
    print(f"Connection Config: Host={MYSQL_HOST}, Port={MYSQL_PORT}, User={MYSQL_USER}, DB={MYSQL_DB}")
    ingest_to_mysql(cleaned_df, MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DB)
