from datetime import date
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import (
    create_engine, MetaData, Table, Column, Integer, String, Float, Date,
    ForeignKey, select, insert, update, delete, join
)
from sqlalchemy.exc import IntegrityError

# --------------------------------------------------
# Application and database connection
# --------------------------------------------------

app = FastAPI(
    title="MDF SHOP MANAGEMENT",
    description="MDF shop management API using FastAPI, SQLAlchemy Core and SQLite. All data is sent as JSON.",
    version="1.0.0"
)

engine = create_engine(
    "sqlite:///./mdf_shop.db",
    connect_args={"check_same_thread": False}
)

meta = MetaData()

# --------------------------------------------------
# Table definitions (SQLAlchemy Core)
# --------------------------------------------------

customers = Table(
    "customers",
    meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("FirstName", String(100), nullable=False),
    Column("LastName", String(100), nullable=False),
    Column("Phone", String(30), nullable=True)
)

sales_experts = Table(
    "sales_experts",
    meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("FirstName", String(100), nullable=False),
    Column("LastName", String(100), nullable=False),
    Column("Phone", String(30), nullable=True)
)

mdf_sheets = Table(
    "mdf_sheets",
    meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ProductCode", String(50), unique=True, nullable=False),
    Column("ProductName", String(150), nullable=False),
    Column("Thickness", Float, nullable=False),
    Column("Length", Float, nullable=False),
    Column("Width", Float, nullable=False),
    Column("Price", Float, nullable=False),
    Column("Stock", Integer, nullable=False, default=0)
)

sales = Table(
    "sales",
    meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("Customer_id", Integer, ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False),
    Column("Product_id", Integer, ForeignKey("mdf_sheets.id", ondelete="RESTRICT"), nullable=False),
    Column("Expert_id", Integer, ForeignKey("sales_experts.id", ondelete="RESTRICT"), nullable=False),
    Column("Quantity", Integer, nullable=False),
    Column("SaleDate", Date, nullable=False, default=date.today),
    Column("UnitPrice", Float, nullable=False)
)

meta.create_all(engine)


# --------------------------------------------------
# JSON input schemas (Pydantic)
# --------------------------------------------------

