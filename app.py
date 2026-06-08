"""
GL Kundu & Sons Steel Pvt. Ltd — Business Assistant
Flask backend: chatbot + database + dashboard.
The Claude API key lives ONLY on the server, never in the browser.
"""

import os
import json
from datetime import date

from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
import anthropic

app = Flask(__name__)

# ── Database ───────────────────────────────────────────────────────────
db_url = os.environ.get("DATABASE_URL", "sqlite:///steel.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
if db_url.startswith("postgresql"):
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True, "pool_recycle": 280}

db = SQLAlchemy(app)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")


# ── Indian number formatting (lakhs / crores) ──────────────────────────
def format_inr(amount):
    """Format a number as ₹ with Indian grouping and lakh/crore words."""
    try:
        n = float(amount or 0)
    except (TypeError, ValueError):
        return "₹0"
    if n >= 10000000:      # 1 crore
        return f"₹{n/10000000:.2f} Cr"
    if n >= 100000:        # 1 lakh
        return f"₹{n/100000:.2f} L"
    s = f"{int(round(n)):,}"
    parts = s.replace(",", "")
    if len(parts) > 3:
        last3 = parts[-3:]
        rest = parts[:-3]
        groups = []
        while len(rest) > 2:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.insert(0, rest)
        s = ",".join(groups) + "," + last3
    return f"₹{s}"


# ── Models ─────────────────────────────────────────────────────────────
class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    stock_tons = db.Column(db.Float, default=0)
    reorder_level = db.Column(db.Float, default=0)
    rate_per_ton = db.Column(db.Float, default=0)

    def to_dict(self):
        return {"product": self.name, "stock": self.stock_tons,
                "reorder": self.reorder_level, "rate_per_ton": self.rate_per_ton}


class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    city = db.Column(db.String(80))
    amount_due = db.Column(db.Float, default=0)
    days_overdue = db.Column(db.Integer, default=0)

    def to_dict(self):
        return {"name": self.name, "city": self.city,
                "due": self.amount_due, "days": self.days_overdue}


class Sale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_name = db.Column(db.String(120))
    customer_name = db.Column(db.String(120))
    quantity_tons = db.Column(db.Float)
    amount = db.Column(db.Float)
    sale_date = db.Column(db.Date, default=date.today)

    def to_dict(self):
        return {"product": self.product_name, "customer": self.customer_name,
                "quantity": self.quantity_tons, "amount": self.amount,
                "date": self.sale_date.isoformat() if self.sale_date else None}


# ── Business snapshot for the AI ───────────────────────────────────────
def get_business_data():
    products = [p.to_dict() for p in Product.query.all()]
    customers = [c.to_dict() for c in Customer.query.all()]
    today = date.today()
    todays = Sale.query.filter_by(sale_date=today).all()
    return {
        "inventory": products,
        "customers": customers,
        "today": {
            "tons_sold": round(sum(s.quantity_tons or 0 for s in todays), 2),
            "revenue": round(sum(s.amount or 0 for s in todays), 2),
            "orders": len(todays),
        },
    }


# ── Pages ──────────────────────────────────────────────────────────────
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/entry")
def entry():
    products = Product.query.order_by(Product.name).all()
    customers = Customer.query.order_by(Customer.name).all()
    return render_template("entry.html", products=products, customers=customers)


@app.route("/dashboard")
def dashboard():
    products = Product.query.order_by(Product.name).all()
    customers = Customer.query.order_by(Customer.amount_due.desc()).all()

    low_stock = [p for p in products if p.reorder_level and p.stock_tons <= p.reorder_level]
    overdue = [c for c in customers if c.amount_due and c.amount_due > 0]
    total_due = sum(c.amount_due or 0 for c in overdue)

    today = date.today()
    month_start = today.replace(day=1)
    month_sales = Sale.query.filter(Sale.sale_date >= month_start).all()
    month_revenue = sum(s.amount or 0 for s in month_sales)
    month_tons = round(sum(s.quantity_tons or 0 for s in month_sales), 1)

    cust_totals = {}
    for s in month_sales:
        if s.customer_name:
            cust_totals[s.customer_name] = cust_totals.get(s.customer_name, 0) + (s.amount or 0)
    top = sorted(cust_totals.items(), key=lambda x: x[1], reverse=True)[:5]
    maxval = top[0][1] if top else 0
    top_customers = [
        {"name": n, "amount_fmt": format_inr(a), "pct": (a / maxval * 100) if maxval else 0}
        for n, a in top
    ]

    overdue_view = [
        {"name": c.name, "city": c.city, "due_fmt": format_inr(c.amount_due),
         "days": c.days_overdue or 0}
        for c in overdue
    ]

    products_view = []
    for p in products:
        if p.reorder_level:
            pct = min(100, (p.stock_tons / (p.reorder_level * 2)) * 100)
            is_low = p.stock_tons <= p.reorder_level
        else:
            pct, is_low = 60, False
        products_view.append({
            "name": p.name, "stock": p.stock_tons, "reorder": p.reorder_level,
            "pct": pct, "low": is_low,
        })

    return render_template(
        "dashboard.html",
        products=products_view,
        low_stock=low_stock,
        overdue=overdue_view,
        total_due_fmt=format_inr(total_due),
        total_due=total_due,
        overdue_count=len(overdue_view),
        month_revenue_fmt=format_inr(month_revenue),
        month_tons=month_tons,
        low_count=len(low_stock),
        product_count=len(products),
        top_customers=top_customers,
    )


