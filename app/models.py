from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey, Boolean, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from .database import Base


class ServerType(str, enum.Enum):
    WEB = "web"
    DATABASE = "database"
    APPLICATION = "application"
    STORAGE = "storage"
    OTHER = "other"


class AlertLevel(str, enum.Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    FATAL = "fatal"


class AlertStatus(str, enum.Enum):
    PENDING = "pending"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


class ApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class OrderStatus(str, enum.Enum):
    DRAFT = "draft"
    ISSUED = "issued"
    IN_PROGRESS = "in_progress"
    DELIVERED = "delivered"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class VerificationStatus(str, enum.Enum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class ResourceType(str, enum.Enum):
    CPU = "cpu"
    MEMORY = "memory"
    DISK = "disk"
    NETWORK = "network"


class Server(Base):
    __tablename__ = "servers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True, nullable=False)
    type = Column(String(50), nullable=False)
    ip = Column(String(50))
    description = Column(String(500))
    cpu_cores = Column(Integer, default=4)
    memory_gb = Column(Float, default=8)
    disk_gb = Column(Float, default=100)
    network_mbps = Column(Integer, default=1000)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    metrics = relationship("ResourceMetric", back_populates="server")
    baselines = relationship("Baseline", back_populates="server")
    predictions = relationship("Prediction", back_populates="server")
    alerts = relationship("Alert", back_populates="server")


class ResourceMetric(Base):
    __tablename__ = "resource_metrics"

    id = Column(Integer, primary_key=True, index=True)
    server_id = Column(Integer, ForeignKey("servers.id"), nullable=False)
    timestamp = Column(DateTime, index=True, nullable=False)
    cpu_usage = Column(Float, nullable=False)
    memory_usage = Column(Float, nullable=False)
    disk_usage = Column(Float, nullable=False)
    network_usage = Column(Float, nullable=False)

    server = relationship("Server", back_populates="metrics")


class Baseline(Base):
    __tablename__ = "baselines"

    id = Column(Integer, primary_key=True, index=True)
    server_id = Column(Integer, ForeignKey("servers.id"), nullable=False)
    resource_type = Column(String(20), nullable=False)
    baseline_value = Column(Float, nullable=False)
    peak_value = Column(Float, nullable=False)
    percentile_95 = Column(Float, nullable=False)
    percentile_99 = Column(Float, nullable=False)
    std_dev = Column(Float, nullable=False)
    calculated_at = Column(DateTime, default=datetime.now)
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)

    server = relationship("Server", back_populates="baselines")


class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, index=True)
    server_id = Column(Integer, ForeignKey("servers.id"), nullable=False)
    resource_type = Column(String(20), nullable=False)
    forecast_date = Column(DateTime, nullable=False)
    predicted_value = Column(Float, nullable=False)
    upper_bound = Column(Float, nullable=False)
    lower_bound = Column(Float, nullable=False)
    confidence = Column(Float, default=0.95)
    created_at = Column(DateTime, default=datetime.now)

    server = relationship("Server", back_populates="predictions")


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    server_id = Column(Integer, ForeignKey("servers.id"), nullable=False)
    resource_type = Column(String(20), nullable=False)
    alert_level = Column(String(20), nullable=False)
    alert_type = Column(String(50), nullable=False)
    title = Column(String(200), nullable=False)
    message = Column(Text)
    current_value = Column(Float, nullable=False)
    threshold_value = Column(Float, nullable=False)
    status = Column(String(20), default="pending")
    acknowledged_by = Column(String(100))
    acknowledged_at = Column(DateTime)
    resolved_at = Column(DateTime)
    escalated_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    server = relationship("Server", back_populates="alerts")
    expansion_plan = relationship("ExpansionPlan", back_populates="alert", uselist=False)


