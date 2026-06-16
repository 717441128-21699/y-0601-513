#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.scheduler import CapacityManagementSystem
from app.database import get_db, init_db
from app.query_service import QueryService, ExportService
from app.collector import ResourceCollector
from app.predictor import BaselineCalculator, ResourcePredictor
from app.alert_manager import AlertManager
from app.expansion import ExpansionPlanner, ApprovalManager, PurchaseOrderManager
from app.verification import VerificationManager
from app.report_generator import ReportGenerator
from app.audit_logger import get_audit_logs
from datetime import datetime, timedelta


def print_menu():
    print("\n" + "=" * 60)
    print("           IT容量管理系统")
    print("=" * 60)
    print("1. 启动系统（定时任务模式）")
    print("2. 运行系统演示")
    print("3. 执行单次采集分析")
    print("4. 查看服务器列表")
    print("5. 查看预警记录")
    print("6. 查看扩容方案")
    print("7. 查看采购订单")
    print("8. 查看健康报告")
    print("9. 审批扩容方案")
    print("10. 执行扩容验证")
    print("11. 导出数据（Excel）")
    print("12. 查看审计日志")
    print("0. 退出系统")
    print("=" * 60)


def view_servers():
    db = next(get_db())
    service = QueryService(db)
    servers = service.get_server_list()

    print("\n" + "-" * 60)
    print(f"{'服务器名称':<20} {'类型':<12} {'IP地址':<15} {'CPU':>6} {'内存':>8} {'磁盘':>8} {'状态':<8}")
    print("-" * 60)

    type_names = {
        'web': 'Web服务器',
        'database': '数据库',
        'application': '应用服务器',
        'storage': '存储服务器',
        'other': '其他'
    }

    for server in servers:
        status = "运行中" if server.is_active else "已停用"
        type_name = type_names.get(server.type, server.type)
        print(f"{server.name:<20} {type_name:<12} {server.ip:<15} {server.cpu_cores:>4}核 {server.memory_gb:>5}GB {server.disk_gb:>6}GB {status:<8}")

    print("-" * 60)
    print(f"共 {len(servers)} 台服务器")


def view_alerts():
    db = next(get_db())
    service = QueryService(db)

    print("\n请选择筛选条件（直接回车表示不筛选）:")
    server_name = input("  服务器名称: ").strip() or None
    level = input("  预警级别 (warning/critical/fatal): ").strip() or None
    status = input("  状态 (pending/acknowledged/resolved): ").strip() or None
    days = input("  最近多少天: ").strip()

    start_time = None
    if days and days.isdigit():
        start_time = datetime.now() - timedelta(days=int(days))

    result = service.query_alerts(
        server_name=server_name,
        level=level,
        status=status,
        start_time=start_time,
        limit=50
    )

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

    print("\n" + "-" * 70)
    print(f"{'ID':<5} {'服务器':<15} {'资源':<8} {'级别':<6} {'当前值':<8} {'状态':<8} {'创建时间':<20}")
    print("-" * 70)

    servers = {s.id: s.name for s in service.get_server_list()}

    for alert in result['items']:
        server_name = servers.get(alert.server_id, '未知')
        level_name = level_names.get(alert.alert_level, alert.alert_level)
        status_name = status_names.get(alert.status, alert.status)
        resource_name = resource_names.get(alert.resource_type, alert.resource_type)
        create_time = alert.created_at.strftime('%Y-%m-%d %H:%M') if alert.created_at else ''

        print(f"{alert.id:<5} {server_name:<15} {resource_name:<8} {level_name:<6} {alert.current_value:>6}% {status_name:<8} {create_time:<20}")

    print("-" * 70)
    print(f"共 {result['total']} 条记录（显示前50条）")


def view_expansions():
    db = next(get_db())
    service = QueryService(db)

    result = service.query_expansions(limit=50)

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

    print("\n" + "-" * 70)
    print(f"{'ID':<5} {'方案名称':<25} {'资源':<8} {'数量':<5} {'预估费用':<12} {'状态':<8} {'创建时间':<15}")
    print("-" * 70)

    for plan in result['items']:
        status_name = status_names.get(plan.status, plan.status)
        resource_name = resource_names.get(plan.resource_type, plan.resource_type)
        create_time = plan.created_at.strftime('%Y-%m-%d') if plan.created_at else ''

        print(f"{plan.id:<5} {plan.plan_title:<25} {resource_name:<8} {plan.quantity:>4}个 {plan.estimated_cost:>10,.2f} {status_name:<8} {create_time:<15}")

    print("-" * 70)
    print(f"共 {result['total']} 条记录")


