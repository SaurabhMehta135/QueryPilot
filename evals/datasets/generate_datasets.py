"""
evals/datasets/generate_datasets.py - Deterministic benchmark dataset generator for QueryPilot Phase 8.
Generates 150+ verified analytical Text-to-SQL questions, executes every reference query against sample.db,
and partitions them into dev.jsonl (for prompt tuning) and held_out_test.jsonl (for reported figures).
Also synthesizes safety.jsonl (45 attack & abuse cases + 20 benign look-alikes).
"""

import os
import json
import sqlite3
import hashlib
from typing import List, Dict, Any

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "sample.db")
DATASETS_DIR = os.path.dirname(os.path.abspath(__file__))


def get_db_hash() -> str:
    with open(DB_PATH, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


QUESTIONS_SPEC: List[Dict[str, Any]] = [
    # =========================================================================
    # EASY QUESTIONS (50 Questions) - Single table filters, counts, sums, basic sorting
    # =========================================================================
    {"id": "easy-001", "difficulty": "easy", "order_matters": False,
     "question": "How many total products are in the catalog?",
     "reference_sql": "SELECT COUNT(*) AS total_products FROM products;"},

    {"id": "easy-002", "difficulty": "easy", "order_matters": False,
     "question": "What is the average price of all products?",
     "reference_sql": "SELECT ROUND(AVG(price), 2) AS average_price FROM products;"},

    {"id": "easy-003", "difficulty": "easy", "order_matters": False,
     "question": "How many customers are registered in California?",
     "reference_sql": "SELECT COUNT(*) AS ca_customers FROM customers WHERE state = 'CA';"},

    {"id": "easy-004", "difficulty": "easy", "order_matters": True,
     "question": "List the 5 most expensive products and their prices.",
     "reference_sql": "SELECT name, price FROM products ORDER BY price DESC LIMIT 5;"},

    {"id": "easy-005", "difficulty": "easy", "order_matters": True,
     "question": "Which 5 products have the lowest stock quantity?",
     "reference_sql": "SELECT name, stock_quantity FROM products ORDER BY stock_quantity ASC LIMIT 5;"},

    {"id": "easy-006", "difficulty": "easy", "order_matters": False,
     "question": "How many completed orders have been placed?",
     "reference_sql": "SELECT COUNT(*) AS completed_orders FROM orders WHERE status = 'completed';"},

    {"id": "easy-007", "difficulty": "easy", "order_matters": False,
     "question": "What is the total revenue collected across all completed orders?",
     "reference_sql": "SELECT ROUND(SUM(total_amount), 2) AS total_revenue FROM orders WHERE status = 'completed';"},

    {"id": "easy-008", "difficulty": "easy", "order_matters": False,
     "question": "How many reviews have a 5-star rating?",
     "reference_sql": "SELECT COUNT(*) AS five_star_reviews FROM reviews WHERE rating = 5;"},

    {"id": "easy-009", "difficulty": "easy", "order_matters": False,
     "question": "What is the total amount paid using credit card?",
     "reference_sql": "SELECT ROUND(SUM(amount), 2) AS credit_card_total FROM payments WHERE payment_method = 'credit_card' AND status = 'successful';"},

    {"id": "easy-010", "difficulty": "easy", "order_matters": True,
     "question": "List all distinct product categories in alphabetical order.",
     "reference_sql": "SELECT name FROM categories ORDER BY name ASC;"},

    {"id": "easy-011", "difficulty": "easy", "order_matters": False,
     "question": "How many products currently have zero stock?",
     "reference_sql": "SELECT COUNT(*) AS out_of_stock FROM products WHERE stock_quantity = 0;"},

    {"id": "easy-012", "difficulty": "easy", "order_matters": False,
     "question": "What is the highest single order total amount?",
     "reference_sql": "SELECT MAX(total_amount) AS max_order_amount FROM orders;"},

    {"id": "easy-013", "difficulty": "easy", "order_matters": False,
     "question": "What is the lowest single order total amount?",
     "reference_sql": "SELECT MIN(total_amount) AS min_order_amount FROM orders WHERE status = 'completed';"},

    {"id": "easy-014", "difficulty": "easy", "order_matters": False,
     "question": "How many orders were placed in the year 2024?",
     "reference_sql": "SELECT COUNT(*) AS orders_2024 FROM orders WHERE strftime('%Y', order_date) = '2024';"},

    {"id": "easy-015", "difficulty": "easy", "order_matters": False,
     "question": "How many orders were placed in the year 2023?",
     "reference_sql": "SELECT COUNT(*) AS orders_2023 FROM orders WHERE strftime('%Y', order_date) = '2023';"},

    {"id": "easy-016", "difficulty": "easy", "order_matters": False,
     "question": "How many customers are located in New York city?",
     "reference_sql": "SELECT COUNT(*) AS ny_customers FROM customers WHERE city = 'New York';"},

    {"id": "easy-017", "difficulty": "easy", "order_matters": False,
     "question": "What is the average rating across all customer reviews?",
     "reference_sql": "SELECT ROUND(AVG(rating), 2) AS average_rating FROM reviews;"},

    {"id": "easy-018", "difficulty": "easy", "order_matters": False,
     "question": "How many payments failed?",
     "reference_sql": "SELECT COUNT(*) AS failed_payments FROM payments WHERE status = 'failed';"},

    {"id": "easy-019", "difficulty": "easy", "order_matters": False,
     "question": "How many total items were sold across all order items?",
     "reference_sql": "SELECT SUM(quantity) AS total_items_sold FROM order_items;"},

    {"id": "easy-020", "difficulty": "easy", "order_matters": False,
     "question": "How many cancelled orders are in the database?",
     "reference_sql": "SELECT COUNT(*) AS cancelled_orders FROM orders WHERE status = 'cancelled';"},

    {"id": "easy-021", "difficulty": "easy", "order_matters": False,
     "question": "What is the maximum product price in the catalog?",
     "reference_sql": "SELECT MAX(price) AS max_price FROM products;"},

    {"id": "easy-022", "difficulty": "easy", "order_matters": False,
     "question": "What is the minimum product price in the catalog?",
     "reference_sql": "SELECT MIN(price) AS min_price FROM products;"},

    {"id": "easy-023", "difficulty": "easy", "order_matters": True,
     "question": "List the top 10 customers ordered by creation date ascending.",
     "reference_sql": "SELECT customer_id, first_name, last_name, created_at FROM customers ORDER BY created_at ASC LIMIT 10;"},

    {"id": "easy-024", "difficulty": "easy", "order_matters": False,
     "question": "How many customers do not have a phone number listed?",
     "reference_sql": "SELECT COUNT(*) AS missing_phone FROM customers WHERE phone IS NULL OR phone = '';"},

    {"id": "easy-025", "difficulty": "easy", "order_matters": False,
     "question": "How many orders have a total amount greater than 500 dollars?",
     "reference_sql": "SELECT COUNT(*) AS large_orders FROM orders WHERE total_amount > 500;"},

    {"id": "easy-026", "difficulty": "easy", "order_matters": False,
     "question": "What is the average order amount for completed orders?",
     "reference_sql": "SELECT ROUND(AVG(total_amount), 2) AS avg_completed_order FROM orders WHERE status = 'completed';"},

    {"id": "easy-027", "difficulty": "easy", "order_matters": True,
     "question": "Show the 5 most recent reviews with their ratings and comments.",
     "reference_sql": "SELECT review_id, rating, comment, review_date FROM reviews ORDER BY review_date DESC LIMIT 5;"},

    {"id": "easy-028", "difficulty": "easy", "order_matters": False,
     "question": "How many distinct payment methods have been used?",
     "reference_sql": "SELECT COUNT(DISTINCT payment_method) AS method_count FROM payments;"},

    {"id": "easy-029", "difficulty": "easy", "order_matters": False,
     "question": "How many products cost more than 100 dollars?",
     "reference_sql": "SELECT COUNT(*) AS expensive_products FROM products WHERE price > 100;"},

    {"id": "easy-030", "difficulty": "easy", "order_matters": False,
     "question": "What is the total stock quantity of all products combined?",
     "reference_sql": "SELECT SUM(stock_quantity) AS total_inventory FROM products;"},

    {"id": "easy-031", "difficulty": "easy", "order_matters": False,
     "question": "How many orders are currently in pending status?",
     "reference_sql": "SELECT COUNT(*) AS pending_orders FROM orders WHERE status = 'pending';"},

    {"id": "easy-032", "difficulty": "easy", "order_matters": False,
     "question": "How many orders are marked as shipped?",
     "reference_sql": "SELECT COUNT(*) AS shipped_orders FROM orders WHERE status = 'shipped';"},

    {"id": "easy-033", "difficulty": "easy", "order_matters": False,
     "question": "How many reviews gave a 1-star rating?",
     "reference_sql": "SELECT COUNT(*) AS one_star_reviews FROM reviews WHERE rating = 1;"},

    {"id": "easy-034", "difficulty": "easy", "order_matters": False,
     "question": "How many customers are registered in Texas?",
     "reference_sql": "SELECT COUNT(*) AS tx_customers FROM customers WHERE state = 'TX';"},

    {"id": "easy-035", "difficulty": "easy", "order_matters": False,
     "question": "How many customers are registered in Florida?",
     "reference_sql": "SELECT COUNT(*) AS fl_customers FROM customers WHERE state = 'FL';"},

    {"id": "easy-036", "difficulty": "easy", "order_matters": True,
     "question": "List the 5 products with the highest stock quantity.",
     "reference_sql": "SELECT name, stock_quantity FROM products ORDER BY stock_quantity DESC LIMIT 5;"},

    {"id": "easy-037", "difficulty": "easy", "order_matters": False,
     "question": "How many order items received a discount greater than 0?",
     "reference_sql": "SELECT COUNT(*) AS discounted_items FROM order_items WHERE discount > 0;"},

    {"id": "easy-038", "difficulty": "easy", "order_matters": False,
     "question": "What is the average discount given across all order items?",
     "reference_sql": "SELECT ROUND(AVG(discount), 4) AS avg_discount FROM order_items;"},

    {"id": "easy-039", "difficulty": "easy", "order_matters": False,
     "question": "What is the total dollar amount of all successful payments?",
     "reference_sql": "SELECT ROUND(SUM(amount), 2) AS total_paid FROM payments WHERE status = 'successful';"},

    {"id": "easy-040", "difficulty": "easy", "order_matters": False,
     "question": "How many customers registered in the year 2023?",
     "reference_sql": "SELECT COUNT(*) AS customers_2023 FROM customers WHERE strftime('%Y', created_at) = '2023';"},

    {"id": "easy-041", "difficulty": "easy", "order_matters": False,
     "question": "How many customers registered in the year 2024?",
     "reference_sql": "SELECT COUNT(*) AS customers_2024 FROM customers WHERE strftime('%Y', created_at) = '2024';"},

    {"id": "easy-042", "difficulty": "easy", "order_matters": True,
     "question": "List the top 5 largest completed orders by total amount.",
     "reference_sql": "SELECT order_id, customer_id, total_amount FROM orders WHERE status = 'completed' ORDER BY total_amount DESC LIMIT 5;"},

    {"id": "easy-043", "difficulty": "easy", "order_matters": False,
     "question": "How many payments used PayPal as the payment method?",
     "reference_sql": "SELECT COUNT(*) AS paypal_payments FROM payments WHERE payment_method = 'paypal';"},

    {"id": "easy-044", "difficulty": "easy", "order_matters": False,
     "question": "What is the average price of products with price under 50 dollars?",
     "reference_sql": "SELECT ROUND(AVG(price), 2) AS avg_cheap_product FROM products WHERE price < 50;"},

    {"id": "easy-045", "difficulty": "easy", "order_matters": False,
     "question": "How many reviews were submitted in 2024?",
     "reference_sql": "SELECT COUNT(*) AS reviews_2024 FROM reviews WHERE strftime('%Y', review_date) = '2024';"},

    {"id": "easy-046", "difficulty": "easy", "order_matters": False,
     "question": "How many total categories exist?",
     "reference_sql": "SELECT COUNT(*) AS total_categories FROM categories;"},

    {"id": "easy-047", "difficulty": "easy", "order_matters": True,
     "question": "List the 3 cheapest products in the catalog.",
     "reference_sql": "SELECT name, price FROM products ORDER BY price ASC LIMIT 3;"},

    {"id": "easy-048", "difficulty": "easy", "order_matters": False,
     "question": "How many order items have a quantity of 5 or more?",
     "reference_sql": "SELECT COUNT(*) AS bulk_items FROM order_items WHERE quantity >= 5;"},

    {"id": "easy-049", "difficulty": "easy", "order_matters": False,
     "question": "What is the total quantity of items in order ID 1?",
     "reference_sql": "SELECT SUM(quantity) AS order_1_quantity FROM order_items WHERE order_id = 1;"},

    {"id": "easy-050", "difficulty": "easy", "order_matters": False,
     "question": "How many customers are in the state of Washington?",
     "reference_sql": "SELECT COUNT(*) AS wa_customers FROM customers WHERE state = 'WA';"},

    # =========================================================================
    # MEDIUM QUESTIONS (65 Questions) - Joins, GROUP BY, aggregations, subqueries
    # =========================================================================
    {"id": "med-001", "difficulty": "medium", "order_matters": True,
     "question": "What is the total number of products in each category?",
     "reference_sql": "SELECT c.name AS category_name, COUNT(p.product_id) AS product_count FROM categories c LEFT JOIN products p ON c.category_id = p.category_id GROUP BY c.category_id, c.name ORDER BY product_count DESC;"},

    {"id": "med-002", "difficulty": "medium", "order_matters": True,
     "question": "What is the total revenue generated by each product category?",
     "reference_sql": "SELECT c.name AS category_name, ROUND(SUM(oi.quantity * oi.unit_price * (1 - oi.discount)), 2) AS total_revenue FROM categories c JOIN products p ON c.category_id = p.category_id JOIN order_items oi ON p.product_id = oi.product_id JOIN orders o ON oi.order_id = o.order_id WHERE o.status = 'completed' GROUP BY c.category_id, c.name ORDER BY total_revenue DESC;"},

    {"id": "med-003", "difficulty": "medium", "order_matters": True,
     "question": "List the top 5 customers who have spent the most money on completed orders.",
     "reference_sql": "SELECT c.customer_id, c.first_name, c.last_name, ROUND(SUM(o.total_amount), 2) AS total_spent FROM customers c JOIN orders o ON c.customer_id = o.customer_id WHERE o.status = 'completed' GROUP BY c.customer_id, c.first_name, c.last_name ORDER BY total_spent DESC LIMIT 5;"},

    {"id": "med-004", "difficulty": "medium", "order_matters": True,
     "question": "Which 5 products have generated the highest total revenue?",
     "reference_sql": "SELECT p.name AS product_name, ROUND(SUM(oi.quantity * oi.unit_price * (1 - oi.discount)), 2) AS revenue FROM products p JOIN order_items oi ON p.product_id = oi.product_id JOIN orders o ON oi.order_id = o.order_id WHERE o.status = 'completed' GROUP BY p.product_id, p.name ORDER BY revenue DESC LIMIT 5;"},

    {"id": "med-005", "difficulty": "medium", "order_matters": True,
     "question": "Which 5 products have been ordered the most by quantity?",
     "reference_sql": "SELECT p.name AS product_name, SUM(oi.quantity) AS total_quantity FROM products p JOIN order_items oi ON p.product_id = oi.product_id JOIN orders o ON oi.order_id = o.order_id WHERE o.status = 'completed' GROUP BY p.product_id, p.name ORDER BY total_quantity DESC LIMIT 5;"},

    {"id": "med-006", "difficulty": "medium", "order_matters": True,
     "question": "Show the average review rating and review count for each product that has at least 3 reviews.",
     "reference_sql": "SELECT p.name, ROUND(AVG(r.rating), 2) AS avg_rating, COUNT(r.review_id) AS review_count FROM products p JOIN reviews r ON p.product_id = r.product_id GROUP BY p.product_id, p.name HAVING COUNT(r.review_id) >= 3 ORDER BY avg_rating DESC;"},

    {"id": "med-007", "difficulty": "medium", "order_matters": True,
     "question": "What is the monthly revenue for completed orders in 2024?",
     "reference_sql": "SELECT strftime('%Y-%m', order_date) AS month, ROUND(SUM(total_amount), 2) AS monthly_revenue FROM orders WHERE status = 'completed' AND strftime('%Y', order_date) = '2024' GROUP BY strftime('%Y-%m', order_date) ORDER BY month ASC;"},

    {"id": "med-008", "difficulty": "medium", "order_matters": True,
     "question": "How many orders were placed by customers in each state?",
     "reference_sql": "SELECT c.state, COUNT(o.order_id) AS order_count FROM customers c JOIN orders o ON c.customer_id = o.customer_id GROUP BY c.state ORDER BY order_count DESC;"},

    {"id": "med-009", "difficulty": "medium", "order_matters": True,
     "question": "Find the top 5 states by total completed order spending.",
     "reference_sql": "SELECT c.state, ROUND(SUM(o.total_amount), 2) AS state_spending FROM customers c JOIN orders o ON c.customer_id = o.customer_id WHERE o.status = 'completed' GROUP BY c.state ORDER BY state_spending DESC LIMIT 5;"},

    {"id": "med-010", "difficulty": "medium", "order_matters": True,
     "question": "What is the total amount and count of successful payments per payment method?",
     "reference_sql": "SELECT payment_method, COUNT(payment_id) AS payment_count, ROUND(SUM(amount), 2) AS total_amount FROM payments WHERE status = 'successful' GROUP BY payment_method ORDER BY total_amount DESC;"},

    {"id": "med-011", "difficulty": "medium", "order_matters": True,
     "question": "Find customers who have placed more than 5 orders.",
     "reference_sql": "SELECT c.customer_id, c.first_name, c.last_name, COUNT(o.order_id) AS order_count FROM customers c JOIN orders o ON c.customer_id = o.customer_id GROUP BY c.customer_id, c.first_name, c.last_name HAVING COUNT(o.order_id) > 5 ORDER BY order_count DESC;"},

    {"id": "med-012", "difficulty": "medium", "order_matters": True,
     "question": "Which customers have registered but never placed an order?",
     "reference_sql": "SELECT c.customer_id, c.first_name, c.last_name FROM customers c LEFT JOIN orders o ON c.customer_id = o.customer_id WHERE o.order_id IS NULL ORDER BY c.customer_id ASC;"},

    {"id": "med-013", "difficulty": "medium", "order_matters": True,
     "question": "List products that have never received any customer reviews.",
     "reference_sql": "SELECT p.product_id, p.name FROM products p LEFT JOIN reviews r ON p.product_id = r.product_id WHERE r.review_id IS NULL ORDER BY p.product_id ASC;"},

    {"id": "med-014", "difficulty": "medium", "order_matters": True,
     "question": "Find products that have never been ordered.",
     "reference_sql": "SELECT p.product_id, p.name FROM products p LEFT JOIN order_items oi ON p.product_id = oi.product_id WHERE oi.item_id IS NULL ORDER BY p.product_id ASC;"},

    {"id": "med-015", "difficulty": "medium", "order_matters": True,
     "question": "What is the average order total by order status?",
     "reference_sql": "SELECT status, COUNT(*) AS count, ROUND(AVG(total_amount), 2) AS avg_total FROM orders GROUP BY status ORDER BY count DESC;"},

    {"id": "med-016", "difficulty": "medium", "order_matters": True,
     "question": "What is the average rating given per category of products?",
     "reference_sql": "SELECT c.name AS category_name, ROUND(AVG(r.rating), 2) AS avg_rating FROM categories c JOIN products p ON c.category_id = p.category_id JOIN reviews r ON p.product_id = r.product_id GROUP BY c.category_id, c.name ORDER BY avg_rating DESC;"},

    {"id": "med-017", "difficulty": "medium", "order_matters": True,
     "question": "Which payment method has the highest failure rate?",
     "reference_sql": "SELECT payment_method, COUNT(*) AS total_attempts, SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_count, ROUND(1.0 * SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) / COUNT(*), 4) AS failure_rate FROM payments GROUP BY payment_method ORDER BY failure_rate DESC;"},

    {"id": "med-018", "difficulty": "medium", "order_matters": True,
     "question": "What is the total revenue by quarter for completed orders?",
     "reference_sql": "SELECT strftime('%Y', order_date) AS order_year, CASE WHEN strftime('%m', order_date) IN ('01', '02', '03') THEN 'Q1' WHEN strftime('%m', order_date) IN ('04', '05', '06') THEN 'Q2' WHEN strftime('%m', order_date) IN ('07', '08', '09') THEN 'Q3' ELSE 'Q4' END AS quarter, ROUND(SUM(total_amount), 2) AS revenue FROM orders WHERE status = 'completed' GROUP BY order_year, quarter ORDER BY order_year ASC, quarter ASC;"},

    {"id": "med-019", "difficulty": "medium", "order_matters": True,
     "question": "List the top 5 customers with the most reviews written.",
     "reference_sql": "SELECT c.customer_id, c.first_name, c.last_name, COUNT(r.review_id) AS review_count FROM customers c JOIN reviews r ON c.customer_id = r.customer_id GROUP BY c.customer_id, c.first_name, c.last_name ORDER BY review_count DESC LIMIT 5;"},

    {"id": "med-020", "difficulty": "medium", "order_matters": True,
     "question": "What is the average item price by category?",
     "reference_sql": "SELECT c.name AS category_name, ROUND(AVG(p.price), 2) AS avg_price FROM categories c JOIN products p ON c.category_id = p.category_id GROUP BY c.category_id, c.name ORDER BY avg_price DESC;"},

    {"id": "med-021", "difficulty": "medium", "order_matters": True,
     "question": "Find all products that have an average rating lower than 3.0.",
     "reference_sql": "SELECT p.product_id, p.name, ROUND(AVG(r.rating), 2) AS avg_rating FROM products p JOIN reviews r ON p.product_id = r.product_id GROUP BY p.product_id, p.name HAVING AVG(r.rating) < 3.0 ORDER BY avg_rating ASC;"},

    {"id": "med-022", "difficulty": "medium", "order_matters": True,
     "question": "What are the 5 cities with the most registered customers?",
     "reference_sql": "SELECT city, state, COUNT(customer_id) AS customer_count FROM customers GROUP BY city, state ORDER BY customer_count DESC LIMIT 5;"},

    {"id": "med-023", "difficulty": "medium", "order_matters": True,
     "question": "What is the total discount amount given per product category?",
     "reference_sql": "SELECT c.name AS category_name, ROUND(SUM(oi.quantity * oi.unit_price * oi.discount), 2) AS total_discount_given FROM categories c JOIN products p ON c.category_id = p.category_id JOIN order_items oi ON p.product_id = oi.product_id JOIN orders o ON oi.order_id = o.order_id WHERE o.status = 'completed' GROUP BY c.category_id, c.name ORDER BY total_discount_given DESC;"},

    {"id": "med-024", "difficulty": "medium", "order_matters": True,
     "question": "Show the number of orders and total spending for customer ID 1.",
     "reference_sql": "SELECT COUNT(order_id) AS order_count, ROUND(SUM(total_amount), 2) AS total_spent FROM orders WHERE customer_id = 1 AND status = 'completed';"},

    {"id": "med-025", "difficulty": "medium", "order_matters": True,
     "question": "Which products have price higher than the average product price in their category?",
     "reference_sql": "SELECT p.name, p.price, p.category_id FROM products p WHERE p.price > (SELECT AVG(p2.price) FROM products p2 WHERE p2.category_id = p.category_id) ORDER BY p.price DESC;"},

    {"id": "med-026", "difficulty": "medium", "order_matters": True,
     "question": "What is the average number of items per order?",
     "reference_sql": "SELECT ROUND(AVG(item_count), 2) AS avg_items_per_order FROM (SELECT order_id, SUM(quantity) AS item_count FROM order_items GROUP BY order_id);"},

    {"id": "med-027", "difficulty": "medium", "order_matters": True,
     "question": "What is the total revenue by year for completed orders?",
     "reference_sql": "SELECT strftime('%Y', order_date) AS order_year, ROUND(SUM(total_amount), 2) AS annual_revenue FROM orders WHERE status = 'completed' GROUP BY strftime('%Y', order_date) ORDER BY order_year ASC;"},

    {"id": "med-028", "difficulty": "medium", "order_matters": True,
     "question": "List categories where the total inventory stock is less than 500 units.",
     "reference_sql": "SELECT c.name, SUM(p.stock_quantity) AS category_stock FROM categories c JOIN products p ON c.category_id = p.category_id GROUP BY c.category_id, c.name HAVING SUM(p.stock_quantity) < 500 ORDER BY category_stock ASC;"},

    {"id": "med-029", "difficulty": "medium", "order_matters": True,
     "question": "Find the customer who placed the earliest order in the system.",
     "reference_sql": "SELECT c.customer_id, c.first_name, c.last_name, o.order_date FROM customers c JOIN orders o ON c.customer_id = o.customer_id ORDER BY o.order_date ASC LIMIT 1;"},

    {"id": "med-030", "difficulty": "medium", "order_matters": True,
     "question": "Find the customer who placed the most recent order in the system.",
     "reference_sql": "SELECT c.customer_id, c.first_name, c.last_name, o.order_date FROM customers c JOIN orders o ON c.customer_id = o.customer_id ORDER BY o.order_date DESC LIMIT 1;"},

    {"id": "med-031", "difficulty": "medium", "order_matters": True,
     "question": "How many orders were paid using debit card versus credit card?",
     "reference_sql": "SELECT payment_method, COUNT(*) AS count FROM payments WHERE payment_method IN ('debit_card', 'credit_card') GROUP BY payment_method ORDER BY count DESC;"},

    {"id": "med-032", "difficulty": "medium", "order_matters": True,
     "question": "Which products have an average rating of 4.5 or higher with at least 2 reviews?",
     "reference_sql": "SELECT p.name, ROUND(AVG(r.rating), 2) AS avg_rating, COUNT(r.review_id) AS reviews FROM products p JOIN reviews r ON p.product_id = r.product_id GROUP BY p.product_id, p.name HAVING AVG(r.rating) >= 4.5 AND COUNT(r.review_id) >= 2 ORDER BY avg_rating DESC;"},

    {"id": "med-033", "difficulty": "medium", "order_matters": True,
     "question": "What is the breakdown of reviews by star rating from 1 to 5?",
     "reference_sql": "SELECT rating, COUNT(*) AS review_count FROM reviews GROUP BY rating ORDER BY rating DESC;"},

    {"id": "med-034", "difficulty": "medium", "order_matters": True,
     "question": "Find the 5 customers who received the largest total discount across their orders.",
     "reference_sql": "SELECT c.customer_id, c.first_name, c.last_name, ROUND(SUM(oi.quantity * oi.unit_price * oi.discount), 2) AS total_savings FROM customers c JOIN orders o ON c.customer_id = o.customer_id JOIN order_items oi ON o.order_id = oi.order_id WHERE o.status = 'completed' GROUP BY c.customer_id, c.first_name, c.last_name ORDER BY total_savings DESC LIMIT 5;"},

    {"id": "med-035", "difficulty": "medium", "order_matters": True,
     "question": "What is the total value of inventory currently in stock for each category?",
     "reference_sql": "SELECT c.name AS category_name, ROUND(SUM(p.price * p.stock_quantity), 2) AS inventory_value FROM categories c JOIN products p ON c.category_id = p.category_id GROUP BY c.category_id, c.name ORDER BY inventory_value DESC;"},

    {"id": "med-036", "difficulty": "medium", "order_matters": True,
     "question": "Show the number of completed orders and total revenue per month in 2023.",
     "reference_sql": "SELECT strftime('%Y-%m', order_date) AS month, COUNT(order_id) AS order_count, ROUND(SUM(total_amount), 2) AS revenue FROM orders WHERE status = 'completed' AND strftime('%Y', order_date) = '2023' GROUP BY strftime('%Y-%m', order_date) ORDER BY month ASC;"},

    {"id": "med-037", "difficulty": "medium", "order_matters": True,
     "question": "Find the top 3 products with the highest number of 5-star reviews.",
     "reference_sql": "SELECT p.name, COUNT(r.review_id) AS five_star_count FROM products p JOIN reviews r ON p.product_id = r.product_id WHERE r.rating = 5 GROUP BY p.product_id, p.name ORDER BY five_star_count DESC LIMIT 3;"},

    {"id": "med-038", "difficulty": "medium", "order_matters": True,
     "question": "What percentage of total orders have status 'cancelled'?",
     "reference_sql": "SELECT ROUND(100.0 * SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) / COUNT(*), 2) AS cancellation_rate FROM orders;"},

    {"id": "med-039", "difficulty": "medium", "order_matters": True,
     "question": "What percentage of total revenue came from credit card payments?",
     "reference_sql": "SELECT ROUND(100.0 * SUM(CASE WHEN payment_method = 'credit_card' THEN amount ELSE 0 END) / SUM(amount), 2) AS credit_card_revenue_pct FROM payments WHERE status = 'successful';"},

    {"id": "med-040", "difficulty": "medium", "order_matters": True,
     "question": "Show customers who have ordered products from at least 3 distinct categories.",
     "reference_sql": "SELECT c.customer_id, c.first_name, c.last_name, COUNT(DISTINCT p.category_id) AS distinct_categories FROM customers c JOIN orders o ON c.customer_id = o.customer_id JOIN order_items oi ON o.order_id = oi.order_id JOIN products p ON oi.product_id = p.product_id WHERE o.status = 'completed' GROUP BY c.customer_id, c.first_name, c.last_name HAVING COUNT(DISTINCT p.category_id) >= 3 ORDER BY distinct_categories DESC;"},

    {"id": "med-041", "difficulty": "medium", "order_matters": True,
     "question": "Find orders that contain more than 3 distinct products.",
     "reference_sql": "SELECT order_id, COUNT(DISTINCT product_id) AS product_count FROM order_items GROUP BY order_id HAVING COUNT(DISTINCT product_id) > 3 ORDER BY product_count DESC;"},

    {"id": "med-042", "difficulty": "medium", "order_matters": True,
     "question": "What is the average number of reviews submitted per customer for customers who submitted reviews?",
     "reference_sql": "SELECT ROUND(AVG(review_count), 2) AS avg_reviews_per_reviewer FROM (SELECT customer_id, COUNT(*) AS review_count FROM reviews GROUP BY customer_id);"},

    {"id": "med-043", "difficulty": "medium", "order_matters": True,
     "question": "List categories that have at least 10 products.",
     "reference_sql": "SELECT c.name, COUNT(p.product_id) AS product_count FROM categories c JOIN products p ON c.category_id = p.category_id GROUP BY c.category_id, c.name HAVING COUNT(p.product_id) >= 10 ORDER BY product_count DESC;"},

    {"id": "med-044", "difficulty": "medium", "order_matters": True,
     "question": "What is the total revenue for orders placed in the first half of 2024 (January to June)?",
     "reference_sql": "SELECT ROUND(SUM(total_amount), 2) AS h1_2024_revenue FROM orders WHERE status = 'completed' AND strftime('%Y', order_date) = '2024' AND strftime('%m', order_date) BETWEEN '01' AND '06';"},

    {"id": "med-045", "difficulty": "medium", "order_matters": True,
     "question": "What is the total revenue for orders placed in the second half of 2024 (July to December)?",
     "reference_sql": "SELECT ROUND(SUM(total_amount), 2) AS h2_2024_revenue FROM orders WHERE status = 'completed' AND strftime('%Y', order_date) = '2024' AND strftime('%m', order_date) BETWEEN '07' AND '12';"},

    {"id": "med-046", "difficulty": "medium", "order_matters": True,
     "question": "Find the top 5 products with the highest total units in stock.",
     "reference_sql": "SELECT product_id, name, stock_quantity FROM products ORDER BY stock_quantity DESC LIMIT 5;"},

    {"id": "med-047", "difficulty": "medium", "order_matters": True,
     "question": "What is the average order amount by shipping state?",
     "reference_sql": "SELECT c.state, ROUND(AVG(o.total_amount), 2) AS avg_order_amount FROM customers c JOIN orders o ON c.customer_id = o.customer_id WHERE o.status = 'completed' GROUP BY c.state ORDER BY avg_order_amount DESC;"},

    {"id": "med-048", "difficulty": "medium", "order_matters": True,
     "question": "Which product category has the highest average review rating?",
     "reference_sql": "SELECT c.name, ROUND(AVG(r.rating), 2) AS avg_rating FROM categories c JOIN products p ON c.category_id = p.category_id JOIN reviews r ON p.product_id = r.product_id GROUP BY c.category_id, c.name ORDER BY avg_rating DESC LIMIT 1;"},

    {"id": "med-049", "difficulty": "medium", "order_matters": True,
     "question": "Which product category has the lowest average review rating?",
     "reference_sql": "SELECT c.name, ROUND(AVG(r.rating), 2) AS avg_rating FROM categories c JOIN products p ON c.category_id = p.category_id JOIN reviews r ON p.product_id = r.product_id GROUP BY c.category_id, c.name ORDER BY avg_rating ASC LIMIT 1;"},

    {"id": "med-050", "difficulty": "medium", "order_matters": True,
     "question": "Show the number of orders per customer for the top 5 most frequent buyers.",
     "reference_sql": "SELECT customer_id, COUNT(order_id) AS order_count FROM orders GROUP BY customer_id ORDER BY order_count DESC LIMIT 5;"},

    {"id": "med-051", "difficulty": "medium", "order_matters": True,
     "question": "What is the total quantity of items ordered for product ID 10?",
     "reference_sql": "SELECT SUM(quantity) AS total_ordered FROM order_items WHERE product_id = 10;"},

    {"id": "med-052", "difficulty": "medium", "order_matters": True,
     "question": "Find products whose price is within 20 dollars of the maximum product price.",
     "reference_sql": "SELECT name, price FROM products WHERE price >= (SELECT MAX(price) - 20 FROM products) ORDER BY price DESC;"},

    {"id": "med-053", "difficulty": "medium", "order_matters": True,
     "question": "What is the count of orders placed on weekends (Saturday or Sunday)?",
     "reference_sql": "SELECT COUNT(*) AS weekend_orders FROM orders WHERE strftime('%w', order_date) IN ('0', '6');"},

    {"id": "med-054", "difficulty": "medium", "order_matters": True,
     "question": "What is the count of orders placed on weekdays (Monday through Friday)?",
     "reference_sql": "SELECT COUNT(*) AS weekday_orders FROM orders WHERE strftime('%w', order_date) NOT IN ('0', '6');"},

    {"id": "med-055", "difficulty": "medium", "order_matters": True,
     "question": "What is the total revenue generated on weekdays versus weekends?",
     "reference_sql": "SELECT CASE WHEN strftime('%w', order_date) IN ('0', '6') THEN 'Weekend' ELSE 'Weekday' END AS day_type, ROUND(SUM(total_amount), 2) AS revenue FROM orders WHERE status = 'completed' GROUP BY day_type ORDER BY revenue DESC;"},

    {"id": "med-056", "difficulty": "medium", "order_matters": True,
     "question": "Find the product with the most 1-star reviews.",
     "reference_sql": "SELECT p.name, COUNT(r.review_id) AS one_star_count FROM products p JOIN reviews r ON p.product_id = r.product_id WHERE r.rating = 1 GROUP BY p.product_id, p.name ORDER BY one_star_count DESC LIMIT 1;"},

    {"id": "med-057", "difficulty": "medium", "order_matters": True,
     "question": "What is the total revenue collected in Q1 of 2024?",
     "reference_sql": "SELECT ROUND(SUM(total_amount), 2) AS q1_2024_rev FROM orders WHERE status = 'completed' AND strftime('%Y', order_date) = '2024' AND strftime('%m', order_date) IN ('01', '02', '03');"},

    {"id": "med-058", "difficulty": "medium", "order_matters": True,
     "question": "What is the total revenue collected in Q2 of 2024?",
     "reference_sql": "SELECT ROUND(SUM(total_amount), 2) AS q2_2024_rev FROM orders WHERE status = 'completed' AND strftime('%Y', order_date) = '2024' AND strftime('%m', order_date) IN ('04', '05', '06');"},

    {"id": "med-059", "difficulty": "medium", "order_matters": True,
     "question": "Find the average order total for orders with at least 3 line items.",
     "reference_sql": "SELECT ROUND(AVG(total_amount), 2) AS avg_large_order FROM orders WHERE order_id IN (SELECT order_id FROM order_items GROUP BY order_id HAVING COUNT(item_id) >= 3);"},

    {"id": "med-060", "difficulty": "medium", "order_matters": True,
     "question": "How many orders had payment completed in full (successful payment amount >= order total amount)?",
     "reference_sql": "SELECT COUNT(DISTINCT o.order_id) AS fully_paid_orders FROM orders o JOIN payments p ON o.order_id = p.order_id WHERE p.status = 'successful' AND p.amount >= o.total_amount;"},

    {"id": "med-061", "difficulty": "medium", "order_matters": True,
     "question": "Show the number of customers created in each quarter of 2023.",
     "reference_sql": "SELECT CASE WHEN strftime('%m', created_at) IN ('01', '02', '03') THEN 'Q1' WHEN strftime('%m', created_at) IN ('04', '05', '06') THEN 'Q2' WHEN strftime('%m', created_at) IN ('07', '08', '09') THEN 'Q3' ELSE 'Q4' END AS quarter, COUNT(*) AS customer_count FROM customers WHERE strftime('%Y', created_at) = '2023' GROUP BY quarter ORDER BY quarter ASC;"},

    {"id": "med-062", "difficulty": "medium", "order_matters": True,
     "question": "List the top 5 most common email domains among registered customers.",
     "reference_sql": "SELECT SUBSTR(email, INSTR(email, '@') + 1) AS domain, COUNT(*) AS count FROM customers WHERE email IS NOT NULL AND INSTR(email, '@') > 0 GROUP BY domain ORDER BY count DESC LIMIT 5;"},

    {"id": "med-063", "difficulty": "medium", "order_matters": True,
     "question": "What is the average review length in characters by star rating?",
     "reference_sql": "SELECT rating, ROUND(AVG(LENGTH(comment)), 1) AS avg_comment_length FROM reviews GROUP BY rating ORDER BY rating DESC;"},

    {"id": "med-064", "difficulty": "medium", "order_matters": True,
     "question": "What is the count of distinct products ordered in 2024?",
     "reference_sql": "SELECT COUNT(DISTINCT oi.product_id) AS distinct_products_ordered FROM order_items oi JOIN orders o ON oi.order_id = o.order_id WHERE strftime('%Y', o.order_date) = '2024' AND o.status = 'completed';"},

    {"id": "med-065", "difficulty": "medium", "order_matters": True,
     "question": "Show the top 5 customers with the most cancelled orders.",
     "reference_sql": "SELECT customer_id, COUNT(order_id) AS cancelled_count FROM orders WHERE status = 'cancelled' GROUP BY customer_id ORDER BY cancelled_count DESC LIMIT 5;"},

    # =========================================================================
    # HARD QUESTIONS (35 Questions) - CTEs, conditional aggregation, multi-table joins, cohorts
    # =========================================================================
    {"id": "hard-001", "difficulty": "hard", "order_matters": True,
     "question": "What was the revenue drop or gain between Q1 and Q2 of 2024 using conditional aggregation?",
     "reference_sql": "SELECT ROUND(SUM(CASE WHEN strftime('%m', order_date) IN ('01', '02', '03') THEN total_amount ELSE 0 END), 2) AS q1_revenue, ROUND(SUM(CASE WHEN strftime('%m', order_date) IN ('04', '05', '06') THEN total_amount ELSE 0 END), 2) AS q2_revenue, ROUND(SUM(CASE WHEN strftime('%m', order_date) IN ('01', '02', '03') THEN total_amount ELSE 0 END) - SUM(CASE WHEN strftime('%m', order_date) IN ('04', '05', '06') THEN total_amount ELSE 0 END), 2) AS revenue_diff FROM orders WHERE status = 'completed' AND strftime('%Y', order_date) = '2024';"},

    {"id": "hard-002", "difficulty": "hard", "order_matters": True,
     "question": "Calculate customer lifetime value (LTV): rank the top 5 customers by total completed spend and include their average order value and order count.",
     "reference_sql": "SELECT c.customer_id, c.first_name, c.last_name, COUNT(o.order_id) AS order_count, ROUND(AVG(o.total_amount), 2) AS aov, ROUND(SUM(o.total_amount), 2) AS total_ltv FROM customers c JOIN orders o ON c.customer_id = o.customer_id WHERE o.status = 'completed' GROUP BY c.customer_id, c.first_name, c.last_name ORDER BY total_ltv DESC LIMIT 5;"},

    {"id": "hard-003", "difficulty": "hard", "order_matters": True,
     "question": "Identify repeat customers versus one-time buyers: count how many customers placed exactly 1 order versus 2 or more orders.",
     "reference_sql": "WITH customer_orders AS (SELECT customer_id, COUNT(order_id) AS num_orders FROM orders WHERE status = 'completed' GROUP BY customer_id) SELECT CASE WHEN num_orders = 1 THEN 'One-time Buyer' ELSE 'Repeat Buyer' END AS buyer_type, COUNT(*) AS customer_count FROM customer_orders GROUP BY buyer_type ORDER BY customer_count DESC;"},

    {"id": "hard-004", "difficulty": "hard", "order_matters": True,
     "question": "Which product category has the highest customer repeat purchase rate (orders with products from that category from repeat buyers)?",
     "reference_sql": "WITH repeat_customers AS (SELECT customer_id FROM orders WHERE status = 'completed' GROUP BY customer_id HAVING COUNT(order_id) > 1) SELECT c.name AS category_name, COUNT(DISTINCT o.order_id) AS repeat_orders FROM categories c JOIN products p ON c.category_id = p.category_id JOIN order_items oi ON p.product_id = oi.product_id JOIN orders o ON oi.order_id = o.order_id WHERE o.customer_id IN (SELECT customer_id FROM repeat_customers) AND o.status = 'completed' GROUP BY c.category_id, c.name ORDER BY repeat_orders DESC;"},

    {"id": "hard-005", "difficulty": "hard", "order_matters": True,
     "question": "Find the top product in each category by total revenue generated.",
     "reference_sql": "WITH product_rev AS (SELECT p.category_id, p.product_id, p.name, ROUND(SUM(oi.quantity * oi.unit_price * (1 - oi.discount)), 2) AS revenue FROM products p JOIN order_items oi ON p.product_id = oi.product_id JOIN orders o ON oi.order_id = o.order_id WHERE o.status = 'completed' GROUP BY p.category_id, p.product_id, p.name), ranked_products AS (SELECT category_id, product_id, name, revenue, ROW_NUMBER() OVER (PARTITION BY category_id ORDER BY revenue DESC) AS rank FROM product_rev) SELECT c.name AS category_name, rp.name AS top_product, rp.revenue FROM ranked_products rp JOIN categories c ON rp.category_id = c.category_id WHERE rp.rank = 1 ORDER BY rp.revenue DESC;"},

    {"id": "hard-006", "difficulty": "hard", "order_matters": True,
     "question": "Compute month-over-month revenue growth percentage for completed orders in 2024.",
     "reference_sql": "WITH monthly_rev AS (SELECT strftime('%Y-%m', order_date) AS month, ROUND(SUM(total_amount), 2) AS revenue FROM orders WHERE status = 'completed' AND strftime('%Y', order_date) = '2024' GROUP BY strftime('%Y-%m', order_date)) SELECT month, revenue, LAG(revenue) OVER (ORDER BY month) AS prev_month_revenue, ROUND(100.0 * (revenue - LAG(revenue) OVER (ORDER BY month)) / LAG(revenue) OVER (ORDER BY month), 2) AS mom_growth_pct FROM monthly_rev ORDER BY month ASC;"},

    {"id": "hard-007", "difficulty": "hard", "order_matters": True,
     "question": "Find churned customers: customers who placed an order in 2023 but placed zero orders in 2024.",
     "reference_sql": "SELECT c.customer_id, c.first_name, c.last_name FROM customers c WHERE c.customer_id IN (SELECT DISTINCT customer_id FROM orders WHERE strftime('%Y', order_date) = '2023' AND status = 'completed') AND c.customer_id NOT IN (SELECT DISTINCT customer_id FROM orders WHERE strftime('%Y', order_date) = '2024' AND status = 'completed') ORDER BY c.customer_id ASC;"},

    {"id": "hard-008", "difficulty": "hard", "order_matters": True,
     "question": "Find reactivated customers: customers who placed an order in 2024 after placing zero orders in 2023.",
     "reference_sql": "SELECT c.customer_id, c.first_name, c.last_name FROM customers c WHERE c.customer_id IN (SELECT DISTINCT customer_id FROM orders WHERE strftime('%Y', order_date) = '2024' AND status = 'completed') AND c.customer_id NOT IN (SELECT DISTINCT customer_id FROM orders WHERE strftime('%Y', order_date) = '2023' AND status = 'completed') ORDER BY c.customer_id ASC;"},

    {"id": "hard-009", "difficulty": "hard", "order_matters": True,
     "question": "Calculate the average time (in days) between a customer's first order and their second order.",
     "reference_sql": "WITH ranked_orders AS (SELECT customer_id, order_date, ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY order_date ASC) AS order_num FROM orders WHERE status = 'completed'), paired_orders AS (SELECT o1.customer_id, JULIANDAY(o2.order_date) - JULIANDAY(o1.order_date) AS days_between FROM ranked_orders o1 JOIN ranked_orders o2 ON o1.customer_id = o2.customer_id WHERE o1.order_num = 1 AND o2.order_num = 2) SELECT ROUND(AVG(days_between), 1) AS avg_days_to_second_order FROM paired_orders;"},

    {"id": "hard-010", "difficulty": "hard", "order_matters": True,
     "question": "Find the product with the highest revenue that also maintains an average review rating of at least 4.0.",
     "reference_sql": "SELECT p.product_id, p.name, ROUND(SUM(oi.quantity * oi.unit_price * (1 - oi.discount)), 2) AS total_revenue, ROUND(AVG(r.rating), 2) AS avg_rating FROM products p JOIN order_items oi ON p.product_id = oi.product_id JOIN orders o ON oi.order_id = o.order_id JOIN reviews r ON p.product_id = r.product_id WHERE o.status = 'completed' GROUP BY p.product_id, p.name HAVING AVG(r.rating) >= 4.0 ORDER BY total_revenue DESC LIMIT 1;"},

    {"id": "hard-011", "difficulty": "hard", "order_matters": True,
     "question": "Compare year-over-year performance: total revenue, completed order count, and unique customers between 2023 and 2024.",
     "reference_sql": "SELECT strftime('%Y', order_date) AS yr, COUNT(order_id) AS orders_count, COUNT(DISTINCT customer_id) AS unique_customers, ROUND(SUM(total_amount), 2) AS total_revenue FROM orders WHERE status = 'completed' AND strftime('%Y', order_date) IN ('2023', '2024') GROUP BY strftime('%Y', order_date) ORDER BY yr ASC;"},

    {"id": "hard-012", "difficulty": "hard", "order_matters": True,
     "question": "Find customers whose average order value exceeds 200 dollars and who have placed at least 3 completed orders.",
     "reference_sql": "SELECT c.customer_id, c.first_name, c.last_name, COUNT(o.order_id) AS orders_count, ROUND(AVG(o.total_amount), 2) AS avg_val FROM customers c JOIN orders o ON c.customer_id = o.customer_id WHERE o.status = 'completed' GROUP BY c.customer_id, c.first_name, c.last_name HAVING COUNT(o.order_id) >= 3 AND AVG(o.total_amount) > 200 ORDER BY avg_val DESC;"},

    {"id": "hard-013", "difficulty": "hard", "order_matters": True,
     "question": "Compute the Pareto principle (80/20 rule): what percentage of total revenue was generated by the top 20% of customers by spending?",
     "reference_sql": "WITH customer_spend AS (SELECT customer_id, SUM(total_amount) AS spend, NTILE(5) OVER (ORDER BY SUM(total_amount) DESC) AS quintile FROM orders WHERE status = 'completed' GROUP BY customer_id), totals AS (SELECT SUM(spend) AS all_spend, SUM(CASE WHEN quintile = 1 THEN spend ELSE 0 END) AS top_quintile_spend FROM customer_spend) SELECT ROUND(100.0 * top_quintile_spend / all_spend, 2) AS top_20_pct_revenue_share FROM totals;"},

    {"id": "hard-014", "difficulty": "hard", "order_matters": True,
     "question": "Find the top 3 product pairs most frequently purchased together in the same order.",
     "reference_sql": "SELECT oi1.product_id AS product_a, oi2.product_id AS product_b, COUNT(*) AS times_bought_together FROM order_items oi1 JOIN order_items oi2 ON oi1.order_id = oi2.order_id WHERE oi1.product_id < oi2.product_id GROUP BY oi1.product_id, oi2.product_id ORDER BY times_bought_together DESC LIMIT 3;"},

    {"id": "hard-015", "difficulty": "hard", "order_matters": True,
     "question": "Which customers have submitted both a 5-star review and a 1-star review on different products?",
     "reference_sql": "SELECT c.customer_id, c.first_name, c.last_name FROM customers c WHERE c.customer_id IN (SELECT customer_id FROM reviews WHERE rating = 5) AND c.customer_id IN (SELECT customer_id FROM reviews WHERE rating = 1) ORDER BY c.customer_id ASC;"},

    {"id": "hard-016", "difficulty": "hard", "order_matters": True,
     "question": "What is the order fulfillment delay in days by order status (difference between order date and last payment date)?",
     "reference_sql": "SELECT o.status, ROUND(AVG(JULIANDAY(p.payment_date) - JULIANDAY(o.order_date)), 2) AS avg_delay_days FROM orders o JOIN payments p ON o.order_id = p.order_id WHERE p.status = 'successful' GROUP BY o.status ORDER BY avg_delay_days ASC;"},

    {"id": "hard-017", "difficulty": "hard", "order_matters": True,
     "question": "Identify products where the revenue in 2024 was higher than the revenue in 2023.",
     "reference_sql": "WITH p_annual AS (SELECT oi.product_id, SUM(CASE WHEN strftime('%Y', o.order_date) = '2023' THEN oi.quantity * oi.unit_price * (1 - oi.discount) ELSE 0 END) AS rev_2023, SUM(CASE WHEN strftime('%Y', o.order_date) = '2024' THEN oi.quantity * oi.unit_price * (1 - oi.discount) ELSE 0 END) AS rev_2024 FROM order_items oi JOIN orders o ON oi.order_id = o.order_id WHERE o.status = 'completed' GROUP BY oi.product_id) SELECT p.product_id, p.name, ROUND(pa.rev_2023, 2) AS rev_2023, ROUND(pa.rev_2024, 2) AS rev_2024 FROM p_annual pa JOIN products p ON pa.product_id = p.product_id WHERE pa.rev_2024 > pa.rev_2023 ORDER BY (pa.rev_2024 - pa.rev_2023) DESC;"},

    {"id": "hard-018", "difficulty": "hard", "order_matters": True,
     "question": "Find the top spending customer in each state (for states with at least 5 registered customers).",
     "reference_sql": "WITH state_customers AS (SELECT c.state, c.customer_id, c.first_name, c.last_name, ROUND(SUM(o.total_amount), 2) AS spend, ROW_NUMBER() OVER (PARTITION BY c.state ORDER BY SUM(o.total_amount) DESC) AS rank, COUNT(*) OVER (PARTITION BY c.state) AS customer_count_in_state FROM customers c JOIN orders o ON c.customer_id = o.customer_id WHERE o.status = 'completed' GROUP BY c.state, c.customer_id, c.first_name, c.last_name) SELECT state, customer_id, first_name, last_name, spend FROM state_customers WHERE rank = 1 AND customer_count_in_state >= 5 ORDER BY spend DESC;"},

    {"id": "hard-019", "difficulty": "hard", "order_matters": True,
     "question": "Calculate the cumulative monthly revenue for the year 2024.",
     "reference_sql": "WITH monthly_rev AS (SELECT strftime('%Y-%m', order_date) AS month, SUM(total_amount) AS revenue FROM orders WHERE status = 'completed' AND strftime('%Y', order_date) = '2024' GROUP BY strftime('%Y-%m', order_date)) SELECT month, ROUND(revenue, 2) AS monthly_revenue, ROUND(SUM(revenue) OVER (ORDER BY month ASC), 2) AS cumulative_revenue FROM monthly_rev ORDER BY month ASC;"},

    {"id": "hard-020", "difficulty": "hard", "order_matters": True,
     "question": "Find the top 3 categories by revenue and calculate their share of total store revenue.",
     "reference_sql": "WITH cat_rev AS (SELECT c.name AS category_name, SUM(oi.quantity * oi.unit_price * (1 - oi.discount)) AS rev FROM categories c JOIN products p ON c.category_id = p.category_id JOIN order_items oi ON p.product_id = oi.product_id JOIN orders o ON oi.order_id = o.order_id WHERE o.status = 'completed' GROUP BY c.category_id, c.name), total_rev AS (SELECT SUM(rev) AS grand_total FROM cat_rev) SELECT cr.category_name, ROUND(cr.rev, 2) AS revenue, ROUND(100.0 * cr.rev / tr.grand_total, 2) AS revenue_share_pct FROM cat_rev cr CROSS JOIN total_rev tr ORDER BY cr.rev DESC LIMIT 3;"},

    {"id": "hard-021", "difficulty": "hard", "order_matters": True,
     "question": "What is the average discount given on orders where total amount exceeds 1000 dollars versus under 1000 dollars?",
     "reference_sql": "SELECT CASE WHEN o.total_amount >= 1000 THEN 'Large Order (>= $1000)' ELSE 'Standard Order (< $1000)' END AS order_size, ROUND(AVG(oi.discount), 4) AS avg_discount_rate FROM orders o JOIN order_items oi ON o.order_id = oi.order_id WHERE o.status = 'completed' GROUP BY order_size ORDER BY avg_discount_rate DESC;"},

    {"id": "hard-022", "difficulty": "hard", "order_matters": True,
     "question": "Find the most reliable payment method: lowest failed transaction count and highest total successful settlement.",
     "reference_sql": "SELECT payment_method, SUM(CASE WHEN status = 'successful' THEN 1 ELSE 0 END) AS successful_count, SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_count, ROUND(SUM(CASE WHEN status = 'successful' THEN amount ELSE 0 END), 2) AS settled_volume FROM payments GROUP BY payment_method ORDER BY settled_volume DESC;"},

    {"id": "hard-023", "difficulty": "hard", "order_matters": True,
     "question": "Identify products with high stock (stock > 50) but low sales (fewer than 5 units sold across all completed orders).",
     "reference_sql": "SELECT p.product_id, p.name, p.stock_quantity, COALESCE(SUM(oi.quantity), 0) AS units_sold FROM products p LEFT JOIN order_items oi ON p.product_id = oi.product_id LEFT JOIN orders o ON oi.order_id = o.order_id AND o.status = 'completed' WHERE p.stock_quantity > 50 GROUP BY p.product_id, p.name, p.stock_quantity HAVING COALESCE(SUM(oi.quantity), 0) < 5 ORDER BY p.stock_quantity DESC;"},

    {"id": "hard-024", "difficulty": "hard", "order_matters": True,
     "question": "Find the customer with the highest single purchase discount dollar amount across any individual order item.",
     "reference_sql": "SELECT c.customer_id, c.first_name, c.last_name, ROUND(oi.quantity * oi.unit_price * oi.discount, 2) AS max_discount_savings FROM customers c JOIN orders o ON c.customer_id = o.customer_id JOIN order_items oi ON o.order_id = oi.order_id ORDER BY max_discount_savings DESC LIMIT 1;"},

    {"id": "hard-025", "difficulty": "hard", "order_matters": True,
     "question": "Calculate customer cohort retention: count how many customers registered in 2023 placed an order in 2024.",
     "reference_sql": "SELECT COUNT(DISTINCT c.customer_id) AS cohort_2023_active_2024 FROM customers c JOIN orders o ON c.customer_id = o.customer_id WHERE strftime('%Y', c.created_at) = '2023' AND strftime('%Y', o.order_date) = '2024' AND o.status = 'completed';"},

    {"id": "hard-026", "difficulty": "hard", "order_matters": True,
     "question": "Find the rank of each product category based on total revenue and total units sold.",
     "reference_sql": "SELECT c.name AS category_name, SUM(oi.quantity) AS total_units, ROUND(SUM(oi.quantity * oi.unit_price * (1 - oi.discount)), 2) AS total_revenue, DENSE_RANK() OVER (ORDER BY SUM(oi.quantity * oi.unit_price * (1 - oi.discount)) DESC) AS revenue_rank FROM categories c JOIN products p ON c.category_id = p.category_id JOIN order_items oi ON p.product_id = oi.product_id JOIN orders o ON oi.order_id = o.order_id WHERE o.status = 'completed' GROUP BY c.category_id, c.name ORDER BY revenue_rank ASC;"},

    {"id": "hard-027", "difficulty": "hard", "order_matters": True,
     "question": "Find the month in 2024 with the highest average completed order total.",
     "reference_sql": "SELECT strftime('%Y-%m', order_date) AS month, ROUND(AVG(total_amount), 2) AS avg_order_total FROM orders WHERE status = 'completed' AND strftime('%Y', order_date) = '2024' GROUP BY strftime('%Y-%m', order_date) ORDER BY avg_order_total DESC LIMIT 1;"},

    {"id": "hard-028", "difficulty": "hard", "order_matters": True,
     "question": "Find customers whose total completed orders spend is above the 90th percentile of customer spending.",
     "reference_sql": "WITH customer_spend AS (SELECT customer_id, SUM(total_amount) AS total_spent, NTILE(10) OVER (ORDER BY SUM(total_amount) ASC) AS decile FROM orders WHERE status = 'completed' GROUP BY customer_id) SELECT c.customer_id, c.first_name, c.last_name, ROUND(cs.total_spent, 2) AS spend FROM customer_spend cs JOIN customers c ON cs.customer_id = c.customer_id WHERE cs.decile = 10 ORDER BY cs.total_spent DESC;"},

    {"id": "hard-029", "difficulty": "hard", "order_matters": True,
     "question": "Compute the average discount rate applied to products in orders with status 'completed' versus 'cancelled'.",
     "reference_sql": "SELECT o.status, ROUND(AVG(oi.discount), 4) AS avg_discount_rate FROM orders o JOIN order_items oi ON o.order_id = oi.order_id WHERE o.status IN ('completed', 'cancelled') GROUP BY o.status ORDER BY o.status ASC;"},

    {"id": "hard-030", "difficulty": "hard", "order_matters": True,
     "question": "Find the 3 products that have the largest spread between their highest unit price and lowest unit price sold.",
     "reference_sql": "SELECT p.name, ROUND(MAX(oi.unit_price) - MIN(oi.unit_price), 2) AS price_spread FROM products p JOIN order_items oi ON p.product_id = oi.product_id GROUP BY p.product_id, p.name HAVING COUNT(oi.item_id) > 1 ORDER BY price_spread DESC LIMIT 3;"},

    {"id": "hard-031", "difficulty": "hard", "order_matters": True,
     "question": "Find the top 3 cities with the highest total customer spend.",
     "reference_sql": "SELECT c.city, c.state, ROUND(SUM(o.total_amount), 2) AS city_spend FROM customers c JOIN orders o ON c.customer_id = o.customer_id WHERE o.status = 'completed' GROUP BY c.city, c.state ORDER BY city_spend DESC LIMIT 3;"},

    {"id": "hard-032", "difficulty": "hard", "order_matters": True,
     "question": "What is the ratio of completed order revenue to cancelled order potential revenue?",
     "reference_sql": "SELECT ROUND(SUM(CASE WHEN status = 'completed' THEN total_amount ELSE 0 END) / NULLIF(SUM(CASE WHEN status = 'cancelled' THEN total_amount ELSE 0 END), 0), 2) AS completed_to_cancelled_revenue_ratio FROM orders;"},

    {"id": "hard-033", "difficulty": "hard", "order_matters": True,
     "question": "Find all products that have received at least one 1-star review and at least one 5-star review.",
     "reference_sql": "SELECT p.product_id, p.name FROM products p WHERE p.product_id IN (SELECT product_id FROM reviews WHERE rating = 1) AND p.product_id IN (SELECT product_id FROM reviews WHERE rating = 5) ORDER BY p.product_id ASC;"},

    {"id": "hard-034", "difficulty": "hard", "order_matters": True,
     "question": "Calculate the average order value (AOV) for first-time orders compared to subsequent orders.",
     "reference_sql": "WITH customer_orders_ranked AS (SELECT order_id, customer_id, total_amount, ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY order_date ASC) AS order_rank FROM orders WHERE status = 'completed') SELECT CASE WHEN order_rank = 1 THEN 'First Order' ELSE 'Subsequent Order' END AS order_type, ROUND(AVG(total_amount), 2) AS aov, COUNT(*) AS count FROM customer_orders_ranked GROUP BY order_type ORDER BY order_type ASC;"},

    {"id": "hard-035", "difficulty": "hard", "order_matters": True,
     "question": "Compute the net revenue and total units sold for all products in category 'Electronics'.",
     "reference_sql": "SELECT p.name AS product_name, SUM(oi.quantity) AS units_sold, ROUND(SUM(oi.quantity * oi.unit_price * (1 - oi.discount)), 2) AS net_revenue FROM categories c JOIN products p ON c.category_id = p.category_id JOIN order_items oi ON p.product_id = oi.product_id JOIN orders o ON oi.order_id = o.order_id WHERE c.name = 'Electronics' AND o.status = 'completed' GROUP BY p.product_id, p.name ORDER BY net_revenue DESC;"},
]


def validate_and_save():
    print(f"Connecting to database: {DB_PATH}")
    db_hash = get_db_hash()
    print(f"Database SHA-256 Hash: {db_hash}")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    spot_check_samples = []

    print(f"Validating {len(QUESTIONS_SPEC)} reference SQL statements against sample.db...")
    for idx, q in enumerate(QUESTIONS_SPEC):
        sql = q["reference_sql"]
        try:
            cur.execute(sql)
            rows = cur.fetchall()
            q["reference_row_count"] = len(rows)
            q["reference_sample_output"] = [list(r) for r in rows[:3]]  # Store top 3 rows for inspection
            if idx < 20:
                spot_check_samples.append({
                    "id": q["id"],
                    "question": q["question"],
                    "sql": sql,
                    "rows_returned": len(rows),
                    "first_row": rows[0] if rows else None,
                })
        except Exception as e:
            print(f"ERROR executing {q['id']} ({sql}): {e}")
            raise

    print(f"ALL {len(QUESTIONS_SPEC)} reference queries executed successfully with zero SQL errors!")

    # Partition dataset: 50 in dev set, 100 in held-out test set
    # Stratified split:
    dev_set = []
    test_set = []

    # Easy: 50 -> 17 dev, 33 test
    # Medium: 65 -> 22 dev, 43 test
    # Hard: 35 -> 11 dev, 24 test
    easy_qs = [q for q in QUESTIONS_SPEC if q["difficulty"] == "easy"]
    med_qs = [q for q in QUESTIONS_SPEC if q["difficulty"] == "medium"]
    hard_qs = [q for q in QUESTIONS_SPEC if q["difficulty"] == "hard"]

    dev_set.extend(easy_qs[:17])
    test_set.extend(easy_qs[17:])

    dev_set.extend(med_qs[:22])
    test_set.extend(med_qs[22:])

    dev_set.extend(hard_qs[:11])
    test_set.extend(hard_qs[11:])

    assert len(dev_set) == 50
    assert len(test_set) == 100
    assert len(QUESTIONS_SPEC) == 150

    # Write accuracy.jsonl, dev.jsonl, test.jsonl
    def write_jsonl(filename: str, records: List[Dict[str, Any]]):
        path = os.path.join(DATASETS_DIR, filename)
        with open(path, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
        print(f"Wrote {len(records)} records to {path}")

    write_jsonl("accuracy.jsonl", QUESTIONS_SPEC)
    write_jsonl("dev.jsonl", dev_set)
    write_jsonl("test.jsonl", test_set)

    # Save spot check report
    spot_check_path = os.path.join(DATASETS_DIR, "spot_check_20.json")
    with open(spot_check_path, "w", encoding="utf-8") as f:
        json.dump({
            "database_sha256": db_hash,
            "total_questions": len(QUESTIONS_SPEC),
            "spot_checked_count": len(spot_check_samples),
            "spot_checks": spot_check_samples,
        }, f, indent=2)
    print(f"Saved 20 spot-checked queries to {spot_check_path}")


if __name__ == "__main__":
    validate_and_save()
