from sqlalchemy import Column, BigInteger, String, Numeric, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class HealthMetric(Base):
    __tablename__ = "health_metrics"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    metric_type = Column(String(64), nullable=False, index=True)
    # metric_type: weight | sleep_hours | steps | heart_rate | calories |
    #              water_oz | workout_minutes | body_fat | blood_pressure_sys |
    #              blood_pressure_dia | stress | energy
    value = Column(Numeric(12, 4), nullable=False)
    unit = Column(String(32), nullable=True)
    notes = Column(String(512), nullable=True)
    recorded_at = Column(DateTime(timezone=True), nullable=False, index=True,
                         server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
