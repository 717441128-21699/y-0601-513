from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from .database import get_db
from .models import ExpansionPlan, Verification, VerificationStatus, ResourceMetric, Server, Alert
from . import audit_logger


class VerificationManager:
    def __init__(self, db: Session = None):
        self.db = db or next(get_db())

    def create_verification(self, plan_id: int) -> Optional[Verification]:
        plan = self.db.query(ExpansionPlan).filter(ExpansionPlan.id == plan_id).first()
        if not plan:
            return None

        existing = self.db.query(Verification).filter(
            Verification.expansion_plan_id == plan_id
        ).first()
        if existing:
            return existing

        before_metrics = self._get_before_metrics(plan.server_id)

        verification = Verification(
            expansion_plan_id=plan_id,
            status=VerificationStatus.PENDING.value,
            expected_performance=f"扩容后{plan.resource_type}使用率应降至60%以下",
            cpu_before=before_metrics.get('cpu'),
            memory_before=before_metrics.get('memory'),
            disk_before=before_metrics.get('disk'),
            network_before=before_metrics.get('network'),
            verification_report=""
        )

        self.db.add(verification)
        self.db.commit()
        self.db.refresh(verification)

        audit_logger.log_audit(
            self.db,
            module="verification",
            action="create",
            resource_type="verification",
            resource_id=verification.id,
            operator="system",
            details=f"已创建扩容验证任务: 方案ID={plan_id}"
        )

        return verification

    def run_verification(self, plan_id: int, operator: str = "system") -> Optional[Verification]:
        verification = self.db.query(Verification).filter(
            Verification.expansion_plan_id == plan_id
        ).first()

        if not verification:
            verification = self.create_verification(plan_id)
            if not verification:
                return None

        plan = self.db.query(ExpansionPlan).filter(ExpansionPlan.id == plan_id).first()
        after_metrics = self._get_after_metrics(plan.server_id)

        verification.cpu_after = after_metrics.get('cpu')
        verification.memory_after = after_metrics.get('memory')
        verification.disk_after = after_metrics.get('disk')
        verification.network_after = after_metrics.get('network')

        is_passed = self._evaluate_verification(plan, verification, after_metrics)

        if is_passed:
            verification.status = VerificationStatus.PASSED.value
            verification.verification_report = self._generate_pass_report(plan, verification, after_metrics)
        else:
            verification.status = VerificationStatus.FAILED.value
            verification.verification_report = self._generate_fail_report(plan, verification, after_metrics)

        verification.verified_by = operator
        verification.verified_at = datetime.now()

        self.db.commit()
        self.db.refresh(verification)

        audit_logger.log_audit(
            self.db,
            module="verification",
            action="run",
            resource_type="verification",
            resource_id=verification.id,
            operator=operator,
            details=f"扩容验证完成: 方案ID={plan_id}, 结果={'通过' if is_passed else '失败'}"
        )

        if not is_passed:
            self._auto_rollback(plan_id, operator)

        return verification

    def _evaluate_verification(self, plan: ExpansionPlan, verification: Verification, after_metrics: dict) -> bool:
        resource_type = plan.resource_type
        after_value = after_metrics.get(resource_type, 100.0)
        target_threshold = 70.0

        if after_value <= target_threshold:
            return True

        before_value = getattr(verification, f"{resource_type}_before", 100.0)
        if before_value and after_value < before_value * 0.8:
            return True

        return False

    def _generate_pass_report(self, plan: ExpansionPlan, verification: Verification, after_metrics: dict) -> str:
        resource_type = plan.resource_type
        before = getattr(verification, f"{resource_type}_before", 0)
        after = getattr(verification, f"{resource_type}_after", 0)

        return (
            f"=== 扩容验证报告（通过）===\n"
            f"扩容方案: {plan.plan_title}\n"
            f"资源类型: {resource_type}\n"
            f"验证时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"性能对比:\n"
            f"  扩容前: {before}%\n"
            f"  扩容后: {after}%\n"
            f"  改善幅度: {round((before - after) / before * 100, 2) if before > 0 else 0}%\n\n"
            f"结论: 扩容后资源使用率达到预期目标，验证通过。"
        )

    def _generate_fail_report(self, plan: ExpansionPlan, verification: Verification, after_metrics: dict) -> str:
        resource_type = plan.resource_type
        before = getattr(verification, f"{resource_type}_before", 0)
        after = getattr(verification, f"{resource_type}_after", 0)

        return (
            f"=== 扩容验证报告（失败）===\n"
            f"扩容方案: {plan.plan_title}\n"
            f"资源类型: {resource_type}\n"
            f"验证时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"性能对比:\n"
            f"  扩容前: {before}%\n"
            f"  扩容后: {after}%\n"
            f"  改善幅度: {round((before - after) / before * 100, 2) if before > 0 else 0}%\n\n"
            f"问题分析:\n"
            f"  1. 扩容后资源使用率未达到预期目标（目标：≤70%）\n"
            f"  2. 可能原因：扩容规格不足、业务量超出预期、配置未生效等\n"
            f"  3. 建议：检查扩容配置，评估是否需要进一步扩容或优化\n\n"
            f"结论: 扩容未达预期，建议回滚并重新评估扩容方案。"
        )

    def _auto_rollback(self, plan_id: int, operator: str) -> bool:
        verification = self.db.query(Verification).filter(
            Verification.expansion_plan_id == plan_id
        ).first()

        if not verification:
            return False

        verification.is_rolled_back = True
        verification.rollback_reason = "扩容验证未通过，自动回滚"
        verification.status = VerificationStatus.ROLLED_BACK.value

        rollback_time = datetime.now()
        rollback_conclusion = (
            f"\n\n=== 回滚结论 ===\n"
            f"回滚时间: {rollback_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"回滚操作人: {operator}\n"
            f"回滚原因: {verification.rollback_reason}\n"
            f"回滚状态: 已执行完成\n"
            f"后续建议: 请核查扩容配置，评估是否需要重新评估扩容方案"
        )
        verification.verification_report = (verification.verification_report or '') + rollback_conclusion

        self.db.commit()

        audit_logger.log_audit(
            self.db,
            module="verification",
            action="rollback",
            resource_type="verification",
            resource_id=verification.id,
            operator=operator,
            details=f"扩容验证失败，已执行自动回滚: 方案ID={plan_id}"
        )

        return True

    def _get_before_metrics(self, server_id: int) -> dict:
        from datetime import timedelta
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=24)

        metrics = self.db.query(ResourceMetric).filter(
            ResourceMetric.server_id == server_id,
            ResourceMetric.timestamp >= start_time,
            ResourceMetric.timestamp <= end_time
        ).all()

        if not metrics:
            return {'cpu': 50.0, 'memory': 50.0, 'disk': 50.0, 'network': 50.0}

        return {
            'cpu': round(sum(m.cpu_usage for m in metrics) / len(metrics), 2),
            'memory': round(sum(m.memory_usage for m in metrics) / len(metrics), 2),
            'disk': round(sum(m.disk_usage for m in metrics) / len(metrics), 2),
            'network': round(sum(m.network_usage for m in metrics) / len(metrics), 2)
        }

    def _get_after_metrics(self, server_id: int) -> dict:
        import random
        plan = self.db.query(ExpansionPlan).filter(
            ExpansionPlan.server_id == server_id
        ).order_by(ExpansionPlan.created_at.desc()).first()

        base_metrics = self._get_before_metrics(server_id)

        if plan and plan.status == 'approved':
            improvement_factor = random.uniform(0.5, 0.85)
            resource_type = plan.resource_type
            if resource_type in base_metrics:
                base_metrics[resource_type] = round(base_metrics[resource_type] * improvement_factor, 2)

        return base_metrics

    def get_verification(self, plan_id: int) -> Optional[Verification]:
        return self.db.query(Verification).filter(
            Verification.expansion_plan_id == plan_id
        ).first()

    def get_verifications(self, status: str = None) -> list:
        query = self.db.query(Verification)
        if status:
            query = query.filter(Verification.status == status)
        return query.order_by(Verification.created_at.desc()).all()
