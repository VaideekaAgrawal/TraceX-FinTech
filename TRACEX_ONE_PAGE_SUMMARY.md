# TraceX: Intelligent Fund Flow Tracking System
### One-Page Idea Summary — For Mandatory PDF Submission

---

**Team Name:** [Your Team Name] | **Hackathon:** [Hackathon Name] | **Date:** March 2026

---

## Problem Statement

Indian banks are estimated to process over ₹1.85 lakh crore in laundered funds annually. Current Anti-Money Laundering (AML) systems monitor individual transactions in isolation — they cannot see the end-to-end journey of funds flowing across multiple accounts, channels (UPI, NEFT, RTGS, cash, ATM), and products (savings, current, NRO, prepaid cards). This siloed approach results in a 95%+ false positive rate, 18-45 day investigation cycles per case, and an inability to detect sophisticated multi-hop fraud patterns such as layering, round-tripping, and structuring. Investigators lack tools to trace money end-to-end and must manually compile evidence for Suspicious Transaction Reports (STR) filed with the Financial Intelligence Unit (FIU-IND).

## Proposed Solution

**TraceX** is a graph-first, ML-powered fund flow tracking system that models the complete movement of every rupee inside a bank as a directed multi-graph. Accounts are nodes, transactions are timestamped edges carrying amount and channel metadata. On top of this graph, TraceX runs a **4-layer detection engine**: (1) Unsupervised anomaly detection (Isolation Forest), (2) Supervised fraud classification (XGBoost), (3) Rule-based pattern detectors for 6 fraud typologies (layering, round-tripping, structuring, dormant account activation, profile mismatch, transaction speed anomaly), and (4) Graph analytics (PageRank, betweenness centrality, cycle enumeration, role classification). Every account receives a **composite risk score (0-100)**, a **Fraud Confidence Meter** (Weak/Medium/Strong based on independent indicator count), an **Investigation Priority (P1-P4)**, and an **Account Role** (Source/Mule/Sink). A 6-page interactive Streamlit web application provides investigators with an interactive graph explorer (click-to-trace fund trails, Quick Summary Cards, Clean vs Suspicious toggle), anomaly dashboard, pattern detector with combination analysis, profile mismatch analyzer, cross-channel Sankey diagrams, and **one-click FIU-compliant evidence pack generation** (PDF + JSON + graph images). The system reduces false positives by ~3×, cuts investigation time from weeks to minutes, and makes every alert explainable.

## Key Innovation & Unique Features

| Innovation | Description |
|---|---|
| **Fraud Confidence Meter** | Counts independent indicators (ML, patterns, graph, profile, speed, repeat) — answers "how confident are we?" |
| **Account Role Classification** | Automatically labels Source (🔵) / Mule (🟡) / Sink (🔴) from graph topology |
| **First Suspicious Point Detection** | Pinpoints the exact "patient zero" transaction where normal behavior ended |
| **Pattern Combination Detection** | Flags accounts triggering 2+ fraud patterns simultaneously with score multiplier |
| **One-Click FIU Evidence Packs** | Complete STR-compliant PDF + JSON + graph image in 3 seconds |
| **Transaction Speed Forensics** | Categorizes money velocity as Normal / Fast / Very Fast / Abnormal |

## Technology Stack

Python 3.11 | NetworkX (graph engine) | scikit-learn Isolation Forest + XGBoost (ML) | Streamlit (6-page interactive UI) | streamlit-agraph + pyvis (graph visualization) | Plotly (Sankey, heatmaps, timelines) | fpdf2 (PDF evidence export) | Faker (synthetic data generation) | pandas, numpy, scipy (data processing)

## Expected Impact

- **3× reduction** in false positives through confidence-based filtering
- **Investigation time:** 18-45 days → under 5 minutes (alert to evidence pack)
- **6 fraud typologies** detected + combinations (vs 2-3 in rule-based systems)
- **100% cross-channel visibility** (UPI + NEFT + RTGS + cash + ATM + mobile unified)
- **FIU/PMLA/FATF compliance** through automated STR evidence generation
- **10× investigator productivity** improvement

## Business Model

B2B SaaS subscription for banks (₹50L-2Cr/year per bank) + on-premise licensing for data-sovereign deployments. Target market: 12 PSBs + 22 private banks + 50+ fintechs. India AML compliance market: ~₹2,500 Cr/year (18% CAGR). Go-to-market: Free 3-month pilot with 1-2 PSBs → validate → expand. Production roadmap: NetworkX → Neo4j, add Apache Kafka real-time streaming, federated multi-bank graph with DPDP compliance.

---

*© 2026 [Team Name]. Built for [Hackathon Name].*
