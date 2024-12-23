import logging
import logging.handlers
import sys
from pathlib import Path
from datetime import datetime
import json
from typing import Optional, Dict, Any


class BotLogger:
    def __init__(self, log_dir: str = "data/logs", config: Optional[Dict[str, Any]] = None):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Varsayılan ayarlar
        self.config = {
            'log_level': logging.INFO,
            'max_file_size': 5 * 1024 * 1024,  # 5MB
            'backup_count': 5,
            'console_output': True
        }

        if config:
            self.config.update(config)

        # Ana logger'ı yapılandır
        self.setup_logger()

        # Alt sistem logger'larını oluştur
        self.setup_subsystem_loggers()

    def setup_logger(self):
        """Ana logger'ı yapılandır"""
        # Root logger'ı temizle
        logging.getLogger().handlers = []

        # Ana logger'ı oluştur
        logger = logging.getLogger("BDOBot")
        logger.setLevel(self.config['log_level'])
        logger.propagate = False

        # Formatı ayarla
        formatter = logging.Formatter(
            '%(asctime)s | %(name)-12s | %(levelname)-8s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # Dosya handler'ı
        log_file = self.log_dir / f"bot_{datetime.now():%Y%m%d}.log"
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=self.config['max_file_size'],
            backupCount=self.config['backup_count'],
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # Konsol handler'ı
        if self.config['console_output']:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)

    def setup_subsystem_loggers(self):
        """Alt sistemler için logger'ları yapılandır"""
        subsystems = [
            "Vision",
            "Combat",
            "Movement",
            "InputHandler",
            "RouteManager",
            "ConfigManager"
        ]

        for subsystem in subsystems:
            logger = logging.getLogger(subsystem)
            logger.setLevel(self.config['log_level'])
            logger.propagate = True  # Ana logger'a gönder

    def create_session_log(self):
        """Yeni bir oturum logu oluştur"""
        session_file = self.log_dir / f"session_{datetime.now():%Y%m%d_%H%M%S}.json"

        session_data = {
            "start_time": datetime.now().isoformat(),
            "events": []
        }

        with open(session_file, 'w', encoding='utf-8') as f:
            json.dump(session_data, f, indent=4)

        return session_file

    def log_session_event(self, session_file: Path, event_type: str, event_data: Dict):
        """Oturum olayını kaydet"""
        try:
            with open(session_file, 'r+', encoding='utf-8') as f:
                session_data = json.load(f)

                event = {
                    "timestamp": datetime.now().isoformat(),
                    "type": event_type,
                    "data": event_data
                }

                session_data["events"].append(event)

                f.seek(0)
                json.dump(session_data, f, indent=4)
                f.truncate()

        except Exception as e:
            logging.getLogger("BDOBot").error(f"Oturum logu kaydetme hatası: {e}")

    def get_debug_logger(self, name: str) -> logging.Logger:
        """Debug logger'ı oluştur"""
        logger = logging.getLogger(f"Debug.{name}")
        logger.setLevel(logging.DEBUG)

        # Debug dosyası
        debug_file = self.log_dir / f"debug_{name}.log"
        handler = logging.FileHandler(debug_file, encoding='utf-8')

        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)

        logger.addHandler(handler)
        return logger

    def rotate_logs(self, max_age_days: int = 7):
        """Eski log dosyalarını temizle"""
        try:
            current_time = datetime.now()
            for log_file in self.log_dir.glob("*.log"):
                file_time = datetime.fromtimestamp(log_file.stat().st_mtime)
                age_days = (current_time - file_time).days

                if age_days > max_age_days:
                    log_file.unlink()

            # JSON session logları için de aynısını yap
            for session_file in self.log_dir.glob("session_*.json"):
                file_time = datetime.fromtimestamp(session_file.stat().st_mtime)
                age_days = (current_time - file_time).days

                if age_days > max_age_days:
                    session_file.unlink()

        except Exception as e:
            logging.getLogger("BDOBot").error(f"Log rotasyon hatası: {e}")

    def create_stat_logger(self):
        """İstatistik logger'ı oluştur"""
        stats_file = self.log_dir / f"stats_{datetime.now():%Y%m%d}.csv"

        # CSV başlıklarını oluştur
        if not stats_file.exists():
            with open(stats_file, 'w', encoding='utf-8') as f:
                headers = [
                    "timestamp",
                    "mob_kills",
                    "silver_earned",
                    "exp_gained",
                    "items_collected",
                    "death_count",
                    "combat_time",
                    "travel_time"
                ]
                f.write(','.join(headers) + '\n')

        return stats_file

    def log_stats(self, stats_file: Path, stats: Dict[str, Any]):
        """İstatistikleri kaydet"""
        try:
            with open(stats_file, 'a', encoding='utf-8') as f:
                row = [
                    datetime.now().isoformat(),
                    str(stats.get('mob_kills', 0)),
                    str(stats.get('silver_earned', 0)),
                    str(stats.get('exp_gained', 0)),
                    str(stats.get('items_collected', 0)),
                    str(stats.get('death_count', 0)),
                    str(stats.get('combat_time', 0)),
                    str(stats.get('travel_time', 0))
                ]
                f.write(','.join(row) + '\n')

        except Exception as e:
            logging.getLogger("BDOBot").error(f"İstatistik kaydetme hatası: {e}")

    def create_error_report(self, error: Exception, context: Dict[str, Any]):
        """Hata raporu oluştur"""
        report_file = self.log_dir / f"error_{datetime.now():%Y%m%d_%H%M%S}.json"

        report_data = {
            "timestamp": datetime.now().isoformat(),
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": logging.traceback.format_exc(),
            "context": context
        }

        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=4)

        return report_file