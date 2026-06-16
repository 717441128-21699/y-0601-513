import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from .database import get_db, BASE_DIR
from .models import Server, Alert, ExpansionPlan, PurchaseOrder, ResourceMetric, AuditLog, Verification
from . import audit_logger


class QueryService:
    def __init__(self, db: Session = None):
        self.db = db or next(get_db())

    def query_alerts(self, server_name: str = None, start_time: datetime = None,
                     end_time: datetime = None, level: str = None, status: str = None,
                     limit: int = 100, offset: int = 0) -> Dict:
        query = self.db.query(Alert).join(Server, Alert.server_id == Server.id)

        if server_name:
            query = query.filter(Server.name.like(f"%{server_name}%"))
        if start_time:
            query = query.filter(Alert.created_at >= start_time)
        if end_time:
            query = query.filter(Alert.created_at <= end_time)
        if level:
            query = query.filter(Alert.alert_level == level)
        if status:
            query = query.filter(Alert.status == status)

        total = query.count()
        alerts = query.order_by(Alert.created_at.desc()).offset(offset).limit(limit).all()

        return {
            'total': total,
            'items': alerts,
            'page': offset // limit + 1,
            'page_size': limit
        }

    def query_expansions(self, server_name: str = None, start_time: datetime = None,
                         end_time: datetime = None, status: str = None,
                         limit: int = 100, offset: int = 0) -> Dict:
        query = self.db.query(ExpansionPlan).join(Server, ExpansionPlan.server_id == Server.id)

        if server_name:
            query = query.filter(Server.name.like(f"%{server_name}%"))
        if start_time:
            query = query.filter(ExpansionPlan.created_at >= start_time)
        if end_time:
            query = query.filter(ExpansionPlan.created_at <= end_time)
        if status:
            query = query.filter(ExpansionPlan.status == status)

        total = query.count()
        plans = query.order_by(ExpansionPlan.created_at.desc()).offset(offset).limit(limit).all()

        return {
            'total': total,
            'items': plans,
            'page': offset // limit + 1,
            'page_size': limit
        }

    def query_orders(self, order_no: str = None, supplier: str = None, status: str = None,
                     start_time: datetime = None, end_time: datetime = None,
                     limit: int = 100, offset: int = 0) -> Dict:
        query = self.db.query(PurchaseOrder)

        if order_no:
            query = query.filter(PurchaseOrder.order_no.like(f"%{order_no}%"))
        if supplier:
            query = query.filter(PurchaseOrder.supplier.like(f"%{supplier}%"))
        if status:
            query = query.filter(PurchaseOrder.status == status)
        if start_time:
            query = query.filter(PurchaseOrder.created_at >= start_time)
        if end_time:
            query = query.filter(PurchaseOrder.created_at <= end_time)

        total = query.count()
        orders = query.order_by(PurchaseOrder.created_at.desc()).offset(offset).limit(limit).all()

        return {
            'total': total,
            'items': orders,
            'page': offset // limit + 1,
            'page_size': limit
        }

    def query_metrics(self, server_name: str = None, start_time: datetime = None,
                      end_time: datetime = None, limit: int = 1000) -> Dict:
        query = self.db.query(ResourceMetric).join(Server, ResourceMetric.server_id == Server.id)

        if server_name:
            query = query.filter(Server.name.like(f"%{server_name}%"))
        if start_time:
            query = query.filter(ResourceMetric.timestamp >= start_time)
        if end_time:
            query = query.filter(ResourceMetric.timestamp <= end_time)

        total = query.count()
        metrics = query.order_by(ResourceMetric.timestamp.desc()).limit(limit).all()

        return {
            'total': total,
            'items': metrics
        }

    def query_audit_logs(self, module: str = None, action: str = None,
                         operator: str = None, start_time: datetime = None,
                         end_time: datetime = None, limit: int = 100, offset: int = 0) -> Dict:
        query = self.db.query(AuditLog)

        if module:
            query = query.filter(AuditLog.module == module)
        if action:
            query = query.filter(AuditLog.action == action)
        if operator:
            query = query.filter(AuditLog.operator.like(f"%{operator}%"))
        if start_time:
            query = query.filter(AuditLog.timestamp >= start_time)
        if end_time:
            query = query.filter(AuditLog.timestamp <= end_time)

        total = query.count()
        logs = query.order_by(AuditLog.timestamp.desc()).offset(offset).limit(limit).all()

        return {
            'total': total,
            'items': logs,
            'page': offset // limit + 1,
            'page_size': limit
        }

    def get_server_list(self, server_type: str = None, is_active: bool = None) -> List[Server]:
        query = self.db.query(Server)
        if server_type:
            query = query.filter(Server.type == server_type)
        if is_active is not None:
            query = query.filter(Server.is_active == is_active)
        return query.order_by(Server.name).all()


