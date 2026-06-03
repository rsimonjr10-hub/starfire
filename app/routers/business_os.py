"""
Business OS API — businesses, customers, projects, invoices.
Auth: HMAC dashboard token.
"""
import hashlib
import hmac
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.business import Business, Customer, Project, Invoice

router = APIRouter(prefix="/api/business", tags=["business"])


def _make_token(tid: int) -> str:
    return hmac.new(settings.app_secret_key.encode(), str(tid).encode(),
                    hashlib.sha256).hexdigest()[:32]

async def _get_user(token: str = Query(...)) -> User:
    async with AsyncSessionLocal() as session:
        for u in (await session.execute(select(User).where(User.is_active == True))).scalars().all():
            if hmac.compare_digest(_make_token(u.telegram_id), token):
                return u
    raise HTTPException(status_code=403, detail="Invalid token")


# ── Schemas ────────────────────────────────────────────────────────────────
class BusinessCreate(BaseModel):
    name: str
    description: Optional[str] = None
    business_type: str = "saas"
    website: Optional[str] = None
    mrr: float = 0
    arr: float = 0

class BusinessUpdate(BaseModel):
    name: Optional[str] = None
    mrr: Optional[float] = None
    arr: Optional[float] = None
    status: Optional[str] = None
    description: Optional[str] = None

class CustomerCreate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    monthly_value: float = 0
    business_id: Optional[int] = None

class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    customer_id: Optional[int] = None
    business_id: Optional[int] = None
    budget: Optional[float] = None

class InvoiceCreate(BaseModel):
    customer_id: Optional[int] = None
    project_id: Optional[int] = None
    amount: float
    currency: str = "USD"
    line_items: list[dict] = []
    notes: Optional[str] = None
    due_date: Optional[str] = None


# ── Business endpoints ─────────────────────────────────────────────────────
@router.get("/overview")
async def business_overview(user: User = Depends(_get_user)):
    async with AsyncSessionLocal() as session:
        businesses = (await session.execute(
            select(Business).where(Business.user_id == user.id)
        )).scalars().all()
        total_mrr = sum(float(b.mrr or 0) for b in businesses)
        total_arr = sum(float(b.arr or 0) for b in businesses)

        customer_count = (await session.execute(
            select(sqlfunc.count()).where(
                Customer.user_id == user.id, Customer.status == "active"
            )
        )).scalar()

        outstanding = (await session.execute(
            select(sqlfunc.sum(Invoice.amount)).where(
                Invoice.user_id == user.id, Invoice.status.in_(["sent", "overdue"])
            )
        )).scalar()

        open_projects = (await session.execute(
            select(sqlfunc.count()).where(
                Project.user_id == user.id, Project.status == "active"
            )
        )).scalar()

    return {
        "total_mrr": total_mrr,
        "total_arr": total_arr,
        "active_customers": customer_count or 0,
        "outstanding_invoices": float(outstanding or 0),
        "open_projects": open_projects or 0,
        "businesses": [_biz(b) for b in businesses],
    }

@router.get("/businesses")
async def list_businesses(user: User = Depends(_get_user)):
    async with AsyncSessionLocal() as session:
        items = (await session.execute(
            select(Business).where(Business.user_id == user.id)
        )).scalars().all()
    return [_biz(b) for b in items]

@router.post("/businesses")
async def create_business(body: BusinessCreate, user: User = Depends(_get_user)):
    async with AsyncSessionLocal() as session:
        b = Business(user_id=user.id, **body.model_dump())
        session.add(b)
        await session.commit()
        await session.refresh(b)
    return _biz(b)

@router.put("/businesses/{bid}")
async def update_business(bid: int, body: BusinessUpdate, user: User = Depends(_get_user)):
    async with AsyncSessionLocal() as session:
        b = await _get_obj(session, Business, bid, user.id)
        for k, v in body.model_dump(exclude_none=True).items():
            setattr(b, k, v)
        await session.commit()
    return {"ok": True}


