import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from .database import get_db, config
from .models import (
    Server, Alert, ExpansionPlan, Approval, PurchaseOrder,
    ApprovalStatus, OrderStatus, ResourceType
)
from . import audit_logger, notifier


class ExpansionPlanner:
    def __init__(self, db: Session = None):
        self.db = db or next(get_db())

    PRICING_CATALOG = {
        'cpu': {
            'small': {'spec': '2核', 'cost': 500, 'unit': '核'},
            'medium': {'spec': '4核', 'cost': 1000, 'unit': '核'},
            'large': {'spec': '8核', 'cost': 2000, 'unit': '核'},
            'xlarge': {'spec': '16核', 'cost': 4000, 'unit': '核'},
        },
        'memory': {
            'small': {'spec': '8GB', 'cost': 400, 'unit': 'GB'},
            'medium': {'spec': '16GB', 'cost': 800, 'unit': 'GB'},
            'large': {'spec': '32GB', 'cost': 1600, 'unit': 'GB'},
            'xlarge': {'spec': '64GB', 'cost': 3200, 'unit': 'GB'},
        },
        'disk': {
            'small': {'spec': '500GB SSD', 'cost': 600, 'unit': 'GB'},
            'medium': {'spec': '1TB SSD', 'cost': 1200, 'unit': 'GB'},
            'large': {'spec': '2TB SSD', 'cost': 2400, 'unit': 'GB'},
            'xlarge': {'spec': '4TB SSD', 'cost': 4800, 'unit': 'GB'},
        },
        'network': {
            'small': {'spec': '100Mbps', 'cost': 300, 'unit': 'Mbps'},
            'medium': {'spec': '1Gbps', 'cost': 1000, 'unit': 'Mbps'},
            'large': {'spec': '10Gbps', 'cost': 5000, 'unit': 'Mbps'},
            'xlarge': {'spec': '25Gbps', 'cost': 12000, 'unit': 'Mbps'},
        }
    }

    SPEC_MAP = {
        'cpu': ['small', 'medium', 'large', 'xlarge'],
        'memory': ['small', 'medium', 'large', 'xlarge'],
        'disk': ['small', 'medium', 'large', 'xlarge'],
        'network': ['small', 'medium', 'large', 'xlarge']
    }

    def generate_plan_from_alert(self, alert_id: int) -> Optional[ExpansionPlan]:
        alert = self.db.query(Alert).filter(Alert.id == alert_id).first()
        if not alert:
            return None

        existing_plan = self.db.query(ExpansionPlan).filter(
            ExpansionPlan.alert_id == alert_id
        ).first()
        if existing_plan:
            return existing_plan

        server = self.db.query(Server).filter(Server.id == alert.server_id).first()
        if not server:
            return None

        resource_type = alert.resource_type
        current_value = alert.current_value
        target_usage = 60.0

        expansion_ratio = current_value / target_usage

        plan_data = self._calculate_expansion(server, resource_type, expansion_ratio)

        plan = ExpansionPlan(
            alert_id=alert_id,
            server_id=server.id,
            resource_type=resource_type,
            plan_title=f"{server.name} {resource_type}扩容方案",
            current_spec=plan_data['current_spec'],
            recommended_spec=plan_data['recommended_spec'],
            quantity=plan_data['quantity'],
            estimated_cost=plan_data['estimated_cost'],
            cost_currency="CNY",
            delivery_days=config['expansion']['delivery_days'],
            justification=self._build_justification(server, alert, plan_data),
            status=ApprovalStatus.PENDING.value,
            created_by="system"
        )

        self.db.add(plan)
        self.db.commit()
        self.db.refresh(plan)

        audit_logger.log_audit(
            self.db,
            module="expansion",
            action="generate_plan",
            resource_type="expansion_plan",
            resource_id=plan.id,
            operator="system",
            details=f"已生成扩容方案: {plan.plan_title}，预估费用: {plan.estimated_cost} CNY"
        )

        notifier.send_expansion_notification(plan)

        return plan

    def _calculate_expansion(self, server: Server, resource_type: str, expansion_ratio: float) -> Dict:
        current_specs = {
            'cpu': {'value': server.cpu_cores, 'unit': '核'},
            'memory': {'value': server.memory_gb, 'unit': 'GB'},
            'disk': {'value': server.disk_gb, 'unit': 'GB'},
            'network': {'value': server.network_mbps, 'unit': 'Mbps'}
        }

        current = current_specs[resource_type]
        current_value = current['value']
        target_value = current_value * expansion_ratio

        catalog = self.PRICING_CATALOG[resource_type]
        spec_levels = self.SPEC_MAP[resource_type]

        recommended_level = spec_levels[0]
        for level in spec_levels:
            spec_info = catalog[level]
            if self._spec_value(resource_type, level) >= target_value:
                recommended_level = level
                break
        else:
            recommended_level = spec_levels[-1]

        rec_spec = catalog[recommended_level]
        rec_value = self._spec_value(resource_type, recommended_level)
        quantity = max(1, int(target_value / rec_value))

        if quantity * rec_value < target_value:
            quantity += 1

        estimated_cost = rec_spec['cost'] * quantity

        return {
            'current_spec': f"{current_value}{current['unit']}",
            'recommended_spec': rec_spec['spec'],
            'quantity': quantity,
            'estimated_cost': estimated_cost,
            'target_value': target_value
        }

    def _spec_value(self, resource_type: str, level: str) -> float:
        values = {
            'cpu': {'small': 2, 'medium': 4, 'large': 8, 'xlarge': 16},
            'memory': {'small': 8, 'medium': 16, 'large': 32, 'xlarge': 64},
            'disk': {'small': 500, 'medium': 1000, 'large': 2000, 'xlarge': 4000},
            'network': {'small': 100, 'medium': 1000, 'large': 10000, 'xlarge': 25000}
        }
        return values[resource_type][level]

    def _build_justification(self, server: Server, alert: Alert, plan_data: Dict) -> str:
        resource_names = {
            'cpu': 'CPU',
            'memory': '内存',
            'disk': '磁盘',
            'network': '网络带宽'
        }
        return (
            f"根据未来7天{resource_names[alert.resource_type]}使用率预测峰值为 {alert.current_value}%，"
            f"超过{alert.threshold_value}%预警阈值。\n"
            f"当前配置: {plan_data['current_spec']}\n"
            f"建议扩容至: {plan_data['recommended_spec']} x {plan_data['quantity']}\n"
            f"扩容后预期使用率控制在60%左右，预留充足冗余以应对业务增长。"
        )

    def get_plans(self, server_id: int = None, status: str = None,
                  start_time: datetime = None, end_time: datetime = None) -> List[ExpansionPlan]:
        query = self.db.query(ExpansionPlan)
        if server_id:
            query = query.filter(ExpansionPlan.server_id == server_id)
        if status:
            query = query.filter(ExpansionPlan.status == status)
        if start_time:
            query = query.filter(ExpansionPlan.created_at >= start_time)
        if end_time:
            query = query.filter(ExpansionPlan.created_at <= end_time)
        return query.order_by(ExpansionPlan.created_at.desc()).all()

    def get_plan(self, plan_id: int) -> Optional[ExpansionPlan]:
        return self.db.query(ExpansionPlan).filter(ExpansionPlan.id == plan_id).first()


