# 🏦 Fund Flow Tracking System — 24-Hour Hackathon Development Plan

> **Project Title:** TraceX — Intelligent Fund Flow Tracking System  
> **Tagline:** "Every rupee leaves a trail. We make it visible."  
> **Duration:** 24 hours | **Team size:** 4 developers + Claude AI pair-programming

---

## 📐 Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                        STREAMLIT UI                              │
│  ┌──────────┐ ┌───────────┐ ┌──────────┐ ┌───────────────────┐  │
│  │ Graph    │ │ Timeline  │ │ Risk     │ │ FIU Evidence      │  │
│  │ Viewer   │ │ Explorer  │ │ Dashboard│ │ Export Panel      │  │
│  │(agraph/  │ │(Plotly    │ │(Metrics +│ │(PDF/JSON one-     │  │
│  │ pyvis)   │ │ timeline) │ │ Sankey)  │ │ click export)     │  │
│  └────┬─────┘ └─────┬─────┘ └────┬─────┘ └────────┬──────────┘  │
│       │             │            │                 │             │
├───────┴─────────────┴────────────┴─────────────────┴─────────────┤
│                     FASTAPI BACKEND                              │
│  ┌──────────────┐ ┌───────────────┐ ┌──────────────────────────┐ │
│  │ Graph Engine │ │ ML Detector   │ │ Evidence Generator       │ │
│  │ (NetworkX    │ │ (XGBoost +    │ │ (FPDF + JSON serializer) │ │
│  │  DiGraph)    │ │  Isolation    │ │                          │ │
│  │              │ │  Forest)      │ │                          │ │
│  └──────┬───────┘ └───────┬───────┘ └──────────┬───────────────┘ │
│         │                 │                    │                 │
├─────────┴─────────────────┴────────────────────┴─────────────────┤
│                    DATA LAYER                                    │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │  Synthetic Transaction Generator (Faker + custom rules)      │ │
│  │  → CSV/Parquet files  → In-memory NetworkX MultiDiGraph      │ │
│  │  → SQLite (optional for persistence)                         │ │
│  └──────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

### Why This Stack (Not Neo4j)?

For a 24-hr hackathon, **Neo4j adds installation/config overhead** that can eat 2–3 hours. Instead:
- **NetworkX** (in-memory graph) gives you cycle detection, PageRank, centrality, shortest paths — all built-in.
- **streamlit-agraph** or **pyvis** renders beautiful interactive graphs directly in Streamlit.
- **No database server to manage** — everything runs from `streamlit run app.py`.
- If judges ask about scalability, you say: *"Production version swaps NetworkX → Neo4j via a graph-abstraction layer. The algorithms are identical."*

---

## 🗂 Final Folder Structure

```
fund-flow-tracker/
├── app.py                          # Streamlit main entry (multipage nav)
├── pages/
│   ├── 1_🔍_Graph_Explorer.py      # Interactive graph visualization
│   ├── 2_⚠️_Anomaly_Dashboard.py   # ML-flagged alerts + risk scores
│   ├── 3_🔄_Pattern_Detector.py    # Layering, cycles, structuring
│   ├── 4_👤_Profile_Analyzer.py    # Dormant account + profile mismatch
│   ├── 5_📊_Channel_Analytics.py   # Sankey diagram + channel heatmap
│   └── 6_📋_FIU_Evidence.py        # One-click evidence pack export
├── core/
│   ├── __init__.py
│   ├── graph_engine.py             # NetworkX graph builder + algorithms
│   ├── data_generator.py           # Synthetic transaction + account data
│   ├── ml_detector.py              # XGBoost + Isolation Forest models
│   ├── pattern_detector.py         # Cycle, layering, structuring detection
│   ├── profile_analyzer.py         # Profile-vs-behavior mismatch
│   ├── risk_scorer.py              # Composite risk scoring engine
│   ├── role_classifier.py          # Account role detection (Source/Mule/Sink)
│   ├── speed_analyzer.py           # Transaction speed alerts + chain velocity
│   └── evidence_generator.py       # PDF/JSON evidence pack builder
├── utils/
│   ├── __init__.py
│   ├── constants.py                # Account types, channels, thresholds
│   ├── helpers.py                  # Formatting, color mapping, etc.
│   └── visualization.py           # Reusable chart/graph components
├── data/
│   ├── synthetic_accounts.csv      # Generated on first run
│   ├── synthetic_transactions.csv  # Generated on first run
│   └── sample_scenarios/           # Pre-built fraud scenarios for demo
│       ├── layering.json
│       ├── round_trip.json
│       └── dormant_activation.json
├── exports/                        # Generated evidence packs land here
├── requirements.txt
├── .streamlit/
│   └── config.toml                 # Theme + wide mode
└── README.md
```

---

## 🕐 SESSION-BY-SESSION PLAN

---

### ⏱ SESSION 1: Foundation & Data Layer (Hours 0–4)

**Goal:** Project scaffolding, synthetic data generation, and the core graph engine — the backbone everything else builds on.

---

#### Task 1.1 — Environment Setup (30 min)

```bash
mkdir fund-flow-tracker && cd fund-flow-tracker
python -m venv venv && source venv/bin/activate

pip install streamlit pandas numpy networkx faker scikit-learn xgboost \
  plotly fpdf2 streamlit-agraph pyvis matplotlib seaborn
```

**Create `requirements.txt`:**
```
streamlit>=1.30.0
pandas>=2.0.0
numpy>=1.24.0
networkx>=3.1
faker>=20.0.0
scikit-learn>=1.3.0
xgboost>=2.0.0
plotly>=5.18.0
fpdf2>=2.7.0
streamlit-agraph>=0.0.45
pyvis>=0.3.2
matplotlib>=3.8.0
seaborn>=0.13.0
```

**Create `.streamlit/config.toml`:**
```toml
[theme]
primaryColor = "#1f77b4"
backgroundColor = "#0e1117"
secondaryBackgroundColor = "#262730"
textColor = "#fafafa"

[server]
maxUploadSize = 200

[browser]
gatherUsageStats = false
```

---

#### Task 1.2 — Constants & Config (30 min)

**File: `utils/constants.py`**

Define all the domain constants that make your prototype feel real:

```python
# Account types found in Indian PSBs
ACCOUNT_TYPES = ["savings", "current", "salary", "NRO", "NRE", "overdraft", "prepaid_card"]

# Transaction channels
CHANNELS = ["net_banking", "mobile_app", "UPI", "NEFT", "RTGS", "IMPS", "ATM", "branch_cash", "cheque"]

# Branch cities (Indian tier-1 and tier-2 for realism)
BRANCH_CITIES = ["Mumbai", "Delhi", "Bengaluru", "Chennai", "Kolkata", "Hyderabad",
                 "Pune", "Ahmedabad", "Jaipur", "Lucknow", "Nagpur", "Indore",
                 "Bhopal", "Surat", "Kochi", "Guwahati"]

# Occupation categories for profile generation
OCCUPATIONS = ["salaried", "self_employed", "business_owner", "professional",
               "retired", "student", "homemaker", "farmer", "NRI"]

# Income brackets (annual, INR)
INCOME_BRACKETS = {
    "low":    (100000, 500000),
    "medium": (500001, 1500000),
    "high":   (1500001, 5000000),
    "very_high": (5000001, 50000000)
}

# Regulatory thresholds (RBI/PMLA guidelines)
REPORTING_THRESHOLD = 1000000      # ₹10 lakh — CTR threshold
STRUCTURING_THRESHOLD = 950000     # Just below ₹10 lakh — structuring signal
SUSPICIOUS_VELOCITY = 5            # Transactions in <10 min window
MAX_DORMANT_DAYS = 180             # 6 months = dormant
```

