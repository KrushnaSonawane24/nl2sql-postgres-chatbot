# PostgreSQL Database Setup Guide

## 📦 Database Structure

### **Database Name:** `nl2sql_demo`

### **Tables:**

1. **customers** (200 records)
   - `cst_id` - Serial Primary Key
   - `cst_key` - Unique customer key (e.g., CUST-000001)
   - `cst_firstname` - First name
   - `cst_lastname` - Last name
   - `cst_marital_status` - Single/Married/Divorced/Widowed
   - `cst_gndr` - Male/Female/Other
   - `cst_create_date` - Account creation date

2. **orders** (200 records)
   - `sls_ord_num` - Serial Primary Key
   - `sls_prd_key` - Product key (e.g., PRD-LAPTOP-1234)
   - `sls_cust_id` - Foreign Key → customers(cst_id)
   - `sls_order_dt` - Order date
   - `sls_ship_dt` - Shipping date
   - `sls_due_dt` - Due date
   - `sls_sales` - Total sales amount
   - `sls_quantity` - Quantity ordered
   - `sls_price` - Price per unit

---

## 🚀 Setup Instructions

### **Step 1: Configure PostgreSQL**

Edit `setup_database.py` and update:

```python
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'user': 'postgres',
    'password': 'YOUR_PASSWORD_HERE',  # ← Change this!
    'database': 'nl2sql_demo'
}
```

### **Step 2: Run Setup Script**

```bash
python setup_database.py
```

Expected output:
```
========================================================
🚀 PostgreSQL Database Setup
========================================================

📦 Step 1: Creating database...
✅ Database 'nl2sql_demo' created successfully!

🔌 Step 2: Connecting to database...
✅ Connected to 'nl2sql_demo'

📋 Step 3: Creating tables...
✅ Customers table created!
✅ Orders table created!

👥 Step 4: Generating customer data...
✅ Generated 200 customers

💾 Step 5: Inserting customers...
✅ Inserted 200 customers!

📦 Step 6: Generating order data...
✅ Generated 200 orders

💾 Step 7: Inserting orders...
✅ Inserted 200 orders!

✅ Step 8: Verifying data...
   Customers: 200
   Orders: 200

========================================================
🎉 Database setup completed successfully!
========================================================
```

### **Step 3: Update .env File**

Update your `.env` with the new database URL:

```env
DATABASE_URL=postgresql://postgres:your_password@localhost:5432/nl2sql_demo
```

---

## 🔍 Sample Queries to Test

### **Customer Queries:**
```sql
-- Show all customers
SELECT * FROM customers LIMIT 10;

-- Count customers by gender
SELECT cst_gndr, COUNT(*) FROM customers GROUP BY cst_gndr;

-- Find customers created in last year
SELECT * FROM customers WHERE cst_create_date >= CURRENT_DATE - INTERVAL '1 year';

-- Married customers
SELECT * FROM customers WHERE cst_marital_status = 'Married';
```

### **Order Queries:**
```sql
-- Show all orders
SELECT * FROM orders LIMIT 10;

-- Total sales
SELECT SUM(sls_sales) as total_sales FROM orders;

-- Orders by customer
SELECT c.cst_firstname, c.cst_lastname, COUNT(o.sls_ord_num) as order_count
FROM customers c
LEFT JOIN orders o ON c.cst_id = o.sls_cust_id
GROUP BY c.cst_id, c.cst_firstname, c.cst_lastname
ORDER BY order_count DESC;

-- Top 10 highest value orders
SELECT * FROM orders ORDER BY sls_sales DESC LIMIT 10;

-- Average order value
SELECT AVG(sls_sales) as avg_order_value FROM orders;
```

### **Join Queries:**
```sql
-- Customer orders with full details
SELECT 
    c.cst_key,
    c.cst_firstname,
    c.cst_lastname,
    o.sls_prd_key,
    o.sls_order_dt,
    o.sls_sales
FROM customers c
JOIN orders o ON c.cst_id = o.sls_cust_id
LIMIT 20;

-- Customers with most sales
SELECT 
    c.cst_id,
    c.cst_firstname,
    c.cst_lastname,
    SUM(o.sls_sales) as total_revenue
FROM customers c
JOIN orders o ON c.cst_id = o.sls_cust_id
GROUP BY c.cst_id, c.cst_firstname, c.cst_lastname
ORDER BY total_revenue DESC
LIMIT 10;
```

---

## 🎯 Natural Language Queries to Test

Try these in your NL2SQL chatbot:

1. **Simple queries:**
   - "Show me all customers"
   - "How many orders do we have?"
   - "What's the total sales?"

2. **Filtering:**
   - "Show married male customers"
   - "Find orders above 1000"
   - "Customers created this year"

3. **Aggregations:**
   - "Count customers by marital status"
   - "Average order value"
   - "Top 10 customers by revenue"

4. **Joins:**
   - "Show customer names with their orders"
   - "Which customer has the most orders?"
   - "List all products ordered by customer John"

5. **Complex:**
   - "Show customers who never placed an order"
   - "Monthly sales trend"
   - "Average order value by customer gender"

---

## 🐛 Troubleshooting

### **Error: Database connection failed**
- Check PostgreSQL is running: `psql --version`
- Verify credentials in `DB_CONFIG`
- Check port 5432 is not blocked

### **Error: Permission denied**
- Make sure PostgreSQL user has CREATE DATABASE permission
- Run as superuser or with proper grants

### **Error: Table already exists**
- Script automatically drops tables before creating
- Or manually: `DROP TABLE orders, customers CASCADE;`

---

## 📊 Data Statistics

- **Customers:** 200 unique records
- **Orders:** 200 records (1-5 orders per customer)
- **Date Range:** Orders from last 2 years
- **Products:** 20 different product types
- **Price Range:** $10 - $2000 per item

---

**Status:** ✅ Ready for NL2SQL testing!
