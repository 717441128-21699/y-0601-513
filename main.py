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
    print("7. 查看采购订单（含交付跟踪）")
    print("8. 查看健康报告（日/周/月）")
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
    order_manager = PurchaseOrderManager(db)

    result = service.query_orders(limit=50)

    status_names = {
        'draft': '草稿',
        'issued': '已下达',
        'in_progress': '进行中',
        'delivered': '已交付',
        'completed': '已完成',
        'cancelled': '已取消'
    }

    print("\n" + "-" * 80)
    print(f"{'ID':<5} {'订单号':<18} {'供应商':<12} {'金额':<10} {'状态':<8} {'交付截止':<12} {'扩容方案ID':<10}")
    print("-" * 80)

    for order in result['items']:
        status_name = status_names.get(order.status, order.status)
        deadline = order.delivery_deadline.strftime('%Y-%m-%d') if order.delivery_deadline else ''
        print(f"{order.id:<5} {order.order_no:<18} {order.supplier:<12} {order.total_amount:>8,.2f} {status_name:<8} {deadline:<12} {order.expansion_plan_id:<10}")

    print("-" * 80)
    print(f"共 {result['total']} 条记录")

    while True:
        print("\n操作选项：")
        print("  1. 更新订单状态（交付完成自动触发验证）")
        print("  2. 查看订单详情")
        print("  0. 返回主菜单")
        choice = input("\n请选择操作 [0-2]: ").strip()

        if choice == '0':
            return
        elif choice == '1':
            order_id = input("请输入订单ID: ").strip()
            if not order_id.isdigit():
                print("[X] 无效的ID")
                continue
            order = order_manager.get_order(int(order_id))
            if not order:
                print("[X] 订单不存在")
                continue

            print(f"\n当前订单: {order.order_no}, 状态: {status_names.get(order.status, order.status)}")
            print("\n可选状态:")
            print("  1. 已下达 (issued)")
            print("  2. 进行中 (in_progress)")
            print("  3. 已交付 (delivered) - 交付后自动触发扩容验证")
            print("  4. 已完成 (completed) - 完成后自动触发扩容验证")
            print("  5. 已取消 (cancelled)")
            status_choice = input("\n请选择新状态 [1-5]: ").strip()
            status_map = {'1': 'issued', '2': 'in_progress', '3': 'delivered', '4': 'completed', '5': 'cancelled'}
            new_status = status_map.get(status_choice)
            if not new_status:
                print("[X] 无效选择")
                continue

            operator = input("请输入操作人姓名: ").strip() or "admin"
            remarks = input("请输入备注（可选）: ").strip() or ""

            if new_status in ['delivered', 'completed']:
                print("\n[!] 标记交付/完成后将自动触发扩容验证，请确认...")
                confirm = input("确认继续？(y/n): ").strip().lower()
                if confirm != 'y':
                    print("已取消")
                    continue

            updated = order_manager.update_order_status(int(order_id), new_status, operator, remarks)
            if updated:
                print(f"\n[OK] 订单状态已更新为: {status_names.get(new_status, new_status)}")
                if new_status in ['delivered', 'completed']:
                    print("[OK] 已自动触发扩容验证流程，请查看验证结果")
            else:
                print("\n[X] 更新失败")

        elif choice == '2':
            order_id = input("请输入订单ID: ").strip()
            if not order_id.isdigit():
                print("[X] 无效的ID")
                continue
            order = order_manager.get_order(int(order_id))
            if not order:
                print("[X] 订单不存在")
                continue

            print("\n" + "=" * 60)
            print(f"                    订单详情 (ID: {order.id})")
            print("=" * 60)
            print(f"  订单号:       {order.order_no}")
            print(f"  供应商:       {order.supplier}")
            print(f"  关联扩容方案: {order.expansion_plan_id}")
            print(f"  订单金额:     {order.total_amount:,.2f} {order.currency}")
            print(f"  当前状态:     {status_names.get(order.status, order.status)}")
            print(f"  交付截止:     {order.delivery_deadline.strftime('%Y-%m-%d') if order.delivery_deadline else '-'}")
            print(f"  交付时间:     {order.delivered_at.strftime('%Y-%m-%d %H:%M') if order.delivered_at else '-'}")
            print(f"  完成时间:     {order.completed_at.strftime('%Y-%m-%d %H:%M') if order.completed_at else '-'}")
            print(f"  创建时间:     {order.created_at.strftime('%Y-%m-%d %H:%M') if order.created_at else '-'}")
            if order.remarks:
                print(f"  备注:         {order.remarks}")
            print("=" * 60)
        else:
            print("[!] 无效选择")