---

#### Task 1.3 — Synthetic Data Generator (90 min) ⭐ CRITICAL

**File: `core/data_generator.py`**

This is the most important early task. You need **realistic-looking** data with **embedded fraud patterns** so you can demo effectively.

**Generate two datasets:**

1. **Accounts DataFrame** (~500 accounts):
   - `account_id`, `customer_name`, `account_type`, `branch_city`, `occupation`, `income_bracket`, `declared_annual_income`, `account_open_date`, `last_active_date`, `avg_monthly_txn_volume`, `avg_monthly_txn_value`
   
2. **Transactions DataFrame** (~10,000–50,000 transactions):
   - `txn_id`, `timestamp`, `source_account`, `dest_account`, `amount`, `channel`, `txn_type` (credit/debit/transfer), `description`, `branch_id`

**Embedded fraud scenarios (hardcoded into generator):**

| Scenario | What to Generate | Accounts Involved |
|---|---|---|
| **Layering** | 5–7 accounts in a chain; rapid transfers (within 10 min) each reducing amount slightly | ACC_L001 → ACC_L002 → ... → ACC_L006 |
| **Round-tripping** | A → B → C → A cycle, 3 iterations, amounts ~₹4–8 lakh | ACC_R001, ACC_R002, ACC_R003 |
| **Structuring** | One source making 10+ transfers of ₹9.0–9.9 lakh to different accounts | ACC_S001 → many targets |
| **Dormant activation** | Account inactive 8+ months, suddenly 15+ high-value transfers in 3 days | ACC_D001 |
| **Profile mismatch** | Student/homemaker account doing ₹50 lakh+ monthly volume | ACC_P001, ACC_P002 |
| **Normal behavior** | ~90% of accounts with normal, expected transaction patterns | ACC_N001–ACC_N450 |

**Implementation approach:**
```python
# Use Faker for realistic names, dates
# Use numpy random for amounts with realistic distributions
# Hardcode fraud scenarios as specific functions:
#   generate_layering_scenario() → returns accounts + transactions
#   generate_round_trip_scenario() → returns accounts + transactions
#   generate_structuring_scenario() → returns accounts + transactions
#   etc.
# Then mix them into the normal data
```

**Key design decision:** Tag each fraud account with a hidden `is_fraud` flag and `fraud_type` field — you'll use this later for ML training AND for demo purposes (to show the system "discovering" known fraud).

---

#### Task 1.4 — Graph Engine (90 min) ⭐ CRITICAL

**File: `core/graph_engine.py`**

Build the core graph from your transaction data using **NetworkX MultiDiGraph** (directed, allows multiple edges between same pair).

**Core class: `TransactionGraph`**

```python
class TransactionGraph:
    def __init__(self, accounts_df, transactions_df):
        self.G = nx.MultiDiGraph()
        self._build_graph(accounts_df, transactions_df)
    
    def _build_graph(self, accounts_df, transactions_df):
        # Add account nodes with metadata
        # Add transaction edges with timestamp, amount, channel
        pass
    
    # --- Query Methods ---
    def get_fund_trail(self, account_id, direction="both", max_depth=5):
        """BFS/DFS to trace money forward/backward from an account"""
        pass
    
    def get_subgraph(self, account_ids):
        """Extract subgraph involving specific accounts"""
        pass
    
    # --- Analytics Methods ---
    def compute_centrality_scores(self):
        """PageRank, betweenness, in/out degree centrality"""
        pass
    
    def detect_cycles(self, max_length=6):
        """Find all simple cycles up to length k (round-trip detection)"""
        pass
    
    def detect_rapid_chains(self, time_window_minutes=10, min_hops=3):
        """Find transaction chains where money hops 3+ times in <10 min"""
        pass
    
    def get_ego_subgraph(self, account_id, radius=2):
        """Get the local neighborhood of an account"""
        pass
    
    def compute_flow_metrics(self, account_id):
        """Total in-flow, out-flow, net flow, unique counterparties"""
        pass
```

**Algorithms to implement:**
1. **Cycle detection:** `nx.simple_cycles(G)` — filters by cycle length and time window
2. **PageRank:** `nx.pagerank(G)` — accounts that are hubs for fund flow
3. **Betweenness centrality:** `nx.betweenness_centrality(G)` — accounts that act as intermediaries
4. **Connected components:** `nx.weakly_connected_components(G)` — isolated clusters
5. **Fund trail:** Custom BFS with depth limit that follows money forward/backward

---

### ☕ BREAK (15 min)

---

### ⏱ SESSION 2: ML Detection Engine (Hours 4–8)

**Goal:** Build the anomaly detection models that score every account and flag suspicious patterns.

---

#### Task 2.1 — Feature Engineering (60 min)

**File: `core/ml_detector.py` (first half)**

Extract **graph-based + behavioral features** for each account:

| Feature | Description | Source |
|---|---|---|
| `in_degree` | Number of unique incoming counterparties | Graph |
| `out_degree` | Number of unique outgoing counterparties | Graph |
| `total_in_flow` | Sum of all incoming transaction amounts | Graph |
| `total_out_flow` | Sum of all outgoing transaction amounts | Graph |
| `net_flow` | total_in_flow - total_out_flow | Graph |
| `pagerank` | PageRank centrality score | Graph |
| `betweenness` | Betweenness centrality score | Graph |
| `clustering_coeff` | Local clustering coefficient | Graph |
| `avg_txn_amount` | Mean transaction amount | Transactions |
| `std_txn_amount` | Std dev of transaction amounts | Transactions |
| `max_txn_amount` | Maximum single transaction | Transactions |
| `txn_count` | Total number of transactions | Transactions |
| `unique_channels` | Number of distinct channels used | Transactions |
| `channel_entropy` | Shannon entropy of channel distribution | Transactions |
| `velocity_10min` | Max transactions in any 10-min window | Transactions |
| `velocity_1hour` | Max transactions in any 1-hour window | Transactions |
| `near_threshold_count` | Transactions between ₹9–10 lakh | Transactions |
| `dormancy_days` | Days of inactivity before latest burst | Account |
| `income_to_volume_ratio` | Declared income / actual monthly volume | Account + Txn |
| `is_weekend_heavy` | >50% of transactions on weekends | Transactions |
| `night_txn_ratio` | Fraction of transactions between 11PM–5AM | Transactions |

