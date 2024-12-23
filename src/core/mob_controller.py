from typing import List, Dict, Optional, Tuple
import numpy as np
import asyncio
import logging
from dataclasses import dataclass
from src.vision.detection import FeatureBasedDetector
from src.core.game_state import GameState, Position


@dataclass
class MobInfo:
    mob_id: int
    mob_type: str
    position: Position
    health: float
    size: Tuple[int, int]  # width, height
    distance: float
    threat_level: float
    last_seen: float  # timestamp
    is_aggro: bool = False
    is_elite: bool = False


class MobController:
    def __init__(self, game_state: GameState, template_dir: str):
        self.logger = logging.getLogger("MobController")
        self.game_state = game_state

        # Mob tespiti için detector'ı başlat
        self.detector = FeatureBasedDetector(template_dir)

        # Mob takibi için değişkenler
        self.tracked_mobs: Dict[int, MobInfo] = {}
        self.current_target: Optional[MobInfo] = None
        self.mob_id_counter = 0

        # Mob grup yönetimi
        self.min_group_size = 3
        self.max_chase_distance = 50.0
        self.mob_memory_time = 3.0  # saniye

        # Performans metrikleri
        self.detection_times: List[float] = []

    async def process_frame(self, frame: np.ndarray) -> List[MobInfo]:
        """Frame'deki mobları tespit et ve takip et"""
        try:
            # Mob tespiti yap
            detections = await self.detector.detect_mobs(frame)

            # Tespit edilen mobları işle
            current_mobs: Dict[int, MobInfo] = {}
            player_pos = self.game_state.position

            for detection in detections:
                mob_type = detection['mob_type']
                position = self._screen_to_world_pos(detection['bbox'])
                distance = player_pos.distance_to(position)

                # Mevcut takip edilen mob mu kontrol et
                tracked_mob = self._find_matching_mob(position, distance)

                if tracked_mob:
                    # Mevcut mobu güncelle
                    mob_id = tracked_mob.mob_id
                    tracked_mob.position = position
                    tracked_mob.distance = distance
                    tracked_mob.last_seen = asyncio.get_event_loop().time()
                    current_mobs[mob_id] = tracked_mob
                else:
                    # Yeni mob oluştur
                    mob_id = self._generate_mob_id()
                    new_mob = MobInfo(
                        mob_id=mob_id,
                        mob_type=mob_type,
                        position=position,
                        health=100.0,
                        size=detection['bbox'][2:],
                        distance=distance,
                        threat_level=self._calculate_threat_level(detection),
                        last_seen=asyncio.get_event_loop().time(),
                        is_elite='elite' in detection
                    )
                    current_mobs[mob_id] = new_mob

            # Eski mobları temizle ve güncelle
            self._cleanup_old_mobs()
            self.tracked_mobs = current_mobs

            # Game state'i güncelle
            await self.game_state.update_mobs([
                self._mob_info_to_dict(mob) for mob in current_mobs.values()
            ])

            return list(current_mobs.values())

        except Exception as e:
            self.logger.error(f"Frame işleme hatası: {e}")
            return []

    def _find_matching_mob(self, position: Position, distance: float) -> Optional[MobInfo]:
        """Pozisyona en yakın eşleşen mobu bul"""
        best_match = None
        min_distance = float('inf')

        for mob in self.tracked_mobs.values():
            dist = mob.position.distance_to(position)
            if dist < min_distance and dist < 5.0:  # 5 birim maksimum eşleşme mesafesi
                min_distance = dist
                best_match = mob

        return best_match

    def _screen_to_world_pos(self, bbox: Tuple[int, int, int, int]) -> Position:
        """Ekran koordinatlarını dünya koordinatlarına çevir"""
        x, y, w, h = bbox
        center_x = x + w / 2
        center_y = y + h / 2

        # Basit projeksiyon - gerçek oyun için özelleştirilmeli
        world_x = center_x
        world_y = 0  # Y ekseni yükseklik
        world_z = center_y

        return Position(world_x, world_y, world_z)

    def _calculate_threat_level(self, detection: Dict) -> float:
        """Mob tehdit seviyesini hesapla"""
        threat = 0.0

        # Boyut bazlı tehdit
        size = detection['bbox'][2] * detection['bbox'][3]
        threat += size / 10000.0  # normalize

        # Elite mob kontrolü
        if detection.get('is_elite', False):
            threat += 0.5

        # Mesafe bazlı tehdit
        if detection.get('distance', 0) < 10.0:
            threat += 0.3

        return min(threat, 1.0)

    def _cleanup_old_mobs(self):
        """Belirli süre görülmeyen mobları temizle"""
        current_time = asyncio.get_event_loop().time()

        for mob_id, mob in list(self.tracked_mobs.items()):
            if current_time - mob.last_seen > self.mob_memory_time:
                del self.tracked_mobs[mob_id]

    def _generate_mob_id(self) -> int:
        """Unique mob ID üret"""
        self.mob_id_counter += 1
        return self.mob_id_counter

    async def select_target(self) -> Optional[MobInfo]:
        """En uygun hedefi seç"""
        if not self.tracked_mobs:
            return None

        # Hedef seçim kriterleri
        candidates = []
        player_pos = self.game_state.position

        for mob in self.tracked_mobs.values():
            score = 0.0

            # Mesafe puanı (yakın = yüksek puan)
            distance_score = 1.0 - (mob.distance / self.max_chase_distance)
            score += distance_score * 0.4

            # Grup puanı
            group_score = self._calculate_group_score(mob)
            score += group_score * 0.3

            # Tehdit puanı
            score += mob.threat_level * 0.2

            # Elite bonus
            if mob.is_elite:
                score += 0.1

            candidates.append((mob, score))

        # En yüksek puanlı mobu seç
        if candidates:
            best_mob, _ = max(candidates, key=lambda x: x[1])
            self.current_target = best_mob
            return best_mob

        return None

    def _calculate_group_score(self, center_mob: MobInfo) -> float:
        """Mob etrafındaki grup yoğunluğunu hesapla"""
        nearby_count = 0

        for mob in self.tracked_mobs.values():
            if mob.mob_id != center_mob.mob_id:
                if center_mob.position.distance_to(mob.position) < 15.0:  # 15 birim grup mesafesi
                    nearby_count += 1

        return min(nearby_count / self.min_group_size, 1.0)

    def _mob_info_to_dict(self, mob: MobInfo) -> Dict:
        """MobInfo nesnesini dictionary'ye çevir"""
        return {
            'id': mob.mob_id,
            'type': mob.mob_type,
            'position': {
                'x': mob.position.x,
                'y': mob.position.y,
                'z': mob.position.z
            },
            'health': mob.health,
            'distance': mob.distance,
            'threat_level': mob.threat_level,
            'is_aggro': mob.is_aggro,
            'is_elite': mob.is_elite
        }

    async def get_mob_group_positions(self) -> List[Position]:
        """Mob gruplarının merkez noktalarını hesapla"""
        if not self.tracked_mobs:
            return []

        # Basit grup tespiti - gelişmiş kümeleme eklenebilir
        groups = []
        processed = set()

        for mob_id, mob in self.tracked_mobs.items():
            if mob_id in processed:
                continue

            # Mob'un etrafındaki diğer mobları bul
            group = [mob]
            processed.add(mob_id)

            for other_id, other_mob in self.tracked_mobs.items():
                if other_id not in processed:
                    if mob.position.distance_to(other_mob.position) < 15.0:
                        group.append(other_mob)
                        processed.add(other_id)

            if len(group) >= self.min_group_size:
                # Grup merkezi
                center = Position(
                    x=sum(m.position.x for m in group) / len(group),
                    y=sum(m.position.y for m in group) / len(group),
                    z=sum(m.position.z for m in group) / len(group)
                )
                groups.append(center)

        return groups

    async def is_target_valid(self) -> bool:
        """Mevcut hedefin geçerli olup olmadığını kontrol et"""
        if not self.current_target:
            return False

        # Hedef hala takip ediliyor mu?
        if self.current_target.mob_id not in self.tracked_mobs:
            return False

        # Mesafe kontrolü
        if self.current_target.distance > self.max_chase_distance:
            return False

        return True

    def cleanup(self):
        """Kaynakları temizle"""
        self.tracked_mobs.clear()
        self.current_target = None
        self.detector.cleanup()