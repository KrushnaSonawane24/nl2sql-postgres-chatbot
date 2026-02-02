"""
PostgreSQL Database Setup Script
Creates sample database with Customer and Orders tables
Each table has 200 records with realistic data
"""
import psycopg2
from psycopg2 import sql
from datetime import datetime, timedelta
import random
from faker import Faker

# Initialize Faker for generating realistic data
fake = Faker()

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'user': 'postgres',
    'password': 'your_password',  # Change this!
    'database': 'nl2sql_demo'
}

# Product categories for orders
PRODUCTS = [
    'Laptop', 'Mouse', 'Keyboard', 'Monitor', 'Headphones',
    'Webcam', 'Printer', 'Scanner', 'USB Cable', 'Hard Drive',
    'SSD', 'RAM', 'Graphics Card', 'Motherboard', 'CPU',
    'Power Supply', 'Case', 'Cooling Fan', 'Thermal Paste', 'Screwdriver Set'
]

def create_database():
    """Create the database if it doesn't exist"""
    try:
        # Connect to default 'postgres' database
        conn = psycopg2.connect(
            host=DB_CONFIG['host'],
            port=DB_CONFIG['port'],
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password'],
            database='postgres'
        )
        conn.autocommit = True
        cursor = conn.cursor()
        
        # Check if database exists
        cursor.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (DB_CONFIG['database'],)
        )
        exists = cursor.fetchone()
        
        if not exists:
            cursor.execute(
                sql.SQL("CREATE DATABASE {}").format(
                    sql.Identifier(DB_CONFIG['database'])
                )
            )
            print(f"✅ Database '{DB_CONFIG['database']}' created successfully!")
        else:
            print(f"ℹ️  Database '{DB_CONFIG['database']}' already exists.")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error creating database: {e}")
        raise


def create_tables(conn):
    """Create customer and orders tables"""
    cursor = conn.cursor()
    
    # Drop tables if they exist
    cursor.execute("DROP TABLE IF EXISTS orders CASCADE;")
    cursor.execute("DROP TABLE IF EXISTS customers CASCADE;")
    
    # Create customers table
    cursor.execute("""
        CREATE TABLE customers (
            cst_id SERIAL PRIMARY KEY,
            cst_key VARCHAR(50) UNIQUE NOT NULL,
            cst_firstname VARCHAR(100) NOT NULL,
            cst_lastname VARCHAR(100) NOT NULL,
            cst_marital_status VARCHAR(20),
            cst_gndr VARCHAR(10),
            cst_create_date DATE NOT NULL
        );
    """)
    print("✅ Customers table created!")
    
    # Create orders table
    cursor.execute("""
        CREATE TABLE orders (
            sls_ord_num SERIAL PRIMARY KEY,
            sls_prd_key VARCHAR(50) NOT NULL,
            sls_cust_id INTEGER NOT NULL REFERENCES customers(cst_id),
            sls_order_dt DATE NOT NULL,
            sls_ship_dt DATE,
            sls_due_dt DATE,
            sls_sales DECIMAL(10, 2) NOT NULL,
            sls_quantity INTEGER NOT NULL,
            sls_price DECIMAL(10, 2) NOT NULL
        );
    """)
    print("✅ Orders table created!")
    
    conn.commit()
    cursor.close()


def generate_customer_data(num_records=200):
    """Generate realistic customer data"""
    customers = []
    marital_statuses = ['Single', 'Married', 'Divorced', 'Widowed']
    genders = ['Male', 'Female', 'Other']
    
    for i in range(1, num_records + 1):
        customer = {
            'cst_key': f'CUST-{i:06d}',
            'cst_firstname': fake.first_name(),
            'cst_lastname': fake.last_name(),
            'cst_marital_status': random.choice(marital_statuses),
            'cst_gndr': random.choice(genders),
            'cst_create_date': fake.date_between(start_date='-5y', end_date='today')
        }
        customers.append(customer)
    
    return customers


