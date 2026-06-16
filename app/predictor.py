import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
from sqlalchemy.orm import Session
from .database import get_db, config
from .models import Server, ResourceMetric, Baseline, Prediction
from . import audit_logger


class BaselineCalculator:
    def __init__(self, db: Session = None):
        self.db = db or next(get_db())
        self.history_days = config['baseline']['history_days']
        self.method = config['baseline']['calculation_method']

    def calculate_all_baselines(self) -> List[Baseline]:
        servers = self.db.query(Server).filter(Server.is_active == True).all()
        all_baselines = []
        for server in servers:
            baselines = self.calculate_server_baselines(server)
            all_baselines.extend(baselines)

        audit_logger.log_audit(
            self.db,
            module="baseline",
            action="calculate_all",
            resource_type="baseline",
            operator="system",
            details=f"已计算 {len(servers)} 台服务器的资源基线"
        )
        return all_baselines

    def calculate_server_baselines(self, server: Server) -> List[Baseline]:
        resource_types = ['cpu', 'memory', 'disk', 'network']
        baselines = []

        for resource_type in resource_types:
            baseline = self._calculate_single_baseline(server, resource_type)
            if baseline:
                baselines.append(baseline)

        return baselines

    def _calculate_single_baseline(self, server: Server, resource_type: str) -> Baseline:
        end_time = datetime.now()
        start_time = end_time - timedelta(days=self.history_days)

        metrics = self.db.query(ResourceMetric).filter(
            ResourceMetric.server_id == server.id,
            ResourceMetric.timestamp >= start_time,
            ResourceMetric.timestamp <= end_time
        ).all()

        if not metrics:
            return None

        values = self._extract_resource_values(metrics, resource_type)

        if len(values) == 0:
            return None

        baseline_value = np.mean(values)
        peak_value = np.max(values)
        percentile_95 = np.percentile(values, 95)
        percentile_99 = np.percentile(values, 99)
        std_dev = np.std(values)

        existing = self.db.query(Baseline).filter(
            Baseline.server_id == server.id,
            Baseline.resource_type == resource_type
        ).first()

        if existing:
            existing.baseline_value = round(float(baseline_value), 2)
            existing.peak_value = round(float(peak_value), 2)
            existing.percentile_95 = round(float(percentile_95), 2)
            existing.percentile_99 = round(float(percentile_99), 2)
            existing.std_dev = round(float(std_dev), 2)
            existing.calculated_at = datetime.now()
            existing.period_start = start_time
            existing.period_end = end_time
            self.db.commit()
            self.db.refresh(existing)
            return existing
        else:
            baseline = Baseline(
                server_id=server.id,
                resource_type=resource_type,
                baseline_value=round(float(baseline_value), 2),
                peak_value=round(float(peak_value), 2),
                percentile_95=round(float(percentile_95), 2),
                percentile_99=round(float(percentile_99), 2),
                std_dev=round(float(std_dev), 2),
                period_start=start_time,
                period_end=end_time
            )
            self.db.add(baseline)
            self.db.commit()
            self.db.refresh(baseline)
            return baseline

    def _extract_resource_values(self, metrics: List[ResourceMetric], resource_type: str) -> List[float]:
        field_map = {
            'cpu': 'cpu_usage',
            'memory': 'memory_usage',
            'disk': 'disk_usage',
            'network': 'network_usage'
        }
        field = field_map.get(resource_type, 'cpu_usage')
        return [getattr(m, field) for m in metrics if getattr(m, field) is not None]

    def get_current_baseline(self, server_id: int, resource_type: str) -> Baseline:
        return self.db.query(Baseline).filter(
            Baseline.server_id == server_id,
            Baseline.resource_type == resource_type
        ).order_by(Baseline.calculated_at.desc()).first()