**Implementation:**
```python
class FeatureExtractor:
    def __init__(self, graph_engine, accounts_df, transactions_df):
        ...
    
    def extract_all_features(self) -> pd.DataFrame:
        """Returns a DataFrame with account_id as index and all features as columns"""
        graph_features = self._extract_graph_features()
        behavioral_features = self._extract_behavioral_features()
        profile_features = self._extract_profile_features()
        return pd.concat([graph_features, behavioral_features, profile_features], axis=1)
```

---

#### Task 2.2 — Anomaly Detection Models (90 min)

**File: `core/ml_detector.py` (second half)**

**Two complementary models:**

**Model A — Isolation Forest (Unsupervised)**
- No labels needed — works on the full feature matrix
- Flags accounts that are "outliers" in the feature space
- Good for catching novel/unknown fraud patterns

```python
from sklearn.ensemble import IsolationForest

class AnomalyDetector:
    def __init__(self):
        self.isolation_forest = IsolationForest(
            n_estimators=200,
            contamination=0.05,  # Expect ~5% anomalies
            random_state=42
        )
    
    def fit_predict(self, features_df):
        """Returns anomaly scores (-1 = anomaly, 1 = normal)"""
        scores = self.isolation_forest.fit_predict(features_df)
        anomaly_scores = self.isolation_forest.decision_function(features_df)
        return scores, anomaly_scores
```

**Model B — XGBoost Classifier (Supervised)**
- Uses the `is_fraud` labels from your synthetic data
- Trained to classify accounts as fraud/not-fraud
- Provides **feature importance** for explainability

```python
import xgboost as xgb
from sklearn.model_selection import train_test_split

class FraudClassifier:
    def __init__(self):
        self.model = xgb.XGBClassifier(
            n_estimators=100,
            max_depth=5,
            scale_pos_weight=10,  # Handle class imbalance
            random_state=42
        )
    
    def train(self, features_df, labels):
        X_train, X_test, y_train, y_test = train_test_split(...)
        self.model.fit(X_train, y_train)
        # Return accuracy, precision, recall, F1
    
    def predict_proba(self, features_df):
        """Returns fraud probability for each account"""
        return self.model.predict_proba(features_df)[:, 1]
    
    def get_feature_importance(self):
        """Returns sorted feature importance for explainability"""
        return pd.Series(
            self.model.feature_importances_,
            index=self.feature_names
        ).sort_values(ascending=False)
```

---

#### Task 2.3 — Pattern Detection Module (60 min)

**File: `core/pattern_detector.py`**

Dedicated module for **rule-based + graph-based** pattern detection:

```python
class PatternDetector:
    def __init__(self, graph_engine, transactions_df):
        self.graph = graph_engine
        self.txns = transactions_df
    
    def detect_layering(self, time_window_min=10, min_hops=3, min_amount=100000):
        """
        Find rapid multi-hop chains:
        - 3+ hops within time_window_min
        - Each hop amount > min_amount
        - Decreasing amounts (possible commission extraction)
        Returns: List of layering paths with details
        """
        pass
    
    def detect_round_tripping(self, max_cycle_length=5, time_window_days=30):
        """
        Find cycles where money returns to origin:
        - Use nx.simple_cycles(G) with length filter
        - Filter by time window
        - Calculate net delta (should be near-zero for round-trips)
        Returns: List of cycles with timing and amounts
        """
        pass
    
    def detect_structuring(self, threshold=1000000, margin=0.1, min_count=3):
        """
        Find accounts making multiple transactions just below threshold:
        - Transactions between threshold*(1-margin) and threshold
        - At least min_count such transactions
        - To different destination accounts
        Returns: List of structuring accounts with details
        """
        pass
    
    def detect_dormant_activation(self, dormant_days=180, burst_days=7, min_burst_txns=5):
        """
        Find accounts that were dormant then suddenly active:
        - No transactions for dormant_days
        - Then burst_days with min_burst_txns+ transactions
        Returns: List of dormant-activated accounts
        """
        pass
    
    def get_all_patterns(self):
        """Run all detectors, return consolidated results"""
        return {
            "layering": self.detect_layering(),
            "round_tripping": self.detect_round_tripping(),
            "structuring": self.detect_structuring(),
            "dormant_activation": self.detect_dormant_activation()
        }
```

---

#### Task 2.4 — Risk Scoring Engine (30 min)

**File: `core/risk_scorer.py`**

Composite risk score that combines ML + patterns + graph features:

```python
class RiskScorer:
    def compute_composite_score(self, account_id, ml_score, pattern_flags, graph_metrics):
        """
        Weighted composite score (0–100):
        - ML anomaly score:      30% weight
        - XGBoost fraud prob:    25% weight  
        - Pattern detection:     25% weight (binary flags → 0 or 25)
        - Graph centrality:      10% weight
        - Profile mismatch:      10% weight
        
        Returns: score (0–100), risk_level (LOW/MEDIUM/HIGH/CRITICAL), explanation
        """
        pass
```

Risk levels:
- **0–25:** 🟢 LOW — Normal behavior
- **26–50:** 🟡 MEDIUM — Unusual but may be legitimate
- **51–75:** 🟠 HIGH — Likely suspicious, investigate
- **76–100:** 🔴 CRITICAL — Strong fraud indicators

---

#### Task 2.5 — Fraud Confidence Meter (20 min) 🆕

**Integrate into: `core/risk_scorer.py`**

The risk score alone isn't enough — investigators need to know **how confident** the system is. Add a confidence layer:

```python
def compute_confidence(self, account_id, pattern_results, ml_scores, graph_metrics):
    """
    Confidence = f(number of independent fraud indicators)
    
    Independent indicators:
      1. ML anomaly score above threshold
      2. XGBoost fraud probability > 0.7
      3. Pattern detection hit (layering/cycle/structuring/dormant)
      4. Profile mismatch z-score > 3
      5. Graph centrality anomaly (top 5% PageRank or betweenness)
      6. Transaction velocity anomaly
      7. Repeat behavior detected
    
    Confidence levels:
      - 1 indicator:   LOW    ("Weak signal — may be false positive")
      - 2 indicators:  MEDIUM ("Multiple signals — warrants review")
      - 3+ indicators: HIGH   ("Strong convergent evidence")
    
    Returns: confidence_level, indicator_count, indicator_list
    """
    indicators = []
    if ml_scores['isolation_forest'] < -0.3:
        indicators.append("ML anomaly detection (Isolation Forest)")
    if ml_scores['xgboost_prob'] > 0.7:
        indicators.append("Supervised fraud classifier (XGBoost)")
    if any(pattern_results.values()):
        for ptype, hits in pattern_results.items():
            if hits:
                indicators.append(f"Pattern: {ptype}")
    # ... check profile, centrality, velocity, repeat behavior
    
    count = len(indicators)
    level = "Low" if count <= 1 else "Medium" if count == 2 else "Strong"
    return level, count, indicators
```

**UI Display (in Dashboard + Quick Summary Card):**
```
┌─────────────────────────────────────┐
│  Risk: HIGH (82/100)                │
│  Confidence: Strong ████████░░      │
│  3 independent fraud indicators:    │
│    ✓ ML anomaly detection           │
│    ✓ Pattern: layering              │
│    ✓ Transaction velocity anomaly   │
└─────────────────────────────────────┘
```

