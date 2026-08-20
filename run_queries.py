import sqlite3
import pandas as pd

def run_query(conn, query_name, sql):
    print("\n" + "="*50)
    print(f"RUNNING: {query_name}")
    print("="*50)
    try:
        df = pd.read_sql_query(sql, conn)
        print(df.to_string(index=False))
    except Exception as e:
        print(f"Error executing {query_name}: {e}")

if __name__ == "__main__":
    db_path = "ecommerce.db"
    conn = sqlite3.connect(db_path)
    
    # Query 1: Funnel Conversion
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
        ROUND(
            (unique_users * 100.0) / LAG(unique_users, 1) OVER (ORDER BY stage_order), 
            2
        ) AS pct_conversion_from_previous,
        ROUND(
            100.0 - ((unique_users * 100.0) / LAG(unique_users, 1) OVER (ORDER BY stage_order)), 
            2
        ) AS pct_drop_off_from_previous,
        FIRST_VALUE(unique_users) OVER (ORDER BY stage_order) AS landing_users,
        ROUND(
            (unique_users * 100.0) / FIRST_VALUE(unique_users) OVER (ORDER BY stage_order), 
            2
        ) AS pct_overall_conversion
    FROM stage_ordered
    ORDER BY stage_order;
    """
    
    # Query 2: Time-to-Purchase (SQLite version)
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
            -- SQLite timestamp conversion (julianday returns fraction of days, multiply by 86400 to get seconds)
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
    
    # Query 3: High-Value Churn
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
    ORDER BY estimated_lost_revenue_usd DESC, last_activity_time DESC
    LIMIT 10;
    """
    
    run_query(conn, "1. Overall Funnel Conversion Rate", q1)
    run_query(conn, "2. Time-to-Purchase (Window Function)", q2)
    run_query(conn, "3. High-Value Churn (Top 10 Users by Potential Loss)", q3)
    
    conn.close()
