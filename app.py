"""
GL Kundu & Sons Steel Pvt. Ltd — Business Assistant
Flask backend that connects the chatbot to a real database and Claude AI.

The Claude API key lives ONLY on the server (never in the browser),
so it stays private and secure.
"""

import os
import json
from datetime import datetime, date

from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
import anthropic

# ── App setup ──────────────────────────────────────────────────────────
app = Flask(__name__)

# Database: uses your Supabase PostgreSQL in the cloud if DATABASE_URL is set,
# otherwise falls back to a local SQLite file for testing on your own laptop.
db_url = os.environ.get("DATABASE_URL", "sqlite:///steel.db")
# Some providers give "postgres://" but SQLAlchemy needs "postgresql://"
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Recycle connections so the app stays healthy on free hosting that sleeps,
# and survives Supabase closing idle connections.
if db_url.startswith("postgresql"):
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }

db = SQLAlchemy(app)

# Claude client — reads the key from an environment variable
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
# You can upgrade this model string anytime as newer models release.
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")


# ── Database models ────────────────────────────────────────────────────
class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    stock_tons = db.Column(db.Float, default=0)
    reorder_level = db.Column(db.Float, default=0)
    rate_per_ton = db.Column(db.Float, default=0)

    def to_dict(self):
        return {
            "product": self.name,
            "stock": self.stock_tons,
            "reorder": self.reorder_level,
            "rate_per_ton": self.rate_per_ton,
        }


class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    city = db.Column(db.String(80))
    amount_due = db.Column(db.Float, default=0)
    days_overdue = db.Column(db.Integer, default=0)

    def to_dict(self):
        return {
            "name": self.name,
            "city": self.city,
            "due": self.amount_due,
            "days": self.days_overdue,
        }


class Sale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_name = db.Column(db.String(120))
    customer_name = db.Column(db.String(120))
    quantity_tons = db.Column(db.Float)
    amount = db.Column(db.Float)
    sale_date = db.Column(db.Date, default=date.today)

    def to_dict(self):
        return {
            "product": self.product_name,
            "customer": self.customer_name,
            "quantity": self.quantity_tons,
            "amount": self.amount,
            "date": self.sale_date.isoformat() if self.sale_date else None,
        }


# ── Build a snapshot of the business for Claude ────────────────────────
def get_business_data():
    """Pull everything from the DB into a dict the AI can reason over."""
    products = [p.to_dict() for p in Product.query.all()]
    customers = [c.to_dict() for c in Customer.query.all()]

    today = date.today()
    todays_sales = Sale.query.filter_by(sale_date=today).all()
    today_summary = {
        "tons_sold": round(sum(s.quantity_tons or 0 for s in todays_sales), 2),
        "revenue": round(sum(s.amount or 0 for s in todays_sales), 2),
        "orders": len(todays_sales),
    }

    return {
        "inventory": products,
        "customers": customers,
        "today": today_summary,
    }


# ── Routes: pages ──────────────────────────────────────────────────────
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/entry")
def entry():
    products = Product.query.order_by(Product.name).all()
    customers = Customer.query.order_by(Customer.name).all()
    return render_template("entry.html", products=products, customers=customers)


# ── Routes: API ────────────────────────────────────────────────────────
@app.route("/api/inventory")
def api_inventory():
    """Used by the chatbot sidebar to show live stock."""
    return jsonify([p.to_dict() for p in Product.query.order_by(Product.name).all()])


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """Receive a question, look up real data, ask Claude, return the answer."""
    data = request.get_json(force=True)
    history = data.get("history", [])

    if not ANTHROPIC_API_KEY:
        return jsonify({
            "reply": "⚠️ The AI is not connected yet. The site owner needs to "
                     "add the ANTHROPIC_API_KEY. Until then, you can still add "
                     "and view data on the Data Entry page."
        })

    business = get_business_data()
    system_prompt = f"""You are a smart, friendly business assistant for GL Kundu & Sons Steel Pvt. Ltd,
an authorised Tata Steel distributor based in Malda, West Bengal, India.
Service area: Malda, Uttar & Dakshin Dinajpur, Darjeeling, Jalpaiguri, and Sikkim.
Products: Tata Tiscon, Tiscon Superlinks, Tiscon Footings, Tata Shaktee, Wama, Ridge, Tata Pravesh, Fosroc.
Contact: +91 9593027864 | www.glksspl.com

Here is the CURRENT business data from the database:
{json.dumps(business, indent=2)}

Guidelines:
- Answer warmly and very simply — the owners may not be tech-savvy.
- Use Indian number formatting (Lakhs/Crores) where it helps.
- Clearly flag anything urgent: stock below its reorder level, or payments overdue more than 30 days.
- Keep answers short and actionable.
- If the user writes in Hindi or Bengali, reply in that same language.
- Only use the data above. If something isn't in the data, say so kindly."""

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1000,
            system=system_prompt,
            messages=history,
        )
        reply = resp.content[0].text
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"reply": f"⚠️ Sorry, something went wrong: {str(e)}"})


