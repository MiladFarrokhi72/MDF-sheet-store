from datetime import date
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from peewee import (
    Model, MySQLDatabase, CharField, FloatField, IntegerField,
    DateField, ForeignKeyField, IntegrityError
)
import os

# --------------------------------------------------
# Application and database
# --------------------------------------------------

app = FastAPI(
    title="MDF SHOP MANAGEMENT",
    description="MDF shop management API using FastAPI, Peewee and MySQL. All data is sent as JSON.",
    version="1.0.0"
)

# Database settings are read from environment variables.
# Defaults are suitable for a local MySQL server.
db = MySQLDatabase(
    os.getenv("DB_NAME", "mdf_shop"),
    user=os.getenv("DB_USER", "root"),
    password=os.getenv("DB_PASSWORD", ""),
    host=os.getenv("DB_HOST", "127.0.0.1"),
    port=int(os.getenv("DB_PORT", "3306")),
    charset="utf8mb4",
)


class BaseModelDB(Model):
    class Meta:
        database = db


# --------------------------------------------------
# Database models (Peewee)
# --------------------------------------------------

class Customer(BaseModelDB):
    FirstName = CharField()
    LastName = CharField()
    Phone = CharField(null=True)


class SalesExpert(BaseModelDB):
    FirstName = CharField()
    LastName = CharField()
    Phone = CharField(null=True)


class MDFSheet(BaseModelDB):
    ProductCode = CharField(unique=True)
    ProductName = CharField()
    Thickness = FloatField()
    Length = FloatField()
    Width = FloatField()
    Price = FloatField()
    Stock = IntegerField(default=0)


class Sale(BaseModelDB):
    Customer = ForeignKeyField(Customer, backref="sales", on_delete="RESTRICT")
    Product = ForeignKeyField(MDFSheet, backref="sales", on_delete="RESTRICT")
    Expert = ForeignKeyField(SalesExpert, backref="sales", on_delete="RESTRICT")
    Quantity = IntegerField()
    SaleDate = DateField(default=date.today)
    UnitPrice = FloatField()


def initialize_database():
    if db.is_closed():
        db.connect()
    db.create_tables([Customer, SalesExpert, MDFSheet, Sale], safe=True)


@app.on_event("startup")
def startup():
    initialize_database()


@app.on_event("shutdown")
def shutdown():
    if not db.is_closed():
        db.close()


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

def get_or_404(model, item_id: int, label: str):
    item = model.get_or_none(model.id == item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"{label} with ID {item_id} was not found.")
    return item


def customer_to_dict(item):
    return {
        "id": item.id,
        "first_name": item.FirstName,
        "last_name": item.LastName,
        "phone": item.Phone
    }


def expert_to_dict(item):
    return {
        "id": item.id,
        "first_name": item.FirstName,
        "last_name": item.LastName,
        "phone": item.Phone
    }


def product_to_dict(item):
    return {
        "id": item.id,
        "product_code": item.ProductCode,
        "product_name": item.ProductName,
        "thickness": item.Thickness,
        "length": item.Length,
        "width": item.Width,
        "price": item.Price,
        "stock": item.Stock
    }


def sale_to_dict(item):
    return {
        "id": item.id,
        "customer_id": item.Customer_id,
        "customer_name": f"{item.Customer.FirstName} {item.Customer.LastName}",
        "product_id": item.Product_id,
        "product_name": item.Product.ProductName,
        "expert_id": item.Expert_id,
        "expert_name": f"{item.Expert.FirstName} {item.Expert.LastName}",
        "quantity": item.Quantity,
        "sale_date": item.SaleDate.isoformat(),
        "unit_price": item.UnitPrice,
        "total_price": item.Quantity * item.UnitPrice
    }


def check_foreign_keys(data: SaleInput):
    customer = Customer.get_or_none(Customer.id == data.customer_id)
    product = MDFSheet.get_or_none(MDFSheet.id == data.product_id)
    expert = SalesExpert.get_or_none(SalesExpert.id == data.expert_id)

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
    item = Customer.create(
        FirstName=data.first_name,
        LastName=data.last_name,
        Phone=data.phone
    )
    return {"message": "Customer created successfully.", "customer": customer_to_dict(item)}


@app.get("/customers")
def get_customers(customer_id: Optional[int] = None):
    if customer_id is not None:
        return customer_to_dict(get_or_404(Customer, customer_id, "Customer"))
    return [customer_to_dict(item) for item in Customer.select().order_by(Customer.id)]


@app.put("/customers/{customer_id}")
def update_customer(customer_id: int, data: CustomerInput):
    item = get_or_404(Customer, customer_id, "Customer")
    item.FirstName = data.first_name
    item.LastName = data.last_name
    item.Phone = data.phone
    item.save()
    return {"message": "Customer updated successfully.", "customer": customer_to_dict(item)}


@app.delete("/customers/{customer_id}")
def delete_customer(customer_id: int):
    item = get_or_404(Customer, customer_id, "Customer")
    try:
        item.delete_instance()
    except IntegrityError:
        raise HTTPException(status_code=409, detail="This customer is connected to a sale and cannot be deleted.")
    return {"message": "Customer deleted successfully.", "id": customer_id}


# --------------------------------------------------
# Sales experts - CRUD and search by ID
# --------------------------------------------------

@app.post("/experts", status_code=201)
def create_expert(data: ExpertInput):
    item = SalesExpert.create(
        FirstName=data.first_name,
        LastName=data.last_name,
        Phone=data.phone
    )
    return {"message": "Sales expert created successfully.", "expert": expert_to_dict(item)}


