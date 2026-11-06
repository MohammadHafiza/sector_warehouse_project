import os
import streamlit as st
import plotly.express as px
from etl_pipeline import build_star_schema
from olap_engine import MarketOLAPEngine

st.set_page_config(
    page_title="Intelligent Multi-Year Sector Trend Analytics",
    page_icon="📈",
    layout="wide"
)

if not os.path.exists("warehouse.db"):
    with st.spinner("Initializing Data Warehouse Star Schema & Ingesting Data..."):
        build_star_schema()

engine = MarketOLAPEngine()
sectors = engine.get_sectors()
min_year, max_year = engine.get_year_range()

st.title("📈 Multi-Year Sector-Wise Trend Comparison System")
st.caption("Time-Series Data Warehouse & Multidimensional OLAP Cube Analytics")

st.sidebar.header("OLAP Cube Slicing & Dicing")

selected_years = st.sidebar.slider(
    "Select Year Range:",
    min_value=min_year,
    max_value=max_year,
    value=(min_year, max_year)
)

selected_sectors = st.sidebar.multiselect(
    "Select Sectors (Dice):",
    options=sectors,
    default=sectors
)

if not selected_sectors:
    st.warning("Please select at least one sector from the sidebar.")
    st.stop()

tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Trend Comparison (Dice)",
    "🔲 Analytical Heatmap (Pivot)",
    "🔍 Granular Drill-Down",
    "🏛 Warehouse Architecture"
])

with tab1:
    st.subheader("Multi-Year Annualized Performance by Sector")
    diced_data = engine.dice_multi_year_sector_cube(
        selected_sectors, selected_years[0], selected_years[1]
    )

    col1, col2 = st.columns([2, 1])

    with col1:
        fig_trend = px.line(
            diced_data,
            x="year",
            y="annualized_return_pct",
            color="sector_name",
            markers=True,
            title="Sector Annualized Return Trend (%)",
            labels={"annualized_return_pct": "Annualized Return (%)", "year": "Year", "sector_name": "Sector"}
        )
        fig_trend.update_layout(hovermode="x unified")
        st.plotly_chart(fig_trend, use_container_width=True)

    with col2:
        fig_vol = px.bar(
            diced_data,
            x="year",
            y="total_volume_millions",
            color="sector_name",
            barmode="group",
            title="Traded Volume per Sector (Millions)",
            labels={"total_volume_millions": "Volume (M)"}
        )
        st.plotly_chart(fig_vol, use_container_width=True)

    st.dataframe(diced_data, use_container_width=True)

with tab2:
    st.subheader("OLAP Pivot: Cross-Year Sector Returns Matrix (%)")
    pivot_matrix = engine.pivot_sector_returns_matrix()

    fig_heat = px.imshow(
        pivot_matrix,
        text_auto=True,
        aspect="auto",
        color_continuous_scale="RdYlGn",
        title="Annualized Return Heatmap by Sector"
    )
    st.plotly_chart(fig_heat, use_container_width=True)
    st.markdown("#### Tabular Cube Representation")
    st.dataframe(pivot_matrix.style.format("{:.2f}%"), use_container_width=True)

with tab3:
    st.subheader("OLAP Drill-Down: Sector ➔ Company Equities")
    d_col1, d_col2 = st.columns(2)
    with d_col1:
        target_sector = st.selectbox("Select Sector to Drill Down:", options=sectors)
    with d_col2:
        target_year = st.selectbox("Select Year:", options=list(range(min_year, max_year + 1)))

    company_breakdown = engine.drilldown_sector_to_companies(target_sector, target_year)

    if not company_breakdown.empty:
        fig_bar = px.bar(
            company_breakdown,
            x="ticker",
            y="annualized_return_pct",
            color="annualized_return_pct",
            color_continuous_scale="Viridis",
            title=f"Constituent Equities Performance for {target_sector} ({target_year})"
        )
        st.plotly_chart(fig_bar, use_container_width=True)
        st.dataframe(company_breakdown, use_container_width=True)
    else:
        st.info("No records found for the selected combination.")

with tab4:
    st.subheader("Star Schema Physical Model")
    st.code("""
  +--------------------+        +------------------------------+        +--------------------+
  |      Dim_Date      |        | Fact_DailyStockPerformance   |        |    Dim_Company     |
  +--------------------+        +------------------------------+        +--------------------+
  | date_key (PK)      |<-------| fact_id (PK)                 |------->| company_key (PK)   |
  | full_date          |        | date_key (FK)                |        | ticker             |
  | calendar_year      |        | company_key (FK)             |        | company_name       |
  | calendar_quarter   |        | sector_key (FK)              |----+   | sector_key (FK)    |
  | calendar_month     |        | open_price                   |    |   +--------------------+
  | month_name         |        | high_price                   |    |
  | day_of_week        |        | low_price                    |    |
  +--------------------+        | close_price                  |    |   +--------------------+
                                | volume                       |    +-->|     Dim_Sector     |
                                | daily_return                 |        +--------------------+
                                | traded_value                 |        | sector_key (PK)    |
                                +------------------------------+        | sector_name        |
                                                                        +--------------------+
    """, language="text")