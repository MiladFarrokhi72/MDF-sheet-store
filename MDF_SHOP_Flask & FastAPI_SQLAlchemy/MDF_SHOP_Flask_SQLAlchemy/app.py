from datetime import date
from types import SimpleNamespace

from flask import Flask, abort, flash, redirect, render_template, request, url_for
from sqlalchemy import (
    create_engine, MetaData, Table, Column, Integer, String, Float, Date, event,
    Text, ForeignKey, select, insert, update, delete, func, and_
)
from sqlalchemy.exc import IntegrityError

app = Flask(__name__)
app.secret_key = "change-this-secret-key"

# SQLAlchemy Core database connection (SQLite by default).
engine = create_engine(
    "sqlite:///mdf_shop.db",
    connect_args={"check_same_thread": False}
)
@event.listens_for(engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

meta = MetaData()

customers = Table(
    "customers", meta,
    Column("id", Integer, primary_key=True),
    Column("first_name", String(60), nullable=False),
    Column("last_name", String(60), nullable=False),
    Column("phone", String(30)),
    Column("address", Text),
)
experts = Table(
    "salesexpert", meta,
    Column("id", Integer, primary_key=True),
    Column("first_name", String(60), nullable=False),
    Column("last_name", String(60), nullable=False),
    Column("phone", String(30)),
)
products = Table(
    "mdfsheet", meta,
    Column("id", Integer, primary_key=True),
    Column("product_code", String(50), unique=True, nullable=False),
    Column("manufacturer_name", String(100), nullable=False),
    Column("product_name", String(100), nullable=False),
    Column("thickness_mm", Float, nullable=False),
    Column("length_mm", Float, nullable=False),
    Column("width_mm", Float, nullable=False),
    Column("price", Float, nullable=False),
    Column("stock", Integer, nullable=False, server_default="0"),
)
sales = Table(
    "sale", meta,
    Column("id", Integer, primary_key=True),
    Column("customer_id", Integer, ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False),
    Column("expert_id", Integer, ForeignKey("salesexpert.id", ondelete="RESTRICT"), nullable=False),
    Column("sheet_id", Integer, ForeignKey("mdfsheet.id", ondelete="RESTRICT"), nullable=False),
    Column("quantity", Integer, nullable=False),
    Column("unit_price", Float, nullable=False),
    Column("sale_date", Date, nullable=False),
)

# Create tables if they do not exist.
meta.create_all(engine)

SECTIONS = {
    "customers": {
        "title": "Customers", "table": customers,
        "fields": [
            ("first_name", "First name", "text", True),
            ("last_name", "Last name", "text", True),
            ("phone", "Phone", "text", False),
            ("address", "Address", "textarea", False),
        ],
    },
    "experts": {
        "title": "Sales Experts", "table": experts,
        "fields": [
            ("first_name", "First name", "text", True),
            ("last_name", "Last name", "text", True),
            ("phone", "Phone", "text", False),
        ],
    },
    "products": {
        "title": "MDF Sheets", "table": products,
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


def as_obj(row):
    return SimpleNamespace(**dict(row._mapping))


def get_record(table, record_id):
    try:
        record_id = int(record_id)
    except (TypeError, ValueError):
        abort(404)
    with engine.connect() as conn:
        row = conn.execute(select(table).where(table.c.id == record_id)).first()
    if row is None:
        abort(404)
    return as_obj(row)


def read_form(fields):
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
        if kind in ("number", "integer") and raw and values[name] < 0:
            raise ValueError(f"{label} cannot be negative.")
    return values


def section_url(section):
    return url_for("manage_section", section=section)


@app.route("/")
def home():
    with engine.connect() as conn:
        counts = {
            "customers": conn.execute(select(func.count()).select_from(customers)).scalar_one(),
            "experts": conn.execute(select(func.count()).select_from(experts)).scalar_one(),
            "products": conn.execute(select(func.count()).select_from(products)).scalar_one(),
            "sales": conn.execute(select(func.count()).select_from(sales)).scalar_one(),
        }
    return render_template("home.html", counts=counts)


@app.route("/<section>", methods=["GET", "POST"])
def manage_section(section):
    if section == "sales":
        return manage_sales()
    if section not in SECTIONS:
        abort(404)

    config = SECTIONS[section]
    table = config["table"]
    if request.method == "POST":
        try:
            values = read_form(config["fields"])
            with engine.begin() as conn:
                conn.execute(insert(table).values(**values))
            flash("Record created successfully.")
        except ValueError as error:
            flash(str(error))
        except IntegrityError:
            flash("This manufacturer product code already exists.")
        return redirect(section_url(section))

    search_value = request.args.get("code" if section == "products" else "id", "").strip()
    stmt = select(table)
    if search_value:
        if section == "products":
            stmt = stmt.where(table.c.product_code == search_value)
        else:
            try:
                stmt = stmt.where(table.c.id == int(search_value))
            except ValueError:
                stmt = stmt.where(table.c.id == -1)
                flash("ID must be a number.")
    stmt = stmt.order_by(table.c.id.desc())
    with engine.connect() as conn:
        records = [as_obj(row) for row in conn.execute(stmt).all()]
    return render_template("records.html", section=section, config=config,
                           records=records, record=None, search_value=search_value)


@app.route("/<section>/edit/<int:record_id>", methods=["GET", "POST"])
def edit_record(section, record_id):
    if section == "sales":
        return edit_sale(record_id)
    if section not in SECTIONS:
        abort(404)

    config = SECTIONS[section]
    table = config["table"]
    record = get_record(table, record_id)
    if request.method == "POST":
        try:
            values = read_form(config["fields"])
            with engine.begin() as conn:
                conn.execute(update(table).where(table.c.id == record_id).values(**values))
            flash("Record updated successfully.")
            return redirect(section_url(section))
        except ValueError as error:
            flash(str(error))
        except IntegrityError:
            flash("This manufacturer product code belongs to another sheet.")
        record = get_record(table, record_id)

    return render_template("records.html", section=section, config=config,
                           records=[], record=record, search_value="")


@app.route("/<section>/delete/<int:record_id>", methods=["POST"])
def delete_record(section, record_id):
    if section == "sales":
        sale = get_record(sales, record_id)
        with engine.begin() as conn:
            conn.execute(update(products).where(products.c.id == sale.sheet_id)
                         .values(stock=products.c.stock + sale.quantity))
            conn.execute(delete(sales).where(sales.c.id == record_id))
    else:
        if section not in SECTIONS:
            abort(404)
        table = SECTIONS[section]["table"]
        get_record(table, record_id)
        try:
            with engine.begin() as conn:
                conn.execute(delete(table).where(table.c.id == record_id))
        except IntegrityError:
            flash("This record is connected to a sale and cannot be deleted.")
            return redirect(section_url(section))
    flash("Record deleted.")
    return redirect(section_url(section))


def sale_form_data():
    customer_id = int(request.form.get("customer_id", "0"))
    expert_id = int(request.form.get("expert_id", "0"))
    sheet_id = int(request.form.get("sheet_id", "0"))
    quantity = int(request.form.get("quantity", "0"))
    unit_price = float(request.form.get("unit_price", "0"))
    sale_date = date.fromisoformat(request.form.get("sale_date") or date.today().isoformat())

    customer = get_record(customers, customer_id)
    expert = get_record(experts, expert_id)
    sheet = get_record(products, sheet_id)
    if quantity <= 0:
        raise ValueError("Quantity must be greater than zero.")
    if unit_price < 0:
        raise ValueError("Unit price cannot be negative.")
    return customer, expert, sheet, quantity, unit_price, sale_date


def load_sale_objects(rows):
    result = []
    for row in rows:
        m = row._mapping
        result.append(SimpleNamespace(
            id=m["sale_id"], customer_id=m["customer_id"], expert_id=m["expert_id"],
            sheet_id=m["sheet_id"], quantity=m["quantity"], unit_price=m["unit_price"],
            sale_date=m["sale_date"],
            customer=SimpleNamespace(first_name=m["customer_first"], last_name=m["customer_last"]),
            expert=SimpleNamespace(first_name=m["expert_first"], last_name=m["expert_last"]),
            sheet=SimpleNamespace(product_code=m["product_code"],
                                  manufacturer_name=m["manufacturer_name"],
                                  product_name=m["product_name"])
        ))
    return result


def sale_select():
    return select(
        sales.c.id.label("sale_id"), sales.c.customer_id, sales.c.expert_id,
        sales.c.sheet_id, sales.c.quantity, sales.c.unit_price, sales.c.sale_date,
        customers.c.first_name.label("customer_first"),
        customers.c.last_name.label("customer_last"),
        experts.c.first_name.label("expert_first"),
        experts.c.last_name.label("expert_last"),
        products.c.product_code, products.c.manufacturer_name, products.c.product_name,
    ).select_from(
        sales.join(customers, sales.c.customer_id == customers.c.id)
             .join(experts, sales.c.expert_id == experts.c.id)
             .join(products, sales.c.sheet_id == products.c.id)
    )


def sale_page(sale_rows, sale=None):
    with engine.connect() as conn:
        customer_rows = conn.execute(select(customers).order_by(customers.c.id)).all()
        expert_rows = conn.execute(select(experts).order_by(experts.c.id)).all()
        product_rows = conn.execute(select(products).order_by(products.c.id)).all()
    return render_template(
        "sales.html", sales=sale_rows, sale=sale,
        customers=[as_obj(r) for r in customer_rows],
        experts=[as_obj(r) for r in expert_rows],
        products=[as_obj(r) for r in product_rows],
        search_id=request.args.get("id", "").strip(),
        today=date.today().isoformat(),
    )


def manage_sales():
    if request.method == "POST":
        try:
            customer, expert, sheet, quantity, price, sale_date = sale_form_data()
            with engine.begin() as conn:
                current_stock = conn.execute(
                    select(products.c.stock).where(products.c.id == sheet.id)
                ).scalar_one()
                if quantity > current_stock:
                    raise ValueError("There is not enough stock.")
                conn.execute(insert(sales).values(
                    customer_id=customer.id, expert_id=expert.id, sheet_id=sheet.id,
                    quantity=quantity, unit_price=price, sale_date=sale_date
                ))
                conn.execute(update(products).where(products.c.id == sheet.id)
                             .values(stock=products.c.stock - quantity))
            flash("Sale created. Stock quantity was reduced.")
        except (ValueError, TypeError) as error:
            flash(str(error))
        return redirect(section_url("sales"))

    search_id = request.args.get("id", "").strip()
    stmt = sale_select()
    if search_id:
        try:
            stmt = stmt.where(sales.c.id == int(search_id))
        except ValueError:
            stmt = stmt.where(sales.c.id == -1)
            flash("Sale ID must be a number.")
    stmt = stmt.order_by(sales.c.id.desc())
    with engine.connect() as conn:
        rows = conn.execute(stmt).all()
    return sale_page(load_sale_objects(rows))


def edit_sale(record_id):
    sale = get_record(sales, record_id)
    if request.method == "POST":
        try:
            customer, expert, new_sheet, quantity, price, sale_date = sale_form_data()
            with engine.begin() as conn:
                old_stock = conn.execute(
                    select(products.c.stock).where(products.c.id == sale.sheet_id)
                ).scalar_one()
                new_stock = conn.execute(
                    select(products.c.stock).where(products.c.id == new_sheet.id)
                ).scalar_one()
                available = old_stock + sale.quantity if sale.sheet_id == new_sheet.id else new_stock
                if quantity > available:
                    raise ValueError("There is not enough stock.")

                conn.execute(update(products).where(products.c.id == sale.sheet_id)
                             .values(stock=products.c.stock + sale.quantity))
                conn.execute(update(products).where(products.c.id == new_sheet.id)
                             .values(stock=products.c.stock - quantity))
                conn.execute(update(sales).where(sales.c.id == record_id).values(
                    customer_id=customer.id, expert_id=expert.id, sheet_id=new_sheet.id,
                    quantity=quantity, unit_price=price, sale_date=sale_date
                ))
            flash("Sale updated and stock adjusted.")
            return redirect(section_url("sales"))
        except (ValueError, TypeError) as error:
            flash(str(error))

    with engine.connect() as conn:
        row = conn.execute(sale_select().where(sales.c.id == record_id)).first()
    sale_obj = load_sale_objects([row])[0]
    return sale_page([sale_obj], sale=sale_obj)


if __name__ == "__main__":
    app.run(debug=True)
