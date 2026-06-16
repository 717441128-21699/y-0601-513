import random
import psutil
from datetime import datetime, timedelta
from typing import List, Dict
from sqlalchemy.orm import Session
from .database import get_db, config
from .models import Server, ResourceMetric
from . import audit_logger


class ResourceCollector:
    def __init__(self, db: Session = None):
        self.db = db or next(get_db())

    def collect_all_servers(self) -> List[ResourceMetric]:
        servers = self.db.query(Server).filter(Server.is_active == True).all()
        metrics = []
        for server in servers:
            metric = self.collect_server_metrics(server)
            if metric:
                metrics.append(metric)
        audit_logger.log_audit(
            self.db,
            module="collection",
            action="collect_all",
            resource_type="server_metrics",
            operator="system",
            details=f"已采集 {len(metrics)} 台服务器的资源数据"
        )
        return metrics

    def collect_server_metrics(self, server: Server) -> ResourceMetric:
        usage_data = self._get_resource_usage(server)
        metric = ResourceMetric(
            server_id=server.id,
            timestamp=datetime.now(),
            cpu_usage=usage_data['cpu'],
            memory_usage=usage_data['memory'],
            disk_usage=usage_data['disk'],
            network_usage=usage_data['network']
        )
        self.db.add(metric)
        self.db.commit()
        self.db.refresh(metric)
        return metric

    def _get_resource_usage(self, server: Server) -> Dict[str, float]:
        if self._is_localhost(server):
            return self._collect_local_metrics()
        else:
            return self._simulate_remote_metrics(server)

    def _is_localhost(self, server: Server) -> bool:
        return server.ip in ['127.0.0.1', 'localhost', '0.0.0.0']

    def _collect_local_metrics(self) -> Dict[str, float]:
        cpu = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory().percent
        disk = psutil.disk_usage('/').percent

        net_io = psutil.net_io_counters()
        net_usage = min(100.0, (net_io.bytes_sent + net_io.bytes_recv) / 1024 / 1024 / 10 * 100)

        return {
            'cpu': round(cpu, 2),
            'memory': round(memory, 2),
            'disk': round(disk, 2),
            'network': round(net_usage, 2)
        }

    def _simulate_remote_metrics(self, server: Server) -> Dict[str, float]:
        base_usage = {
            'web': {'cpu': 45, 'memory': 60, 'disk': 30, 'network': 50},
            'database': {'cpu': 35, 'memory': 70, 'disk': 65, 'network': 30},
            'application': {'cpu': 50, 'memory': 55, 'disk': 25, 'network': 40},
            'storage': {'cpu': 20, 'memory': 40, 'disk': 80, 'network': 60},
            'other': {'cpu': 30, 'memory': 45, 'disk': 40, 'network': 25}
        }

        base = base_usage.get(server.type, base_usage['other'])
        hour = datetime.now().hour

        load_factor = 1.0
        if 9 <= hour <= 11 or 14 <= hour <= 17:
            load_factor = 1.3
        elif 0 <= hour <= 6:
            load_factor = 0.6
        elif 20 <= hour <= 23:
            load_factor = 0.8

        return {
            'cpu': round(min(99.0, max(5.0, base['cpu'] * load_factor + random.uniform(-10, 10))), 2),
            'memory': round(min(99.0, max(10.0, base['memory'] * load_factor + random.uniform(-5, 5))), 2),
            'disk': round(min(99.0, max(10.0, base['disk'] + random.uniform(-2, 2))), 2),
            'network': round(min(99.0, max(2.0, base['network'] * load_factor + random.uniform(-8, 8))), 2)
        }

    def generate_historical_data(self, days: int = 30) -> int:
        servers = self.db.query(Server).filter(Server.is_active == True).all()
        total_count = 0
        now = datetime.now()

        for server in servers:
            for day in range(days, 0, -1):
                for hour in range(0, 24, 2):
                    timestamp = now - timedelta(days=day, hours=hour)
                    usage_data = self._simulate_historical(server, timestamp)
                    metric = ResourceMetric(
                        server_id=server.id,
                        timestamp=timestamp,
                        cpu_usage=usage_data['cpu'],
                        memory_usage=usage_data['memory'],
                        disk_usage=usage_data['disk'],
                        network_usage=usage_data['network']
                    )
                    self.db.add(metric)
                    total_count += 1

        self.db.commit()
        audit_logger.log_audit(
            self.db,
            module="collection",
            action="generate_history",
            resource_type="server_metrics",
            operator="system",
            details=f"已生成 {total_count} 条历史数据，覆盖 {days} 天"
        )
        return total_count

    def _simulate_historical(self, server: Server, timestamp: datetime) -> Dict[str, float]:
        base_usage = {
            'web': {'cpu': 45, 'memory': 60, 'disk': 30, 'network': 50},
            'database': {'cpu': 35, 'memory': 70, 'disk': 65, 'network': 30},
            'application': {'cpu': 50, 'memory': 55, 'disk': 25, 'network': 40},
            'storage': {'cpu': 20, 'memory': 40, 'disk': 80, 'network': 60},
            'other': {'cpu': 30, 'memory': 45, 'disk': 40, 'network': 25}
        }

        base = base_usage.get(server.type, base_usage['other'])
        hour = timestamp.hour
        day_of_week = timestamp.weekday()

        load_factor = 1.0
        if day_of_week >= 5:
            load_factor = 0.7

        if 9 <= hour <= 11 or 14 <= hour <= 17:
            load_factor *= 1.3
        elif 0 <= hour <= 6:
            load_factor *= 0.6
        elif 20 <= hour <= 23:
            load_factor *= 0.8

        trend_factor = 1.0 + (30 - (datetime.now() - timestamp).days) / 30 * 0.15

        return {
            'cpu': round(min(99.0, max(5.0, base['cpu'] * load_factor * trend_factor + random.uniform(-10, 10))), 2),
            'memory': round(min(99.0, max(10.0, base['memory'] * load_factor * trend_factor + random.uniform(-5, 5))), 2),
            'disk': round(min(99.0, max(10.0, base['disk'] * trend_factor + random.uniform(-2, 2))), 2),
            'network': round(min(99.0, max(2.0, base['network'] * load_factor * trend_factor + random.uniform(-8, 8))), 2)
        }

    def get_metrics_by_server(self, server_id: int, start_time: datetime = None, end_time: datetime = None) -> List[ResourceMetric]:
        query = self.db.query(ResourceMetric).filter(ResourceMetric.server_id == server_id)
        if start_time:
            query = query.filter(ResourceMetric.timestamp >= start_time)
        if end_time:
            query = query.filter(ResourceMetric.timestamp <= end_time)
        return query.order_by(ResourceMetric.timestamp).all()
