#!/usr/bin/env python3
"""
Generate a synthetic daily EOD transaction CSV file in IBM AML format.
Used for testing the incremental ingestion pipeline.

Usage:
    python scripts/generate_test_eod.py [--output data/eod_test_2026-05-31.csv] [--num-txns 1000]
"""
import argparse
import os
import random
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def generate_eod_csv(output_path: str, num_transactions: int = 1000,
                     date: str = None, num_accounts: int = 200,
                     fraud_ratio: float = 0.05):
    """Generate a synthetic EOD CSV in IBM AML format."""
    date = date or datetime.now().strftime("%Y/%m/%d")

    # Generate account pool (mix of new and potentially existing accounts)
    accounts = [f"{random.randint(1, 999):03d}{random.choice('ABCDE')}{random.randint(1000, 9999)}"
                for _ in range(num_accounts)]
    # Add some known accounts that might already exist in the system
    known_accounts = ["803DA4620", "100EC5127", "200AB3315", "500CF8890", "700GH2234"]
    accounts.extend(known_accounts)

    banks = ["ICICI", "SBI", "HDFC", "AXIS", "PNB", "BOB", "KOTAK", "YES", "IDBI", "CANARA"]
    currencies = ["US Dollar", "Indian Rupee", "Euro", "UK Pound", "Bitcoin"]
    payment_formats = ["Cheque", "ACH", "Wire", "Credit Card", "Reinvestment"]

    # Generate structuring pattern (amounts near ₹10L threshold)
    structuring_accounts = random.sample(accounts, max(3, int(num_accounts * 0.02)))

    # Generate fan-out pattern
    fan_out_sources = random.sample(accounts, max(2, int(num_accounts * 0.01)))

    # Generate round-trip pairs
    round_trip_pairs = [(random.choice(accounts), random.choice(accounts)) for _ in range(5)]

    lines = []
    lines.append("Timestamp,From Bank,Account,To Bank,Account.1,Amount Received,Receiving Currency,Amount Paid,Payment Currency,Payment Format,Is Laundering")

    fraud_count = 0
    for i in range(num_transactions):
        hour = random.randint(0, 23)
        minute = random.randint(0, 59)
        timestamp = f"{date} {hour:02d}:{minute:02d}"

        from_bank = random.choice(banks)
        to_bank = random.choice(banks)
        src_account = random.choice(accounts)
        dst_account = random.choice([a for a in accounts if a != src_account])

        currency = random.choice(currencies)
        payment_format = random.choice(payment_formats)

        # Determine amount and fraud label
        is_laundering = 0

        # Structuring: amounts near ₹10L (in original currency this is ~12,000 USD)
        if src_account in structuring_accounts and random.random() < 0.3:
            amount = random.uniform(10800, 11900)  # Just below $12k equivalent
            is_laundering = 1
            fraud_count += 1
        # Fan-out: source sends to many
        elif src_account in fan_out_sources and random.random() < 0.2:
            amount = random.uniform(5000, 50000)
            is_laundering = 1
            fraud_count += 1
        # Round-trip
        elif any(src_account == p[0] and dst_account == p[1] for p in round_trip_pairs):
            amount = random.uniform(10000, 100000)
            is_laundering = 1
            fraud_count += 1
        # Normal transaction
        else:
            # Log-normal distribution for realistic amounts
            amount = min(random.lognormvariate(7.5, 1.8), 500000)
            if random.random() < fraud_ratio:
                is_laundering = 1
                fraud_count += 1

        amount_received = round(amount * random.uniform(0.98, 1.02), 2)
        amount_paid = round(amount, 2)

        line = f"{timestamp},{from_bank},{src_account},{to_bank},{dst_account},{amount_received},{currency},{amount_paid},{currency},{payment_format},{is_laundering}"
        lines.append(line)

    # Write
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    with open(output_path, "w") as f:
        f.write("\n".join(lines))

    print(f"✅ Generated {num_transactions} transactions → {output_path}")
    print(f"   Accounts: {num_accounts + len(known_accounts)}")
    print(f"   Fraud transactions: {fraud_count} ({fraud_count/num_transactions*100:.1f}%)")
    print(f"   Date: {date}")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate test EOD CSV")
    parser.add_argument("--output", "-o", default="data/eod_test.csv", help="Output path")
    parser.add_argument("--num-txns", "-n", type=int, default=1000, help="Number of transactions")
    parser.add_argument("--num-accounts", "-a", type=int, default=200, help="Number of accounts")
    parser.add_argument("--date", "-d", default=None, help="Date (YYYY/MM/DD)")
    parser.add_argument("--fraud-ratio", "-f", type=float, default=0.05, help="Fraud ratio")

    args = parser.parse_args()
    generate_eod_csv(args.output, args.num_txns, args.date, args.num_accounts, args.fraud_ratio)