class ExportService:
    def __init__(self, db: Session = None):
        self.db = db or next(get_db())
        self.export_dir = os.path.join(BASE_DIR, 'exports')
        os.makedirs(self.export_dir, exist_ok=True)

    def export_alerts_excel(self, server_name: str = None, start_time: datetime = None,
                            end_time: datetime = None, level: str = None, status: str = None) -> str:
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

            query_service = QueryService(self.db)
            result = query_service.query_alerts(
                server_name=server_name,
                start_time=start_time,
                end_time=end_time,
                level=level,
                status=status,
                limit=10000
            )

            filename = f"alerts_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            filepath = os.path.join(self.export_dir, filename)

            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "预警记录"

            header_font = Font(bold=True, size=11)
            header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
            header_font_white = Font(bold=True, size=11, color="FFFFFF")
            center_align = Alignment(horizontal='center', vertical='center')
            thin_border = Border(
                left=Side(style='thin'),
                right=Side(style='thin'),
                top=Side(style='thin'),
                bottom=Side(style='thin')
            )

            headers = ['预警ID', '服务器名称', '资源类型', '预警级别', '标题', '当前值', '阈值', '状态', '创建时间', '确认人', '确认时间', '解决时间']

            for col, header in enumerate(headers, 1):
                cell = ws.cell(row=1, column=col, value=header)
                cell.font = header_font_white
                cell.fill = header_fill
                cell.alignment = center_align
                cell.border = thin_border

            level_names = {
                'info': '信息',
                'warning': '警告',
                'critical': '严重',
                'fatal': '致命'
            }
            status_names = {
                'pending': '待处理',
                'acknowledged': '已确认',
                'resolved': '已解决',
                'escalated': '已升级'
            }
            resource_names = {
                'cpu': 'CPU',
                'memory': '内存',
                'disk': '磁盘',
                'network': '网络'
            }

            for row, alert in enumerate(result['items'], 2):
                server = self.db.query(Server).filter(Server.id == alert.server_id).first()
                data = [
                    alert.id,
                    server.name if server else '未知',
                    resource_names.get(alert.resource_type, alert.resource_type),
                    level_names.get(alert.alert_level, alert.alert_level),
                    alert.title,
                    f"{alert.current_value}%",
                    f"{alert.threshold_value}%",
                    status_names.get(alert.status, alert.status),
                    alert.created_at.strftime('%Y-%m-%d %H:%M:%S') if alert.created_at else '',
                    alert.acknowledged_by or '',
                    alert.acknowledged_at.strftime('%Y-%m-%d %H:%M:%S') if alert.acknowledged_at else '',
                    alert.resolved_at.strftime('%Y-%m-%d %H:%M:%S') if alert.resolved_at else ''
                ]
                for col, value in enumerate(data, 1):
                    cell = ws.cell(row=row, column=col, value=value)
                    cell.border = thin_border

            for col in range(1, len(headers) + 1):
                ws.column_dimensions[chr(64 + col) if col <= 26 else 'A' + chr(64 + col - 26)].width = 18

            ws.row_dimensions[1].height = 25

            wb.save(filepath)

            audit_logger.log_audit(
                self.db,
                module="export",
                action="export_alerts",
                resource_type="alert",
                operator="system",
                details=f"已导出 {result['total']} 条预警记录到 {filename}"
            )

            return filepath

        except Exception as e:
            print(f"导出预警记录失败: {e}")
            raise

    def export_expansions_excel(self, server_name: str = None, start_time: datetime = None,
                                end_time: datetime = None, status: str = None) -> str:
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

            query_service = QueryService(self.db)
            result = query_service.query_expansions(
                server_name=server_name,
                start_time=start_time,
                end_time=end_time,
                status=status,
                limit=10000
            )

            filename = f"expansions_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            filepath = os.path.join(self.export_dir, filename)

            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "扩容记录"

            header_font_white = Font(bold=True, size=11, color="FFFFFF")
            header_fill = PatternFill(start_color="70AD47", end_color="70AD47", fill_type="solid")
            center_align = Alignment(horizontal='center', vertical='center')
            thin_border = Border(
                left=Side(style='thin'),
                right=Side(style='thin'),
                top=Side(style='thin'),
                bottom=Side(style='thin')
            )

            headers = ['方案ID', '方案名称', '服务器', '资源类型', '当前配置', '推荐配置', '数量', '预估费用', '状态', '创建人', '创建时间']

            for col, header in enumerate(headers, 1):
                cell = ws.cell(row=1, column=col, value=header)
                cell.font = header_font_white
                cell.fill = header_fill
                cell.alignment = center_align
                cell.border = thin_border

            status_names = {
                'pending': '待审批',
                'approved': '已通过',
                'rejected': '已拒绝'
            }
            resource_names = {
                'cpu': 'CPU',
                'memory': '内存',
                'disk': '磁盘',
                'network': '网络'
            }

            for row, plan in enumerate(result['items'], 2):
                server = self.db.query(Server).filter(Server.id == plan.server_id).first()
                data = [
                    plan.id,
                    plan.plan_title,
                    server.name if server else '未知',
                    resource_names.get(plan.resource_type, plan.resource_type),
                    plan.current_spec or '',
                    plan.recommended_spec or '',
                    plan.quantity,
                    f"{plan.estimated_cost:,.2f} {plan.cost_currency}",
                    status_names.get(plan.status, plan.status),
                    plan.created_by or '',
                    plan.created_at.strftime('%Y-%m-%d %H:%M:%S') if plan.created_at else ''
                ]
                for col, value in enumerate(data, 1):
                    cell = ws.cell(row=row, column=col, value=value)
                    cell.border = thin_border

            for col in range(1, len(headers) + 1):
                ws.column_dimensions[chr(64 + col) if col <= 26 else 'A' + chr(64 + col - 26)].width = 18

            ws.row_dimensions[1].height = 25

            wb.save(filepath)

            audit_logger.log_audit(
                self.db,
                module="export",
                action="export_expansions",
                resource_type="expansion_plan",
                operator="system",
                details=f"已导出 {result['total']} 条扩容记录到 {filename}"
            )

            return filepath

        except Exception as e:
            print(f"导出扩容记录失败: {e}")
            raise

    def batch_export(self, export_types: List[str], start_time: datetime = None,
                     end_time: datetime = None, server_name: str = None) -> Dict:
        results = {}

        if 'alerts' in export_types:
            results['alerts'] = self.export_alerts_excel(
                server_name=server_name,
                start_time=start_time,
                end_time=end_time
            )

        if 'expansions' in export_types:
            results['expansions'] = self.export_expansions_excel(
                server_name=server_name,
                start_time=start_time,
                end_time=end_time
            )

        return results
