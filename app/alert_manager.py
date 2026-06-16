from datetime import datetime, timedelta
from typing import List, Dict
from sqlalchemy.orm import Session
from .database import get_db, config
from .models import Server, Alert, AlertLevel, AlertStatus
from .predictor import ResourcePredictor
from . import audit_logger, notifier


class AlertManager:
    def __init__(self, db: Session = None):
        self.db = db or next(get_db())
        self.predictor = ResourcePredictor(self.db)
        self.warning_threshold = config['alert']['warning_threshold']
        self.critical_threshold = config['alert']['critical_threshold']
        self.fatal_threshold = config['alert']['fatal_threshold']

    def check_all_alerts(self) -> List[Alert]:
        servers = self.db.query(Server).filter(Server.is_active == True).all()
        all_alerts = []

        for server in servers:
            alerts = self.check_server_alerts(server)
            all_alerts.extend(alerts)

        audit_logger.log_audit(
            self.db,
            module="alert",
            action="check_all",
            resource_type="alert",
            operator="system",
            details=f"已检查 {len(servers)} 台服务器，生成 {len(all_alerts)} 条预警"
        )
        return all_alerts

    def check_server_alerts(self, server: Server) -> List[Alert]:
        resource_types = ['cpu', 'memory', 'disk', 'network']
        alerts = []

        for resource_type in resource_types:
            alert = self._check_resource_alert(server, resource_type)
            if alert:
                alerts.append(alert)

        return alerts

    def _check_resource_alert(self, server: Server, resource_type: str) -> Alert:
        prediction_peak = self.predictor.get_prediction_peak(server.id, resource_type)
        peak_value = prediction_peak['peak_value']

        if peak_value < self.warning_threshold:
            return None

        alert_level = self._determine_alert_level(peak_value)

        existing_alert = self._get_existing_active_alert(server.id, resource_type)
        if existing_alert:
            if existing_alert.alert_level != alert_level.value:
                existing_alert.alert_level = alert_level.value
                existing_alert.current_value = peak_value
                existing_alert.message = self._build_alert_message(server, resource_type, peak_value, alert_level)
                existing_alert.updated_at = datetime.now()
                self.db.commit()
                self.db.refresh(existing_alert)
            return existing_alert

        alert = Alert(
            server_id=server.id,
            resource_type=resource_type,
            alert_level=alert_level.value,
            alert_type="capacity_prediction",
            title=self._build_alert_title(server, resource_type, alert_level),
            message=self._build_alert_message(server, resource_type, peak_value, alert_level),
            current_value=peak_value,
            threshold_value=self.critical_threshold,
            status=AlertStatus.PENDING.value
        )

        self.db.add(alert)
        self.db.commit()
        self.db.refresh(alert)

        notifier.send_alert_notification(alert, server)

        return alert

    def _determine_alert_level(self, value: float) -> AlertLevel:
        if value >= self.fatal_threshold:
            return AlertLevel.FATAL
        elif value >= self.critical_threshold:
            return AlertLevel.CRITICAL
        elif value >= self.warning_threshold:
            return AlertLevel.WARNING
        else:
            return AlertLevel.INFO

    def _build_alert_title(self, server: Server, resource_type: str, level: AlertLevel) -> str:
        level_names = {
            'warning': '警告',
            'critical': '严重',
            'fatal': '致命',
            'info': '信息'
        }
        resource_names = {
            'cpu': 'CPU',
            'memory': '内存',
            'disk': '磁盘',
            'network': '网络带宽'
        }
        return f"[{level_names.get(level.value, level.value)}] {server.name} {resource_names.get(resource_type, resource_type)}容量预警"

    def _build_alert_message(self, server: Server, resource_type: str, peak_value: float, level: AlertLevel) -> str:
        resource_names = {
            'cpu': 'CPU',
            'memory': '内存',
            'disk': '磁盘',
            'network': '网络带宽'
        }
        return (
            f"服务器 {server.name} ({server.ip}) 的{resource_names.get(resource_type, resource_type)} "
            f"未来7天预测峰值为 {peak_value}%，超过{self.critical_threshold}%阈值。\n"
            f"建议立即评估并执行扩容操作。"
        )

    def _get_existing_active_alert(self, server_id: int, resource_type: str) -> Alert:
        return self.db.query(Alert).filter(
            Alert.server_id == server_id,
            Alert.resource_type == resource_type,
            Alert.alert_type == "capacity_prediction",
            Alert.status.in_([AlertStatus.PENDING.value, AlertStatus.ACKNOWLEDGED.value])
        ).order_by(Alert.created_at.desc()).first()

    def acknowledge_alert(self, alert_id: int, operator: str) -> Alert:
        alert = self.db.query(Alert).filter(Alert.id == alert_id).first()
        if not alert:
            return None

        alert.status = AlertStatus.ACKNOWLEDGED.value
        alert.acknowledged_by = operator
        alert.acknowledged_at = datetime.now()
        alert.updated_at = datetime.now()
        self.db.commit()
        self.db.refresh(alert)

        audit_logger.log_audit(
            self.db,
            module="alert",
            action="acknowledge",
            resource_type="alert",
            resource_id=alert_id,
            operator=operator,
            details=f"确认预警: {alert.title}"
        )
        return alert

    def resolve_alert(self, alert_id: int, operator: str, resolution: str = "") -> Alert:
        alert = self.db.query(Alert).filter(Alert.id == alert_id).first()
        if not alert:
            return None

        alert.status = AlertStatus.RESOLVED.value
        alert.resolved_at = datetime.now()
        alert.updated_at = datetime.now()
        if resolution:
            alert.message += f"\n处理结果: {resolution}"
        self.db.commit()
        self.db.refresh(alert)

        audit_logger.log_audit(
            self.db,
            module="alert",
            action="resolve",
            resource_type="alert",
            resource_id=alert_id,
            operator=operator,
            details=f"解决预警: {alert.title}"
        )
        return alert

    def escalate_alert(self, alert_id: int, operator: str = "system") -> Alert:
        alert = self.db.query(Alert).filter(Alert.id == alert_id).first()
        if not alert:
            return None

        alert.status = AlertStatus.ESCALATED.value
        alert.escalated_at = datetime.now()
        alert.updated_at = datetime.now()
        self.db.commit()
        self.db.refresh(alert)

        server = self.db.query(Server).filter(Server.id == alert.server_id).first()
        notifier.send_escalation_notification(alert, server)

        audit_logger.log_audit(
            self.db,
            module="alert",
            action="escalate",
            resource_type="alert",
            resource_id=alert_id,
            operator=operator,
            details=f"升级预警: {alert.title}"
        )
        return alert

    def check_timeout_alerts(self) -> List[Alert]:
        upgrade_hours = config['alert']['upgrade_hours']
        cutoff_time = datetime.now() - timedelta(hours=upgrade_hours)

        timeout_alerts = self.db.query(Alert).filter(
            Alert.status.in_([AlertStatus.PENDING.value, AlertStatus.ACKNOWLEDGED.value]),
            Alert.created_at < cutoff_time,
            Alert.escalated_at == None
        ).all()

        escalated = []
        for alert in timeout_alerts:
            escalated_alert = self.escalate_alert(alert.id)
            if escalated_alert:
                escalated.append(escalated_alert)

        return escalated

    def get_alerts(self, server_id: int = None, status: str = None, level: str = None,
                   start_time: datetime = None, end_time: datetime = None) -> List[Alert]:
        query = self.db.query(Alert)
        if server_id:
            query = query.filter(Alert.server_id == server_id)
        if status:
            query = query.filter(Alert.status == status)
        if level:
            query = query.filter(Alert.alert_level == level)
        if start_time:
            query = query.filter(Alert.created_at >= start_time)
        if end_time:
            query = query.filter(Alert.created_at <= end_time)
        return query.order_by(Alert.created_at.desc()).all()