**Benefit:** Dramatically reduces false positives. Investigators can prioritize high-risk + high-confidence cases first.

---

#### Task 2.6 — Account Role Classification (25 min) 🆕

**File: `core/role_classifier.py`**

Classify every account into a role based on its position in the fund flow graph:

```python
class AccountRoleClassifier:
    """
    Roles:
      SOURCE  — Origin of funds (high out-flow, low in-flow, few predecessors)
      MULE    — Intermediate routing account (high both in & out, pass-through)
      SINK    — Final destination / withdrawal point (high in-flow, low out-flow)
      NORMAL  — Balanced, typical transaction behavior
    """
    
    def classify_all(self, graph_engine) -> dict:
        """Returns {account_id: role} for all accounts"""
        roles = {}
        G = graph_engine.G
        
        for node in G.nodes():
            in_flow = sum(d['amount'] for _, _, d in G.in_edges(node, data=True))
            out_flow = sum(d['amount'] for _, _, d in G.out_edges(node, data=True))
            in_deg = G.in_degree(node)
            out_deg = G.out_degree(node)
            
            if out_flow > 0 and in_flow / max(out_flow, 1) < 0.2:
                roles[node] = "SOURCE"
            elif in_flow > 0 and out_flow / max(in_flow, 1) < 0.2:
                roles[node] = "SINK"
            elif in_deg >= 2 and out_deg >= 2 and 0.3 < in_flow / max(out_flow, 1) < 3.0:
                roles[node] = "MULE"
            else:
                roles[node] = "NORMAL"
        
        return roles
    
    def get_mule_accounts(self, roles):
        """Mule accounts are high-priority for investigation"""
        return [acc for acc, role in roles.items() if role == "MULE"]
```

**Visual representation in Graph Explorer:**
- 🔵 SOURCE nodes = blue diamond shape
- 🟡 MULE nodes = yellow triangle shape  
- 🔴 SINK nodes = red square shape
- ⚪ NORMAL nodes = grey circle

---

#### Task 2.7 — Transaction Speed Analyzer (20 min) 🆕

**File: `core/speed_analyzer.py`**

```python
class SpeedAnalyzer:
    """
    Measure how quickly money moves across accounts in a chain.
    Categorize: Normal | Fast | Very Fast | Abnormal
    """
    
    SPEED_THRESHOLDS = {
        "Normal":   60,    # > 60 min between hops
        "Fast":     30,    # 10–60 min between hops  
        "Very Fast": 10,   # 2–10 min between hops
        "Abnormal":  2,    # < 2 min between hops
    }
    
    def analyze_chain_speed(self, transaction_chain):
        """
        Input: ordered list of transactions in a chain
        Output: {
            'total_time_minutes': float,
            'avg_hop_time_minutes': float,
            'speed_category': str,
            'total_amount': float,
            'num_hops': int,
            'alert_text': str  # e.g. "₹20L moved across 4 accounts in 7 minutes"
        }
        """
        if len(transaction_chain) < 2:
            return None
        
        timestamps = [t['timestamp'] for t in transaction_chain]
        total_time = (timestamps[-1] - timestamps[0]).total_seconds() / 60
        avg_hop = total_time / (len(transaction_chain) - 1)
        
        if avg_hop < 2:
            category = "Abnormal"
        elif avg_hop < 10:
            category = "Very Fast"
        elif avg_hop < 30:
            category = "Fast"
        else:
            category = "Normal"
        
        total_amount = sum(t['amount'] for t in transaction_chain)
        alert = f"₹{total_amount/100000:.1f}L moved across {len(transaction_chain)} accounts in {total_time:.0f} minutes"
        
        return {
            'total_time_minutes': total_time,
            'avg_hop_time_minutes': avg_hop,
            'speed_category': category,
            'total_amount': total_amount,
            'num_hops': len(transaction_chain),
            'alert_text': alert
        }
```

---

#### Task 2.8 — Pattern Combination Detector (15 min) 🆕

**Add to: `core/pattern_detector.py`**

```python
def detect_combined_patterns(self):
    """
    Detect accounts involved in MULTIPLE fraud patterns simultaneously.
    Combinations are far more suspicious than individual patterns.
    
    Example outputs:
      - ACC_X: Layering + Structuring (Combo Score: 95)
      - ACC_Y: Round-tripping + Dormant Activation (Combo Score: 98)
    
    Scoring:
      - 1 pattern: base score
      - 2 patterns: score * 1.5
      - 3+ patterns: score * 2.0 (auto-CRITICAL)
    """
    all_patterns = self.get_all_patterns()
    
    # Build account → patterns mapping
    account_patterns = defaultdict(set)
    for pattern_type, results in all_patterns.items():
        for result in results:
            for account in result['accounts']:
                account_patterns[account].add(pattern_type)
    
    # Filter accounts with 2+ patterns
    combined = {
        acc: patterns for acc, patterns in account_patterns.items()
        if len(patterns) >= 2
    }
    
    return combined
```

---

#### Task 2.9 — First Suspicious Point Detection (20 min) 🆕

**Add to: `core/pattern_detector.py`**

```python
def detect_first_suspicious_point(self, account_id):
    """
    For a flagged account, identify the FIRST transaction that deviated
    from normal behavior — the "patient zero" of the fraud chain.
    
    Method:
      1. Get all transactions for this account, sorted by timestamp
      2. Compute rolling statistics (mean, std of amounts over last 30 txns)
      3. Find the first transaction where:
         - Amount > mean + 3*std (sudden spike)
         - OR velocity suddenly increases (>3 txns in 10 min after being slow)
         - OR new channel/counterparty never seen before in large amount
      4. Mark this as the "first suspicious point"
    
    Returns: {
        'first_suspicious_txn': txn_dict,
        'timestamp': datetime,
        'reason': str,  # "Amount spike: ₹9.5L vs average ₹45K"
        'preceding_normal_txns': int,
        'subsequent_suspicious_txns': int
    }
    """
    pass
```

**UI:** Highlighted with a ⚡ marker on both the timeline view and the graph edge.

---

#### Task 2.10 — Repeat Behavior Detection (15 min) 🆕

**Add to: `core/pattern_detector.py`**

```python
def detect_repeat_behavior(self, time_window_days=90):
    """
    Identify accounts that show suspicious patterns REPEATEDLY.
    
    Method:
      1. For each flagged account, look at temporal windows
      2. Count how many separate "episodes" of suspicious activity occurred
      3. An episode = cluster of suspicious txns separated by >7 days of quiet
    
    Output per account:
      - episode_count: int ("This account showed suspicious behavior 3 times")
      - episode_dates: list of date ranges
      - escalating: bool (are episodes getting larger/faster?)
    
    Accounts with 3+ episodes = habitual offenders → auto-escalate priority
    """
    pass
```

---

#### Task 2.11 — Top Suspicious Path Ranking (15 min) 🆕

**Add to: `core/graph_engine.py`**

