import asyncio
import logging
from typing import Dict, Optional
from pathlib import Path

from src.core.game_state import GameState
from src.core.mob_controller import MobController
from src.core.combat_system import CombatSystem
from src.core.combo_manager import ComboManager
from src.core.route_manager import RouteManager
from src.utils.input_handler import InputHandler
from src.utils.config_manager import ConfigManager
from src.vision.detection import FeatureBasedDetector


class BDOBot:
    def __init__(self, settings: Dict):
        self.logger = logging.getLogger("BDOBot")
        self.settings = settings
        self.running = False

        # Config yöneticisi
        self.config = ConfigManager()

        # Game State
        self.game_state = GameState()

        # Input Handler
        self.input_handler = InputHandler(
            self.config.get_setting("game_settings.window_name")
        )

        # Mob tespiti ve kontrolü
        self.mob_detector = FeatureBasedDetector(
            self.config.get_setting("paths.templates_dir")
        )
        self.mob_controller = MobController(
            self.game_state,
            self.config.get_setting("paths.templates_dir")
        )

        # Combo Manager
        self.combo_manager = ComboManager(
            self.game_state,
            self.input_handler
        )

        # Combat System
        self.combat_system = CombatSystem(
            self.game_state,
            self.mob_controller,
            self.combo_manager
        )

        # Route Manager
        self.route_manager = RouteManager(
            self.config.get_setting("paths.scripts_dir") + "/routes"
        )

        # Bot metrics
        self.metrics = {
            "runtime": 0,
            "kills": 0,
            "deaths": 0,
            "exp_gained": 0,
            "silver_earned": 0
        }

        # Bot durumu
        self.paused = False
        self.emergency_stop = False

    async def load_class(self, class_name: str):
        """Sınıf kombolarını yükle"""
        try:
            self.logger.info(f"Sınıf yükleniyor: {class_name}")
            await self.combo_manager.load_class_combos(class_name)
        except Exception as e:
            self.logger.error(f"Sınıf yükleme hatası: {e}")
            raise

    async def load_route(self, route_name: str):
        """Grind rotasını yükle"""
        try:
            self.logger.info(f"Rota yükleniyor: {route_name}")
            await self.route_manager.load_route(route_name)
        except Exception as e:
            self.logger.error(f"Rota yükleme hatası: {e}")
            raise

    async def start(self):
        """Bot'u başlat"""
        self.running = True
        self.logger.info("Bot başlatılıyor...")

        try:
            while self.running:
                if self.paused:
                    await asyncio.sleep(1)
                    continue

                # Ana döngü
                await self._main_loop()

                # CPU kullanımını optimize et
                await asyncio.sleep(0.1)

        except KeyboardInterrupt:
            self.logger.info("Bot kapatılıyor...")
        except Exception as e:
            self.logger.error(f"Kritik hata: {e}")
            self.emergency_stop = True
        finally:
            await self.cleanup()

    async def _main_loop(self):
        """Ana bot döngüsü"""
        try:
            # Ekran görüntüsü al ve analiz et
            screen = await self.input_handler.capture_screen()

            # Mob tespiti
            mobs = await self.mob_detector.detect_mobs(screen)
            await self.mob_controller.process_frame(screen)

            # Durum analizi
            if self.game_state.character_state.value == "dead":
                await self._handle_death()
                return

            # PvP tehdidi kontrolü
            if len(self.game_state.nearby_players) > 0:
                await self.combat_system.handle_pvp_threat()
                return

            # HP/MP kontrolü
            if not await self._check_resources():
                await self._handle_low_resources()
                return

            # Combat durumu
            if self.game_state.combat_state.value != "none":
                await self.combat_system.update()
            else:
                # Rota takibi
                next_point = await self.route_manager.get_next_waypoint()
                if next_point:
                    await self._move_to_point(next_point)

            # Metrikleri güncelle
            await self._update_metrics()

        except Exception as e:
            self.logger.error(f"Ana döngü hatası: {e}")
            if self.emergency_stop:
                raise

    async def _check_resources(self) -> bool:
        """HP/MP durumunu kontrol et"""
        hp_ratio = self.game_state.stats.hp / self.game_state.stats.hp_max
        mp_ratio = self.game_state.stats.mp / self.game_state.stats.mp_max

        min_hp = self.config.get_setting("bot_settings.auto_pot.hp_threshold")
        min_mp = self.config.get_setting("bot_settings.auto_pot.mp_threshold")

        return hp_ratio > min_hp and mp_ratio > min_mp

    async def _handle_low_resources(self):
        """Düşük HP/MP durumunu yönet"""
        # Potion kullan
        if self.config.get_setting("bot_settings.auto_pot.enabled"):
            hp_key = self.config.get_keybinding("items.hp_pot")
            mp_key = self.config.get_keybinding("items.mp_pot")

            if hp_key and self.game_state.stats.hp < self.game_state.stats.hp_max * 0.7:
                await self.input_handler.press_key(hp_key)

            if mp_key and self.game_state.stats.mp < self.game_state.stats.mp_max * 0.3:
                await self.input_handler.press_key(mp_key)

    async def _handle_death(self):
        """Ölüm durumunu yönet"""
        self.metrics["deaths"] += 1

        if self.config.get_setting("bot_settings.safety.logout_on_death"):
            self.running = False
            return

        # Node'a ışınlan
        await asyncio.sleep(3)  # Respawn menüsünü bekle
        await self.input_handler.press_key('r')  # Node'a dön

    async def _move_to_point(self, point):
        """Belirtilen noktaya git"""
        try:
            # Hedefe yönel
            current_pos = self.game_state.position
            target_pos = point.position

            # Mesafe kontrolü
            distance = current_pos.distance_to(target_pos)
            if distance < 1.0:  # Hedefe ulaşıldı
                await self.route_manager.advance_to_next_waypoint()
                return

            # Hareket tuşlarını kontrol et
            if target_pos.x > current_pos.x:
                await self.input_handler.press_key('d')
            elif target_pos.x < current_pos.x:
                await self.input_handler.press_key('a')

            if target_pos.z > current_pos.z:
                await self.input_handler.press_key('w')
            elif target_pos.z < current_pos.z:
                await self.input_handler.press_key('s')

            # Sprint
            if distance > 10.0:
                await self.input_handler.hold_key('shift')

        except Exception as e:
            self.logger.error(f"Hareket hatası: {e}")

    async def _update_metrics(self):
        """Metrikleri güncelle"""
        combat_stats = self.combat_system.get_combat_stats()
        self.metrics["kills"] = combat_stats["kills"]

        # İstatistikleri kaydet
        if self.config.get_setting("debug.enabled"):
            self.logger.debug(f"Güncel metrikler: {self.metrics}")

    async def get_statistics(self) -> Dict:
        """Bot istatistiklerini al"""
        combat_stats = self.combat_system.get_combat_stats()
        combo_stats = await self.combo_manager.get_combo_stats()

        return {
            **self.metrics,
            **combat_stats,
            **combo_stats,
            "is_running": self.running,
            "is_paused": self.paused,
            "emergency_stop": self.emergency_stop
        }

    async def pause(self):
        """Bot'u duraklat"""
        self.paused = True
        self.logger.info("Bot duraklatıldı")

    async def resume(self):
        """Bot'u devam ettir"""
        self.paused = False
        self.logger.info("Bot devam ediyor")

    async def cleanup(self):
        """Kaynakları temizle"""
        self.running = False

        # Alt sistemleri temizle
        self.combat_system.cleanup()
        self.combo_manager.cleanup()
        self.route_manager.cleanup()
        self.mob_controller.cleanup()

        # Tuşları bırak
        await self.input_handler.release_all()

        self.logger.info("Bot kapatıldı")