@app.route("/api/add-stock", methods=["POST"])
def add_stock():
    """Add or update product stock (e.g. new delivery from Tata Steel)."""
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
        product = Product(
            name=name,
            stock_tons=qty,
            rate_per_ton=float(rate) if rate else 0,
            reorder_level=float(reorder) if reorder else 0,
        )
        db.session.add(product)

    db.session.commit()
    return jsonify({"ok": True, "product": product.to_dict()})


@app.route("/api/add-customer", methods=["POST"])
def add_customer():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "Customer name is required."})

    customer = Customer(
        name=name,
        city=(data.get("city") or "").strip(),
        amount_due=float(data.get("due") or 0),
        days_overdue=int(data.get("days") or 0),
    )
    db.session.add(customer)
    db.session.commit()
    return jsonify({"ok": True, "customer": customer.to_dict()})


@app.route("/api/add-sale", methods=["POST"])
def add_sale():
    """Record a sale and reduce stock accordingly."""
    data = request.get_json(force=True)
    product_name = (data.get("product") or "").strip()
    qty = float(data.get("quantity") or 0)

    sale = Sale(
        product_name=product_name,
        customer_name=(data.get("customer") or "").strip(),
        quantity_tons=qty,
        amount=float(data.get("amount") or 0),
        sale_date=date.today(),
    )
    db.session.add(sale)

    # reduce stock
    product = Product.query.filter(db.func.lower(Product.name) == product_name.lower()).first()
    if product:
        product.stock_tons = max(0, (product.stock_tons or 0) - qty)

    db.session.commit()
    return jsonify({"ok": True, "sale": sale.to_dict()})


# ── First-run database setup with sample data ─────────────────────────
def seed_if_empty():
    """Create tables and add a few sample rows the first time only."""
    db.create_all()
    if Product.query.count() == 0:
        samples = [
            Product(name="Tata Tiscon (TMT Fe-500)", stock_tons=84, reorder_level=50, rate_per_ton=56000),
            Product(name="Tata Shaktee (Sheets)", stock_tons=31, reorder_level=40, rate_per_ton=68000),
            Product(name="Tata Pravesh (Doors)", stock_tons=18, reorder_level=15, rate_per_ton=82000),
            Product(name="Tiscon Superlinks", stock_tons=12, reorder_level=20, rate_per_ton=61000),
            Product(name="Tiscon Footings", stock_tons=9, reorder_level=15, rate_per_ton=63000),
            Product(name="Fosroc Products", stock_tons=22, reorder_level=10, rate_per_ton=45000),
        ]
        customers = [
            Customer(name="Ramesh Construction", city="Malda", amount_due=185000, days_overdue=45),
            Customer(name="Bengal Infra Pvt Ltd", city="Kolkata", amount_due=0, days_overdue=0),
            Customer(name="Suresh Steel Works", city="Malda", amount_due=92000, days_overdue=12),
            Customer(name="North Bengal Builders", city="Siliguri", amount_due=340000, days_overdue=62),
            Customer(name="Mondal & Sons", city="Englishbazar", amount_due=0, days_overdue=0),
        ]
        db.session.add_all(samples + customers)
        db.session.commit()
        print("Database seeded with sample data.")


with app.app_context():
    seed_if_empty()


if __name__ == "__main__":
    # Local testing only. In the cloud, gunicorn runs the app (see render.yaml).
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
