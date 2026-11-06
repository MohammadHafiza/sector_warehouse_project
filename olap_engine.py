import sqlite3
import pandas as pd


class MarketOLAPEngine:
    def __init__(self, db_path="warehouse.db"):
        self.db_path = db_path

    def _query(self, sql_query, params=()):
        with sqlite3.connect(self.db_path) as conn:
            return pd.read_sql_query(sql_query, conn, params=params)

    def get_sectors(self):
        return self._query("SELECT sector_name FROM Dim_Sector ORDER BY sector_name")["sector_name"].tolist()

    def get_year_range(self):
        df = self._query("SELECT MIN(calendar_year) as min_y, MAX(calendar_year) as max_y FROM Dim_Date")
        return int(df["min_y"][0]), int(df["max_y"][0])

    def rollup_annual_sector_performance(self):
        query = """
        SELECT 
            d.calendar_year AS year,
            s.sector_name,
            ROUND(AVG(f.daily_return) * 252 * 100, 2) AS annualized_return_pct,
            ROUND(AVG(f.daily_return * f.daily_return) * 252, 4) AS annualized_variance,
            ROUND(SUM(f.traded_value) / 1e9, 2) AS total_traded_value_billions,
            COUNT(DISTINCT f.company_key) AS active_companies
        FROM Fact_DailyStockPerformance f
        JOIN Dim_Date d ON f.date_key = d.date_key
        JOIN Dim_Sector s ON f.sector_key = s.sector_key
        GROUP BY d.calendar_year, s.sector_name
        ORDER BY d.calendar_year ASC, annualized_return_pct DESC;
        """
        return self._query(query)

    def dice_multi_year_sector_cube(self, selected_sectors, start_year, end_year):
        placeholders = ",".join(["?"] * len(selected_sectors))
        query = f"""
        SELECT 
            d.calendar_year AS year,
            s.sector_name,
            ROUND(AVG(f.daily_return) * 252 * 100, 2) AS annualized_return_pct,
            ROUND(SUM(f.volume) / 1e6, 2) AS total_volume_millions
        FROM Fact_DailyStockPerformance f
        JOIN Dim_Date d ON f.date_key = d.date_key
        JOIN Dim_Sector s ON f.sector_key = s.sector_key
        WHERE s.sector_name IN ({placeholders})
          AND d.calendar_year BETWEEN ? AND ?
        GROUP BY d.calendar_year, s.sector_name
        ORDER BY d.calendar_year, s.sector_name;
        """
        params = list(selected_sectors) + [start_year, end_year]
        return self._query(query, params=params)

    def drilldown_sector_to_companies(self, sector_name, year):
        query = """
        SELECT 
            c.ticker,
            c.company_name,
            ROUND(AVG(f.daily_return) * 252 * 100, 2) AS annualized_return_pct,
            ROUND(MIN(f.low_price), 2) AS yearly_low,
            ROUND(MAX(f.high_price), 2) AS yearly_high,
            ROUND(AVG(f.close_price), 2) AS avg_price,
            ROUND(SUM(f.traded_value) / 1e9, 3) AS total_value_billions
        FROM Fact_DailyStockPerformance f
        JOIN Dim_Date d ON f.date_key = d.date_key
        JOIN Dim_Company c ON f.company_key = c.company_key
        JOIN Dim_Sector s ON f.sector_key = s.sector_key
        WHERE s.sector_name = ? AND d.calendar_year = ?
        GROUP BY c.ticker, c.company_name
        ORDER BY annualized_return_pct DESC;
        """
        return self._query(query, params=(sector_name, year))

    def pivot_sector_returns_matrix(self):
        df = self.rollup_annual_sector_performance()
        return df.pivot(index="sector_name", columns="year", values="annualized_return_pct")