def view_orders():
    db = next(get_db())
    service = QueryService(db)

    result = service.query_orders(limit=50)

    status_names = {
        'draft': '草稿',
        'issued': '已下达',
        'in_progress': '进行中',
        'delivered': '已交付',
        'completed': '已完成',
        'cancelled': '已取消'
    }

    print("\n" + "-" * 70)
    print(f"{'订单号':<20} {'供应商':<15} {'金额':<12} {'状态':<10} {'交付截止':<12} {'创建时间':<12}")
    print("-" * 70)

    for order in result['items']:
        status_name = status_names.get(order.status, order.status)
        deadline = order.delivery_deadline.strftime('%Y-%m-%d') if order.delivery_deadline else ''
        create_time = order.created_at.strftime('%Y-%m-%d') if order.created_at else ''

        print(f"{order.order_no:<20} {order.supplier:<15} {order.total_amount:>10,.2f} {status_name:<10} {deadline:<12} {create_time:<12}")

    print("-" * 70)
    print(f"共 {result['total']} 条记录")


def view_reports():
    db = next(get_db())
    report_gen = ReportGenerator(db)

    reports = report_gen.get_reports(limit=20)

    print("\n" + "-" * 60)
    print(f"{'ID':<5} {'报告日期':<12} {'类型':<8} {'预警数':<8} {'扩容数':<8} {'CPU':<8} {'内存':<8}")
    print("-" * 60)

    type_names = {
        'daily': '日报',
        'weekly': '周报',
        'monthly': '月报'
    }

    for report in reports:
        type_name = type_names.get(report.report_type, report.report_type)
        report_date = report.report_date.strftime('%Y-%m-%d') if report.report_date else ''

        print(f"{report.id:<5} {report_date:<12} {type_name:<8} {report.alert_count:>6}条 {report.expansion_count:>6}个 {report.avg_cpu_usage:>6}% {report.avg_memory_usage:>6}%")

    print("-" * 60)
    print(f"共 {len(reports)} 份报告（显示最近20份）")


def approve_expansion():
    db = next(get_db())
    planner = ExpansionPlanner(db)
    approval_manager = ApprovalManager(db)

    plan_id = input("\n请输入要审批的扩容方案ID: ").strip()
    if not plan_id.isdigit():
        print("无效的ID")
        return

    plan = planner.get_plan(int(plan_id))
    if not plan:
        print("方案不存在")
        return

    print(f"\n方案详情:")
    print(f"  方案名称: {plan.plan_title}")
    print(f"  资源类型: {plan.resource_type}")
    print(f"  当前配置: {plan.current_spec}")
    print(f"  推荐配置: {plan.recommended_spec} x {plan.quantity}")
    print(f"  预估费用: {plan.estimated_cost:,.2f} {plan.cost_currency}")
    print(f"  当前状态: {plan.status}")
    print(f"\n  方案说明:")
    print(f"    {plan.justification}")

    action = input("\n请选择操作 (1-通过, 2-拒绝, 0-取消): ").strip()

    if action == '1':
        approver = input("请输入审批人姓名: ").strip() or "admin"
        comments = input("请输入审批意见（可选）: ").strip() or ""
        result = approval_manager.approve_plan(int(plan_id), approver, comments)
        if result:
            print(f"\n[OK] 方案已审批通过，采购订单已自动生成")
        else:
            print("\n[X] 审批失败")
    elif action == '2':
        approver = input("请输入审批人姓名: ").strip() or "admin"
        comments = input("请输入拒绝原因: ").strip() or ""
        result = approval_manager.reject_plan(int(plan_id), approver, comments)
        if result:
            print(f"\n[OK] 方案已拒绝")
        else:
            print("\n[X] 操作失败")
    else:
        print("已取消")


