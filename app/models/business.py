from sqlalchemy import Column, BigInteger, String, Numeric, Boolean, DateTime, Text, ForeignKey, JSON
from sqlalchemy.sql import func
from app.database import Base


class Business(Base):
    __tablename__ = "businesses"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(256), nullable=False)
    description = Column(Text, nullable=True)
    business_type = Column(String(64), default="saas")  # saas | agency | ecommerce | consulting | other
    status = Column(String(32), default="active")        # active | paused | closed
    website = Column(String(512), nullable=True)
    mrr = Column(Numeric(18, 2), default=0)
    arr = Column(Numeric(18, 2), default=0)
    total_revenue_mtd = Column(Numeric(18, 2), default=0)
    total_revenue_ytd = Column(Numeric(18, 2), default=0)
    customer_count = Column(BigInteger, default=0)
    extra_data = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class Customer(Base):
    __tablename__ = "customers"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    business_id = Column(BigInteger, ForeignKey("businesses.id"), nullable=True, index=True)
    name = Column(String(256), nullable=False)
    email = Column(String(256), nullable=True)
    phone = Column(String(64), nullable=True)
    company = Column(String(256), nullable=True)
    status = Column(String(32), default="active")  # active | churned | prospect | paused
    lifetime_value = Column(Numeric(18, 2), default=0)
    monthly_value = Column(Numeric(18, 2), default=0)
    notes = Column(Text, nullable=True)
    tags = Column(JSON, default=list)
    extra_data = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class Project(Base):
    __tablename__ = "projects"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    business_id = Column(BigInteger, ForeignKey("businesses.id"), nullable=True, index=True)
    customer_id = Column(BigInteger, ForeignKey("customers.id"), nullable=True, index=True)
    name = Column(String(256), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(32), default="active")  # active | completed | paused | cancelled
    priority = Column(BigInteger, default=5)
    budget = Column(Numeric(18, 2), nullable=True)
    revenue = Column(Numeric(18, 2), default=0)
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=True)
    tags = Column(JSON, default=list)
    extra_data = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    customer_id = Column(BigInteger, ForeignKey("customers.id"), nullable=True, index=True)
    project_id = Column(BigInteger, ForeignKey("projects.id"), nullable=True, index=True)
    invoice_number = Column(String(64), nullable=True)
    status = Column(String(32), default="draft")  # draft | sent | paid | overdue | cancelled
    amount = Column(Numeric(18, 2), nullable=False)
    tax_amount = Column(Numeric(18, 2), default=0)
    currency = Column(String(8), default="USD")
    line_items = Column(JSON, default=list)   # [{desc, qty, rate, total}]
    notes = Column(Text, nullable=True)
    issue_date = Column(DateTime(timezone=True), nullable=True)
    due_date = Column(DateTime(timezone=True), nullable=True)
    paid_date = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