class ApprovalManager:
    def __init__(self, db: Session = None):
        self.db = db or next(get_db())

    def approve_plan(self, plan_id: int, approver: str, comments: str = "") -> Optional[ExpansionPlan]:
        plan = self.db.query(ExpansionPlan).filter(ExpansionPlan.id == plan_id).first()
        if not plan:
            return None

        plan.status = ApprovalStatus.APPROVED.value
        plan.updated_at = datetime.now()

        approval = Approval(
            expansion_plan_id=plan_id,
            approver=approver,
            status=ApprovalStatus.APPROVED.value,
            comments=comments,
            approved_at=datetime.now()
        )
        self.db.add(approval)
        self.db.commit()
        self.db.refresh(plan)

        audit_logger.log_audit(
            self.db,
            module="approval",
            action="approve",
            resource_type="expansion_plan",
            resource_id=plan_id,
            operator=approver,
            details=f"审批通过扩容方案: {plan.plan_title}"
        )

        notifier.send_approval_notification(plan, approval)

        self._create_purchase_order(plan)

        return plan

    def reject_plan(self, plan_id: int, approver: str, comments: str = "") -> Optional[ExpansionPlan]:
        plan = self.db.query(ExpansionPlan).filter(ExpansionPlan.id == plan_id).first()
        if not plan:
            return None

        plan.status = ApprovalStatus.REJECTED.value
        plan.updated_at = datetime.now()

        approval = Approval(
            expansion_plan_id=plan_id,
            approver=approver,
            status=ApprovalStatus.REJECTED.value,
            comments=comments,
            approved_at=datetime.now()
        )
        self.db.add(approval)
        self.db.commit()
        self.db.refresh(plan)

        audit_logger.log_audit(
            self.db,
            module="approval",
            action="reject",
            resource_type="expansion_plan",
            resource_id=plan_id,
            operator=approver,
            details=f"拒绝扩容方案: {plan.plan_title}"
        )

        notifier.send_approval_notification(plan, approval)

        return plan

    def _create_purchase_order(self, plan: ExpansionPlan) -> PurchaseOrder:
        order_no = f"PO{datetime.now().strftime('%Y%m%d')}{uuid.uuid4().hex[:6].upper()}"

        order = PurchaseOrder(
            order_no=order_no,
            expansion_plan_id=plan.id,
            supplier=config['expansion']['default_supplier'],
            total_amount=plan.estimated_cost,
            currency=plan.cost_currency,
            delivery_deadline=datetime.now() + timedelta(days=plan.delivery_days),
            status=OrderStatus.ISSUED.value,
            issued_by="system",
            issued_at=datetime.now(),
            remarks=f"扩容工单: {plan.plan_title}"
        )

        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)

        audit_logger.log_audit(
            self.db,
            module="purchase_order",
            action="create",
            resource_type="purchase_order",
            resource_id=order.id,
            operator="system",
            details=f"已创建采购订单: {order.order_no}，金额: {order.total_amount} {order.currency}"
        )

        return order

    def get_approvals(self, plan_id: int) -> List[Approval]:
        return self.db.query(Approval).filter(
            Approval.expansion_plan_id == plan_id
        ).order_by(Approval.created_at.desc()).all()


