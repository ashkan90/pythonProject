import json
import os
from typing import Dict, Any, Optional
from pathlib import Path
import logging
import definitions


class ConfigManager:
    def __init__(self, config_dir: str = definitions.ROOT_DIR + "/config"):
        self.logger = logging.getLogger("ConfigManager")
        self.config_dir = Path(config_dir)
        self.settings: Dict[str, Any] = {}
        self.keybindings: Dict[str, Any] = {}
        self.load_configs()

    def load_configs(self):
        """Tüm yapılandırma dosyalarını yükle"""
        try:
            # Settings dosyasını yükle
            settings_path = self.config_dir / "settings.json"
            with open(settings_path, 'r', encoding='utf-8') as f:
                self.settings = json.load(f)

            # Tuş bağlantılarını yükle
            keybindings_path = self.config_dir / "keybindings.json"
            with open(keybindings_path, 'r', encoding='utf-8') as f:
                self.keybindings = json.load(f)

            self.logger.info("Yapılandırmalar başarıyla yüklendi")

        except FileNotFoundError as e:
            self.logger.error(f"Yapılandırma dosyası bulunamadı: {e}")
            raise
        except json.JSONDecodeError as e:
            self.logger.error(f"Yapılandırma dosyası formatı hatalı: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Yapılandırma yükleme hatası: {e}")
            raise

    def get_setting(self, path: str, default: Any = None) -> Any:
        """Nokta notasyonu ile ayar değeri al
        Örnek: config.get_setting("bot_settings.auto_pot.enabled")
        """
        try:
            value = self.settings
            for key in path.split('.'):
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default

    def get_keybinding(self, action_path: str) -> Optional[str]:
        """Nokta notasyonu ile tuş bağlantısı al
        Örnek: config.get_keybinding("combat.basic_attack")
        """
        try:
            value = self.keybindings
            for key in action_path.split('.'):
                value = value[key]
            return value
        except (KeyError, TypeError):
            return None

    def update_setting(self, path: str, value: Any):
        """Belirli bir ayarı güncelle ve kaydet"""
        try:
            # Ayarı güncelle
            current = self.settings
            *path_parts, final_key = path.split('.')

            for key in path_parts:
                current = current[key]
            current[final_key] = value

            # Dosyaya kaydet
            settings_path = self.config_dir / "settings.json"
            with open(settings_path, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=4)

            self.logger.info(f"Ayar güncellendi: {path} = {value}")

        except Exception as e:
            self.logger.error(f"Ayar güncelleme hatası: {e}")
            raise

    def update_keybinding(self, action_path: str, key: str):
        """Tuş bağlantısını güncelle ve kaydet"""
        try:
            # Tuş bağlantısını güncelle
            current = self.keybindings
            *path_parts, final_key = action_path.split('.')

            for key in path_parts:
                current = current[key]
            current[final_key] = key

            # Dosyaya kaydet
            keybindings_path = self.config_dir / "keybindings.json"
            with open(keybindings_path, 'w', encoding='utf-8') as f:
                json.dump(self.keybindings, f, indent=4)

            self.logger.info(f"Tuş bağlantısı güncellendi: {action_path} = {key}")

        except Exception as e:
            self.logger.error(f"Tuş bağlantısı güncelleme hatası: {e}")
            raise

    def validate_configs(self) -> bool:
        """Yapılandırmaların doğruluğunu kontrol et"""
        try:
            # Gerekli ayarların varlığını kontrol et
            required_settings = [
                "game_settings.window_name",
                "game_settings.resolution",
                "game_settings.class_name",
                "paths.templates_dir",
                "paths.logs_dir"
            ]

            for setting in required_settings:
                if self.get_setting(setting) is None:
                    self.logger.error(f"Gerekli ayar eksik: {setting}")
                    return False

            # Gerekli tuş bağlantılarının varlığını kontrol et
            required_keybindings = [
                "movement.forward",
                "movement.backward",
                "combat.basic_attack",
                "combat.strong_attack"
            ]

            for binding in required_keybindings:
                if self.get_keybinding(binding) is None:
                    self.logger.error(f"Gerekli tuş bağlantısı eksik: {binding}")
                    return False

            return True

        except Exception as e:
            self.logger.error(f"Yapılandırma doğrulama hatası: {e}")
            return False