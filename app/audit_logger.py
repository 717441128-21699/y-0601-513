from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session
from .models import AuditLog
from .database import get_db


def log_audit(db: Session, module: str, action: str, resource_type: str = None,
              resource_id: int = None, operator: str = None, details: str = None,
              ip_address: str = None, result: str = "success") -> AuditLog:
    log = AuditLog(
        timestamp=datetime.now(),
        module=module,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        operator=operator,
        details=details,
        ip_address=ip_address,
        result=result
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def get_audit_logs(db: Session = None, module: str = None, action: str = None,
                   operator: str = None, start_time: datetime = None,
                   end_time: datetime = None, limit: int = 100) -> List[AuditLog]:
    if db is None:
        db = next(get_db())

    query = db.query(AuditLog)

    if module:
        query = query.filter(AuditLog.module == module)
    if action:
        query = query.filter(AuditLog.action == action)
    if operator:
        query = query.filter(AuditLog.operator == operator)
    if start_time:
        query = query.filter(AuditLog.timestamp >= start_time)
    if end_time:
        query = query.filter(AuditLog.timestamp <= end_time)

    return query.order_by(AuditLog.timestamp.desc()).limit(limit).all()


def get_recent_logs(module: str = None, limit: int = 50) -> List[AuditLog]:
    db = next(get_db())
    return get_audit_logs(db, module=module, limit=limit)