def generate_order_data(num_customers=200, orders_per_customer_range=(1, 5)):
    """Generate realistic order data"""
    orders = []
    
    for cust_id in range(1, num_customers + 1):
        # Each customer gets 1-5 orders
        num_orders = random.randint(*orders_per_customer_range)
        
        for _ in range(num_orders):
            product = random.choice(PRODUCTS)
            quantity = random.randint(1, 10)
            price = round(random.uniform(10.0, 2000.0), 2)
            sales = round(price * quantity, 2)
            
            order_date = fake.date_between(start_date='-2y', end_date='today')
            ship_date = order_date + timedelta(days=random.randint(1, 5))
            due_date = order_date + timedelta(days=random.randint(7, 30))
            
            order = {
                'sls_prd_key': f'PRD-{product.upper().replace(" ", "-")}-{random.randint(1000, 9999)}',
                'sls_cust_id': cust_id,
                'sls_order_dt': order_date,
                'sls_ship_dt': ship_date,
                'sls_due_dt': due_date,
                'sls_sales': sales,
                'sls_quantity': quantity,
                'sls_price': price
            }
            orders.append(order)
    
    # Ensure we have exactly 200 orders (adjust if needed)
    if len(orders) > 200:
        orders = orders[:200]
    elif len(orders) < 200:
        # Add more orders to reach 200
        while len(orders) < 200:
            cust_id = random.randint(1, num_customers)
            product = random.choice(PRODUCTS)
            quantity = random.randint(1, 10)
            price = round(random.uniform(10.0, 2000.0), 2)
            sales = round(price * quantity, 2)
            
            order_date = fake.date_between(start_date='-2y', end_date='today')
            ship_date = order_date + timedelta(days=random.randint(1, 5))
            due_date = order_date + timedelta(days=random.randint(7, 30))
            
            order = {
                'sls_prd_key': f'PRD-{product.upper().replace(" ", "-")}-{random.randint(1000, 9999)}',
                'sls_cust_id': cust_id,
                'sls_order_dt': order_date,
                'sls_ship_dt': ship_date,
                'sls_due_dt': due_date,
                'sls_sales': sales,
                'sls_quantity': quantity,
                'sls_price': price
            }
            orders.append(order)
    
    return orders


def insert_customers(conn, customers):
    """Insert customer data into database"""
    cursor = conn.cursor()
    
    insert_query = """
        INSERT INTO customers 
        (cst_key, cst_firstname, cst_lastname, cst_marital_status, cst_gndr, cst_create_date)
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    
    for customer in customers:
        cursor.execute(insert_query, (
            customer['cst_key'],
            customer['cst_firstname'],
            customer['cst_lastname'],
            customer['cst_marital_status'],
            customer['cst_gndr'],
            customer['cst_create_date']
        ))
    
    conn.commit()
    cursor.close()
    print(f"✅ Inserted {len(customers)} customers!")


def insert_orders(conn, orders):
    """Insert order data into database"""
    cursor = conn.cursor()
    
    insert_query = """
        INSERT INTO orders 
        (sls_prd_key, sls_cust_id, sls_order_dt, sls_ship_dt, sls_due_dt, 
         sls_sales, sls_quantity, sls_price)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    
    for order in orders:
        cursor.execute(insert_query, (
            order['sls_prd_key'],
            order['sls_cust_id'],
            order['sls_order_dt'],
            order['sls_ship_dt'],
            order['sls_due_dt'],
            order['sls_sales'],
            order['sls_quantity'],
            order['sls_price']
        ))
    
    conn.commit()
    cursor.close()
    print(f"✅ Inserted {len(orders)} orders!")


def main():
    """Main setup function"""
    print("=" * 60)
    print("🚀 PostgreSQL Database Setup")
    print("=" * 60)
    
    try:
        # Step 1: Create database
        print("\n📦 Step 1: Creating database...")
        create_database()
        
        # Step 2: Connect to the new database
        print("\n🔌 Step 2: Connecting to database...")
        conn = psycopg2.connect(**DB_CONFIG)
        print(f"✅ Connected to '{DB_CONFIG['database']}'")
        
        # Step 3: Create tables
        print("\n📋 Step 3: Creating tables...")
        create_tables(conn)
        
        # Step 4: Generate customer data
        print("\n👥 Step 4: Generating customer data...")
        customers = generate_customer_data(200)
        print(f"✅ Generated {len(customers)} customers")
        
        # Step 5: Insert customers
        print("\n💾 Step 5: Inserting customers...")
        insert_customers(conn, customers)
        
        # Step 6: Generate order data
        print("\n📦 Step 6: Generating order data...")
        orders = generate_order_data(200)
        print(f"✅ Generated {len(orders)} orders")
        
        # Step 7: Insert orders
        print("\n💾 Step 7: Inserting orders...")
        insert_orders(conn, orders)
        
        # Step 8: Verify data
        print("\n✅ Step 8: Verifying data...")
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM customers;")
        customer_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM orders;")
        order_count = cursor.fetchone()[0]
        cursor.close()
        
        print(f"   Customers: {customer_count}")
        print(f"   Orders: {order_count}")
        
        # Close connection
        conn.close()
        
        print("\n" + "=" * 60)
        print("🎉 Database setup completed successfully!")
        print("=" * 60)
        print(f"\n📍 Connection String:")
        print(f"   postgresql://{DB_CONFIG['user']}:***@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
        print("\n💡 Update your .env file with:")
        print(f"   DATABASE_URL=postgresql://{DB_CONFIG['user']}:your_password@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
