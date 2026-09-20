import streamlit as st
import pandas as pd
import os
from pathlib import Path
import altair as alt
import dashboard_content
import dashboard_evidence

PROJECT_ROOT = Path(__file__).resolve().parent
ARTIFACTS_ROOT = PROJECT_ROOT / "artifacts"
RUNS_ROOT = PROJECT_ROOT / "artifacts" / "runs"
LEGACY_OUTPUT = PROJECT_ROOT / "dremel_final_output.csv"

# 1. Page Configuration
st.set_page_config(page_title="Dremel Trend Engine", page_icon="⚙️", layout="wide")

# 2. Vibrant Dremel Corporate CSS & TRUNCATION FIX
st.markdown("""
    <style>
    /* Primary Generate Button Styling */
    .stButton>button { 
        width: 100%; 
        border-radius: 6px; 
        font-weight: bold; 
        background-color: #005b9f; 
        color: #ffffff;
        border: 2px solid #005b9f;
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        background-color: #00467f; 
        border-color: #00467f;
        color: #ffffff;
    }
    
    /* Download Button Styling */
    .stDownloadButton>button { 
        width: 100%; 
        border-radius: 6px; 
        background-color: #1e2130; 
        color: white; 
        font-weight: bold;
    }
    
    /* Vibrant KPI Card Styling */
    [data-testid="stMetric"] {
        background-color: #f0f7fb; 
        border-top: 6px solid #005b9f; 
        padding: 20px;
        border-radius: 8px;
        box-shadow: 0 4px 6px rgba(0,91,159,0.08); 
    }
    
    /* FIX FOR TRUNCATED TEXT: Forces text to wrap instead of showing '...' */
    [data-testid="stMetricValue"] > div {
        white-space: normal !important; 
        overflow: visible !important;
        text-overflow: clip !important;
        line-height: 1.2 !important;
        font-size: 1.6rem !important;
        padding-bottom: 5px;
        color: #005b9f !important;
        font-weight: 800 !important;
    }
    
    /* Custom colored divider */
    hr {
        border-top: 2px solid #e0e6ed;
    }
    
    /* Sidebar styling to make it pop */
    [data-testid="stSidebar"] {
        background-color: #ffffff;
        border-right: 1px solid #e0e6ed;
    }
    </style>
""", unsafe_allow_html=True)

# --- PERFORMANCE CACHING ---
@st.cache_data
def load_data(path, file_version):
    try:
        df = pd.read_csv(path)
        return dashboard_evidence.validate_dashboard_dataframe(df)
    except Exception:
        return pd.DataFrame()

def file_version(path):
    try:
        stat = os.stat(path)
        return (stat.st_mtime_ns, stat.st_size)
    except OSError:
        return None


evidence_context = dashboard_evidence.load_latest_evidence(RUNS_ROOT)
if evidence_context:
    data_path = evidence_context["dashboard_snapshot"]
elif dashboard_evidence.latest_pointer_exists(RUNS_ROOT):
    st.error(
        "The latest evidence bundle failed validation. "
        "The dashboard stopped rather than falling back to mutable legacy data."
    )
    st.stop()
else:
    data_path = LEGACY_OUTPUT
df = load_data(str(data_path), file_version(data_path))
if evidence_context and "video_id" in df.columns:
    df["source_url"] = df["video_id"].map(evidence_context["source_urls"])
maya_brief = (
    dashboard_content.load_maya_brief(ARTIFACTS_ROOT, evidence_context["run_id"])
    if evidence_context
    else None
)

if df.empty:
    st.error("Data pipeline empty. Please run main.py to generate the dataset.")
    st.stop()

# --- INITIALIZE SESSION STATE ---
if "generated_brief" not in st.session_state:
    st.session_state.generated_brief = None
if "current_trend" not in st.session_state:
    st.session_state.current_trend = None

# --- SIDEBAR: THE CONTROL CENTER ---
with st.sidebar:
    # Restored Local Image Handling
    try:
        st.image(str(PROJECT_ROOT / "dremel_logo.png"), width="stretch")
    except Exception:
        st.error("⚠️ dremel_logo.png not found. Please ensure the transparent PNG is saved in the same directory as app.py.")
        
    st.write("") 
    st.markdown("### 🎛️ Strategy Controls")
    st.divider()
    
    st.markdown("**1. Select Target Market Trend**")
    selected_trend = st.selectbox("Active Signals:", df['action_pair'].tolist(), label_visibility="collapsed")
    selected_row = df[df["action_pair"] == selected_trend].iloc[0]
    brief_matches_selection = bool(
        maya_brief
        and "video_id" in selected_row
        and selected_row["video_id"] == maya_brief["candidate_id"]
    )
    
    st.markdown("**2. Open Maya Brief**")
    generate_btn = st.button(
        "Open Content Brief",
        disabled=not brief_matches_selection,
        help=(
            "A Maya brief is not available for this selected trend."
            if not brief_matches_selection
            else None
        ),
    )
    
    st.divider()
    st.caption("🟢 Engine Status: ONLINE")
    st.caption("🧠 Content Specialist: Maya")
    st.caption("📍 Market Target: UK Region")