class ExpansionPlan(Base):
    __tablename__ = "expansion_plans"

    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=False)
    server_id = Column(Integer, ForeignKey("servers.id"), nullable=False)
    resource_type = Column(String(20), nullable=False)
    plan_title = Column(String(200), nullable=False)
    current_spec = Column(String(500))
    recommended_spec = Column(String(500))
    quantity = Column(Integer, default=1)
    estimated_cost = Column(Float, nullable=False)
    cost_currency = Column(String(10), default="CNY")
    delivery_days = Column(Integer, default=7)
    justification = Column(Text)
    status = Column(String(20), default="pending")
    created_by = Column(String(100))
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    alert = relationship("Alert", back_populates="expansion_plan")
    approvals = relationship("Approval", back_populates="expansion_plan", order_by="Approval.created_at")
    purchase_orders = relationship("PurchaseOrder", back_populates="expansion_plan")
    verification = relationship("Verification", back_populates="expansion_plan", uselist=False)


class Approval(Base):
    __tablename__ = "approvals"

    id = Column(Integer, primary_key=True, index=True)
    expansion_plan_id = Column(Integer, ForeignKey("expansion_plans.id"), nullable=False)
    approver = Column(String(100), nullable=False)
    status = Column(String(20), default="pending")
    comments = Column(Text)
    approved_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.now)

    expansion_plan = relationship("ExpansionPlan", back_populates="approvals")


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id = Column(Integer, primary_key=True, index=True)
    order_no = Column(String(50), unique=True, index=True, nullable=False)
    expansion_plan_id = Column(Integer, ForeignKey("expansion_plans.id"), nullable=False)
    supplier = Column(String(200), nullable=False)
    total_amount = Column(Float, nullable=False)
    currency = Column(String(10), default="CNY")
    delivery_deadline = Column(DateTime, nullable=False)
    status = Column(String(20), default="draft")
    issued_by = Column(String(100))
    issued_at = Column(DateTime)
    delivered_at = Column(DateTime)
    completed_at = Column(DateTime)
    remarks = Column(Text)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    expansion_plan = relationship("ExpansionPlan", back_populates="purchase_orders")


class Verification(Base):
    __tablename__ = "verifications"

    id = Column(Integer, primary_key=True, index=True)
    expansion_plan_id = Column(Integer, ForeignKey("expansion_plans.id"), nullable=False)
    status = Column(String(20), default="pending")
    expected_performance = Column(String(500))
    actual_performance = Column(String(500))
    cpu_before = Column(Float)
    cpu_after = Column(Float)
    memory_before = Column(Float)
    memory_after = Column(Float)
    disk_before = Column(Float)
    disk_after = Column(Float)
    network_before = Column(Float)
    network_after = Column(Float)
    is_rolled_back = Column(Boolean, default=False)
    rollback_reason = Column(Text)
    verification_report = Column(Text)
    verified_by = Column(String(100))
    verified_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.now)

    expansion_plan = relationship("ExpansionPlan", back_populates="verification")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.now, index=True)
    module = Column(String(50), nullable=False)
    action = Column(String(50), nullable=False)
    resource_type = Column(String(50))
    resource_id = Column(Integer)
    operator = Column(String(100))
    details = Column(Text)
    ip_address = Column(String(50))
    result = Column(String(20), default="success")


class HealthReport(Base):
    __tablename__ = "health_reports"

    id = Column(Integer, primary_key=True, index=True)
    report_date = Column(DateTime, index=True, nullable=False)
    report_type = Column(String(20), default="daily")
    total_servers = Column(Integer, default=0)
    alert_count = Column(Integer, default=0)
    warning_count = Column(Integer, default=0)
    critical_count = Column(Integer, default=0)
    expansion_count = Column(Integer, default=0)
    expansion_completed_count = Column(Integer, default=0)
    expansion_completion_rate = Column(Float, default=0.0)
    avg_cpu_usage = Column(Float, default=0.0)
    avg_memory_usage = Column(Float, default=0.0)
    avg_disk_usage = Column(Float, default=0.0)
    avg_network_usage = Column(Float, default=0.0)
    summary = Column(Text)
    pdf_path = Column(String(500))
    excel_path = Column(String(500))
    created_at = Column(DateTime, default=datetime.now)