class PurchaseOrderManager:
    def __init__(self, db: Session = None):
        self.db = db or next(get_db())

    def update_order_status(self, order_id: int, status: str, operator: str, remarks: str = "") -> Optional[PurchaseOrder]:
        order = self.db.query(PurchaseOrder).filter(PurchaseOrder.id == order_id).first()
        if not order:
            return None

        order.status = status
        order.updated_at = datetime.now()

        if status == OrderStatus.DELIVERED.value:
            order.delivered_at = datetime.now()
        elif status == OrderStatus.COMPLETED.value:
            order.completed_at = datetime.now()

        if remarks:
            order.remarks = (order.remarks or "") + f"\n{remarks}"

        self.db.commit()
        self.db.refresh(order)

        audit_logger.log_audit(
            self.db,
            module="purchase_order",
            action="update_status",
            resource_type="purchase_order",
            resource_id=order_id,
            operator=operator,
            details=f"更新订单 {order.order_no} 状态为: {status}"
        )

        return order

    def get_orders(self, plan_id: int = None, status: str = None,
                   start_time: datetime = None, end_time: datetime = None) -> List[PurchaseOrder]:
        query = self.db.query(PurchaseOrder)
        if plan_id:
            query = query.filter(PurchaseOrder.expansion_plan_id == plan_id)
        if status:
            query = query.filter(PurchaseOrder.status == status)
        if start_time:
            query = query.filter(PurchaseOrder.created_at >= start_time)
        if end_time:
            query = query.filter(PurchaseOrder.created_at <= end_time)
        return query.order_by(PurchaseOrder.created_at.desc()).all()

    def get_order(self, order_id: int) -> Optional[PurchaseOrder]:
        return self.db.query(PurchaseOrder).filter(PurchaseOrder.id == order_id).first()