# --- MAIN STAGE: EXECUTIVE DASHBOARD ---
st.title("Predictive Trend Engine")
st.markdown("##### Multimodal Intelligence & Neuromarketing Pipeline")
if evidence_context:
    st.caption(
        f"Evidence collected: {evidence_context['collected_at']} · "
        f"Run: {evidence_context['run_id']} · "
        f"Status: {evidence_context['status']}"
    )
    if evidence_context["partial_failure_count"]:
        st.warning(
            "This dataset is usable but collection was partial. "
            f"Recorded source-level failures: {evidence_context['partial_failure_count']}."
        )
st.write("") 

# KPI Metrics Row
top_trend = df.iloc[0]
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(label="🔥 Top Emerging Trend", value=top_trend['action_pair'].title())
with col2:
    st.metric(label="📈 Peak Velocity", value=f"{top_trend['velocity_score']} V/d", delta="Accelerating", delta_color="normal")
with col3:
    st.metric(label="🧠 Dominant Emotion", value=top_trend['cv_emotion'])
with col4:
    st.metric(label="📡 Market Signals", value=len(df))

st.write("")
st.write("")

# --- THE EXECUTIVE TABBED LAYOUT ---
tab1, tab2, tab3, tab4 = st.tabs(["🤖 Autonomous Content Ideation", "📊 Trend Lifecycle Matrix", "🔍 Raw Intelligence Feed", "🧮 Campaign ROI Estimator"])

# --- TAB 1: THE AI GENERATOR ---
with tab1:
    st.markdown("#### Agentic Strategy Deployment")
    st.caption("Select a validated trend from the sidebar to deploy an Information Gap brief.")
    
    if generate_btn and brief_matches_selection:
        st.session_state.generated_brief = dashboard_content.format_maya_brief(maya_brief)
        st.session_state.current_trend = selected_trend

    if (
        st.session_state.generated_brief
        and st.session_state.current_trend == selected_trend
    ):
        st.success(f"Active Strategy deployed for: {st.session_state.current_trend.title()}")
        st.markdown(st.session_state.generated_brief)
        
        st.download_button(
            label="📥 Download Brief for Marketing Team",
            data=st.session_state.generated_brief,
            file_name=f"Dremel_Brief_{st.session_state.current_trend.replace(' ', '_')}.txt",
            mime="text/plain"
        )
    elif not brief_matches_selection:
        st.info("Maya has not produced a content brief for this trend yet.")

# --- TAB 2: THE VISUAL MATRIX ---
with tab2:
    st.markdown("#### Market Positioning Matrix")
    df['total_engagement'] = df['velocity_score'] * 14 
    scatter_chart = alt.Chart(df).mark_circle(size=250, opacity=0.9).encode(
        x=alt.X('total_engagement:Q', title='Market Share (Estimated Engagement)', axis=alt.Axis(labels=False, grid=False)),
        y=alt.Y('velocity_score:Q', title='Market Growth (Velocity Score)'),
        color=alt.Color('cv_emotion:N', title="Emotional Trigger", scale=alt.Scale(scheme='tableau10')),
        tooltip=['action_pair', 'velocity_score', 'cv_emotion']
    ).interactive().properties(height=400)

    st.altair_chart(scatter_chart, width="stretch")

# --- TAB 3: THE RAW DATA ---
with tab3:
    st.markdown("#### Auditable Intelligence Feed")
    st.caption("Verify the exact thumbnail, NLP action pair, and velocity score for every isolated trend.")
    evidence_columns = ['thumbnail_url', 'action_pair', 'velocity_score', 'cv_emotion', 'cv_color_hex']
    if "source_url" in df.columns:
        evidence_columns.append("source_url")
    st.dataframe(
        df[evidence_columns],
        column_config={
            "thumbnail_url": st.column_config.ImageColumn("Visual Context", help="Thumbnail Preview"),
            "action_pair": st.column_config.TextColumn("Detected Action", max_chars=50),
            "velocity_score": st.column_config.ProgressColumn(
                "Velocity Score",
                format="%.2f",
                min_value=0,
                max_value=float(df['velocity_score'].max())
            ),
            "cv_emotion": st.column_config.TextColumn("Emotional Trigger"),
            "cv_color_hex": st.column_config.TextColumn("Palette"),
            "source_url": st.column_config.LinkColumn("Source video")
        },
        hide_index=True,
        width="stretch"
    )
    