```python
def rank_suspicious_paths(self, risk_scores, top_n=10):
    """
    Rank all fund-flow paths by suspiciousness.
    
    Path score = sum of node risk scores along path + speed bonus + amount bonus
    
    Returns top_n paths:
    [
        {
            'rank': 1,
            'path': ['ACC_L001', 'ACC_L002', 'ACC_L003', 'ACC_L004'],
            'path_score': 92,
            'total_amount': 4500000,
            'duration_minutes': 7,
            'speed_category': 'Abnormal',
            'patterns_detected': ['layering', 'structuring']
        },
        ...
    ]
    """
    pass
```

**UI in Dashboard:** A ranked table with clickable paths → clicking jumps to Graph Explorer with that path highlighted.

---

#### Task 2.12 — Investigation Priority Score (10 min) 🆕

**Add to: `core/risk_scorer.py`**

```python
def compute_investigation_priority(self, account_id, risk_score, confidence_level,
                                     amount_involved, accounts_involved_count,
                                     pattern_severity, is_repeat_offender):
    """
    Separate from risk score — this is an INVESTIGATION PRIORITY.
    
    Factors:
      - Risk score (weight: 25%)
      - Confidence level (weight: 20%)
      - Total amount involved in suspicious txns (weight: 20%)
      - Number of accounts in the suspicious network (weight: 15%)
      - Pattern severity: structuring=1, layering=2, combo=3 (weight: 10%)
      - Repeat offender bonus: +10% if 2+ episodes (weight: 10%)
    
    Priority Levels:
      - P1 (URGENT):  Score >= 80 — Investigate within 24 hours
      - P2 (HIGH):    Score 60-79 — Investigate within 3 days
      - P3 (MEDIUM):  Score 40-59 — Investigate within 1 week
      - P4 (LOW):     Score < 40  — Add to monitoring watchlist
    """
    pass
```

---

### 🍕 BREAK + FOOD (30 min)

---

### ⏱ SESSION 3: Frontend — Graph Explorer & Dashboard (Hours 8–13)

**Goal:** Build the Streamlit UI that makes judges go "wow." This is the longest session because the UI IS the demo.

---

#### Task 3.1 — Main App + Navigation (30 min)

**File: `app.py`**

```python
import streamlit as st

st.set_page_config(
    page_title="TraceX — Fund Flow Intelligence",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🏦 TraceX — Fund Flow Intelligence")
st.markdown("**Graph-first, ML-second, law-enforcement-ready** fund flow tracking for public sector banks")

# Load data once and cache
@st.cache_data
def load_data():
    # Generate or load synthetic data
    pass

@st.cache_resource
def build_graph(accounts_df, transactions_df):
    # Build the graph engine
    pass

# Show overview metrics on home page
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Accounts", "500")
col2.metric("Total Transactions", "47,231")
col3.metric("Flagged Accounts", "23", delta="+3 today")
col4.metric("Active Alerts", "7", delta="-2 resolved")
```

---

#### Task 3.2 — Interactive Graph Explorer (120 min) ⭐ SHOWSTOPPER

**File: `pages/1_🔍_Graph_Explorer.py`**

This is the **star of your demo**. Two visualization approaches (implement both, let the user toggle):

**Approach A — streamlit-agraph (embedded, interactive):**
```python
from streamlit_agraph import agraph, Node, Edge, Config

# Color-code nodes by risk level
# Size nodes by transaction volume
# Color edges by channel type
# Clicking a node shows its details in a sidebar panel
```

**Approach B — pyvis (richer physics, opens in iframe):**
```python
from pyvis.network import Network

# Build pyvis network from NetworkX subgraph
# Export as HTML, embed via st.components.v1.html()
```

**Key features to implement:**
1. **Search bar:** Enter account ID → centers graph on that account's ego-subgraph
2. **Depth slider:** Control how many hops to show (1–5)
3. **Filter panel:** Filter by channel, amount range, date range, risk level
4. **Node details panel:** Click a node → show account metadata, risk score, flag history
5. **Path tracer:** Select source + destination → highlight the shortest fund trail with timestamps and amounts
6. **Color legend:** 
   - 🔴 Red nodes = CRITICAL risk
   - 🟠 Orange nodes = HIGH risk
   - 🟡 Yellow nodes = MEDIUM risk
   - 🟢 Green nodes = LOW risk
   - Edge colors = channel type (UPI=purple, NEFT=blue, cash=green, etc.)
7. **🆕 Quick Summary Card:** When any node is selected, show a compact info card:
   ```
   ┌──────────────────────────────────┐
   │ 🏦 ACC_L003                      │
   │ Risk: HIGH (82) | Conf: Strong  │
   │ Role: MULE 🟡                    │
   │ Priority: P1 (URGENT)           │
   │ Patterns: Layering, Structuring │
   │ Speed: ₹20L across 4 accs / 7m │
   │ Repeat: 2 prior episodes        │
   │ ⚡ First suspicious: 15-Mar 2:14AM│
   │ Insight: "Funds split into 5     │
   │ accounts within 3 minutes"       │
   │ [ 🔍 Deep Dive ] [ 📋 Add to Case ] │
   └──────────────────────────────────┘
   ```
8. **🆕 Clean vs Suspicious Mode Toggle:**
   ```python
   view_mode = st.toggle("Show only suspicious transactions", value=False)
   if view_mode:
       # Filter graph to show only nodes with risk > MEDIUM
       # and edges involved in detected patterns
       filtered_nodes = [n for n in nodes if risk_scores[n] > 50]
   else:
       # Show all nodes (normal + suspicious)
       filtered_nodes = all_nodes
   ```
   This toggle appears at the top of the graph explorer and instantly switches between:
   - **All view:** Full transaction network (good for context)
   - **Suspicious-only view:** Only flagged accounts and their connections (good for focused investigation)
9. **🆕 First Suspicious Point Marker:** On the timeline and graph edges, mark the ⚡ "patient zero" transaction with a glowing highlight
10. **🆕 Account Role Badges:** Show Source 🔵 / Mule 🟡 / Sink 🔴 badges on each node

---

#### Task 3.3 — Anomaly Dashboard (60 min)

**File: `pages/2_⚠️_Anomaly_Dashboard.py`**

**Layout:**
```
┌─────────────────────────┬─────────────────────────┐
│  Risk Distribution      │  Top 10 Flagged Accounts│
│  (Donut chart)          │  (Sortable table)       │
├─────────────────────────┼─────────────────────────┤
│  Feature Importance     │  Anomaly Score           │
│  (Bar chart - XGBoost)  │  Distribution (Histogram)│
├─────────────────────────┴─────────────────────────┤
│  Alert Timeline (Plotly scatter - time vs risk)    │
└───────────────────────────────────────────────────┘
```

**Key features:**
- Sortable, filterable table of flagged accounts with risk scores
- Click any account → jumps to Graph Explorer centered on that account
- Feature importance chart showing WHY accounts are flagged (XGBoost SHAP-like)
- Real-time-looking metrics (use `st.metric` with delta indicators)
- **🆕 Fraud Confidence Meter:** Each flagged account shows Risk Score + Confidence Level + indicator count
- **🆕 Investigation Priority Queue:** Sorted P1/P2/P3/P4 list with color-coded priority badges
- **🆕 Top Suspicious Paths Panel:** Ranked table of the top 10 most suspicious fund-flow paths with scores, click to trace
- **🆕 Transaction Speed Alerts:** Cards showing the fastest money-movement chains with speed category badges (Normal/Fast/Very Fast/Abnormal)
- **🆕 Repeat Offender Badges:** Accounts flagged multiple times get a 🔁 repeat indicator with episode count