class ResourcePredictor:
    def __init__(self, db: Session = None):
        self.db = db or next(get_db())
        self.forecast_days = config['prediction']['forecast_days']
        self.algorithm = config['prediction']['algorithm']

    def predict_all_servers(self) -> List[Prediction]:
        servers = self.db.query(Server).filter(Server.is_active == True).all()
        all_predictions = []

        for server in servers:
            predictions = self.predict_server_resources(server)
            all_predictions.extend(predictions)

        audit_logger.log_audit(
            self.db,
            module="prediction",
            action="predict_all",
            resource_type="prediction",
            operator="system",
            details=f"已预测 {len(servers)} 台服务器未来 {self.forecast_days} 天的资源需求"
        )
        return all_predictions

    def predict_server_resources(self, server: Server) -> List[Prediction]:
        resource_types = ['cpu', 'memory', 'disk', 'network']
        predictions = []

        for resource_type in resource_types:
            resource_predictions = self._predict_resource(server, resource_type)
            predictions.extend(resource_predictions)

        return predictions

    def _predict_resource(self, server: Server, resource_type: str) -> List[Prediction]:
        history_days = config['baseline']['history_days']
        end_time = datetime.now()
        start_time = end_time - timedelta(days=history_days)

        metrics = self.db.query(ResourceMetric).filter(
            ResourceMetric.server_id == server.id,
            ResourceMetric.timestamp >= start_time,
            ResourceMetric.timestamp <= end_time
        ).order_by(ResourceMetric.timestamp).all()

        if len(metrics) < 10:
            return []

        df = self._metrics_to_dataframe(metrics, resource_type)
        daily_stats = self._get_daily_stats(df)

        if len(daily_stats) < 7:
            return []

        predictions = []
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        for day in range(1, self.forecast_days + 1):
            forecast_date = today + timedelta(days=day)
            predicted, upper, lower = self._linear_prediction(daily_stats, day)

            predicted = min(100.0, max(0.0, predicted))
            upper = min(100.0, max(0.0, upper))
            lower = min(100.0, max(0.0, lower))

            prediction = Prediction(
                server_id=server.id,
                resource_type=resource_type,
                forecast_date=forecast_date,
                predicted_value=round(float(predicted), 2),
                upper_bound=round(float(upper), 2),
                lower_bound=round(float(lower), 2),
                confidence=0.95
            )
            predictions.append(prediction)

        self.db.query(Prediction).filter(
            Prediction.server_id == server.id,
            Prediction.resource_type == resource_type,
            Prediction.forecast_date > today
        ).delete()

        for p in predictions:
            self.db.add(p)

        self.db.commit()
        return predictions

    def _metrics_to_dataframe(self, metrics: List[ResourceMetric], resource_type: str) -> pd.DataFrame:
        field_map = {
            'cpu': 'cpu_usage',
            'memory': 'memory_usage',
            'disk': 'disk_usage',
            'network': 'network_usage'
        }
        field = field_map.get(resource_type, 'cpu_usage')

        data = {
            'timestamp': [m.timestamp for m in metrics],
            'value': [getattr(m, field) for m in metrics]
        }
        df = pd.DataFrame(data)
        df['date'] = df['timestamp'].dt.date
        return df

    def _get_daily_stats(self, df: pd.DataFrame) -> pd.DataFrame:
        daily = df.groupby('date')['value'].agg([
            ('mean', 'mean'),
            ('max', 'max'),
            ('min', 'min'),
            ('count', 'count')
        ]).reset_index()
        return daily

    def _linear_prediction(self, daily_stats: pd.DataFrame, days_ahead: int) -> Tuple[float, float, float]:
        x = np.arange(len(daily_stats))
        y = daily_stats['max'].values

        n = len(x)
        sum_x = np.sum(x)
        sum_y = np.sum(y)
        sum_xy = np.sum(x * y)
        sum_x2 = np.sum(x ** 2)

        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x ** 2)
        intercept = (sum_y - slope * sum_x) / n

        predicted = intercept + slope * (n + days_ahead)

        residuals = y - (intercept + slope * x)
        std_error = np.std(residuals)
        margin = 1.96 * std_error * (1 + 1/n) ** 0.5

        upper = predicted + margin
        lower = predicted - margin

        return predicted, upper, lower

    def get_prediction_peak(self, server_id: int, resource_type: str) -> Dict:
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = today + timedelta(days=self.forecast_days)

        predictions = self.db.query(Prediction).filter(
            Prediction.server_id == server_id,
            Prediction.resource_type == resource_type,
            Prediction.forecast_date >= today,
            Prediction.forecast_date <= end_date
        ).all()

        if not predictions:
            return {'peak_value': 0, 'peak_date': None, 'avg_value': 0}

        upper_values = [p.upper_bound for p in predictions]
        avg_values = [p.predicted_value for p in predictions]
        max_idx = np.argmax(upper_values)

        return {
            'peak_value': round(float(upper_values[max_idx]), 2),
            'peak_date': predictions[max_idx].forecast_date,
            'avg_value': round(float(np.mean(avg_values)), 2)
        }
