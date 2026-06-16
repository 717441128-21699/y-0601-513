import json
from datetime import datetime
from typing import Optional
from .database import config
from . import audit_logger


class NotificationService:
    def __init__(self):
        self.enabled = config['notification']['enabled']
        self.webhook_url = config['notification']['webhook_url']
        self.it_group = config['notification']['it_management_group']

    def send_alert(self, alert, server) -> bool:
        if not self.enabled:
            return False

        message = self._format_alert_message(alert, server)
        return self._send_notification(message, "alert")

    def send_escalation(self, alert, server) -> bool:
        if not self.enabled:
            return False

        message = self._format_escalation_message(alert, server)
        return self._send_notification(message, "escalation")

    def send_expansion_notification(self, plan) -> bool:
        if not self.enabled:
            return False

        message = self._format_expansion_message(plan)
        return self._send_notification(message, "expansion")

    def send_approval_notification(self, plan, approval) -> bool:
        if not self.enabled:
            return False

        message = self._format_approval_message(plan, approval)
        return self._send_notification(message, "approval")

    def _format_alert_message(self, alert, server) -> str:
        level_emoji = {
            'info': '[i]',
            'warning': '[!]',
            'critical': '[X]',
            'fatal': '[F]'
        }

        level_name = {
            'info': '信息',
            'warning': '警告',
            'critical': '严重',
            'fatal': '致命'
        }

        resource_names = {
            'cpu': 'CPU',
            'memory': '内存',
            'disk': '磁盘',
            'network': '网络带宽'
        }

        emoji = level_emoji.get(alert.alert_level, '⚠️')
        level = level_name.get(alert.alert_level, alert.alert_level)
        resource = resource_names.get(alert.resource_type, alert.resource_type)

        return (
            f"{emoji} 【容量预警-{level}】\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"服务器: {server.name}\n"
            f"IP地址: {server.ip}\n"
            f"资源类型: {resource}\n"
            f"预测峰值: {alert.current_value}%\n"
            f"预警阈值: {alert.threshold_value}%\n"
            f"预警时间: {alert.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"请及时处理！"
        )

    def _format_escalation_message(self, alert, server) -> str:
        resource_names = {
            'cpu': 'CPU',
            'memory': '内存',
            'disk': '磁盘',
            'network': '网络带宽'
        }

        resource = resource_names.get(alert.resource_type, alert.resource_type)
        upgrade_hours = config['alert']['upgrade_hours']

        return (
            f"[!!!] 【预警升级通知】[!!!]\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"以下预警已超过 {upgrade_hours} 小时未处理，已自动升级！\n\n"
            f"服务器: {server.name}\n"
            f"资源类型: {resource}\n"
            f"预警级别: {alert.alert_level}\n"
            f"当前值: {alert.current_value}%\n"
            f"预警时间: {alert.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"请IT管理层关注并督促处理！"
        )

    def _format_expansion_message(self, plan) -> str:
        return (
            f"[-] 【扩容方案待审批】\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"方案名称: {plan.plan_title}\n"
            f"资源类型: {plan.resource_type}\n"
            f"推荐配置: {plan.recommended_spec} x {plan.quantity}\n"
            f"预估费用: {plan.estimated_cost:,.2f} {plan.cost_currency}\n"
            f"预计交付: {plan.delivery_days}天\n"
            f"创建时间: {plan.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"请及时审批！"
        )

    def _format_approval_message(self, plan, approval) -> str:
        status_text = "通过" if approval.status == "approved" else "拒绝"
        return (
            f"[OK] 【扩容方案已审批】\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"方案名称: {plan.plan_title}\n"
            f"审批结果: {status_text}\n"
            f"审批人: {approval.approver}\n"
            f"审批时间: {approval.approved_at.strftime('%Y-%m-%d %H:%M:%S') if approval.approved_at else '-'}\n"
            f"审批意见: {approval.comments or '无'}\n"
            f"━━━━━━━━━━━━━━━━━━"
        )

    def _send_notification(self, message: str, msg_type: str) -> bool:
        if not self.enabled or not self.webhook_url:
            print(f"\n[通知-{msg_type}] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("-" * 40)
            print(message)
            print("-" * 40 + "\n")
            return True

        try:
            import requests
            payload = {
                "msgtype": "text",
                "text": {
                    "content": message
                }
            }
            response = requests.post(self.webhook_url, json=payload, timeout=10)
            return response.status_code == 200
        except Exception as e:
            print(f"发送通知失败: {e}")
            return False


_notification_service = None


def get_notification_service() -> NotificationService:
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service


def send_alert_notification(alert, server) -> bool:
    service = get_notification_service()
    return service.send_alert(alert, server)


def send_escalation_notification(alert, server) -> bool:
    service = get_notification_service()
    return service.send_escalation(alert, server)


def send_expansion_notification(plan) -> bool:
    service = get_notification_service()
    return service.send_expansion_notification(plan)


def send_approval_notification(plan, approval) -> bool:
    service = get_notification_service()
    return service.send_approval_notification(plan, approval)