---

#### Task 3.4 — Pattern Detector Page (60 min)

**File: `pages/3_🔄_Pattern_Detector.py`**

**Four tabs, one per pattern type:**

**Tab 1 — Layering Detection:**
- Show detected layering chains as horizontal flow diagrams
- Timeline showing the rapid hops with timestamps
- Amount degradation chart (bar chart showing decreasing amounts per hop)

**Tab 2 — Round-Tripping:**
- Circular graph visualization of detected cycles
- Table: cycle accounts, amounts, time span, net delta
- Highlight with animated-looking pulsing (use streamlit-agraph with colors)

**Tab 3 — Structuring:**
- Histogram of transaction amounts near the ₹10 lakh threshold
- Table of structuring accounts with count of near-threshold transactions
- "Structuring Score" metric per account

**Tab 4 — Dormant Activation:**
- Before/after comparison: activity timeline showing dormancy gap then burst
- Account profile card showing declared income vs sudden volume

**Tab 5 — 🆕 Pattern Combinations:**
- Venn-diagram-style visualization showing accounts that trigger multiple patterns
- Table: Account → Patterns detected → Combined score → Priority
- Example display: *"ACC_X001: Layering + Structuring detected simultaneously (Combo Score: 95, Priority: P1)"*
- These combination cases are auto-escalated to the top of the investigation queue

**Tab 6 — 🆕 Repeat Offenders:**
- Timeline showing multiple episodes of suspicious activity per account
- Escalation trend chart (are episodes getting worse?)
- Table: Account → Episode count → Date ranges → Escalating? → Priority

---

#### Task 3.5 — Profile Analyzer Page (45 min)

**File: `pages/4_👤_Profile_Analyzer.py`**

**"Dormant-to-Sudden-Millionaire" detector UI:**
- Scatter plot: X = declared income, Y = actual transaction volume, color = risk
- Accounts far above the diagonal line = profile mismatch
- Click any dot → account detail card with:
  - Profile info (occupation, income bracket, account type)
  - Behavior stats (actual monthly volume, channel mix, counterparty count)
  - Mismatch explanation: *"Volume is 40× higher than similar-profile accounts"*
  - Comparison with peer group (box plot of similar accounts)

---

#### Task 3.6 — Channel Analytics Page (45 min)

**File: `pages/5_📊_Channel_Analytics.py`**

**Two main visualizations:**

**Sankey Diagram (Plotly):**
- Left: Source account types (savings, current, NRO, etc.)
- Middle: Channels (UPI, NEFT, RTGS, cash, etc.)
- Right: Destination account types
- Width = total flow volume
- Highlight suspicious flows in red

**Channel Heatmap:**
- X-axis: Hour of day (0–23)
- Y-axis: Channel type
- Color intensity: Transaction volume
- Suspicious clusters glow red (e.g., high ATM usage at 2AM)

---

### 😴 BREAK — Power Nap / Walk (30 min)

---

### ⏱ SESSION 4: FIU Evidence & Money Trail Simulator (Hours 13–17)

**Goal:** Build the evidence export system and the "what-if" simulator — the features that make this look production-ready.

---

#### Task 4.1 — Evidence Generator Backend (90 min) ⭐ UNIQUE DIFFERENTIATOR

**File: `core/evidence_generator.py`**

**One-click evidence pack generation:**

```python
from fpdf import FPDF
import json
import matplotlib.pyplot as plt

class EvidenceGenerator:
    def generate_evidence_pack(self, case_id, account_ids, graph_engine, risk_data):
        """
        Generates a complete FIU-compliant evidence package:
        
        1. PDF Report containing:
           - Case header (auto-generated case number, date, investigating officer field)
           - Subject account details (CDD-style)
           - Fund trail visualization (matplotlib graph → embedded image)
           - Transaction table (all suspicious transactions)
           - Risk score breakdown with explanations
           - Pattern detection results
           - Typology classification (layering/round-trip/structuring/etc.)
           - Recommendations field
        
        2. JSON Data Package:
           - Machine-readable version of all the above
           - Graph adjacency data (for further analysis)
           - Can be imported into FIU systems
        
        3. Graph Image:
           - High-res PNG of the suspicious subgraph
           - Nodes labeled, edges with amounts and timestamps
        """
        pass
    
    def _generate_pdf(self, case_data) -> bytes:
        pdf = FPDF()
        pdf.add_page()
        # Header
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(200, 10, "SUSPICIOUS TRANSACTION REPORT", ln=True, align="C")
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(200, 10, f"Case ID: {case_data['case_id']} | Generated: {datetime.now()}", ln=True)
        # ... build complete report
        return pdf.output()
    
    def _generate_json_pack(self, case_data) -> dict:
        return {
            "case_id": case_data["case_id"],
            "generated_at": datetime.now().isoformat(),
            "subject_accounts": [...],
            "fund_trail": {...},
            "risk_assessment": {...},
            "detected_patterns": [...],
            "typology": "...",
            "transactions": [...],
            "graph_data": {
                "nodes": [...],
                "edges": [...]
            }
        }
    
    def _generate_graph_image(self, subgraph) -> bytes:
        """Render NetworkX subgraph as a publication-quality PNG"""
        fig, ax = plt.subplots(1, 1, figsize=(12, 8))
        pos = nx.spring_layout(subgraph, k=2, seed=42)
        # Draw with custom colors, labels, edge annotations
        # Save to BytesIO buffer
        pass
```

---

#### Task 4.2 — FIU Evidence Page UI (60 min)

**File: `pages/6_📋_FIU_Evidence.py`**

**Layout:**
```
┌────────────────────────────────────────────────────┐
│  Case Builder                                       │
│  ┌─────────────────┐ ┌──────────────────────────┐  │
│  │ Select accounts │ │ Select pattern type      │  │
│  │ (multiselect)   │ │ (dropdown)               │  │
│  └─────────────────┘ └──────────────────────────┘  │
│  ┌─────────────────────────────────────────────┐   │
│  │ Case Notes (text area)                       │   │
│  └─────────────────────────────────────────────┘   │
│  [ 📄 Generate Evidence Pack ]  ← Big button       │
├────────────────────────────────────────────────────┤
│  Preview Panel                                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│  │ PDF      │ │ JSON     │ │ Graph    │           │
│  │ Preview  │ │ Preview  │ │ Image    │           │
│  │ (iframe) │ │ (st.json)│ │(st.image)│           │
│  └──────────┘ └──────────┘ └──────────┘           │
│  [ ⬇️ Download PDF ] [ ⬇️ Download JSON ]          │
└────────────────────────────────────────────────────┘
```

**Key features:**
- Multi-select accounts to include in the case
- Auto-populate fields from detected patterns
- Preview everything before download
- `st.download_button` for both PDF and JSON

---

