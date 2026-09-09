#!/usr/bin/env python3
"""Regression tests for fail-closed legacy Gumroad CSV observation."""
import os
import tempfile

import traffic_monitor as monitor


def check(label, condition):
    if not condition:
        raise AssertionError(label)
    print("PASS", label)


def run_case(text):
    with tempfile.TemporaryDirectory() as temp_dir:
        path = os.path.join(temp_dir, "gumroad-sales.csv")
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        old = monitor.SALES
        try:
            monitor.SALES = path
            return monitor.sales_summary()
        finally:
            monitor.SALES = old


def main():
    line, trusted = run_case("date,units,amount_thb\n")
    check("header-only file is not treated as sales data", not trusted and "ยังไม่" in line)
    line, trusted = run_case("purchase_date,product,price_thb,buyer_email\n")
    check("legacy PII schema fails closed", not trusted and "UNRECONCILED" in line)
    line, trusted = run_case("date,units,amount_thb\n2026-08-16,2,258\n")
    check(
        "valid aggregate remains excluded from verified revenue",
        not trusted and "UNRECONCILED" in line and "2 ชิ้น" in line and "258 บาท" in line,
    )
    line, trusted = run_case("date,units,amount_thb\nnot-a-date,1,59\n")
    check("invalid values fail closed", not trusted and "UNRECONCILED" in line)
    print("sales data contract: all checks passed")


if __name__ == "__main__":
    main()
