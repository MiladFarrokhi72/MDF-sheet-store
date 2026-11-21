from datetime import date

from flask import Flask, abort, flash, redirect, render_template, request, url_for
from peewee import (
    CharField, DateField, DoesNotExist, FloatField, ForeignKeyField,
    IntegrityError, IntegerField, Model, PostgresqlDatabase, TextField,
)

app = Flask(__name__)
app.secret_key = "change-this-secret-key"
import os
from peewee import PostgresqlDatabase

db = PostgresqlDatabase(
    os.getenv("DB_NAME", "mdf_shop"),
    user=os.getenv("DB_USER", "postgres"),
    password=os.getenv("DB_PASSWORD", ""),
    host=os.getenv("DB_HOST", "127.0.0.1"),
    port=int(os.getenv("DB_PORT", "5432")),
)


class BaseModel(Model):
    class Meta:
        database = db


class Customer(BaseModel):
    first_name = CharField(max_length=60)
    last_name = CharField(max_length=60)
    phone = CharField(max_length=30, null=True)
    address = TextField(null=True)


class SalesExpert(BaseModel):
    first_name = CharField(max_length=60)
    last_name = CharField(max_length=60)
    phone = CharField(max_length=30, null=True)


class MDFSheet(BaseModel):
    product_code = CharField(max_length=50, unique=True)
    manufacturer_name = CharField(max_length=100)
    product_name = CharField(max_length=100)
    thickness_mm = FloatField()
    length_mm = FloatField()
    width_mm = FloatField()
    price = FloatField()
    stock = IntegerField(default=0)


class Sale(BaseModel):
    customer = ForeignKeyField(Customer, backref="sales", on_delete="RESTRICT")
    expert = ForeignKeyField(SalesExpert, backref="sales", on_delete="RESTRICT")
    sheet = ForeignKeyField(MDFSheet, backref="sales", on_delete="RESTRICT")
    quantity = IntegerField()
    unit_price = FloatField()
    sale_date = DateField(default=date.today)


# Field format: (database field, label, input type, required)
SECTIONS = {
    "customers": {
        "title": "Customers", "model": Customer,
        "fields": [
            ("first_name", "First name", "text", True),
            ("last_name", "Last name", "text", True),
            ("phone", "Phone", "text", False),
            ("address", "Address", "textarea", False),
        ],
    },
    "experts": {
        "title": "Sales Experts", "model": SalesExpert,
        "fields": [
            ("first_name", "First name", "text", True),
            ("last_name", "Last name", "text", True),
            ("phone", "Phone", "text", False),
        ],
    },
    "products": {
        "title": "MDF Sheets", "model": MDFSheet,
        "fields": [
            ("product_code", "Manufacturer Product Code", "text", True),
            ("manufacturer_name", "Manufacturer Company", "text", True),
            ("product_name", "Product name", "text", True),
            ("thickness_mm", "Thickness (mm)", "number", True),
            ("length_mm", "Length (mm)", "number", True),
            ("width_mm", "Width (mm)", "number", True),
            ("price", "Price", "number", True),
            ("stock", "Stock quantity", "integer", True),
        ],
    },
}


def get_record(model, record_id):
    try:
        return model.get_by_id(int(record_id))
    except (DoesNotExist, TypeError, ValueError):
        abort(404)


def read_form(fields):
    """Read and convert fields described in SECTIONS."""
    values = {}
    for name, label, kind, required in fields:
        raw = request.form.get(name, "").strip()
        if required and not raw:
            raise ValueError(f"{label} is required.")
        if not raw:
            values[name] = None
        elif kind == "number":
            values[name] = float(raw)
        elif kind == "integer":
            values[name] = int(raw)
        else:
            values[name] = raw

        if kind in ("number", "integer") and raw:
            if values[name] < 0:
                raise ValueError(f"{label} cannot be negative.")
    return values


def section_url(section):
    return url_for("manage_section", section=section)


@app.route("/")
def home():
    counts = {
        "customers": Customer.select().count(),
        "experts": SalesExpert.select().count(),
        "products": MDFSheet.select().count(),
        "sales": Sale.select().count(),
    }
    return render_template("home.html", counts=counts)


@app.route("/<section>", methods=["GET", "POST"])
def manage_section(section):
    if section == "sales":
        return manage_sales()
    if section not in SECTIONS:
        abort(404)

    config = SECTIONS[section]
    model = config["model"]
    if request.method == "POST":
        try:
            model.create(**read_form(config["fields"]))
            flash("Record created successfully.")
        except ValueError as error:
            flash(str(error))
        except IntegrityError:
            flash("This manufacturer product code already exists.")
        return redirect(section_url(section))

    # Products use the manufacturer's unique product code; other records use ID.
    search_value = request.args.get("code" if section == "products" else "id", "").strip()
    query = model.select()
    if search_value:
        if section == "products":
            query = query.where(MDFSheet.product_code == search_value)
        else:
            try:
                query = query.where(model.id == int(search_value))
            except ValueError:
                query = query.where(model.id == -1)
                flash("ID must be a number.")

    records = list(query.order_by(model.id.desc()))
    return render_template("records.html", section=section, config=config,
                           records=records, record=None, search_value=search_value)