class CustomerInput(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    phone: Optional[str] = None


class ExpertInput(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    phone: Optional[str] = None


class ProductInput(BaseModel):
    product_code: str = Field(min_length=1, max_length=50)
    product_name: str = Field(min_length=1, max_length=150)
    thickness: float = Field(gt=0)
    length: float = Field(gt=0)
    width: float = Field(gt=0)
    price: float = Field(ge=0)
    stock: int = Field(ge=0)


class SaleInput(BaseModel):
    customer_id: int = Field(gt=0)
    product_id: int = Field(gt=0)
    expert_id: int = Field(gt=0)
    quantity: int = Field(gt=0)
    sale_date: date
    unit_price: float = Field(ge=0)


# --------------------------------------------------
# Helper functions
# --------------------------------------------------

def get_row_or_404(conn, table, item_id: int, label: str):
    row = conn.execute(
        select(table).where(table.c.id == item_id)
    ).mappings().first()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"{label} with ID {item_id} was not found."
        )
    return row


def customer_to_dict(row):
    return {
        "id": row["id"],
        "first_name": row["FirstName"],
        "last_name": row["LastName"],
        "phone": row["Phone"]
    }


def expert_to_dict(row):
    return {
        "id": row["id"],
        "first_name": row["FirstName"],
        "last_name": row["LastName"],
        "phone": row["Phone"]
    }


def product_to_dict(row):
    return {
        "id": row["id"],
        "product_code": row["ProductCode"],
        "product_name": row["ProductName"],
        "thickness": row["Thickness"],
        "length": row["Length"],
        "width": row["Width"],
        "price": row["Price"],
        "stock": row["Stock"]
    }


def sale_to_dict(row):
    return {
        "id": row["id"],
        "customer_id": row["Customer_id"],
        "customer_name": f'{row["CustomerFirstName"]} {row["CustomerLastName"]}',
        "product_id": row["Product_id"],
        "product_name": row["ProductName"],
        "expert_id": row["Expert_id"],
        "expert_name": f'{row["ExpertFirstName"]} {row["ExpertLastName"]}',
        "quantity": row["Quantity"],
        "sale_date": row["SaleDate"].isoformat(),
        "unit_price": row["UnitPrice"],
        "total_price": row["Quantity"] * row["UnitPrice"]
    }


def get_sale_details(conn, sale_id=None):
    stmt = (
        select(
            sales.c.id,
            sales.c.Customer_id,
            customers.c.FirstName.label("CustomerFirstName"),
            customers.c.LastName.label("CustomerLastName"),
            sales.c.Product_id,
            mdf_sheets.c.ProductName,
            sales.c.Expert_id,
            sales_experts.c.FirstName.label("ExpertFirstName"),
            sales_experts.c.LastName.label("ExpertLastName"),
            sales.c.Quantity,
            sales.c.SaleDate,
            sales.c.UnitPrice
        )
        .select_from(
            sales.join(customers, sales.c.Customer_id == customers.c.id)
                 .join(mdf_sheets, sales.c.Product_id == mdf_sheets.c.id)
                 .join(sales_experts, sales.c.Expert_id == sales_experts.c.id)
        )
        .order_by(sales.c.id)
    )

    if sale_id is not None:
        stmt = stmt.where(sales.c.id == sale_id)

    return conn.execute(stmt).mappings()


def check_foreign_keys(conn, data: SaleInput):
    customer = conn.execute(
        select(customers).where(customers.c.id == data.customer_id)
    ).mappings().first()
    product = conn.execute(
        select(mdf_sheets).where(mdf_sheets.c.id == data.product_id)
    ).mappings().first()
    expert = conn.execute(
        select(sales_experts).where(sales_experts.c.id == data.expert_id)
    ).mappings().first()

    if customer is None:
        raise HTTPException(status_code=404, detail="Customer ID was not found.")
    if product is None:
        raise HTTPException(status_code=404, detail="Product ID was not found.")
    if expert is None:
        raise HTTPException(status_code=404, detail="Sales expert ID was not found.")

    return customer, product, expert


# --------------------------------------------------
# Home
# --------------------------------------------------

@app.get("/")
def home():
    return {
        "message": "MDF SHOP MANAGEMENT API",
        "documentation": "/docs",
        "sections": ["/customers", "/experts", "/products", "/sales"]
    }


# --------------------------------------------------
# Customers - CRUD and search by ID
# --------------------------------------------------

@app.post("/customers", status_code=201)
def create_customer(data: CustomerInput):
    values = {
        "FirstName": data.first_name,
        "LastName": data.last_name,
        "Phone": data.phone
    }

    with engine.begin() as conn:
        result = conn.execute(insert(customers).values(**values))
        row = get_row_or_404(conn, customers, result.inserted_primary_key[0], "Customer")

    return {"message": "Customer created successfully.", "customer": customer_to_dict(row)}


@app.get("/customers")
def get_customers(customer_id: Optional[int] = None):
    with engine.connect() as conn:
        if customer_id is not None:
            row = get_row_or_404(conn, customers, customer_id, "Customer")
            return customer_to_dict(row)

        rows = conn.execute(select(customers).order_by(customers.c.id)).mappings().all()
        return [customer_to_dict(row) for row in rows]


@app.put("/customers/{customer_id}")
def update_customer(customer_id: int, data: CustomerInput):
    with engine.begin() as conn:
        get_row_or_404(conn, customers, customer_id, "Customer")
        conn.execute(
            update(customers)
            .where(customers.c.id == customer_id)
            .values(
                FirstName=data.first_name,
                LastName=data.last_name,
                Phone=data.phone
            )
        )
        row = get_row_or_404(conn, customers, customer_id, "Customer")

    return {"message": "Customer updated successfully.", "customer": customer_to_dict(row)}


@app.delete("/customers/{customer_id}")
def delete_customer(customer_id: int):
    try:
        with engine.begin() as conn:
            get_row_or_404(conn, customers, customer_id, "Customer")
            conn.execute(delete(customers).where(customers.c.id == customer_id))
    except IntegrityError:
        raise HTTPException(status_code=409, detail="This customer is connected to a sale and cannot be deleted.")

    return {"message": "Customer deleted successfully.", "id": customer_id}


# --------------------------------------------------
# Sales experts - CRUD and search by ID
# --------------------------------------------------

@app.post("/experts", status_code=201)
def create_expert(data: ExpertInput):
    with engine.begin() as conn:
        result = conn.execute(
            insert(sales_experts).values(
                FirstName=data.first_name,
                LastName=data.last_name,
                Phone=data.phone
            )
        )
        row = get_row_or_404(conn, sales_experts, result.inserted_primary_key[0], "Sales expert")

    return {"message": "Sales expert created successfully.", "expert": expert_to_dict(row)}


@app.get("/experts")
def get_experts(expert_id: Optional[int] = None):
    with engine.connect() as conn:
        if expert_id is not None:
            row = get_row_or_404(conn, sales_experts, expert_id, "Sales expert")
            return expert_to_dict(row)

        rows = conn.execute(select(sales_experts).order_by(sales_experts.c.id)).mappings().all()
        return [expert_to_dict(row) for row in rows]


@app.put("/experts/{expert_id}")
def update_expert(expert_id: int, data: ExpertInput):
    with engine.begin() as conn:
        get_row_or_404(conn, sales_experts, expert_id, "Sales expert")
        conn.execute(
            update(sales_experts)
            .where(sales_experts.c.id == expert_id)
            .values(
                FirstName=data.first_name,
                LastName=data.last_name,
                Phone=data.phone
            )
        )
        row = get_row_or_404(conn, sales_experts, expert_id, "Sales expert")

    return {"message": "Sales expert updated successfully.", "expert": expert_to_dict(row)}


@app.delete("/experts/{expert_id}")
def delete_expert(expert_id: int):
    try:
        with engine.begin() as conn:
            get_row_or_404(conn, sales_experts, expert_id, "Sales expert")
            conn.execute(delete(sales_experts).where(sales_experts.c.id == expert_id))
    except IntegrityError:
        raise HTTPException(status_code=409, detail="This expert is connected to a sale and cannot be deleted.")

    return {"message": "Sales expert deleted successfully.", "id": expert_id}


# --------------------------------------------------
# MDF sheets / products - CRUD and search by ID
# --------------------------------------------------

@app.post("/products", status_code=201)
def create_product(data: ProductInput):
    try:
        with engine.begin() as conn:
            result = conn.execute(
                insert(mdf_sheets).values(
                    ProductCode=data.product_code,
                    ProductName=data.product_name,
                    Thickness=data.thickness,
                    Length=data.length,
                    Width=data.width,
                    Price=data.price,
                    Stock=data.stock
                )
            )
            row = get_row_or_404(conn, mdf_sheets, result.inserted_primary_key[0], "Product")
    except IntegrityError:
        raise HTTPException(status_code=409, detail="This product code already exists.")

    return {"message": "MDF sheet created successfully.", "product": product_to_dict(row)}


@app.get("/products")
def get_products(product_id: Optional[int] = None):
    with engine.connect() as conn:
        if product_id is not None:
            row = get_row_or_404(conn, mdf_sheets, product_id, "Product")
            return product_to_dict(row)

        rows = conn.execute(select(mdf_sheets).order_by(mdf_sheets.c.id)).mappings().all()
        return [product_to_dict(row) for row in rows]


@app.put("/products/{product_id}")
def update_product(product_id: int, data: ProductInput):
    try:
        with engine.begin() as conn:
            get_row_or_404(conn, mdf_sheets, product_id, "Product")
            conn.execute(
                update(mdf_sheets)
                .where(mdf_sheets.c.id == product_id)
                .values(
                    ProductCode=data.product_code,
                    ProductName=data.product_name,
                    Thickness=data.thickness,
                    Length=data.length,
                    Width=data.width,
                    Price=data.price,
                    Stock=data.stock
                )
            )
            row = get_row_or_404(conn, mdf_sheets, product_id, "Product")
    except IntegrityError:
        raise HTTPException(status_code=409, detail="This product code already exists.")

    return {"message": "MDF sheet updated successfully.", "product": product_to_dict(row)}


@app.delete("/products/{product_id}")
def delete_product(product_id: int):
    try:
        with engine.begin() as conn:
            get_row_or_404(conn, mdf_sheets, product_id, "Product")
            conn.execute(delete(mdf_sheets).where(mdf_sheets.c.id == product_id))
    except IntegrityError:
        raise HTTPException(status_code=409, detail="This product is connected to a sale and cannot be deleted.")

    return {"message": "MDF sheet deleted successfully.", "id": product_id}


# --------------------------------------------------
# Sales - CRUD and search by ID
# Stock is adjusted when a sale is created, updated or deleted.
# --------------------------------------------------

@app.post("/sales", status_code=201)
def create_sale(data: SaleInput):
    try:
        with engine.begin() as conn:
            customer, product, expert = check_foreign_keys(conn, data)

            if product["Stock"] < data.quantity:
                raise HTTPException(status_code=400, detail="Insufficient stock.")

            conn.execute(
                update(mdf_sheets)
                .where(mdf_sheets.c.id == data.product_id)
                .values(Stock=mdf_sheets.c.Stock - data.quantity)
            )

            result = conn.execute(
                insert(sales).values(
                    Customer_id=data.customer_id,
                    Product_id=data.product_id,
                    Expert_id=data.expert_id,
                    Quantity=data.quantity,
                    SaleDate=data.sale_date,
                    UnitPrice=data.unit_price
                )
            )
            new_sale_id = result.inserted_primary_key[0]
            row = get_sale_details(conn, new_sale_id).mappings().first()
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Could not create sale because of a database constraint.")

    return {"message": "Sale created successfully.", "sale": sale_to_dict(row)}


@app.get("/sales")
def get_sales(sale_id: Optional[int] = None):
    with engine.connect() as conn:
        if sale_id is not None:
            row = get_sale_details(conn, sale_id).mappings().first()
            if row is None:
                raise HTTPException(status_code=404, detail=f"Sale with ID {sale_id} was not found.")
            return sale_to_dict(row)

        rows = get_sale_details(conn).mappings().all()
        return [sale_to_dict(row) for row in rows]


@app.put("/sales/{sale_id}")
def update_sale(sale_id: int, data: SaleInput):
    try:
        with engine.begin() as conn:
            old_sale = get_row_or_404(conn, sales, sale_id, "Sale")
            check_foreign_keys(conn, data)

            # Restore the stock from the old sale.
            conn.execute(
                update(mdf_sheets)
                .where(mdf_sheets.c.id == old_sale["Product_id"])
                .values(Stock=mdf_sheets.c.Stock + old_sale["Quantity"])
            )

            new_product = get_row_or_404(conn, mdf_sheets, data.product_id, "Product")
            if new_product["Stock"] < data.quantity:
                raise HTTPException(status_code=400, detail="Insufficient stock.")

            # Deduct the new sale quantity.
            conn.execute(
                update(mdf_sheets)
                .where(mdf_sheets.c.id == data.product_id)
                .values(Stock=mdf_sheets.c.Stock - data.quantity)
            )

            conn.execute(
                update(sales)
                .where(sales.c.id == sale_id)
                .values(
                    Customer_id=data.customer_id,
                    Product_id=data.product_id,
                    Expert_id=data.expert_id,
                    Quantity=data.quantity,
                    SaleDate=data.sale_date,
                    UnitPrice=data.unit_price
                )
            )
            row = get_sale_details(conn, sale_id).mappings().first()
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Could not update sale because of a database constraint.")

    return {"message": "Sale updated successfully.", "sale": sale_to_dict(row)}


@app.delete("/sales/{sale_id}")
def delete_sale(sale_id: int):
    with engine.begin() as conn:
        sale = get_row_or_404(conn, sales, sale_id, "Sale")

        # Restore the product stock before deleting the sale.
        conn.execute(
            update(mdf_sheets)
            .where(mdf_sheets.c.id == sale["Product_id"])
            .values(Stock=mdf_sheets.c.Stock + sale["Quantity"])
        )
        conn.execute(delete(sales).where(sales.c.id == sale_id))

    return {"message": "Sale deleted successfully. Product stock was restored.", "id": sale_id}
