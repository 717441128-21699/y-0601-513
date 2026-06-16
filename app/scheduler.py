import time
import random
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from .database import config, init_db, get_db
from .collector import ResourceCollector
from .predictor import BaselineCalculator, ResourcePredictor
from .alert_manager import AlertManager
from .expansion import ExpansionPlanner
from .report_generator import ReportGenerator
from . import audit_logger


class CapacityManagementSystem:
    def __init__(self):
        self.scheduler = None
        self.is_running = False

    def start(self):
        print("=" * 60)
        print("IT容量管理系统启动中...")
        print("=" * 60)

        init_db()
        self._init_default_servers()

        self.scheduler = BackgroundScheduler(timezone=config['system']['timezone'])

        collection_interval = config['collection']['interval_minutes']
        self.scheduler.add_job(
            self._job_collect_metrics,
            trigger=IntervalTrigger(minutes=collection_interval),
            id='collect_metrics',
            name='资源数据采集',
            replace_existing=True
        )

        self.scheduler.add_job(
            self._job_calculate_baselines,
            trigger=CronTrigger(hour=1, minute=0),
            id='calculate_baselines',
            name='基线计算',
            replace_existing=True
        )

        self.scheduler.add_job(
            self._job_predict_resources,
            trigger=CronTrigger(hour=1, minute=30),
            id='predict_resources',
            name='资源预测',
            replace_existing=True
        )

        self.scheduler.add_job(
            self._job_check_alerts,
            trigger=CronTrigger(hour=2, minute=0),
            id='check_alerts',
            name='预警检测',
            replace_existing=True
        )

        report_time = config['report']['generate_time']
        hour, minute = map(int, report_time.split(':'))
        self.scheduler.add_job(
            self._job_generate_daily_report,
            trigger=CronTrigger(hour=hour, minute=minute),
            id='generate_daily_report',
            name='生成每日报告',
            replace_existing=True
        )

        self.scheduler.add_job(
            self._job_check_timeout_alerts,
            trigger=IntervalTrigger(minutes=30),
            id='check_timeout_alerts',
            name='超时预警升级检查',
            replace_existing=True
        )

        self.scheduler.start()
        self.is_running = True

        print(f"\n[OK] 系统已启动，当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"[OK] 数据采集: 每 {collection_interval} 分钟执行一次")
        print(f"[OK] 基线计算: 每天 01:00 执行")
        print(f"[OK] 资源预测: 每天 01:30 执行")
        print(f"[OK] 预警检测: 每天 02:00 执行")
        print(f"[OK] 健康报告: 每天 {report_time} 生成")
        print(f"[OK] 超时检查: 每 30 分钟执行一次")
        print("\n按 Ctrl+C 停止系统\n")

    def stop(self):
        if self.scheduler and self.is_running:
            self.scheduler.shutdown()
            self.is_running = False
            print("\n系统已停止")

    def _init_default_servers(self):
        db = next(get_db())
        from .models import Server

        existing_count = db.query(Server).count()
        if existing_count > 0:
            return

        servers_config = config.get('servers', [])
        for server_config in servers_config:
            default_specs = {
                'web': {'cpu_cores': 8, 'memory_gb': 16, 'disk_gb': 500, 'network_mbps': 1000},
                'database': {'cpu_cores': 16, 'memory_gb': 64, 'disk_gb': 2000, 'network_mbps': 1000},
                'application': {'cpu_cores': 8, 'memory_gb': 32, 'disk_gb': 500, 'network_mbps': 1000},
                'storage': {'cpu_cores': 4, 'memory_gb': 16, 'disk_gb': 10000, 'network_mbps': 10000},
                'other': {'cpu_cores': 4, 'memory_gb': 8, 'disk_gb': 200, 'network_mbps': 100}
            }
            specs = default_specs.get(server_config.get('type', 'other'), default_specs['other'])

            server = Server(
                name=server_config['name'],
                type=server_config.get('type', 'other'),
                ip=server_config.get('ip', ''),
                description=f"默认{server_config.get('type', '服务器')}",
                **specs
            )
            db.add(server)

        db.commit()
        print(f"[OK] 已初始化 {len(servers_config)} 台默认服务器")

    def _job_collect_metrics(self):
        try:
            db = next(get_db())
            collector = ResourceCollector(db)
            metrics = collector.collect_all_servers()
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 资源采集完成: {len(metrics)} 条记录")
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 资源采集失败: {e}")

    def _job_calculate_baselines(self):
        try:
            db = next(get_db())
            calculator = BaselineCalculator(db)
            baselines = calculator.calculate_all_baselines()
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 基线计算完成: {len(baselines)} 条基线")
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 基线计算失败: {e}")

    def _job_predict_resources(self):
        try:
            db = next(get_db())
            predictor = ResourcePredictor(db)
            predictions = predictor.predict_all_servers()
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 资源预测完成: {len(predictions)} 条预测")
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 资源预测失败: {e}")

    def _job_check_alerts(self):
        try:
            db = next(get_db())
            alert_manager = AlertManager(db)
            alerts = alert_manager.check_all_alerts()
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 预警检测完成: {len(alerts)} 条预警")

            planner = ExpansionPlanner(db)
            for alert in alerts:
                if alert.alert_level in ['critical', 'fatal']:
                    planner.generate_plan_from_alert(alert.id)
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 预警检测失败: {e}")

    def _job_generate_daily_report(self):
        try:
            db = next(get_db())
            report_gen = ReportGenerator(db)
            report = report_gen.generate_daily_report()
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 健康报告生成完成: ID={report.id}")
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 健康报告生成失败: {e}")

    def _job_check_timeout_alerts(self):
        try:
            db = next(get_db())
            alert_manager = AlertManager(db)
            escalated = alert_manager.check_timeout_alerts()
            if escalated:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 超时预警升级: {len(escalated)} 条")
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 超时预警检查失败: {e}")

    def run_demo(self):
        print("\n" + "=" * 60)
        print("运行系统演示...")
        print("=" * 60 + "\n")

        init_db()
        self._init_default_servers()
        db = next(get_db())

        print("[1/5] 生成历史数据...")
        collector = ResourceCollector(db)
        history_count = collector.generate_historical_data(days=30)
        print(f"  [OK] 已生成 {history_count} 条历史数据\n")

        print("[2/5] 计算动态基线...")
        calculator = BaselineCalculator(db)
        baselines = calculator.calculate_all_baselines()
        print(f"  [OK] 已计算 {len(baselines)} 条资源基线\n")

        print("[3/5] 资源需求预测...")
        predictor = ResourcePredictor(db)
        predictions = predictor.predict_all_servers()
        print(f"  [OK] 已生成 {len(predictions)} 条预测数据\n")

        print("[4/5] 容量预警检测...")
        alert_manager = AlertManager(db)
        alerts = alert_manager.check_all_alerts()
        print(f"  [OK] 已生成 {len(alerts)} 条容量预警\n")

        print("[5/5] 生成扩容方案...")
        planner = ExpansionPlanner(db)
        plan_count = 0
        for alert in alerts:
            if alert.alert_level in ['critical', 'fatal']:
                plan = planner.generate_plan_from_alert(alert.id)
                if plan:
                    plan_count += 1
        print(f"  [OK] 已生成 {plan_count} 个扩容方案\n")

        print("[6/6] 生成健康报告...")
        report_gen = ReportGenerator(db)
        report = report_gen.generate_daily_report()
        print(f"  [OK] 已生成健康报告 (ID: {report.id})\n")

        print("=" * 60)
        print("演示完成！以下是系统概览：")
        print("=" * 60)
        print(f"\n  监控服务器: {report.total_servers} 台")
        print(f"  今日预警数: {report.alert_count} 条")
        print(f"    - 警告级别: {report.warning_count} 条")
        print(f"    - 严重/致命: {report.critical_count} 条")
        print(f"  扩容方案数: {report.expansion_count} 个")
        print(f"  平均CPU使用率: {report.avg_cpu_usage}%")
        print(f"  平均内存使用率: {report.avg_memory_usage}%")
        print(f"  平均磁盘使用率: {report.avg_disk_usage}%")
        print(f"  平均网络使用率: {report.avg_network_usage}%")
        print(f"\n  报告已导出至 exports/ 目录")
        print("=" * 60 + "\n")

    def run_once(self):
        print("\n执行一次完整的容量管理流程...\n")

        init_db()
        self._init_default_servers()

        self._job_collect_metrics()
        self._job_calculate_baselines()
        self._job_predict_resources()
        self._job_check_alerts()
        self._job_check_timeout_alerts()

        db = next(get_db())
        report_gen = ReportGenerator(db)
        report = report_gen.generate_daily_report()
        print(f"[OK] 已生成健康报告 (ID: {report.id})")

        print("\n[OK] 单次执行完成\n")