# ── Customer endpoints ─────────────────────────────────────────────────────
@router.get("/customers")
async def list_customers(user: User = Depends(_get_user)):
    async with AsyncSessionLocal() as session:
        items = (await session.execute(
            select(Customer).where(Customer.user_id == user.id)
            .order_by(Customer.lifetime_value.desc())
        )).scalars().all()
    return [_cust(c) for c in items]

@router.post("/customers")
async def create_customer(body: CustomerCreate, user: User = Depends(_get_user)):
    async with AsyncSessionLocal() as session:
        c = Customer(user_id=user.id, **body.model_dump())
        session.add(c)
        await session.commit()
        await session.refresh(c)
    return _cust(c)


# ── Project endpoints ──────────────────────────────────────────────────────
@router.get("/projects")
async def list_projects(user: User = Depends(_get_user)):
    async with AsyncSessionLocal() as session:
        items = (await session.execute(
            select(Project).where(Project.user_id == user.id)
            .order_by(Project.created_at.desc())
        )).scalars().all()
    return [_proj(p) for p in items]

@router.post("/projects")
async def create_project(body: ProjectCreate, user: User = Depends(_get_user)):
    async with AsyncSessionLocal() as session:
        p = Project(user_id=user.id, **body.model_dump())
        session.add(p)
        await session.commit()
        await session.refresh(p)
    return _proj(p)

@router.put("/projects/{pid}")
async def update_project(pid: int, body: dict, user: User = Depends(_get_user)):
    async with AsyncSessionLocal() as session:
        p = await _get_obj(session, Project, pid, user.id)
        for k, v in body.items():
            if hasattr(p, k):
                setattr(p, k, v)
        await session.commit()
    return {"ok": True}


# ── Invoice endpoints ──────────────────────────────────────────────────────
@router.get("/invoices")
async def list_invoices(
    status: Optional[str] = Query(None),
    user: User = Depends(_get_user)
):
    async with AsyncSessionLocal() as session:
        q = select(Invoice).where(Invoice.user_id == user.id).order_by(Invoice.created_at.desc())
        if status:
            q = q.where(Invoice.status == status)
        items = (await session.execute(q)).scalars().all()
    return [_inv(i) for i in items]

@router.post("/invoices")
async def create_invoice(body: InvoiceCreate, user: User = Depends(_get_user)):
    async with AsyncSessionLocal() as session:
        data = body.model_dump()
        if data.get("due_date"):
            data["due_date"] = datetime.fromisoformat(data["due_date"])
        i = Invoice(user_id=user.id, **data)
        session.add(i)
        await session.commit()
        await session.refresh(i)
    return _inv(i)

@router.put("/invoices/{iid}/status")
async def update_invoice_status(iid: int, status: str, user: User = Depends(_get_user)):
    async with AsyncSessionLocal() as session:
        i = await _get_obj(session, Invoice, iid, user.id)
        i.status = status
        if status == "paid":
            i.paid_date = datetime.utcnow()
        await session.commit()
    return {"ok": True}


# ── Helpers ────────────────────────────────────────────────────────────────
async def _get_obj(session, model, obj_id: int, user_id: int):
    result = await session.execute(
        select(model).where(model.id == obj_id, model.user_id == user_id)
    )
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    return obj

def _biz(b): return {"id": b.id, "name": b.name, "type": b.business_type, "status": b.status,
                      "mrr": float(b.mrr or 0), "arr": float(b.arr or 0), "website": b.website,
                      "customer_count": b.customer_count}
def _cust(c): return {"id": c.id, "name": c.name, "email": c.email, "company": c.company,
                       "status": c.status, "monthly_value": float(c.monthly_value or 0),
                       "lifetime_value": float(c.lifetime_value or 0)}
def _proj(p): return {"id": p.id, "name": p.name, "status": p.status, "priority": p.priority,
                       "budget": float(p.budget or 0), "revenue": float(p.revenue or 0),
                       "tags": p.tags or []}
def _inv(i): return {"id": i.id, "amount": float(i.amount or 0), "status": i.status,
                      "currency": i.currency, "customer_id": i.customer_id,
                      "due_date": i.due_date.isoformat() if i.due_date else None,
                      "paid_date": i.paid_date.isoformat() if i.paid_date else None,
                      "line_items": i.line_items or []}
