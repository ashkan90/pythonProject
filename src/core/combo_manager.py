from lupa import LuaRuntime
import logging
import asyncio
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path
import time
from src.utils.input_handler import InputHandler
from src.core.game_state import GameState

@dataclass
class ComboAction:
    keys: List[str]
    action_type: str  # press, hold, release
    duration: float = 0.0
    animation_time: float = 0.0


@dataclass
class Combo:
    name: str
    actions: List[ComboAction]
    cooldown: float
    mp_cost: float
    range_type: str  # close, mid, long
    total_duration: float
    conditions: Dict


class ComboManager:
    def __init__(self, game_state: GameState, input_handler: InputHandler):
        self.logger = logging.getLogger("ComboManager")
        self.game_state = game_state
        self.input_handler = input_handler

        # Lua ortamını başlat
        self.lua = LuaRuntime(unpack_returned_tuples=True)

        # Kombo verileri
        self.combos: Dict[str, Combo] = {}
        self.current_combo: Optional[str] = None
        self.last_combo_time: float = 0

        # Performans metrikleri
        self.successful_skills = 0
        self.total_skills = 0

        # Kombo geçmişi
        self.combo_history: List[Tuple[str, float]] = []  # (combo_name, timestamp)
        self.max_history = 50

    async def load_class_combos(self, class_name: str, combo_dir: str = "scripts/classes"):
        """Sınıfa ait komboları yükle"""
        try:
            combo_file = Path(combo_dir) / f"{class_name.lower()}.lua"

            with open(combo_file, 'r', encoding='utf-8') as f:
                lua_code = f.read()

            # Lua kodunu çalıştır
            class_table = self.lua.execute(lua_code)

            # Komboları Python nesnelerine dönüştür
            for combo_name, combo_data in class_table.combos.items():
                actions = []
                total_duration = 0.0

                for action_data in combo_data.actions:
                    action = ComboAction(
                        keys=list(action_data.keys),
                        action_type=str(action_data.type),
                        duration=float(action_data.get('duration', 0.0)),
                        animation_time=float(action_data.get('animation_time', 0.0))
                    )
                    actions.append(action)
                    total_duration += action.duration + action.animation_time

                combo = Combo(
                    name=combo_name,
                    actions=actions,
                    cooldown=float(combo_data.cooldown),
                    mp_cost=float(combo_data.mp_cost),
                    range_type=str(combo_data.range_type),
                    total_duration=total_duration,
                    conditions=dict(combo_data.conditions)
                )

                self.combos[combo_name] = combo

            self.logger.info(f"{len(self.combos)} kombo yüklendi: {class_name}")

        except Exception as e:
            self.logger.error(f"Kombo yükleme hatası: {e}")
            raise

    async def get_combo(self, criteria: Dict) -> Optional[str]:
        """Kriterlere uygun kombo seç"""
        try:
            best_combo = None
            best_score = -1

            for combo_name, combo in self.combos.items():
                if not await self._check_combo_conditions(combo):
                    continue

                score = await self._calculate_combo_score(combo, criteria)
                if score > best_score:
                    best_score = score
                    best_combo = combo_name

            return best_combo

        except Exception as e:
            self.logger.error(f"Kombo seçim hatası: {e}")
            return None

    async def execute_combo(self, combo_name: str) -> bool:
        """Komboyu uygula"""
        try:
            if combo_name not in self.combos:
                return False

            combo = self.combos[combo_name]

            # Kombo koşullarını kontrol et
            if not await self._check_combo_conditions(combo):
                return False

            # Komboyu başlat
            self.current_combo = combo_name
            self.last_combo_time = time.time()

            # Kombo geçmişini güncelle
            self.combo_history.append((combo_name, self.last_combo_time))
            if len(self.combo_history) > self.max_history:
                self.combo_history.pop(0)

            # Kombo aksiyonlarını uygula
            for action in combo.actions:
                try:
                    # Durum kontrolü
                    if not await self._check_action_conditions():
                        await self.release_all_keys()
                        return False

                    # Aksiyonu uygula
                    if action.action_type == "press":
                        for key in action.keys:
                            await self.input_handler.press_key(key)
                    elif action.action_type == "hold":
                        for key in action.keys:
                            await self.input_handler.hold_key(key)
                        await asyncio.sleep(action.duration)
                        for key in reversed(action.keys):
                            await self.input_handler.release_key(key)
                    elif action.action_type == "release":
                        for key in action.keys:
                            await self.input_handler.release_key(key)

                    # Animasyon süresini bekle
                    if action.animation_time > 0:
                        await asyncio.sleep(action.animation_time)

                except Exception as e:
                    self.logger.error(f"Aksiyon uygulama hatası: {e}")
                    await self.release_all_keys()
                    return False

            # Kombo başarılı
            self.successful_skills += 1
            self.total_skills += 1

            # Cooldown başlat
            await self._start_cooldown(combo)

            # MP maliyetini düş
            await self._consume_mp(combo)

            return True

        except Exception as e:
            self.logger.error(f"Kombo uygulama hatası: {e}")
            await self.release_all_keys()
            return False
        finally:
            self.current_combo = None

    async def _check_combo_conditions(self, combo: Combo) -> bool:
        """Kombo koşullarını kontrol et"""
        # Cooldown kontrolü
        if not await self._check_cooldown(combo):
            return False

        # MP kontrolü
        if self.game_state.stats.mp < combo.mp_cost:
            return False

        # Özel koşullar
        try:
            conditions_met = self.lua.eval(combo.conditions.get('check', 'return true'))
            if not conditions_met:
                return False
        except Exception as e:
            self.logger.error(f"Koşul kontrolü hatası: {e}")
            return False

        return True

    async def _check_action_conditions(self) -> bool:
        """Aksiyon koşullarını kontrol et"""
        # Karakter durumu kontrolü
        if self.game_state.character_state.value in ['stunned', 'knockdown', 'dead']:
            return False

        # HP kontrolü
        if self.game_state.stats.hp <= 0:
            return False

        return True

    async def _calculate_combo_score(self, combo: Combo, criteria: Dict) -> float:
        """Kombo uygunluk skorunu hesapla"""
        score = 0.0

        # Mesafe kontrolü
        if criteria.get('range_type') == combo.range_type:
            score += 2.0

        # MP verimliliği
        if combo.mp_cost <= self.game_state.stats.mp * 0.3:
            score += 1.0

        # Cooldown durumu
        if await self._check_cooldown(combo):
            score += 1.0

        # Son kullanım zamanı
        last_use = next((_time for name, _time in reversed(self.combo_history)
                         if name == combo.name), 0)
        if time.time() - last_use > 10.0:  # 10 saniye geçmişse bonus
            score += 0.5

        return score

    async def _check_cooldown(self, combo: Combo) -> bool:
        """Cooldown durumunu kontrol et"""
        last_use = next((_time for name, _time in reversed(self.combo_history)
                         if name == combo.name), 0)
        return time.time() - last_use >= combo.cooldown

    async def _start_cooldown(self, combo: Combo):
        """Cooldown başlat"""
        await self.game_state.start_skill_cooldown(combo.name, combo.cooldown)

    async def _consume_mp(self, combo: Combo):
        """MP tüket"""
        self.game_state.stats.mp -= combo.mp_cost

    async def release_all_keys(self):
        """Tüm tuşları bırak"""
        try:
            mod_keys = ['shift', 'ctrl', 'alt']
            for key in mod_keys:
                await self.input_handler.release_key(key)

            if self.current_combo and self.current_combo in self.combos:
                combo = self.combos[self.current_combo]
                for action in combo.actions:
                    for key in action.keys:
                        await self.input_handler.release_key(key)

        except Exception as e:
            self.logger.error(f"Tuş bırakma hatası: {e}")

    async def get_combo_stats(self) -> Dict:
        """Kombo istatistiklerini al"""
        return {
            "total_combos": len(self.combos),
            "successful_skills": self.successful_skills,
            "total_skills": self.total_skills,
            "accuracy": self.successful_skills / max(1, self.total_skills),
            "last_combo": self.current_combo,
            "combo_history_length": len(self.combo_history)
        }

    def cleanup(self):
        """Kaynakları temizle"""
        self.combos.clear()
        self.combo_history.clear()
        self.current_combo = None