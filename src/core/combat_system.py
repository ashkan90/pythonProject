import asyncio
import logging
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from src.core.game_state import GameState, Position, CombatState
from src.core.combo_manager import ComboManager
from src.core.mob_controller import MobController, MobInfo


@dataclass
class CombatMetrics:
    damage_dealt: float = 0.0
    damage_taken: float = 0.0
    skill_accuracy: float = 0.0
    combat_time: float = 0.0
    kills: int = 0


class CombatSystem:
    def __init__(self, game_state: GameState,
                 mob_controller: MobController,
                 combo_manager: ComboManager,
                 config: Dict = None):
        self.logger = logging.getLogger("CombatSystem")
        self.game_state = game_state
        self.mob_controller = mob_controller
        self.combo_manager = combo_manager
        self.config = config or {}

        # Combat durumu
        self.in_combat = False
        self.current_target: Optional[MobInfo] = None
        self.metrics = CombatMetrics()

        # Savaş parametreleri
        self.min_mob_count = self.config.get('min_mob_count', 3)
        self.max_chase_distance = self.config.get('max_chase_distance', 50.0)
        self.min_hp_percent = self.config.get('min_hp_percent', 0.3)
        self.min_mp_percent = self.config.get('min_mp_percent', 0.2)

        # Combat kontrolleri
        self.last_position_check = Position(0, 0, 0)
        self.stuck_counter = 0
        self.max_stuck_time = 5  # 5 saniye

        # PvP kontrolü
        self.pvp_enabled = self.config.get('pvp_enabled', False)
        self.last_pvp_check = 0

        # Combat zamanlaması
        self.last_combat_time = 0
        self.combat_reset_time = 5.0  # 5 saniye savaş dışı kalınca reset

    async def update(self) -> None:
        """Ana combat döngüsü"""
        try:
            current_time = asyncio.get_event_loop().time()

            # Combat durumu kontrolü
            if not self.in_combat and not await self._should_enter_combat():
                return

            # Resource kontrolü
            if not await self._check_resources():
                await self._handle_low_resources()
                return

            # PvP tehdidi kontrolü
            if await self._check_pvp_threat():
                await self._handle_pvp_threat()
                return

            # Hedef kontrolü ve seçimi
            if not self.current_target or not await self._is_target_valid():
                self.current_target = await self._select_new_target()
                if not self.current_target:
                    await self._exit_combat()
                    return

            # Combat eylemlerini uygula
            await self._execute_combat_actions()

            # Metrik güncelleme
            self._update_metrics(current_time)

        except Exception as e:
            self.logger.error(f"Combat update hatası: {e}")
            await self._emergency_exit()

    async def _should_enter_combat(self) -> bool:
        """Combat'a girilmeli mi?"""
        if len(self.mob_controller.tracked_mobs) < self.min_mob_count:
            return False

        if self.game_state.character_state.value in ['stunned', 'knockdown', 'dead']:
            return False

        return True

    async def _check_resources(self) -> bool:
        """HP/MP kontrolü"""
        hp_percent = self.game_state.stats.hp / self.game_state.stats.hp_max
        mp_percent = self.game_state.stats.mp / self.game_state.stats.mp_max

        return (hp_percent > self.min_hp_percent and
                mp_percent > self.min_mp_percent)

    async def _handle_low_resources(self) -> None:
        """Düşük resource durumunu yönet"""
        # Combat'tan çık
        await self._exit_combat()

        # Güvenli noktaya git
        safe_point = await self.mob_controller.get_nearest_special_point(
            self.game_state.position,
            "safe_spot"
        )

        if safe_point:
            self.logger.info("Güvenli noktaya gidiliyor...")
            # Hareket mantığı burada uygulanacak

    async def _check_pvp_threat(self) -> bool:
        """PvP tehdidi var mı?"""
        current_time = asyncio.get_event_loop().time()
        if current_time - self.last_pvp_check < 1.0:  # 1 saniyede bir kontrol
            return False

        self.last_pvp_check = current_time
        return len(self.game_state.nearby_players) > 0 and not self.pvp_enabled

    async def _handle_pvp_threat(self) -> None:
        """PvP tehdidini yönet"""
        self.logger.warning("PvP tehdidi tespit edildi!")
        await self._emergency_exit()

        if self.config.get('channel_swap_on_pvp', False):
            # Kanal değiştirme mantığı
            pass

    async def _select_new_target(self) -> Optional[MobInfo]:
        """Yeni hedef seç"""
        # Önce grup hedeflerini kontrol et
        mob_groups = await self.mob_controller.get_mob_group_positions()
        if mob_groups:
            nearest_group = min(mob_groups,
                                key=lambda pos: self.game_state.position.distance_to(pos))
            return await self.mob_controller.select_target_near_position(nearest_group)

        # Tek hedef seç
        return await self.mob_controller.select_target()

    async def _is_target_valid(self) -> bool:
        """Hedef hala geçerli mi?"""
        if not self.current_target:
            return False

        # Mesafe kontrolü
        distance = self.game_state.position.distance_to(self.current_target.position)
        if distance > self.max_chase_distance:
            return False

        # Hedef hala yaşıyor mu?
        if self.current_target.health <= 0:
            self.metrics.kills += 1
            return False

        return True

    async def _execute_combat_actions(self) -> None:
        """Combat eylemlerini uygula"""
        # Hedefe yönel
        await self._face_target()

        # Mesafeye göre kombo seç
        distance = self.game_state.position.distance_to(self.current_target.position)
        criteria = {
            'range_type': 'close' if distance < 5 else 'mid' if distance < 15 else 'long',
            'target_count': len(self.mob_controller.tracked_mobs),
            'is_elite': self.current_target.is_elite
        }

        # Kombo uygula
        combo = await self.combo_manager.get_combo(criteria)
        if combo:
            success = await self.combo_manager.execute_combo(combo)
            if not success:
                self.logger.warning(f"Kombo başarısız: {combo}")

    async def _face_target(self) -> None:
        """Hedefe dön"""
        if not self.current_target:
            return

        try:
            # Hedef ve karakter arasındaki açıyı hesapla
            target_pos = self.current_target.position
            player_pos = self.game_state.position

            dx = target_pos.x - player_pos.x
            dz = target_pos.z - player_pos.z

            target_angle = np.arctan2(dz, dx)
            current_angle = self.game_state.position.rotation

            # En kısa rotasyonu hesapla
            angle_diff = (target_angle - current_angle + np.pi) % (2 * np.pi) - np.pi

            # Dönüş yönünü belirle ve uygula
            if abs(angle_diff) > 0.1:  # 0.1 radyan tolerans
                turn_key = 'e' if angle_diff > 0 else 'q'
                await self.combo_manager.press_key(turn_key, abs(angle_diff) * 0.1)

        except Exception as e:
            self.logger.error(f"Hedef yönelme hatası: {e}")

    async def _exit_combat(self) -> None:
        """Combat'tan çık"""
        self.in_combat = False
        self.current_target = None
        await self.game_state.update_combat_state(CombatState.NONE)
        await self.combo_manager.release_all_keys()

        self._update_metrics(asyncio.get_event_loop().time())

    async def _emergency_exit(self) -> None:
        """Acil durum çıkışı"""
        await self._exit_combat()

        # Kaçış kombosu
        escape_combo = await self.combo_manager.get_combo({"range_type": "escape"})
        if escape_combo:
            await self.combo_manager.execute_combo(escape_combo)

    def _update_metrics(self, current_time: float) -> None:
        """Combat metriklerini güncelle"""
        if self.in_combat:
            self.metrics.combat_time = current_time - self.last_combat_time

        # Skill doğruluğu güncelle
        if self.combo_manager.total_skills > 0:
            self.metrics.skill_accuracy = (self.combo_manager.successful_skills /
                                           self.combo_manager.total_skills)

    def get_combat_stats(self) -> Dict:
        """Combat istatistiklerini al"""
        return {
            "in_combat": self.in_combat,
            "current_target": self.current_target.mob_type if self.current_target else None,
            "damage_dealt": self.metrics.damage_dealt,
            "damage_taken": self.metrics.damage_taken,
            "skill_accuracy": self.metrics.skill_accuracy,
            "combat_time": self.metrics.combat_time,
            "kills": self.metrics.kills
        }

    def cleanup(self) -> None:
        """Kaynakları temizle"""
        self.in_combat = False
        self.current_target = None
        self.metrics = CombatMetrics()