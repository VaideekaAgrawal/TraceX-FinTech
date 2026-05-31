"""
TraceX — AML Intelligence System
Main Streamlit application entry point.
"""
import streamlit as st
import pandas as pd
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.data_loader import DataLoader, generate_demo_data
from core.graph_engine import TransactionGraph
from core.feature_extractor import FeatureExtractor
from core.ml_detector import AnomalyDetector, FraudClassifier
from core.pattern_detector import PatternDetector
from core.role_classifier import AccountRoleClassifier
from core.speed_analyzer import SpeedAnalyzer
from core.risk_scorer import RiskScorer
from core.profile_analyzer import ProfileAnalyzer
from utils.helpers import format_inr, get_risk_level

st.set_page_config(
    page_title="TraceX — AML Intelligence",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource(show_spinner="Building TraceX analysis engine...")
def build_system(data_source: str, _uploaded_df=None, filepath: str = None):
    """Build the entire analysis pipeline. Cached for performance."""
    loader = DataLoader()

    if data_source == "demo":
        accounts_df, transactions_df = generate_demo_data(
            n_accounts=200, n_transactions=5000, seed=42,
        )
    elif data_source == "ibm_aml" and filepath:
        accounts_df, transactions_df = loader.load("ibm_aml", filepath=filepath)
    elif data_source == "paysim" and filepath:
        accounts_df, transactions_df = loader.load("paysim", filepath=filepath)
    elif data_source == "custom" and _uploaded_df is not None:
        accounts_df, transactions_df = loader.load("custom_csv", dataframe=_uploaded_df)
    else:
        accounts_df, transactions_df = generate_demo_data()

    # Build graph
    graph_engine = TransactionGraph(accounts_df, transactions_df)

    # Feature extraction
    feature_extractor = FeatureExtractor(graph_engine, accounts_df, transactions_df)
    features_df = feature_extractor.extract_all()

    # ML: Anomaly Detection
    anomaly_detector = AnomalyDetector(contamination=0.05)
    anomaly_results = anomaly_detector.fit_predict(features_df)

    # ML: Fraud Classification (supervised — train on is_laundering labels)
    fraud_classifier = FraudClassifier()
    # Build labels from transactions
    fraud_accounts = set(
        transactions_df[transactions_df.get("is_laundering", pd.Series([0])) == 1]["source_account"].unique()
    ) | set(
        transactions_df[transactions_df.get("is_laundering", pd.Series([0])) == 1]["dest_account"].unique()
    )
    labels = pd.Series(
        [1 if acc in fraud_accounts else 0 for acc in features_df.index],
        index=features_df.index,
    )
    if labels.sum() > 0 and labels.sum() < len(labels):
        fraud_metrics = fraud_classifier.train(features_df, labels)
        fraud_results = fraud_classifier.predict(features_df)
    else:
        fraud_metrics = {}
        fraud_results = pd.DataFrame({
            "account_id": features_df.index,
            "fraud_prob": 0.0,
            "fraud_pred": 0,
        })

    # Pattern detection
    pattern_detector = PatternDetector(graph_engine, transactions_df)
    all_patterns = pattern_detector.detect_all()

    # Role classification
    role_classifier = AccountRoleClassifier()
    roles = role_classifier.classify_all(graph_engine)

    # Speed analysis
    speed_analyzer = SpeedAnalyzer()
    speed_alerts = speed_analyzer.get_speed_alerts(graph_engine)

    # Risk scoring
    risk_scorer = RiskScorer()
    risk_scores = risk_scorer.compute_all_scores(
        features_df, anomaly_results, fraud_results, all_patterns, graph_engine,
    )

    # Profile analysis
    profile_analyzer = ProfileAnalyzer(accounts_df, transactions_df)

    return {
        "accounts_df": accounts_df,
        "transactions_df": transactions_df,
        "graph_engine": graph_engine,
        "features_df": features_df,
        "anomaly_results": anomaly_results,
        "fraud_classifier": fraud_classifier,
        "fraud_results": fraud_results,
        "fraud_metrics": fraud_metrics,
        "all_patterns": all_patterns,
        "pattern_detector": pattern_detector,
        "roles": roles,
        "speed_alerts": speed_alerts,
        "risk_scores": risk_scores,
        "risk_scorer": risk_scorer,
        "profile_analyzer": profile_analyzer,
    }


# --- Sidebar ---
st.sidebar.title("🏦 TraceX")
st.sidebar.markdown("**TraceX AML Intelligence**")
st.sidebar.divider()

# Data source selector
data_source = st.sidebar.radio(
    "Data Source",
    ["🏦 Demo (Indian Bank)", "📊 IBM AML Dataset", "💳 PaySim Dataset", "📤 Upload CSV"],
    index=0,
)

filepath = None
uploaded_df = None

if data_source == "📊 IBM AML Dataset":
    filepath = st.sidebar.text_input("Path to IBM AML CSV", value="data/HI-Small_Trans.csv")
    source_key = "ibm_aml"
elif data_source == "💳 PaySim Dataset":
    filepath = st.sidebar.text_input("Path to PaySim CSV", value="data/paysim.csv")
    source_key = "paysim"
elif data_source == "📤 Upload CSV":
    uploaded_file = st.sidebar.file_uploader("Upload transaction CSV", type=["csv"])
    if uploaded_file:
        uploaded_df = pd.read_csv(uploaded_file)
        source_key = "custom"
    else:
        source_key = "demo"
else:
    source_key = "demo"

# Build system
try:
    if source_key == "ibm_aml" and filepath and os.path.isfile(filepath):
        system = build_system("ibm_aml", filepath=filepath)
    elif source_key == "paysim" and filepath and os.path.isfile(filepath):
        system = build_system("paysim", filepath=filepath)
    elif source_key == "custom" and uploaded_df is not None:
        system = build_system("custom", _uploaded_df=uploaded_df)
    else:
        system = build_system("demo")
except Exception as e:
    st.error(f"Error building system: {e}")
    st.info("Falling back to demo data.")
    system = build_system("demo")

# Store in session state
st.session_state["system"] = system

# Sidebar stats
st.sidebar.divider()
st.sidebar.markdown("### 📊 System Stats")
stats = system["graph_engine"].get_stats()
col1, col2 = st.sidebar.columns(2)
col1.metric("Accounts", f"{stats['num_nodes']:,}")
col2.metric("Transactions", f"{stats['num_edges']:,}")

flagged_count = sum(1 for v in system["risk_scores"].values() if v > 50)
critical_count = sum(1 for v in system["risk_scores"].values() if v > 75)
col1.metric("Flagged", flagged_count)
col2.metric("Critical", critical_count, delta=f"+{critical_count}" if critical_count > 0 else None)

st.sidebar.divider()
st.sidebar.markdown("### 🔍 Quick Search")
search_account = st.sidebar.text_input("Account ID", placeholder="e.g. ACC_0001")
if search_account and search_account in system["risk_scores"]:
    risk = system["risk_scores"][search_account]
    level = get_risk_level(risk)
    role = system["roles"].get(search_account, {}).get("role", "NORMAL")
    st.sidebar.markdown(f"**Risk:** {risk:.1f}/100 ({level})")
    st.sidebar.markdown(f"**Role:** {role}")

# --- Main Page ---
st.title("🏦 TraceX — AML Intelligence")
st.markdown(
    "**Graph-first, ML-second, law-enforcement-ready** AML tracking "
    "for Anti-Money Laundering."
)

# Overview metrics
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total Accounts", f"{stats['num_nodes']:,}")
col2.metric("Total Transactions", f"{stats['num_edges']:,}")
col3.metric("Flagged Accounts", flagged_count)
col4.metric("Critical Alerts", critical_count)
col5.metric("Graph Density", f"{stats['density']:.4f}")

st.divider()

# Quick overview tabs
tab1, tab2, tab3 = st.tabs(["📈 Risk Overview", "🔍 Top Alerts", "📊 Model Metrics"])

with tab1:
    from utils.visualization import create_risk_donut, create_alert_timeline
    col1, col2 = st.columns(2)
    with col1:
        fig = create_risk_donut(system["risk_scores"])
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        fig = create_alert_timeline(system["transactions_df"], system["risk_scores"])
        st.plotly_chart(fig, use_container_width=True)

with tab2:
    # Top 10 flagged accounts
    top_flagged = sorted(system["risk_scores"].items(), key=lambda x: x[1], reverse=True)[:10]
    rows = []
    for acc, score in top_flagged:
        role = system["roles"].get(acc, {}).get("role", "NORMAL")
        rows.append({
            "Account": acc,
            "Risk Score": round(score, 1),
            "Level": get_risk_level(score),
            "Role": role,
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

with tab3:
    metrics = system.get("fraud_metrics", {})
    if metrics:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Precision", f"{metrics.get('precision', 0):.3f}")
        col2.metric("Recall", f"{metrics.get('recall', 0):.3f}")
        col3.metric("F1 Score", f"{metrics.get('f1', 0):.3f}")
        col4.metric("AUC-ROC", f"{metrics.get('auc_roc', 0):.3f}")

        st.markdown(f"**Train size:** {metrics.get('train_size', 0)} | "
                    f"**Test size:** {metrics.get('test_size', 0)} | "
                    f"**Positive rate (train):** {metrics.get('positive_rate_train', 0):.3%} | "
                    f"**Positive rate (test):** {metrics.get('positive_rate_test', 0):.3%}")
    else:
        st.info("No labeled data available for supervised model training. "
                "Upload labeled data or use IBM AML dataset.")

st.divider()
st.markdown(
    "👈 **Navigate** using the sidebar pages: Graph Explorer, Anomaly Dashboard, "
    "Pattern Detector, Profile Analyzer, Channel Analytics, FIU Evidence."
)
