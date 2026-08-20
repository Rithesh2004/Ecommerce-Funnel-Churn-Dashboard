import sqlite3
import pandas as pd
import os

def export_queries_to_csv():
    db_path = "ecommerce.db"
    if not os.path.exists(db_path):
        print(f"Error: {db_path} not found. Please run clean_and_ingest.py first.")
        return

    conn = sqlite3.connect(db_path)
    print("Connected to database. Exporting query results to CSV...")

    # 1. Funnel Conversion Rate Query
    q1 = """
    WITH stage_counts AS (
        SELECT 
            funnel_stage,
            COUNT(DISTINCT user_id) AS unique_users
        FROM ecommerce_funnel
        GROUP BY funnel_stage
    ),
    stage_ordered AS (
        SELECT 
            funnel_stage,
            unique_users,
            CASE 
                WHEN funnel_stage = '1_Landing' THEN 1
                WHEN funnel_stage = '2_Product_View' THEN 2
                WHEN funnel_stage = '3_Add_to_Cart' THEN 3
                WHEN funnel_stage = '4_Purchase' THEN 4
                ELSE 5
            END AS stage_order
        FROM stage_counts
    )
    SELECT 
        funnel_stage,
        unique_users,
        LAG(unique_users, 1) OVER (ORDER BY stage_order) AS previous_stage_users,
        ROUND((unique_users * 100.0) / LAG(unique_users, 1) OVER (ORDER BY stage_order), 2) AS pct_conversion_from_previous,
        ROUND(100.0 - ((unique_users * 100.0) / LAG(unique_users, 1) OVER (ORDER BY stage_order)), 2) AS pct_drop_off_from_previous,
        FIRST_VALUE(unique_users) OVER (ORDER BY stage_order) AS landing_users,
        ROUND((unique_users * 100.0) / FIRST_VALUE(unique_users) OVER (ORDER BY stage_order), 2) AS pct_overall_conversion
    FROM stage_ordered
    ORDER BY stage_order;
    """
    df1 = pd.read_sql_query(q1, conn)
    df1.to_csv("funnel_conversion_rate.csv", index=False)
    print("[OK] Exported: funnel_conversion_rate.csv")

    # 2. Time-to-Purchase Query
    q2 = """
    WITH landing_purchase_events AS (
        SELECT 
            user_id,
            session_id,
            funnel_stage,
            timestamp,
            LEAD(timestamp) OVER (PARTITION BY session_id ORDER BY timestamp) AS next_event_time,
            LEAD(funnel_stage) OVER (PARTITION BY session_id ORDER BY timestamp) AS next_event_stage
        FROM ecommerce_funnel
        WHERE funnel_stage IN ('1_Landing', '4_Purchase')
    ),
    session_durations AS (
        SELECT 
            user_id,
            session_id,
            timestamp AS landing_time,
            next_event_time AS purchase_time,
            (julianday(next_event_time) - julianday(timestamp)) * 86400.0 AS time_to_purchase_seconds
        FROM landing_purchase_events
        WHERE funnel_stage = '1_Landing' 
          AND next_event_stage = '4_Purchase'
    )
    SELECT 
        COUNT(session_id) AS total_purchasing_sessions,
        ROUND(AVG(time_to_purchase_seconds) / 60.0, 2) AS avg_time_to_purchase_minutes,
        ROUND(MIN(time_to_purchase_seconds) / 60.0, 2) AS min_time_to_purchase_minutes,
        ROUND(MAX(time_to_purchase_seconds) / 60.0, 2) AS max_time_to_purchase_minutes
    FROM session_durations;
    """
    df2 = pd.read_sql_query(q2, conn)
    df2.to_csv("time_to_purchase.csv", index=False)
    print("[OK] Exported: time_to_purchase.csv")

    # 3. High-Value Churn Query
    q3 = """
    WITH churned_users AS (
        SELECT DISTINCT user_id 
        FROM ecommerce_funnel 
        WHERE funnel_stage = '3_Add_to_Cart'
          AND user_id NOT IN (
              SELECT DISTINCT user_id 
              FROM ecommerce_funnel 
              WHERE funnel_stage = '4_Purchase'
          )
    ),
    category_avg_purchase AS (
        SELECT 
            category,
            AVG(purchase_amount) AS avg_purchase_val
        FROM ecommerce_funnel
        WHERE funnel_stage = '4_Purchase'
        GROUP BY category
    )
    SELECT 
        c.user_id,
        f.category,
        COUNT(DISTINCT f.session_id) AS total_abandoned_sessions,
        MAX(f.timestamp) AS last_activity_time,
        ROUND(cav.avg_purchase_val, 2) AS estimated_lost_revenue_usd
    FROM churned_users c
    JOIN ecommerce_funnel f ON c.user_id = f.user_id
    JOIN category_avg_purchase cav ON f.category = cav.category
    WHERE f.funnel_stage = '3_Add_to_Cart'
    GROUP BY c.user_id, f.category, cav.avg_purchase_val
    ORDER BY estimated_lost_revenue_usd DESC, last_activity_time DESC;
    """
    df3 = pd.read_sql_query(q3, conn)
    df3.to_csv("high_value_churn.csv", index=False)
    print("[OK] Exported: high_value_churn.csv")

    conn.close()
    print("All exports completed! You can now load these CSV files directly into Power BI.")

if __name__ == "__main__":
    export_queries_to_csv()
