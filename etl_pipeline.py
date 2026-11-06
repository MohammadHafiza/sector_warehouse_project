import sqlite3
import numpy as np
import pandas as pd


def generate_mock_stock_history():
    np.random.seed(42)
    dates = pd.date_range(start="2018-01-01", end="2023-12-31", freq="B")

    companies = [
        {"ticker": "NVDA", "name": "NVIDIA Corp", "sector": "Technology"},
        {"ticker": "AAPL", "name": "Apple Inc", "sector": "Technology"},
        {"ticker": "MSFT", "name": "Microsoft Corp", "sector": "Technology"},
        {"ticker": "JNJ", "name": "Johnson & Johnson", "sector": "Healthcare"},
        {"ticker": "PFE", "name": "Pfizer Inc", "sector": "Healthcare"},
        {"ticker": "XOM", "name": "ExxonMobil", "sector": "Energy"},
        {"ticker": "CVX", "name": "Chevron Corp", "sector": "Energy"},
        {"ticker": "JPM", "name": "JPMorgan Chase", "sector": "Financials"},
        {"ticker": "BAC", "name": "Bank of America", "sector": "Financials"},
        {"ticker": "AMZN", "name": "Amazon.com Inc", "sector": "Consumer Discretionary"},
    ]

    sector_drifts = {
        "Technology": 0.00065,
        "Healthcare": 0.00028,
        "Energy": 0.00035,
        "Financials": 0.00030,
        "Consumer Discretionary": 0.00045,
    }

    records = []
    for comp in companies:
        base_price = np.random.uniform(70.0, 180.0)
        drift = sector_drifts[comp["sector"]]
        volatility = 0.016

        for d in dates:
            ret = np.random.normal(drift, volatility)
            base_price = max(5.0, base_price * (1 + ret))
            high_p = base_price * (1 + abs(np.random.normal(0, 0.008)))
            low_p = base_price * (1 - abs(np.random.normal(0, 0.008)))
            open_p = low_p + (high_p - low_p) * np.random.uniform(0.2, 0.8)
            close_p = base_price
            volume = int(np.random.uniform(500_000, 12_000_000))

            records.append({
                "date": d,
                "ticker": comp["ticker"],
                "company_name": comp["name"],
                "sector": comp["sector"],
                "open": round(open_p, 2),
                "high": round(high_p, 2),
                "low": round(low_p, 2),
                "close": round(close_p, 2),
                "adj_close": round(close_p, 2),
                "volume": volume,
                "daily_return": round(ret, 5),
                "traded_value": round(close_p * volume, 2)
            })

    return pd.DataFrame(records)


def build_star_schema(db_path="warehouse.db"):
    raw_df = generate_mock_stock_history()
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.executescript("""
    DROP TABLE IF EXISTS Fact_DailyStockPerformance;
    DROP TABLE IF EXISTS Dim_Date;
    DROP TABLE IF EXISTS Dim_Sector;
    DROP TABLE IF EXISTS Dim_Company;
    """)

    cur.execute("""
    CREATE TABLE Dim_Sector (
        sector_key INTEGER PRIMARY KEY AUTOINCREMENT,
        sector_name TEXT UNIQUE NOT NULL
    );
    """)

    cur.execute("""
    CREATE TABLE Dim_Company (
        company_key INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT UNIQUE NOT NULL,
        company_name TEXT NOT NULL,
        sector_key INTEGER,
        FOREIGN KEY (sector_key) REFERENCES Dim_Sector(sector_key)
    );
    """)

    cur.execute("""
    CREATE TABLE Dim_Date (
        date_key INTEGER PRIMARY KEY,
        full_date TEXT NOT NULL,
        calendar_year INTEGER NOT NULL,
        calendar_quarter INTEGER NOT NULL,
        calendar_month INTEGER NOT NULL,
        month_name TEXT NOT NULL,
        day_of_week TEXT NOT NULL
    );
    """)

    cur.execute("""
    CREATE TABLE Fact_DailyStockPerformance (
        fact_id INTEGER PRIMARY KEY AUTOINCREMENT,
        date_key INTEGER NOT NULL,
        company_key INTEGER NOT NULL,
        sector_key INTEGER NOT NULL,
        open_price REAL,
        high_price REAL,
        low_price REAL,
        close_price REAL,
        volume INTEGER,
        daily_return REAL,
        traded_value REAL,
        FOREIGN KEY (date_key) REFERENCES Dim_Date(date_key),
        FOREIGN KEY (company_key) REFERENCES Dim_Company(company_key),
        FOREIGN KEY (sector_key) REFERENCES Dim_Sector(sector_key)
    );
    """)

    sectors = sorted(raw_df["sector"].unique())
    cur.executemany("INSERT INTO Dim_Sector (sector_name) VALUES (?)", [(s,) for s in sectors])
    sector_map = {row[1]: row[0] for row in cur.execute("SELECT sector_key, sector_name FROM Dim_Sector").fetchall()}

    companies = raw_df[["ticker", "company_name", "sector"]].drop_duplicates()
    for _, row in companies.iterrows():
        cur.execute(
            "INSERT INTO Dim_Company (ticker, company_name, sector_key) VALUES (?, ?, ?)",
            (row["ticker"], row["company_name"], sector_map[row["sector"]])
        )
    company_map = {row[1]: row[0] for row in cur.execute("SELECT company_key, ticker FROM Dim_Company").fetchall()}

    dates_df = raw_df[["date"]].drop_duplicates().copy()
    dates_df["date_key"] = dates_df["date"].dt.strftime("%Y%m%d").astype(int)
    dates_df["full_date"] = dates_df["date"].dt.strftime("%Y-%m-%d")
    dates_df["year"] = dates_df["date"].dt.year
    dates_df["quarter"] = dates_df["date"].dt.quarter
    dates_df["month"] = dates_df["date"].dt.month
    dates_df["month_name"] = dates_df["date"].dt.strftime("%B")
    dates_df["day_name"] = dates_df["date"].dt.strftime("%A")

    date_rows = [
        (int(r["date_key"]), r["full_date"], int(r["year"]), int(r["quarter"]), int(r["month"]), r["month_name"], r["day_name"])
        for _, r in dates_df.iterrows()
    ]
    cur.executemany("""
    INSERT INTO Dim_Date (date_key, full_date, calendar_year, calendar_quarter, calendar_month, month_name, day_of_week)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, date_rows)

    raw_df["date_key"] = raw_df["date"].dt.strftime("%Y%m%d").astype(int)
    raw_df["company_key"] = raw_df["ticker"].map(company_map)
    raw_df["sector_key"] = raw_df["sector"].map(sector_map)

    fact_records = raw_df[[
        "date_key", "company_key", "sector_key", "open", "high", "low", "close", "volume", "daily_return", "traded_value"
    ]].values.tolist()

    cur.executemany("""
    INSERT INTO Fact_DailyStockPerformance (
        date_key, company_key, sector_key, open_price, high_price, low_price, close_price, volume, daily_return, traded_value
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, fact_records)

    cur.execute("CREATE INDEX idx_fact_date ON Fact_DailyStockPerformance(date_key);")
    cur.execute("CREATE INDEX idx_fact_sector ON Fact_DailyStockPerformance(sector_key);")
    cur.execute("CREATE INDEX idx_fact_company ON Fact_DailyStockPerformance(company_key);")

    conn.commit()
    conn.close()
    print("ETL complete. Star schema populated in warehouse.db successfully.")


if __name__ == "__main__":
    build_star_schema()