@app.route("/<section>/edit/<int:record_id>", methods=["GET", "POST"])
def edit_record(section, record_id):
    if section == "sales":
        return edit_sale(record_id)
    if section not in SECTIONS:
        abort(404)

    config = SECTIONS[section]
    record = get_record(config["model"], record_id)
    if request.method == "POST":
        try:
            for field, value in read_form(config["fields"]).items():
                setattr(record, field, value)
            record.save()
            flash("Record updated successfully.")
            return redirect(section_url(section))
        except ValueError as error:
            flash(str(error))
        except IntegrityError:
            flash("This manufacturer product code belongs to another sheet.")

    return render_template("records.html", section=section, config=config,
                           records=[], record=record, search_value="")


@app.route("/<section>/delete/<int:record_id>", methods=["POST"])
def delete_record(section, record_id):
    if section == "sales":
        sale = get_record(Sale, record_id)
        with db.atomic():
            sale.sheet.stock += sale.quantity
            sale.sheet.save()
            sale.delete_instance()
    else:
        if section not in SECTIONS:
            abort(404)
        record = get_record(SECTIONS[section]["model"], record_id)
        try:
            record.delete_instance()
        except IntegrityError:
            flash("This record is connected to a sale and cannot be deleted.")
            return redirect(section_url(section))
    flash("Record deleted.")
    return redirect(section_url(section))


def sale_form_data():
    customer = get_record(Customer, request.form.get("customer_id"))
    expert = get_record(SalesExpert, request.form.get("expert_id"))
    sheet = get_record(MDFSheet, request.form.get("sheet_id"))
    quantity = int(request.form.get("quantity", "0"))
    unit_price = float(request.form.get("unit_price", "0"))
    sale_date = request.form.get("sale_date") or date.today().isoformat()
    if quantity <= 0:
        raise ValueError("Quantity must be greater than zero.")
    if unit_price < 0:
        raise ValueError("Unit price cannot be negative.")
    return customer, expert, sheet, quantity, unit_price, sale_date


def sale_page(sales, sale=None):
    return render_template(
        "sales.html", sales=sales, sale=sale,
        customers=Customer.select(), experts=SalesExpert.select(),
        products=MDFSheet.select(), search_id=request.args.get("id", "").strip(),
        today=date.today().isoformat(),
    )


def manage_sales():
    if request.method == "POST":
        try:
            customer, expert, sheet, quantity, price, sale_date = sale_form_data()
            if quantity > sheet.stock:
                raise ValueError("There is not enough stock.")
            with db.atomic():
                Sale.create(customer=customer, expert=expert, sheet=sheet,
                            quantity=quantity, unit_price=price, sale_date=sale_date)
                sheet.stock -= quantity
                sheet.save()
            flash("Sale created. Stock quantity was reduced.")
        except (ValueError, TypeError) as error:
            flash(str(error))
        return redirect(section_url("sales"))

    search_id = request.args.get("id", "").strip()
    query = Sale.select()
    if search_id:
        try:
            query = query.where(Sale.id == int(search_id))
        except ValueError:
            query = query.where(Sale.id == -1)
            flash("Sale ID must be a number.")
    return sale_page(list(query.order_by(Sale.id.desc())))


def edit_sale(record_id):
    sale = get_record(Sale, record_id)
    if request.method == "POST":
        try:
            customer, expert, new_sheet, quantity, price, sale_date = sale_form_data()
            old_sheet = sale.sheet
            available = old_sheet.stock + sale.quantity if old_sheet.id == new_sheet.id else new_sheet.stock
            if quantity > available:
                raise ValueError("There is not enough stock.")

            with db.atomic():
                old_sheet.stock += sale.quantity
                old_sheet.save()
                new_sheet.stock -= quantity
                new_sheet.save()
                sale.customer, sale.expert, sale.sheet = customer, expert, new_sheet
                sale.quantity, sale.unit_price, sale.sale_date = quantity, price, sale_date
                sale.save()
            flash("Sale updated and stock adjusted.")
            return redirect(section_url("sales"))
        except (ValueError, TypeError) as error:
            flash(str(error))

    return sale_page([sale], sale=sale)


# Create the database tables when the application starts.
db.connect(reuse_if_open=True)
db.create_tables([Customer, SalesExpert, MDFSheet, Sale])

if __name__ == "__main__":
    app.run(debug=True)