def run_verification():
    db = next(get_db())
    planner = ExpansionPlanner(db)
    verifier = VerificationManager(db)

    plan_id = input("\n请输入要验证的扩容方案ID: ").strip()
    if not plan_id.isdigit():
        print("无效的ID")
        return

    plan = planner.get_plan(int(plan_id))
    if not plan:
        print("方案不存在")
        return

    print(f"\n方案信息:")
    print(f"  方案名称: {plan.plan_title}")
    print(f"  当前状态: {plan.status}")

    if plan.status != 'approved':
        print("\n警告: 该方案尚未审批通过，是否仍要验证？")
        confirm = input("(y/n): ").strip().lower()
        if confirm != 'y':
            return

    operator = input("请输入验证人姓名: ").strip() or "system"

    print("\n正在执行扩容验证...")
    verification = verifier.run_verification(int(plan_id), operator)

    if verification:
        print("\n" + "-" * 50)
        print(f"验证结果: {'通过' if verification.status == 'passed' else '失败'}")
        print(f"资源类型: {plan.resource_type}")

        resource = plan.resource_type
        before = getattr(verification, f"{resource}_before", 0)
        after = getattr(verification, f"{resource}_after", 0)

        print(f"扩容前使用率: {before}%")
        print(f"扩容后使用率: {after}%")

        if before and before > 0:
            improvement = round((before - after) / before * 100, 2)
            print(f"改善幅度: {improvement}%")

        if verification.is_rolled_back:
            print(f"\n[!] 已自动回滚，原因: {verification.rollback_reason}")

        print("-" * 50)
    else:
        print("\n验证失败")


def export_data():
    db = next(get_db())
    export_service = ExportService(db)

    print("\n请选择导出类型:")
    print("  1. 导出预警记录 (Excel)")
    print("  2. 导出扩容记录 (Excel)")
    print("  3. 批量导出全部")
    print("  0. 返回")

    choice = input("\n请选择: ").strip()

    if choice == '1':
        print("\n正在导出预警记录...")
        filepath = export_service.export_alerts_excel()
        print(f"[OK] 导出成功: {filepath}")
    elif choice == '2':
        print("\n正在导出扩容记录...")
        filepath = export_service.export_expansions_excel()
        print(f"[OK] 导出成功: {filepath}")
    elif choice == '3':
        print("\n正在批量导出...")
        results = export_service.batch_export(['alerts', 'expansions'])
        for type_name, path in results.items():
            print(f"  [OK] {type_name}: {path}")
        print("[OK] 批量导出完成")
    elif choice == '0':
        return
    else:
        print("无效选择")


def view_audit_logs():
    db = next(get_db())
    logs = get_audit_logs(db, limit=50)

    print("\n" + "-" * 70)
    print(f"{'时间':<20} {'模块':<12} {'操作':<12} {'操作人':<12} {'结果':<8} {'详情'}")
    print("-" * 70)

    for log in logs:
        timestamp = log.timestamp.strftime('%Y-%m-%d %H:%M:%S') if log.timestamp else ''
        details = (log.details or '')[:30]
        print(f"{timestamp:<20} {log.module:<12} {log.action:<12} {(log.operator or ''):<12} {log.result:<8} {details}")

    print("-" * 70)
    print(f"显示最近 {len(logs)} 条记录")


def main():
    print("\n" + "=" * 60)
    print("  欢迎使用 IT容量管理系统 v1.0")
    print("  自动采集 · 动态基线 · 智能预测 · 容量预警 · 扩容管理")
    print("=" * 60)

    init_db()

    system = CapacityManagementSystem()

    while True:
        print_menu()
        choice = input("\n请选择操作 [0-12]: ").strip()

        if choice == '0':
            print("\n感谢使用，再见！")
            break
        elif choice == '1':
            print("\n启动定时任务模式...")
            print("（按 Ctrl+C 可返回菜单）")
            try:
                system.start()
                while True:
                    import time
                    time.sleep(1)
            except KeyboardInterrupt:
                system.stop()
        elif choice == '2':
            system.run_demo()
        elif choice == '3':
            system.run_once()
        elif choice == '4':
            view_servers()
        elif choice == '5':
            view_alerts()
        elif choice == '6':
            view_expansions()
        elif choice == '7':
            view_orders()
        elif choice == '8':
            view_reports()
        elif choice == '9':
            approve_expansion()
        elif choice == '10':
            run_verification()
        elif choice == '11':
            export_data()
        elif choice == '12':
            view_audit_logs()
        else:
            print("\n无效选择，请重新输入")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n系统已退出")