#### Task 4.3 — Money Trail Simulator (60 min) ⭐ WOW FACTOR

**Add to Graph Explorer page as a secondary tab:**

**"What-If" Trace Mode:**
- Select a suspicious account
- System runs **Random Walk with Restart** from that node
- Shows **probability heatmap** of likely accomplices (even if not directly connected)
- Displays results as "probable accomplices" with dashed lines in the graph
- Explanation panel: *"These accounts are statistically likely to be involved based on fund flow topology"*

**Implementation:**
```python
def random_walk_with_restart(G, start_node, restart_prob=0.15, num_steps=1000):
    """
    Personalized PageRank via random walk simulation.
    Returns: dict of account_id → visit probability
    """
    visit_counts = defaultdict(int)
    current = start_node
    for _ in range(num_steps):
        if random.random() < restart_prob:
            current = start_node
        else:
            neighbors = list(G.successors(current))
            if neighbors:
                current = random.choice(neighbors)
            else:
                current = start_node
        visit_counts[current] += 1
    
    total = sum(visit_counts.values())
    return {k: v/total for k, v in visit_counts.items()}
```

---

#### Task 4.4 — Profile-vs-Behavior Mismatch Engine (30 min)

**File: `core/profile_analyzer.py`**

```python
class ProfileAnalyzer:
    def compute_peer_group(self, account_id, accounts_df):
        """Find accounts with similar profile (occupation, income, type)"""
        pass
    
    def compute_mismatch_score(self, account_id, actual_volume, peer_stats):
        """
        Z-score of this account's volume vs peer group.
        Z > 3 = severe mismatch
        """
        pass
    
    def generate_explanation(self, account_id, mismatch_data):
        """
        Natural language explanation:
        "Account ACC_P001 (Student, income bracket Low) has monthly 
         transaction volume of ₹48,00,000 which is 42× the peer group 
         average of ₹1,14,000. This is a CRITICAL profile mismatch."
        """
        pass
```

---

### ☕ BREAK (15 min)

---

### ⏱ SESSION 5: Polish, Integration & Demo Prep (Hours 17–22)

**Goal:** Everything works end-to-end. Polish the UI, fix edge cases, prepare demo scenarios.

---

#### Task 5.1 — End-to-End Integration Testing (60 min)

Run through the complete flow:
1. App loads → data generates → graph builds (should be <5 seconds with caching)
2. Graph Explorer shows the full network → search works → path tracing works
3. Anomaly Dashboard shows flagged accounts → click-through works
4. Pattern Detector finds all 4 pattern types → visualizations render
5. Profile Analyzer shows mismatch scatter plot → explanations generate
6. Channel Analytics shows Sankey + heatmap
7. FIU Evidence generates PDF + JSON → downloads work

**Fix any broken interactions. This is the most important session for quality.**

---

#### Task 5.2 — Demo Scenario Preparation (60 min)

Create **3 scripted demo scenarios** that you'll walk through during the presentation:

**Demo Scenario 1: "The Layering Network" (2 min)**
1. Open Graph Explorer → search for ACC_L001
2. Show the rapid chain: ACC_L001 → L002 → L003 → L004 → L005 → L006
3. Point out: all transfers within 8 minutes, amounts decreasing
4. Switch to Pattern Detector → Layering tab → same accounts highlighted
5. Show risk score: CRITICAL (92/100)
6. One-click → Generate FIU evidence pack → show PDF preview

**Demo Scenario 2: "The Round-Trip Scheme" (2 min)**
1. Open Pattern Detector → Round-Tripping tab
2. Show the cycle: ACC_R001 → R002 → R003 → back to R001
3. Net delta: only ₹15,000 over 3 cycles (money essentially returned)
4. Jump to Graph Explorer → see the circular visualization
5. Show the timeline view of the cycle iterations

**Demo Scenario 3: "The Dormant Millionaire" (1 min)**
1. Open Profile Analyzer → spot ACC_D001 as an extreme outlier
2. Click it → see: dormant for 9 months, then ₹2.3 Cr in 3 days
3. Profile: Homemaker, Low income bracket
4. Show mismatch explanation and peer comparison

**Save these as `data/sample_scenarios/` JSON files** that can be auto-loaded for demo.

---

#### Task 5.3 — UI Polish (90 min)

- **Add a real-time simulation mode:** A toggle that adds transactions one-by-one with a streaming effect (use `st.empty()` + `time.sleep()`) — makes the demo feel "live"
- **Tooltips and help text** on every section (use `st.help`, `st.info`, tooltips)
- **Consistent color scheme** across all pages
- **Loading spinners** with `st.spinner("Analyzing fund flows...")` for dramatic effect
- **Sidebar enhancements:**
  - Quick stats panel (always visible)
  - "Jump to flagged account" dropdown
  - System status indicator (green dot)
- **Add the bank branding placeholder:** Logo area, "Union Bank of India" (or generic "Public Sector Bank") 

---

#### Task 5.4 — Performance Optimization (30 min)

- Ensure `@st.cache_data` and `@st.cache_resource` are used for:
  - Data loading
  - Graph building
  - ML model training
  - Feature extraction
- Test that page switches are fast (<1 second)
- If graph rendering is slow for 500 nodes, add a "show top N nodes" limiter

---

#### Task 5.5 — README and Documentation (30 min)

**File: `README.md`**

```markdown
# 🏦 TraceX — Fund Flow Intelligence System

## Problem Statement
Tracking of Funds within Bank for Fraud Detection...

## Solution Architecture
[Paste the ASCII architecture diagram]

## Key Features
1. **Interactive Graph Explorer** — Trace any rupee from origin to destination
2. **ML-Powered Anomaly Detection** — XGBoost + Isolation Forest ensemble
3. **Pattern Detection** — Layering, round-tripping, structuring, dormant activation
4. **Profile Mismatch Analysis** — Catches dormant-to-millionaire accounts
5. **Cross-Channel Analytics** — Sankey diagrams + channel heatmaps
6. **One-Click FIU Evidence Packs** — PDF + JSON export, law-enforcement-ready

## How to Run
pip install -r requirements.txt
streamlit run app.py

## Tech Stack
- **Graph:** NetworkX (production: Neo4j)
- **ML:** XGBoost, Isolation Forest, scikit-learn
- **UI:** Streamlit, streamlit-agraph, Plotly
- **Export:** fpdf2, JSON
```

---

### ⏱ SESSION 6: Final Testing & Presentation Prep (Hours 22–24)

---

#### Task 6.1 — Full Dry Run (45 min)

- Run through all 3 demo scenarios back-to-back
- Time yourself — should be under 5 minutes total
- Note any crashes, slow loads, or visual glitches
- Have a backup plan if something breaks (pre-generated screenshots)

---

#### Task 6.2 — Presentation Slides (45 min)

Create 5–6 slides (can be in Streamlit itself as a "home" page, or separate):