# --- TAB 4: THE CAMPAIGN ROI ESTIMATOR ---
with tab4:
    st.markdown("#### Financial Feasibility & ROI Projections")
    st.caption("Model the fully burdened financial impact, accounting for traffic funnels, promo discounts, and fixed seeding costs.")
    
    fin_col1, fin_col2 = st.columns([1, 1.8])
    
    with fin_col1:
        st.markdown("**1. Acquisition & Fixed Costs**")
        fin_selected_trend = st.selectbox("Target Trend for Financial Model:", df['action_pair'].tolist())
        influencer_views = st.slider("Target Creator Average Views", min_value=10000, max_value=500000, value=150000, step=10000)
        cpm_rate = st.slider("Influencer CPM (£ per 1000 views)", min_value=5, max_value=50, value=20, step=1)
        fixed_costs = st.slider("Fixed Seeding Costs (£)", min_value=0, max_value=1000, value=150, step=50, help="Cost of giving the creator a free tool + shipping/agency fees.")
        
        st.markdown("**2. Funnel Economics**")
        baseline_ctr = st.slider("Baseline Click-Through Rate (CTR %)", min_value=0.1, max_value=5.0, value=1.0, step=0.1)
        website_cvr = st.slider("Website Conversion Rate (CVR %)", min_value=0.5, max_value=5.0, value=2.0, step=0.1)
        
        st.markdown("**3. Margin & Promotions**")
        tool_retail_price = st.slider("Avg. Dremel Retail Price (£)", min_value=30, max_value=150, value=70, step=5)
        dremel_base_margin = st.slider("Base Tool Margin (£)", min_value=10, max_value=100, value=35, step=5)
        promo_discount = st.slider("Influencer Promo Code Discount (%)", min_value=0, max_value=30, value=10, step=5)
        
        include_clv = st.toggle("Include Year 1 Accessory CLV (+£15/unit)")

    with fin_col2:
        st.markdown("**Projected Outcomes**")
        trend_fin_data = df[df['action_pair'] == fin_selected_trend].iloc[0]
        
        # 1. The Cost Math (Variable + Fixed)
        variable_media_cost = (influencer_views / 1000) * cpm_rate
        total_campaign_cost = variable_media_cost + fixed_costs
        
        # 2. The Traffic Math (Top of Funnel + Trend Lift)
        max_velocity_in_dataset = df['velocity_score'].max()
        trend_velocity = trend_fin_data['velocity_score']
        velocity_lift = (trend_velocity / max_velocity_in_dataset) * 1.5 
        final_ctr = baseline_ctr + velocity_lift
        projected_traffic = influencer_views * (final_ctr / 100)
        
        # 3. The Sales Math (Bottom of Funnel)
        projected_sales_units = projected_traffic * (website_cvr / 100)
        
        # 4. The Margin Math (Accounting for Promo Code Erosion)
        discount_value = tool_retail_price * (promo_discount / 100)
        eroded_margin = dremel_base_margin - discount_value
        actual_unit_margin = eroded_margin + 15 if include_clv else eroded_margin
        
        # 5. Revenue & Profit Math
        projected_revenue = projected_sales_units * actual_unit_margin
        net_profit = projected_revenue - total_campaign_cost
        roi = ((net_profit) / total_campaign_cost) * 100 if total_campaign_cost > 0 else 0
        
        # Display the financial metrics
        f_col1, f_col2, f_col3 = st.columns(3)
        with f_col1:
            st.metric(label="Total Campaign Cost", value=f"£{total_campaign_cost:,.0f}", help="Media Cost + Fixed Seeding Costs")
        with f_col2:
            st.metric(label="Est. Unit Sales", value=f"{int(projected_sales_units):,} units", delta=f"{int(projected_traffic):,} Site Visitors", delta_color="normal")
        with f_col3:
            st.metric(label="Projected Campaign ROI", value=f"{roi:,.0f}%", 
                      delta="Profitable" if roi > 0 else "Negative ROI", 
                      delta_color="normal" if roi > 0 else "inverse")
            
        st.divider()
        st.info(f"**Strategic Takeaway:** By hiring a creator with an audience of {influencer_views:,}, Dremel spends £{total_campaign_cost:,.0f} (Media + Seeding). The high velocity of the **'{fin_selected_trend.title()}'** trend lifts CTR to {final_ctr:.2f}%. Accounting for a {promo_discount}% promo code, our adjusted margin drops to £{actual_unit_margin:.2f}. Even with these strict, fully-burdened parameters, the campaign projects {int(projected_sales_units):,} unit sales and a net profit of £{net_profit:,.0f}.")