@app.get("/experts")
def get_experts(expert_id: Optional[int] = None):
    if expert_id is not None:
        return expert_to_dict(get_or_404(SalesExpert, expert_id, "Sales expert"))
    return [expert_to_dict(item) for item in SalesExpert.select().order_by(SalesExpert.id)]


@app.put("/experts/{expert_id}")
def update_expert(expert_id: int, data: ExpertInput):
    item = get_or_404(SalesExpert, expert_id, "Sales expert")
    item.FirstName = data.first_name
    item.LastName = data.last_name
    item.Phone = data.phone
    item.save()
    return {"message": "Sales expert updated successfully.", "expert": expert_to_dict(item)}


@app.delete("/experts/{expert_id}")
def delete_expert(expert_id: int):
    item = get_or_404(SalesExpert, expert_id, "Sales expert")
    try:
        item.delete_instance()
    except IntegrityError:
        raise HTTPException(status_code=409, detail="This expert is connected to a sale and cannot be deleted.")
    return {"message": "Sales expert deleted successfully.", "id": expert_id}


# --------------------------------------------------
# MDF sheets / products - CRUD and search by ID
# --------------------------------------------------

@app.post("/products", status_code=201)
def create_product(data: ProductInput):
    try:
        item = MDFSheet.create(
            ProductCode=data.product_code,
            ProductName=data.product_name,
            Thickness=data.thickness,
            Length=data.length,
            Width=data.width,
            Price=data.price,
            Stock=data.stock
        )
    except IntegrityError:
        raise HTTPException(status_code=409, detail="This product code already exists.")
    return {"message": "MDF sheet created successfully.", "product": product_to_dict(item)}


@app.get("/products")
def get_products(product_id: Optional[int] = None):
    if product_id is not None:
        return product_to_dict(get_or_404(MDFSheet, product_id, "Product"))
    return [product_to_dict(item) for item in MDFSheet.select().order_by(MDFSheet.id)]


@app.put("/products/{product_id}")
def update_product(product_id: int, data: ProductInput):
    item = get_or_404(MDFSheet, product_id, "Product")
    item.ProductCode = data.product_code
    item.ProductName = data.product_name
    item.Thickness = data.thickness
    item.Length = data.length
    item.Width = data.width
    item.Price = data.price
    item.Stock = data.stock
    try:
        item.save()
    except IntegrityError:
        raise HTTPException(status_code=409, detail="This product code already exists.")
    return {"message": "MDF sheet updated successfully.", "product": product_to_dict(item)}


@app.delete("/products/{product_id}")
def delete_product(product_id: int):
    item = get_or_404(MDFSheet, product_id, "Product")
    try:
        item.delete_instance()
    except IntegrityError:
        raise HTTPException(status_code=409, detail="This product is connected to a sale and cannot be deleted.")
    return {"message": "MDF sheet deleted successfully.", "id": product_id}


# --------------------------------------------------
# Sales - CRUD and search by ID
# Stock is adjusted when a sale is created, updated or deleted.
# --------------------------------------------------

@app.post("/sales", status_code=201)
def create_sale(data: SaleInput):
    customer, product, expert = check_foreign_keys(data)

    with db.atomic():
        # Re-read the product inside the transaction.
        product = MDFSheet.get_by_id(data.product_id)
        if product.Stock < data.quantity:
            raise HTTPException(status_code=400, detail="Insufficient stock.")

        item = Sale.create(
            Customer=customer,
            Product=product,
            Expert=expert,
            Quantity=data.quantity,
            SaleDate=data.sale_date,
            UnitPrice=data.unit_price
        )
        product.Stock -= data.quantity
        product.save()

    return {"message": "Sale created successfully.", "sale": sale_to_dict(item)}


@app.get("/sales")
def get_sales(sale_id: Optional[int] = None):
    if sale_id is not None:
        return sale_to_dict(get_or_404(Sale, sale_id, "Sale"))
    return [sale_to_dict(item) for item in Sale.select().order_by(Sale.id)]


@app.put("/sales/{sale_id}")
def update_sale(sale_id: int, data: SaleInput):
    sale = get_or_404(Sale, sale_id, "Sale")
    customer, requested_product, expert = check_foreign_keys(data)

    with db.atomic():
        # Restore the quantity from the previous sale first.
        old_product = MDFSheet.get_by_id(sale.Product_id)
        old_product.Stock += sale.Quantity
        old_product.save()

        # Check stock after restoring the old sale quantity.
        product = MDFSheet.get_by_id(data.product_id)
        if product.Stock < data.quantity:
            raise HTTPException(status_code=400, detail="Insufficient stock.")

        product.Stock -= data.quantity
        product.save()

        sale.Customer = customer
        sale.Product = product
        sale.Expert = expert
        sale.Quantity = data.quantity
        sale.SaleDate = data.sale_date
        sale.UnitPrice = data.unit_price
        sale.save()

    return {"message": "Sale updated successfully.", "sale": sale_to_dict(sale)}


@app.delete("/sales/{sale_id}")
def delete_sale(sale_id: int):
    sale = get_or_404(Sale, sale_id, "Sale")

    with db.atomic():
        product = MDFSheet.get_by_id(sale.Product_id)
        product.Stock += sale.Quantity
        product.save()
        sale.delete_instance()

    return {"message": "Sale deleted successfully. Product stock was restored.", "id": sale_id}
