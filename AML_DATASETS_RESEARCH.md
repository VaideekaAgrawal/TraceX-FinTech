# AML Fund Flow Tracking - Dataset Research & Regulatory Requirements

## 1. DATASETS FOR AML FUND FLOW TRACKING

---

### 1.1 IBM Transactions for Anti-Money Laundering (AML)

| Field | Details |
|-------|---------|
| **URL** | https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml |
| **Paper** | https://arxiv.org/abs/2306.16424 (NeurIPS 2023) |
| **GitHub (GNN Models)** | https://github.com/IBM/Multi-GNN |
| **Size** | ~41.61 GB total (6 datasets: Small/Medium/Large × High-Illicit/Low-Illicit) |
| **License** | Community Data License Agreement - Sharing 1.0 |

**Description:**
- Synthetically generated transaction data modeling the **entire money laundering cycle**: Placement → Layering → Integration
- Contains a complete financial ecosystem (not limited to one bank's view)
- Transactions are labeled as **laundering or legitimate**
- Tracks illicit funds through **arbitrarily many transaction hops**

**Transaction CSV Columns:**
```
Timestamp, From_Account_ID, From_Bank_ID, To_Account_ID, To_Bank_ID, Amount_Paid, Payment_Currency, Amount_Received, Receiving_Currency, Payment_Type, Is_Laundering
```

**Laundering Patterns Included:**
| Pattern | Description |
|---------|-------------|
| **CYCLE** | Funds cycle through 2-12 hops back to origin |
| **FAN-IN** | Multiple accounts funnel into one (1-13 degree) |
| **FAN-OUT** | One account disperses to many (1-16 degree) |
| **SCATTER-GATHER** | Funds scatter through intermediaries then gather |
| **GATHER-SCATTER** | Funds gather then scatter to multiple destinations |
| **BIPARTITE** | Transactions between two groups of accounts |
| **STACK** | Sequential chain of A→B, C→D type pairs |
| **RANDOM** | Random multi-hop patterns (1-11 hops) |

**Dataset Statistics:**
```
                    SMALL         MEDIUM          LARGE
                    HI     LI    HI      LI      HI       LI
Bank Accounts      515K   705K  2077K   2028K   2116K    2064K
Transactions        5M     7M    32M     31M     180M     176M
Laundering Trans   5.1K   4.0K   35K     16K     223K     100K
Laundering Rate    1:981  1:1942 1:905  1:1948   1:807   1:1750
```

**Use for TraceX:**
- ✅ Graph construction (sender → receiver edges)
- ✅ Multi-hop fund flow tracking
- ✅ GNN model training with labeled patterns
- ✅ Pattern recognition (cycle, fan-in/out, scatter-gather)
- ✅ Cross-currency laundering detection

---

### 1.2 Elliptic Bitcoin Dataset

| Field | Details |
|-------|---------|
| **URL** | https://www.kaggle.com/datasets/ellipticco/elliptic-data-set |
| **Paper** | Weber et al., "Anti-Money Laundering in Bitcoin: Experimenting with Graph Convolutional Networks for Financial Forensics", KDD 2019 |
| **Size** | ~697 MB |
| **License** | CC BY-NC-ND 4.0 |

**Description:**
- Bitcoin transaction **graph** mapped to real entities
- Nodes = transactions, Edges = Bitcoin flow between transactions
- Labels: **licit** (exchanges, wallets, miners) vs **illicit** (scams, malware, terrorist orgs, ransomware, Ponzi schemes)

**Graph Statistics:**
| Metric | Value |
|--------|-------|
| Nodes (transactions) | 203,769 |
| Edges (flows) | 234,355 |
| Illicit (Class 1) | 4,545 (2%) |
| Licit (Class 2) | 42,019 (21%) |
| Unknown | ~157,205 (77%) |

**Features (166 per node):**
- **First 94 features**: Local transaction info (time step, # inputs/outputs, transaction fee, output volume, avg BTC received/spent)
- **Remaining 72 features**: Aggregated 1-hop neighborhood features (max, min, std dev, correlation coefficients of neighbor transactions)
- **49 time steps** (~2 weeks each), single connected component per time step

**Use for TraceX:**
- ✅ Pre-built graph structure for GNN experimentation
- ✅ Real labeled data (illicit vs licit)
- ✅ Temporal transaction patterns
- ✅ Benchmark for graph-based AML models

---

### 1.3 PaySim - Synthetic Financial Dataset for Fraud Detection

| Field | Details |
|-------|---------|
| **URL** | https://www.kaggle.com/datasets/ealaxi/paysim1 |
| **GitHub** | https://github.com/EdgarLopezPhD/PaySim |
| **Paper** | Lopez-Rojas et al., "PaySim: A financial mobile money simulator for fraud detection", EMSS 2016 |
| **Size** | ~493 MB |
| **License** | CC BY-SA 4.0 |

**Description:**
- Simulates **mobile money transactions** based on real transaction logs from an African mobile money service
- 1 month simulation (744 steps = hours)
- ~6.3 million transactions
- Includes both legitimate and **injected fraudulent behavior**
- PaySim 2.0 added **Money Laundering cases** (contributed by Flaminem)

**Columns:**
| Column | Description |
|--------|-------------|
| `step` | Hour of simulation (1-744) |
| `type` | CASH-IN, CASH-OUT, DEBIT, PAYMENT, TRANSFER |
| `amount` | Transaction amount |
| `nameOrig` | Sender customer ID |
| `oldbalanceOrg` | Sender balance before |
| `newbalanceOrig` | Sender balance after |
| `nameDest` | Receiver customer ID |
| `oldbalanceDest` | Receiver balance before |
| `newbalanceDest` | Receiver balance after |
| `isFraud` | Binary fraud label |
| `isFlaggedFraud` | Flagged if transfer > 200,000 |

**Use for TraceX:**
- ✅ Sender-receiver graph construction
- ✅ Temporal transaction analysis
- ✅ Balance-based anomaly detection
- ✅ Multi-type transaction network
- ✅ Fraud label for supervised learning

---

### 1.4 BankSim - Bank Payment Simulation

| Field | Details |
|-------|---------|
| **URL** | https://www.kaggle.com/datasets/ntnu-testimon/banksim1 |
| **Paper** | Lopez-Rojas & Axelsson, "BankSim: A Bank Payment Simulation for Fraud Detection Research" |
| **Size** | ~20 MB |
| **License** | CC BY-SA 4.0 |

**Description:**
- Synthetic dataset simulating bank payments
- Based on aggregated transactional data from a Spanish bank
- Contains customer, merchant, transaction category info
- Labeled for fraud detection

**Key Columns:** customer, merchant, category, amount, fraud_label, age, gender

**Use for TraceX:**
- ✅ Customer-merchant transaction graph
- ✅ Category-based pattern detection
- ✅ Simpler baseline dataset for prototyping

---

### 1.5 Additional Relevant Datasets

| Dataset | URL | Description | Use Case |
|---------|-----|-------------|----------|
| **Ethereum Fraud Detection** | https://www.kaggle.com/datasets/vagifa/ethereum-frauddetection-dataset | Labeled Ethereum addresses (fraud/not) | Crypto AML |
| **Credit Card Transactions (IBM)** | https://www.kaggle.com/datasets/ealtman2019/credit-card-transactions | Synthetic CC transactions with fraud labels | Related fraud patterns |
| **Elliptic++ (Extended)** | https://github.com/git-disl/EllipticPlusPlus | Extended Elliptic with actor & address info | Enhanced Bitcoin AML |
| **AMLSim** | https://github.com/IBM/AMLSim | IBM's AML Transaction Simulator (Java) | Generate custom AML data |
| **SAML-D** | Academic (request-based) | Synthetic AML dataset with temporal patterns | Research benchmarking |

---

## 2. FIU-IND STR (SUSPICIOUS TRANSACTION REPORT) FORMAT

### 2.1 About FIU-IND
- **Full Name**: Financial Intelligence Unit — India
- **Parent**: Department of Revenue, Ministry of Finance, Government of India
- **Established**: November 18, 2004
- **Website**: https://fiuindia.gov.in
- **Reporting Portal**: FINnet 2.0 (online filing system)

### 2.2 Report Types Collected by FIU-IND

| Report Type | Abbreviation | Filing Entity |
|-------------|--------------|---------------|
| Cash Transaction Report | CTR | Banks, Financial Institutions |
| Suspicious Transaction Report | STR | All Reporting Entities |
| Non-Profit Organisation Transaction Report | NTR | NPOs |
| Cross Border Wire Transfer Report | CBWTR | Banks dealing in forex |
| Counterfeit Currency Report | CCR | Banks |
| Immovable Property Report | IPR | Real estate agents |

### 2.3 STR Form Fields (FIU-IND Format)

The STR form filed via FINnet 2.0 contains the following sections and fields:

#### Part A: Reporting Entity Information
| Field | Description |
|-------|-------------|
| Reporting Entity Code | Unique FIU-assigned code |
| Reporting Entity Name | Name of bank/FI |
| Reporting Entity Category | Bank/NBFC/Insurance/Intermediary |
| Branch Code | Branch identifier |
| Branch Name | Branch name |
| Branch Address | Full address |
| Principal Officer Name | Designated PMLA principal officer |
| Principal Officer Designation | Title |
| Principal Officer Phone | Contact number |
| Principal Officer Email | Email address |

#### Part B: Subject (Account Holder) Information
| Field | Description |
|-------|-------------|
| Subject Type | Individual / Non-Individual (Entity) |
| Subject Name | Full name |
| Father's/Spouse Name | As on KYC |
| Date of Birth / Incorporation | DOB or date of incorporation |
| Gender | M/F/Other |
| PAN | Permanent Account Number |
| Aadhaar Number | If available |
| Passport Number | If applicable |
| Voter ID | If applicable |
| Driving License | If applicable |
| Address (Permanent) | Full permanent address with PIN |
| Address (Communication) | Current address |
| Nationality | Country |
| Occupation/Business | Nature of business |
| Phone Number | Contact |
| Email | Email address |
| Customer ID | Internal bank customer ID |
| KYC Status | Verified/Pending |
| Account Number(s) | All associated accounts |
| Account Type | Savings/Current/FD/Loan etc. |
| Date of Account Opening | When account was opened |
| Account Status | Active/Dormant/Closed |

#### Part C: Suspicious Transaction Details
| Field | Description |
|-------|-------------|
| Transaction Reference Number | Unique transaction ID |
| Date of Transaction | Transaction date |
| Transaction Type | Cash/Transfer/Cheque/DD/Electronic |
| Amount | Transaction amount (INR) |
| Currency | If foreign currency involved |
| Mode of Transaction | Cash/RTGS/NEFT/IMPS/UPI/Cheque/DD |
| Debit/Credit | Direction of transaction |
| Remitter Name | Who sent the funds |
| Remitter Account Number | Source account |
| Remitter Bank/Branch | Source bank details |
| Beneficiary Name | Who received the funds |
| Beneficiary Account Number | Destination account |
| Beneficiary Bank/Branch | Destination bank details |
| Value Date | Settlement date |
| Related Account(s) | Other accounts linked to suspicion |

#### Part D: Suspicion Details
| Field | Description |
|-------|-------------|
| Date of Detection | When suspicion was identified |
| Category of Suspicion | Pre-defined categories (see below) |
| Reason for Suspicion | Detailed narrative |
| Summary of Transaction(s) | Overview of suspicious activity |
| Amount Involved | Total suspected amount |
| Period of Suspicious Activity | Date range |
| Action Taken by Reporting Entity | Internal actions (account freeze, enhanced monitoring, etc.) |
| Supporting Documents | References to attached evidence |

#### Part E: Related Persons/Entities
| Field | Description |
|-------|-------------|
| Related Person Name | Associated individuals |
| Relationship | Nature of relationship |
| Related Account Details | Linked accounts |
| Role in Suspicious Activity | Their involvement |

### 2.4 Categories of Suspicion (STR)
1. Terrorist Financing
2. Structuring / Smurfing (splitting transactions to avoid threshold)
3. Unusual pattern inconsistent with customer profile
4. Rapid movement of funds (pass-through)
5. Shell company transactions
6. Circular trading / Round-tripping
7. Layering through multiple accounts
8. Use of third-party accounts
9. Unusual cash transactions
10. Trade-based money laundering
11. Transactions with high-risk jurisdictions
12. Identity document concerns
13. Others (with explanation)

---

## 3. PMLA REPORTING REQUIREMENTS FOR BANKS

### 3.1 Prevention of Money Laundering Act, 2002 (PMLA)

**Key obligations for banks under PMLA & RBI Master Directions:**

#### Reporting Thresholds:
| Report | Threshold | Timeline |
|--------|-----------|----------|
| **CTR** (Cash Transaction Report) | Cash transactions ≥ ₹10 lakh (single) or series totaling ≥ ₹10 lakh in a month | Within 15 days of the month |
| **STR** (Suspicious Transaction Report) | No threshold - suspicion-based | Within 7 working days of confirmation of suspicion |
| **CBWTR** (Cross Border Wire Transfer) | All cross-border wire transfers ≥ ₹5 lakh | Within 15 days of the month |
| **CCR** (Counterfeit Currency Report) | All counterfeit notes detected | Within 15 days of the month |
| **NTR** | Transactions by NPOs ≥ ₹10 lakh | Within 15 days of the month |

#### Bank Obligations under PMLA:
1. **Customer Due Diligence (CDD)** - KYC at account opening and periodic updates
2. **Enhanced Due Diligence (EDD)** - For high-risk customers, PEPs, high-risk jurisdictions
3. **Record Keeping** - Maintain records for **5 years** after business relationship ends
4. **Transaction Monitoring** - Automated systems to flag suspicious patterns
5. **Principal Officer** - Designate a PMLA Principal Officer to file reports
6. **Staff Training** - Regular AML/CFT training programs
7. **Internal Audit** - Concurrent audit of AML compliance
8. **Risk-Based Approach** - Customer risk categorization (Low/Medium/High)

#### RBI Master Direction Key Points:
- **Wire Transfer Rules**: Originator information must accompany all domestic transfers ≥ ₹50,000
- **Shell Company Accounts**: Enhanced scrutiny, immediate STR if suspicion
- **Politically Exposed Persons (PEPs)**: Senior management approval for relationships
- **Correspondent Banking**: Due diligence on respondent banks
- **Record Retention**: All CTR/STR records for 5 years from date of transaction
- **Tipping Off**: Prohibited - cannot inform customer that STR has been filed

---

## 4. FATF STANDARDS & DATA FORMAT REFERENCE

### 4.1 FATF 40 Recommendations (Key Data Points)
The Financial Action Task Force (FATF) specifies these data elements for transaction monitoring:

| Data Element | FATF Requirement |
|--------------|-----------------|
| Originator Name | Full name of sender |
| Originator Account | Account number or unique reference |
| Originator Address/DOB/National ID | At least one identifier |
| Beneficiary Name | Full name of receiver |
| Beneficiary Account | Account number |
| Transaction Amount | Value and currency |
| Date/Time | When transaction occurred |
| Purpose of Payment | Reason/description |
| Intermediary Institution(s) | Banks in the payment chain |

### 4.2 FATF Red Flag Indicators Relevant to Data Features:
- Transactions just below reporting thresholds (structuring)
- Multiple accounts with rapid fund movement
- Transactions inconsistent with customer profile
- Complex layering through multiple jurisdictions
- Use of nominees, shell companies, trusts
- Cash-intensive businesses with high electronic transfers
- Round-trip transactions

---

## 5. RECOMMENDED DATASET STRATEGY FOR TRACEX

### Priority 1 (Must Use):
| Dataset | Why |
|---------|-----|
| **IBM AML** (Large) | Best for multi-hop graph-based detection, labeled patterns, realistic scale |
| **Elliptic Bitcoin** | Pre-built graph, real labels, proven GNN benchmark |

### Priority 2 (Supplement):
| Dataset | Why |
|---------|-----|
| **PaySim** | Good for temporal analysis, balance-based detection |
| **AMLSim** (Generator) | Can create custom Indian-context scenarios |

### Priority 3 (Demo/Prototype):
| Dataset | Why |
|---------|-----|
| **IBM AML** (Small) | Quick prototyping with same schema |
| **BankSim** | Simple customer-merchant graphs |

### Data Mapping to Indian STR Format:
```
IBM AML Column          →  STR Field Equivalent
─────────────────────────────────────────────────
Timestamp               →  Date of Transaction
From_Account_ID         →  Remitter Account Number
From_Bank_ID            →  Remitter Bank
To_Account_ID           →  Beneficiary Account Number
To_Bank_ID              →  Beneficiary Bank
Amount_Paid             →  Amount (Debit)
Amount_Received         →  Amount (Credit)
Payment_Currency        →  Currency
Payment_Type (ACH)      →  Mode of Transaction
Is_Laundering           →  Category of Suspicion
Pattern Type            →  Reason for Suspicion
```

---

## 6. USEFUL LINKS

| Resource | URL |
|----------|-----|
| IBM AML Dataset | https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml |
| IBM Multi-GNN Code | https://github.com/IBM/Multi-GNN |
| Elliptic Dataset | https://www.kaggle.com/datasets/ellipticco/elliptic-data-set |
| PaySim Dataset | https://www.kaggle.com/datasets/ealaxi/paysim1 |
| PaySim Source Code | https://github.com/EdgarLopezPhD/PaySim |
| AMLSim (IBM Generator) | https://github.com/IBM/AMLSim |
| FIU India | https://fiuindia.gov.in |
| FATF Recommendations | https://www.fatf-gafi.org/en/recommendations.html |
| RBI KYC Master Direction | https://rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=11566 |
| PMLA Act 2002 | https://legislative.gov.in/sites/default/files/A2003-15.pdf |
| IBM AML Paper (arXiv) | https://arxiv.org/abs/2306.16424 |
| Elliptic Paper (KDD 2019) | https://arxiv.org/abs/1908.02591 |