# ── API ────────────────────────────────────────────────────────────────
@app.route("/api/inventory")
def api_inventory():
    return jsonify([p.to_dict() for p in Product.query.order_by(Product.name).all()])


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(force=True)
    history = data.get("history", [])
    if not ANTHROPIC_API_KEY:
        return jsonify({"reply": "⚠️ The AI is not connected yet. The site owner "
                                 "needs to add the ANTHROPIC_API_KEY."})

    business = get_business_data()
    system_prompt = f"""You are a smart, friendly business assistant for GL Kundu & Sons Steel Pvt. Ltd,
an authorised Tata Steel distributor based in Malda, West Bengal, India.
Service area: Malda, Uttar & Dakshin Dinajpur, Darjeeling, Jalpaiguri, and Sikkim.
Products: Tata Tiscon, Tiscon Superlinks, Tiscon Footings, Tata Shaktee, Wama, Ridge, Tata Pravesh, Fosroc.
Contact: +91 9593027864 | www.glksspl.com

CURRENT business data from the database:
{json.dumps(business, indent=2)}

Guidelines:
- Answer warmly and very simply — the owners may not be tech-savvy.
- Use Indian number formatting (Lakhs/Crores) where it helps.
- Clearly flag anything urgent: stock at/below reorder level, payments overdue >30 days.
- Keep answers short and actionable.
- If the user writes in Hindi or Bengali, reply in that same language.
- Only use the data above. If something isn't there, say so kindly."""

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        resp = client.messages.create(model=CLAUDE_MODEL, max_tokens=1000,
                                       system=system_prompt, messages=history)
        return jsonify({"reply": resp.content[0].text})
    except Exception as e:
        return jsonify({"reply": f"⚠️ Sorry, something went wrong: {str(e)}"})


@app.route("/api/add-stock", methods=["POST"])
def add_stock():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    qty = float(data.get("quantity") or 0)
    rate = data.get("rate")
    reorder = data.get("reorder")
    if not name:
        return jsonify({"ok": False, "error": "Product name is required."})
    product = Product.query.filter(db.func.lower(Product.name) == name.lower()).first()
    if product:
        product.stock_tons = (product.stock_tons or 0) + qty
        if rate:
            product.rate_per_ton = float(rate)
        if reorder:
            product.reorder_level = float(reorder)
    else:
        product = Product(name=name, stock_tons=qty,
                          rate_per_ton=float(rate) if rate else 0,
                          reorder_level=float(reorder) if reorder else 0)
        db.session.add(product)
    db.session.commit()
    return jsonify({"ok": True, "product": product.to_dict()})


@app.route("/api/add-customer", methods=["POST"])
def add_customer():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "Customer name is required."})
    c = Customer(name=name, city=(data.get("city") or "").strip(),
                 amount_due=float(data.get("due") or 0),
                 days_overdue=int(data.get("days") or 0))
    db.session.add(c)
    db.session.commit()
    return jsonify({"ok": True, "customer": c.to_dict()})


@app.route("/api/add-sale", methods=["POST"])
def add_sale():
    data = request.get_json(force=True)
    pname = (data.get("product") or "").strip()
    qty = float(data.get("quantity") or 0)
    s = Sale(product_name=pname, customer_name=(data.get("customer") or "").strip(),
             quantity_tons=qty, amount=float(data.get("amount") or 0), sale_date=date.today())
    db.session.add(s)
    product = Product.query.filter(db.func.lower(Product.name) == pname.lower()).first()
    if product:
        product.stock_tons = max(0, (product.stock_tons or 0) - qty)
    db.session.commit()
    return jsonify({"ok": True, "sale": s.to_dict()})


# ── First-run seed ─────────────────────────────────────────────────────
def seed_if_empty():
    db.create_all()
    if Product.query.count() == 0:
        db.session.add_all([
            Product(name="Tata Tiscon (TMT Fe-500)", stock_tons=84, reorder_level=50, rate_per_ton=56000),
            Product(name="Tata Shaktee (Sheets)", stock_tons=31, reorder_level=40, rate_per_ton=68000),
            Product(name="Tata Pravesh (Doors)", stock_tons=18, reorder_level=15, rate_per_ton=82000),
            Product(name="Tiscon Superlinks", stock_tons=12, reorder_level=20, rate_per_ton=61000),
            Product(name="Tiscon Footings", stock_tons=9, reorder_level=15, rate_per_ton=63000),
            Product(name="Fosroc Products", stock_tons=22, reorder_level=10, rate_per_ton=45000),
            Customer(name="Ramesh Construction", city="Malda", amount_due=185000, days_overdue=45),
            Customer(name="Bengal Infra Pvt Ltd", city="Kolkata", amount_due=0, days_overdue=0),
            Customer(name="Suresh Steel Works", city="Malda", amount_due=92000, days_overdue=12),
            Customer(name="North Bengal Builders", city="Siliguri", amount_due=340000, days_overdue=62),
            Customer(name="Mondal & Sons", city="Englishbazar", amount_due=0, days_overdue=0),
        ])
        db.session.commit()


with app.app_context():
    seed_if_empty()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