def view_reports():
    db = next(get_db())
    report_gen = ReportGenerator(db)

    type_names = {
        'daily': '日报',
        'weekly': '周报',
        'monthly': '月报'
    }

    while True:
        reports = report_gen.get_reports(limit=20)

        print("\n" + "=" * 80)
        print("                              健康报告列表")
        print("=" * 80)
        print(f"{'ID':<5} {'报告日期':<12} {'类型':<8} {'预警数':<8} {'扩容数':<8} {'CPU平均':<10} {'内存平均':<10} {'文件':<6}")
        print("-" * 80)

        if not reports:
            print("  暂无报告数据，请先生成报告")
            print("-" * 80)
        else:
            for report in reports:
                type_name = type_names.get(report.report_type, report.report_type)
                report_date = report.report_date.strftime('%Y-%m-%d') if report.report_date else ''
                has_files = "[OK]" if (report.pdf_path and report.excel_path) else "[-]"

                print(f"{report.id:<5} {report_date:<12} {type_name:<8} {report.alert_count:>6}条 {report.expansion_count:>6}个 {report.avg_cpu_usage:>8}% {report.avg_memory_usage:>8}% {has_files:<6}")

            print("-" * 80)
            print(f"共 {len(reports)} 份报告（显示最近20份）")

        print("\n操作选项：")
        print("  1. 生成今日日报")
        print("  2. 生成本周周报（近7天汇总）")
        print("  3. 生成本月月报（本月汇总）")
        print("  4. 查看报告详情（含PDF/Excel路径）")
        print("  5. 打开报告所在文件夹")
        print("  0. 返回主菜单")
        choice = input("\n请选择操作 [0-5]: ").strip()

        if choice == '0':
            return
        elif choice == '1':
            print("\n正在生成今日日报...")
            report = report_gen.generate_daily_report()
            print(f"[OK] 日报生成成功！ID: {report.id}")
            print(f"     PDF路径: {report.pdf_path}")
            print(f"     Excel路径: {report.excel_path}")
        elif choice == '2':
            print("\n正在生成本周周报（近7天汇总）...")
            report = report_gen.generate_weekly_report()
            print(f"[OK] 周报生成成功！ID: {report.id}")
            print(f"     PDF路径: {report.pdf_path}")
            print(f"     Excel路径: {report.excel_path}")
        elif choice == '3':
            print("\n正在生成本月月报...")
            report = report_gen.generate_monthly_report()
            print(f"[OK] 月报生成成功！ID: {report.id}")
            print(f"     PDF路径: {report.pdf_path}")
            print(f"     Excel路径: {report.excel_path}")
        elif choice == '4':
            if not reports:
                print("[!] 暂无报告，请先生成")
                continue
            report_id = input("请输入要查看的报告ID: ").strip()
            if not report_id.isdigit():
                print("[X] 无效的ID，请输入数字")
                continue

            report = report_gen.get_report(int(report_id))
            if not report:
                print("[X] 报告不存在")
                continue

            type_name = type_names.get(report.report_type, report.report_type)
            report_date = report.report_date.strftime('%Y-%m-%d') if report.report_date else ''

            print("\n" + "=" * 60)
            print(f"                        报告详情 (ID: {report.id})")
            print("=" * 60)
            print(f"  报告日期:       {report_date}")
            print(f"  报告类型:       {type_name}")
            print(f"  监控服务器数:   {report.total_servers} 台")
            print(f"  预警总数:       {report.alert_count} 条")
            print(f"    - 警告级别:   {report.warning_count} 条")
            print(f"    - 严重/致命:  {report.critical_count} 条")
            print(f"  扩容方案数:     {report.expansion_count} 个")
            print(f"  扩容完成数:     {report.expansion_completed_count} 个")
            print(f"  扩容完成率:     {report.expansion_completion_rate}%")
            print(f"  平均CPU使用率:  {report.avg_cpu_usage}%")
            print(f"  平均内存使用率: {report.avg_memory_usage}%")
            print(f"  平均磁盘使用率: {report.avg_disk_usage}%")
            print(f"  平均网络使用率: {report.avg_network_usage}%")
            print(f"  生成时间:       {report.created_at.strftime('%Y-%m-%d %H:%M:%S') if report.created_at else ''}")
            print("-" * 60)
            print(f"  PDF报告路径:    {report.pdf_path if report.pdf_path else '(未生成)'}")
            print(f"  Excel报告路径:  {report.excel_path if report.excel_path else '(未生成)'}")
            print("-" * 60)

            if report.summary:
                print("\n  报告摘要:")
                for line in report.summary.split('\n'):
                    print(f"    {line}")

            print("=" * 60)

            if report.pdf_path or report.excel_path:
                open_choice = input("\n是否打开报告文件？(y=打开PDF, e=打开Excel, n=不打开): ").strip().lower()
                if open_choice in ['y', 'e']:
                    import os
                    import subprocess
                    file_path = report.pdf_path if open_choice == 'y' else report.excel_path
                    if file_path and os.path.exists(file_path):
                        try:
                            os.startfile(file_path) if os.name == 'nt' else subprocess.Popen(['xdg-open', file_path])
                            print(f"[OK] 已尝试打开: {file_path}")
                        except Exception as e:
                            print(f"[X] 打开失败: {e}")
                            print(f"  请手动打开文件路径: {file_path}")
                    else:
                        print(f"[X] 文件不存在: {file_path}")

        elif choice == '5':
            import os
            import subprocess
            from app.database import BASE_DIR
            export_dir = os.path.join(BASE_DIR, 'exports')
            if os.path.exists(export_dir):
                try:
                    os.startfile(export_dir) if os.name == 'nt' else subprocess.Popen(['xdg-open', export_dir])
                    print(f"[OK] 已打开导出目录: {export_dir}")
                except Exception as e:
                    print(f"[!] 无法自动打开: {e}")
                    print(f"  请手动访问: {export_dir}")
            else:
                print(f"[X] 导出目录不存在: {export_dir}")
        else:
            print("[!] 无效选择，请重新输入")


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
    query_service = QueryService(db)

    print("\n" + "=" * 70)
    print("                          数据导出")
    print("=" * 70)

    servers = query_service.get_server_list()
    print("\n可选业务系统（服务器）列表:")
    print("-" * 70)
    print(f"  {'序号':<5} {'服务器名称':<20} {'类型':<12} {'IP地址':<15}")
    print("-" * 70)
    for idx, s in enumerate(servers, 1):
        type_names = {'web': 'Web', 'database': 'DB', 'application': 'App', 'storage': '存储', 'other': '其他'}
        t = type_names.get(s.type, s.type)
        print(f"  {idx:<5} {s.name:<20} {t:<12} {s.ip:<15}")
    print("-" * 70)
    print("  0: 全部系统")

    server_choice = input("\n请选择业务系统序号（0=全部，直接回车=全部）: ").strip()
    server_name = None
    if server_choice and server_choice.isdigit() and int(server_choice) > 0:
        idx = int(server_choice) - 1
        if 0 <= idx < len(servers):
            server_name = servers[idx].name
            print(f"[OK] 已选择: {server_name}")
        else:
            print("[!] 无效序号，使用全部系统")
    else:
        print("[OK] 已选择: 全部系统")

    print("\n请设置时间范围（直接回车表示不限制）：")
    start_date_str = input("  开始日期 (格式: YYYY-MM-DD): ").strip()
    end_date_str = input("  结束日期 (格式: YYYY-MM-DD): ").strip()

    start_time = None
    end_time = None

    if start_date_str:
        try:
            start_time = datetime.strptime(start_date_str, '%Y-%m-%d')
        except ValueError:
            print(f"[!] 开始日期格式无效，已忽略: {start_date_str}")

    if end_date_str:
        try:
            end_time = datetime.strptime(end_date_str, '%Y-%m-%d')
            end_time = end_time.replace(hour=23, minute=59, second=59)
        except ValueError:
            print(f"[!] 结束日期格式无效，已忽略: {end_date_str}")

    print("\n" + "-" * 70)
    print("当前筛选条件:")
    print(f"  业务系统:   {server_name if server_name else '全部'}")
    print(f"  时间范围:   {start_time.strftime('%Y-%m-%d') if start_time else '不限'} ~ {end_time.strftime('%Y-%m-%d') if end_time else '不限'}")
    print("-" * 70)

    alert_preview = query_service.query_alerts(server_name=server_name, start_time=start_time, end_time=end_time, limit=1)
    expansion_preview = query_service.query_expansions(server_name=server_name, start_time=start_time, end_time=end_time, limit=1)
    order_preview = query_service.query_orders(server_name=server_name, start_time=start_time, end_time=end_time, limit=1)
    verification_preview = query_service.query_verifications(server_name=server_name, start_time=start_time, end_time=end_time, limit=1)

    print(f"\n符合条件的记录数预览:")
    print(f"  预警记录:     {alert_preview['total']} 条")
    print(f"  扩容方案:     {expansion_preview['total']} 条")
    print(f"  采购订单:     {order_preview['total']} 条")
    print(f"  验证记录:     {verification_preview['total']} 条")
    print(f"  合计:         {alert_preview['total'] + expansion_preview['total'] + order_preview['total'] + verification_preview['total']} 条")

    print("\n请选择导出类型:")
    print("  1. 导出预警记录 (Excel)")
    print("  2. 导出扩容记录 (Excel)")
    print("  3. 导出采购订单 (Excel)")
    print("  4. 导出验证记录 (Excel)")
    print("  5. 批量导出全部四类（每个类型独立Excel文件）")
    print("  0. 返回")

    choice = input("\n请选择 [0-5]: ").strip()

    if choice == '0':
        return
    elif choice == '1':
        if alert_preview['total'] == 0:
            print("\n[!] 没有符合条件的预警记录可导出")
            return
        print(f"\n正在导出 {alert_preview['total']} 条预警记录...")
        filepath = export_service.export_alerts_excel(server_name=server_name, start_time=start_time, end_time=end_time)
        if filepath:
            print(f"\n[OK] 导出成功！共导出 {alert_preview['total']} 条记录")
            print(f"     文件路径: {filepath}")
        else:
            print("\n[X] 导出失败")

    elif choice == '2':
        if expansion_preview['total'] == 0:
            print("\n[!] 没有符合条件的扩容记录可导出")
            return
        print(f"\n正在导出 {expansion_preview['total']} 条扩容记录...")
        filepath = export_service.export_expansions_excel(server_name=server_name, start_time=start_time, end_time=end_time)
        if filepath:
            print(f"\n[OK] 导出成功！共导出 {expansion_preview['total']} 条记录")
            print(f"     文件路径: {filepath}")
        else:
            print("\n[X] 导出失败")

    elif choice == '3':
        if order_preview['total'] == 0:
            print("\n[!] 没有符合条件的采购订单可导出")
            return
        print(f"\n正在导出 {order_preview['total']} 条采购订单...")
        filepath = export_service.export_orders_excel(server_name=server_name, start_time=start_time, end_time=end_time)
        if filepath:
            print(f"\n[OK] 导出成功！共导出 {order_preview['total']} 条记录")
            print(f"     文件路径: {filepath}")
        else:
            print("\n[X] 导出失败")

    elif choice == '4':
        if verification_preview['total'] == 0:
            print("\n[!] 没有符合条件的验证记录可导出")
            return
        print(f"\n正在导出 {verification_preview['total']} 条验证记录...")
        filepath = export_service.export_verifications_excel(server_name=server_name, start_time=start_time, end_time=end_time)
        if filepath:
            print(f"\n[OK] 导出成功！共导出 {verification_preview['total']} 条记录")
            print(f"     文件路径: {filepath}")
        else:
            print("\n[X] 导出失败")

    elif choice == '5':
        total = alert_preview['total'] + expansion_preview['total'] + order_preview['total'] + verification_preview['total']
        if total == 0:
            print("\n[!] 没有符合条件的记录可导出")
            return
        print(f"\n正在批量导出共 {total} 条记录...")
        results = export_service.batch_export(
            export_types=['alerts', 'expansions', 'orders', 'verifications'],
            start_time=start_time,
            end_time=end_time,
            server_name=server_name
        )
        print("\n[OK] 批量导出完成！导出文件包含筛选条件摘要Sheet:")
        print(f"  预警记录:   {alert_preview['total']} 条 -> {results.get('alerts', '导出失败')}")
        print(f"  扩容记录:   {expansion_preview['total']} 条 -> {results.get('expansions', '导出失败')}")
        print(f"  采购订单:   {order_preview['total']} 条 -> {results.get('orders', '导出失败')}")
        print(f"  验证记录:   {verification_preview['total']} 条 -> {results.get('verifications', '导出失败')}")
    else:
        print("[!] 无效选择")


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
