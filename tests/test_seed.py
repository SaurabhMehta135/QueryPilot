"""
tests/test_seed.py - Verifies determinism, integrity, and safety fixtures of sample database.
"""

import os
import sqlite3
import tempfile
import pytest
from data.seed import seed_database


def test_seed_determinism():
    """Seeds two separate databases with the same seed and asserts identical row counts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db1 = os.path.join(tmpdir, "test1.db")
        db2 = os.path.join(tmpdir, "test2.db")

        counts1 = seed_database(db1, seed=42)
        counts2 = seed_database(db2, seed=42)

        assert counts1 == counts2
        assert counts1["customers"] == 250
        assert counts1["categories"] == 8
        assert counts1["products"] >= 50
        assert counts1["orders"] > 1000
        assert counts1["order_items"] > 2500
        assert counts1["payments"] > 1000
        assert counts1["reviews"] > 500


def test_seed_schema_and_integrity():
    """Verifies foreign keys, edge cases (cancellations/refunds/nulls), and sensitive columns."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "integrity.db")
        seed_database(db_path, seed=42)

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        # Check sensitive columns exist
        cur.execute("PRAGMA table_info(customers)")
        cols = {row[1] for row in cur.fetchall()}
        assert "email" in cols
        assert "phone" in cols

        # Check nullable phones exist
        cur.execute("SELECT COUNT(*) FROM customers WHERE phone IS NULL")
        null_phones = cur.fetchone()[0]
        assert null_phones > 0, "Expected at least some nullable phones"

        # Check cancelled orders exist
        cur.execute("SELECT COUNT(*) FROM orders WHERE status = 'cancelled'")
        cancelled_orders = cur.fetchone()[0]
        assert cancelled_orders > 0

        # Check refunded payments exist
        cur.execute("SELECT COUNT(*) FROM payments WHERE status = 'refunded'")
        refunded_payments = cur.fetchone()[0]
        assert refunded_payments > 0

        # Check planted prompt injection strings
        cur.execute("SELECT name, description FROM products WHERE description LIKE '%Ignore previous instructions%'")
        planted = cur.fetchall()
        assert len(planted) >= 1, "Planted prompt injection product description not found"

        # Check never-ordered products exist
        cur.execute("""
            SELECT COUNT(*) FROM products
            WHERE product_id NOT IN (SELECT DISTINCT product_id FROM order_items)
        """)
        unpurchased = cur.fetchone()[0]
        assert unpurchased > 0, "Expected some products with zero orders"

        conn.close()
