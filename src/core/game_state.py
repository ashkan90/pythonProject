from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple
import asyncio
import logging
from enum import Enum
import time


class CharacterState(Enum):
    IDLE = "idle"
    MOVING = "moving"
    COMBAT = "combat"
    DEAD = "dead"
    STUNNED = "stunned"
    KNOCKDOWN = "knockdown"
    FROZEN = "frozen"


class CombatState(Enum):
    NONE = "none"
    ATTACKING = "attacking"
    DEFENDING = "defending"
    CHASING = "chasing"
    ESCAPING = "escaping"


@dataclass
class Position:
    x: float
    y: float
    z: float
    rotation: float = 0.0

    def distance_to(self, other: 'Position') -> float:
        return ((self.x - other.x) ** 2 +
                (self.y - other.y) ** 2 +
                (self.z - other.z) ** 2) ** 0.5


@dataclass
class CharacterStats:
    level: int = 1
    hp: float = 100.0
    hp_max: float = 100.0
    mp: float = 100.0
    mp_max: float = 100.0
    wp: float = 100.0  # Black Desert'a özel - Warrior/Striker için
    wp_max: float = 100.0
    stamina: float = 100.0
    stamina_max: float = 100.0
    ap: int = 0
    dp: int = 0
    accuracy: int = 0
    evasion: int = 0


@dataclass
class SkillCooldown:
    skill_id: str
    remaining_time: float
    total_cooldown: float


class GameState:
    def __init__(self):
        self.logger = logging.getLogger("GameState")

        # Karakter durumu
        self.character_state: CharacterState = CharacterState.IDLE
        self.combat_state: CombatState = CombatState.NONE
        self.position = Position(0, 0, 0)
        self.stats = CharacterStats()

        # Envanter ve ekipman
        self.inventory: Dict[int, Dict] = {}
        self.equipment: Dict[str, Dict] = {}
        self.weight: float = 0.0
        self.weight_limit: float = 100.0

        # Beceri ve buff durumları
        self.active_buffs: Dict[str, float] = {}  # buff_id -> bitiş zamanı
        self.skill_cooldowns: Dict[str, SkillCooldown] = {}
        self.combat_stance: bool = False

        # Mob takibi
        self.detected_mobs: List[Dict] = []
        self.targeted_mob: Optional[Dict] = None
        self.aggro_mobs: Set[int] = set()  # mob_id listesi

        # Çevre durumu
        self.nearby_players: List[Dict] = []
        self.is_safe_zone: bool = False
        self.is_pvp_zone: bool = False

        # Performans metrikleri
        self.last_update = time.time()
        self.frame_times: List[float] = []

        # Durum kilitleri
        self._lock = asyncio.Lock()

    async def update_position(self, new_pos: Position):
        """Karakter pozisyonunu güncelle"""
        async with self._lock:
            # Hareket hızını hesapla
            time_diff = time.time() - self.last_update
            if time_diff > 0:
                distance = self.position.distance_to(new_pos)
                speed = distance / time_diff

                # Anormal hareket kontrolü
                if speed > 100:  # maksimum hız limiti
                    self.logger.warning(f"Anormal hareket hızı tespit edildi: {speed}")

            self.position = new_pos
            self.last_update = time.time()

            # Hareket durumunu güncelle
            if distance > 0.1:  # minimum hareket eşiği
                self.character_state = CharacterState.MOVING
            elif self.character_state == CharacterState.MOVING:
                self.character_state = CharacterState.IDLE

    async def update_stats(self, stats: Dict):
        """Karakter istatistiklerini güncelle"""
        async with self._lock:
            self.stats.hp = stats.get('hp', self.stats.hp)
            self.stats.mp = stats.get('mp', self.stats.mp)
            self.stats.wp = stats.get('wp', self.stats.wp)
            self.stats.stamina = stats.get('stamina', self.stats.stamina)

            # Kritik durum kontrolleri
            if self.stats.hp <= 0:
                self.character_state = CharacterState.DEAD
                self.logger.warning("Karakter öldü!")
            elif self.stats.hp < self.stats.hp_max * 0.3:
                self.logger.warning("Düşük HP!")

    async def update_combat_state(self, new_state: CombatState):
        """Savaş durumunu güncelle"""
        async with self._lock:
            if new_state != self.combat_state:
                self.combat_state = new_state
                if new_state == CombatState.ATTACKING:
                    self.character_state = CharacterState.COMBAT
                elif new_state == CombatState.NONE and self.character_state == CharacterState.COMBAT:
                    self.character_state = CharacterState.IDLE

    async def update_skill_cooldowns(self):
        """Skill cooldown'larını güncelle"""
        async with self._lock:
            current_time = time.time()
            expired_skills = []

            for skill_id, cooldown in self.skill_cooldowns.items():
                if current_time >= cooldown.remaining_time:
                    expired_skills.append(skill_id)

            for skill_id in expired_skills:
                del self.skill_cooldowns[skill_id]

    async def start_skill_cooldown(self, skill_id: str, duration: float):
        """Skill cooldown'ı başlat"""
        async with self._lock:
            end_time = time.time() + duration
            self.skill_cooldowns[skill_id] = SkillCooldown(
                skill_id=skill_id,
                remaining_time=end_time,
                total_cooldown=duration
            )

    async def can_use_skill(self, skill_id: str) -> bool:
        """Skill kullanılabilir mi kontrol et"""
        if skill_id not in self.skill_cooldowns:
            return True

        return time.time() >= self.skill_cooldowns[skill_id].remaining_time

    async def update_buffs(self):
        """Buff durumlarını güncelle"""
        async with self._lock:
            current_time = time.time()
            expired_buffs = []

            for buff_id, end_time in self.active_buffs.items():
                if current_time >= end_time:
                    expired_buffs.append(buff_id)

            for buff_id in expired_buffs:
                del self.active_buffs[buff_id]

    async def update_mobs(self, mobs: List[Dict]):
        """Tespit edilen mobları güncelle"""
        async with self._lock:
            self.detected_mobs = mobs

            # Hedef mob kontrolü
            if self.targeted_mob:
                mob_still_exists = False
                for mob in mobs:
                    if mob['id'] == self.targeted_mob['id']:
                        self.targeted_mob = mob
                        mob_still_exists = True
                        break

                if not mob_still_exists:
                    self.targeted_mob = None
                    if self.combat_state == CombatState.ATTACKING:
                        await self.update_combat_state(CombatState.NONE)

    async def update_nearby_players(self, players: List[Dict]):
        """Yakındaki oyuncuları güncelle"""
        async with self._lock:
            self.nearby_players = players

            # PvP tehdidi kontrolü
            has_threat = any(p.get('is_hostile', False) for p in players)
            if has_threat and not self.is_safe_zone:
                self.logger.warning("Yakında düşman oyuncu tespit edildi!")

    async def get_state_summary(self) -> Dict:
        """Güncel durum özeti"""
        async with self._lock:
            return {
                'character_state': self.character_state.value,
                'combat_state': self.combat_state.value,
                'position': {
                    'x': self.position.x,
                    'y': self.position.y,
                    'z': self.position.z
                },
                'stats': {
                    'hp': self.stats.hp,
                    'hp_max': self.stats.hp_max,
                    'mp': self.stats.mp,
                    'mp_max': self.stats.mp_max
                },
                'mob_count': len(self.detected_mobs),
                'player_count': len(self.nearby_players),
                'is_safe': self.is_safe_zone
            }

    def cleanup(self):
        """Kaynakları temizle"""
        self.skill_cooldowns.clear()
        self.active_buffs.clear()
        self.detected_mobs.clear()
        self.nearby_players.clear()