| Slide | Content |
|---|---|
| 1. Problem | "₹1.85 lakh crore laundered annually through Indian banks" + problem statement |
| 2. Our Approach | Architecture diagram, "Graph-first, ML-second" positioning |
| 3. Live Demo | Switch to the running app |
| 4. Tech Deep-Dive | Feature table, ML model metrics (accuracy, precision, recall) |
| 5. Scalability | "NetworkX → Neo4j swap, Kafka streaming, federated privacy" |
| 6. Impact | "12× faster investigation, 40% more patterns caught vs rule-based" |

---

#### Task 6.3 — Edge Case Hardening (30 min)

- What if someone searches for a non-existent account? → Show friendly error
- What if the graph is too dense to render? → Auto-filter to top-risk nodes
- What if no patterns are detected? → Show "All clear" with a green dashboard
- What if PDF generation fails? → Graceful fallback to JSON-only export

---

## 🎯 DELIVERABLES CHECKLIST

| # | Deliverable | Session | Priority | Owner (4-person team) |
|---|---|---|---|---|
| 1 | Synthetic data generator with embedded fraud | Session 1 | 🔴 Must | Dev A |
| 2 | NetworkX graph engine with algorithms | Session 1 | 🔴 Must | Dev B |
| 3 | Feature extraction pipeline | Session 2 | 🔴 Must | Dev A |
| 4 | Isolation Forest anomaly detector | Session 2 | 🔴 Must | Dev A |
| 5 | XGBoost fraud classifier | Session 2 | 🟡 Should | Dev A |
| 6 | Pattern detector (layering, cycles, structuring, dormant) | Session 2 | 🔴 Must | Dev B |
| 7 | Risk scoring engine + Confidence Meter 🆕 | Session 2 | 🔴 Must | Dev C |
| 8 | Account Role Classifier (Source/Mule/Sink) 🆕 | Session 2 | 🔴 Must | Dev B |
| 9 | Transaction Speed Analyzer 🆕 | Session 2 | 🟡 Should | Dev C |
| 10 | Pattern Combination Detector 🆕 | Session 2 | 🟡 Should | Dev B |
| 11 | First Suspicious Point Detection 🆕 | Session 2 | 🟡 Should | Dev C |
| 12 | Repeat Behavior Detection 🆕 | Session 2 | 🟡 Should | Dev C |
| 13 | Investigation Priority Score 🆕 | Session 2 | 🟡 Should | Dev C |
| 14 | Interactive graph explorer + Quick Summary Card 🆕 | Session 3 | 🔴 Must | Dev B |
| 15 | Clean vs Suspicious Mode Toggle 🆕 | Session 3 | 🔴 Must | Dev B |
| 16 | Anomaly dashboard + Top Path Ranking 🆕 + Speed Alerts 🆕 | Session 3 | 🔴 Must | Dev C |
| 17 | Pattern detector UI (6 tabs including combos + repeat) | Session 3 | 🟡 Should | Dev D |
| 18 | Profile mismatch analyzer | Session 3 | 🟡 Should | Dev D |
| 19 | Channel analytics (Sankey + heatmap) | Session 3 | 🟢 Nice | Dev D |
| 20 | FIU evidence PDF/JSON generator | Session 4 | 🔴 Must | Dev A |
| 21 | Money trail simulator (what-if) | Session 4 | 🟢 Nice | Dev B |
| 22 | Demo scenarios + polish | Session 5 | 🔴 Must | All |
| 23 | Presentation + Pitch Video | Session 6 | 🔴 Must | All |

---

## 💡 UNIQUE SELLING POINTS (What Makes This Stand Out)

1. **Graph-First Approach:** Most teams will use tables + rules. You use a real graph with PageRank, centrality, cycle detection.
2. **Multi-Pattern Detection:** Not just one anomaly detector — you detect 4+ distinct fraud typologies + pattern combinations.
3. **Explainability:** Every flag comes with a human-readable explanation, visual evidence, and **Fraud Confidence Meter** showing exactly how many independent indicators converged.
4. **One-Click Evidence Packs:** No other team will have FIU-compliant PDF export.
5. **Cross-Channel Visibility:** Sankey diagrams showing money flowing across UPI/NEFT/cash/etc.
6. **Simulation Mode:** "What-if" scenario engine with probable accomplice detection.
7. **Account Intelligence:** Every account gets a **Role** (Source/Mule/Sink), **Risk Score**, **Confidence Level**, and **Investigation Priority** — a complete intelligence profile.
8. **First Suspicious Point Detection:** System pinpoints the exact transaction where fraud began — answers "where did it start?"
9. **Transaction Speed Forensics:** Measures money velocity across chains and flags abnormally fast movements.
10. **Repeat Offender Tracking:** Identifies habitual offenders across multiple time windows.
11. **Top Path Ranking:** Investigators see the most suspicious fund-flow paths ranked — no need to search blindly.
12. **Clean/Suspicious Toggle:** One-click switch between full network and suspicious-only view for focused investigation.
13. **Production-Ready Pitch:** You explain how NetworkX → Neo4j, how Kafka enables streaming, how federated learning enables multi-bank collaboration — even though the prototype is self-contained.

---

## ⚡ EMERGENCY SHORTCUTS (If Running Behind)

| If you're behind by... | Cut this | Impact |
|---|---|---|
| 30 min | Repeat Behavior Detection | Low — nice-to-have |
| 1 hour | Channel Analytics page | Low — not core |
| 1.5 hours | Pattern Combination tab (keep individual patterns) | Low — merge flag into dashboard |
| 2 hours | Money Trail Simulator + Profile Analyzer page | Medium — merge key metrics into Dashboard |
| 3 hours | Transaction Speed Analyzer (keep velocity feature in ML) | Low — velocity_10min feature still works |
| 4 hours | XGBoost (keep only Isolation Forest) | Low — one model is enough |
| 5+ hours | Drop PDF evidence → JSON-only export | Medium — still impressive |

**With 4 devs + Claude, you should NOT need to cut anything.** The parallel workstreams (see Owner column) mean Session 2 alone produces 2× the output of a solo developer.

---

## 📋 QUICK-REFERENCE: Key Python Snippets

**Cycle detection:**
```python
cycles = list(nx.simple_cycles(G))
short_cycles = [c for c in cycles if len(c) <= 5]
```

**PageRank:**
```python
pr = nx.pagerank(G, alpha=0.85)
top_accounts = sorted(pr.items(), key=lambda x: x[1], reverse=True)[:20]
```

**Structuring detection:**
```python
near_threshold = txns[
    (txns['amount'] >= 900000) & (txns['amount'] < 1000000)
].groupby('source_account').size()
structuring_accounts = near_threshold[near_threshold >= 3].index.tolist()
```

**Sankey diagram (Plotly):**
```python
import plotly.graph_objects as go
fig = go.Figure(go.Sankey(
    node=dict(label=labels, color=colors),
    link=dict(source=sources, target=targets, value=values, color=link_colors)
))
st.plotly_chart(fig, use_container_width=True)
```

**streamlit-agraph node:**
```python
Node(id="ACC001", label="ACC001\n₹45L", size=30, 
     color="#ff4444", shape="dot", 
     title="Risk: CRITICAL\nType: Current\nCity: Mumbai")
```

---

*Good luck! 🚀 Remember: a working demo with 3 strong features beats a broken demo with 10 features.*
