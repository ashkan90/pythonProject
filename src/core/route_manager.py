from lupa import LuaRuntime
import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path
import asyncio


@dataclass
class Position:
    x: float
    y: float
    z: float

    def distance_to(self, other: 'Position') -> float:
        return ((self.x - other.x) ** 2 +
                (self.y - other.y) ** 2 +
                (self.z - other.z) ** 2) ** 0.5


@dataclass
class Waypoint:
    position: Position
    type: str
    mob_density: float = 0.0
    radius: float = 0.0
    min_mob_count: int = 0
    wait_time: float = 0.0


class RouteManager:
    def __init__(self, routes_dir: str):
        self.logger = logging.getLogger("RouteManager")
        self.routes_dir = Path(routes_dir)
        self.lua = LuaRuntime(unpack_returned_tuples=True)

        self.current_route = None
        self.current_waypoint_index = 0
        self.alternative_route = None

        # Rota durumu
        self.last_position = None
        self.stuck_counter = 0
        self.visited_points = set()

    async def load_route(self, route_name: str) -> bool:
        """Lua rota dosyasını yükle"""
        try:
            route_path = self.routes_dir / f"{route_name}.lua"

            with open(route_path, 'r', encoding='utf-8') as f:
                route_code = f.read()

            # Lua kodunu çalıştır ve rota tablosunu al
            self.current_route = self.lua.execute(route_code)
            self.current_waypoint_index = 0
            self.alternative_route = None

            self.logger.info(f"Rota yüklendi: {route_name}")
            return True

        except Exception as e:
            self.logger.error(f"Rota yükleme hatası: {e}")
            return False

    def _convert_lua_position(self, lua_pos: Dict) -> Position:
        """Lua pozisyon tablosunu Python Position nesnesine çevir"""
        return Position(
            x=float(lua_pos['x']),
            y=float(lua_pos['y']),
            z=float(lua_pos['z'])
        )

    def _convert_lua_waypoint(self, lua_wp: Dict) -> Waypoint:
        """Lua waypoint tablosunu Python Waypoint nesnesine çevir"""
        return Waypoint(
            position=self._convert_lua_position(lua_wp['position']),
            type=str(lua_wp['type']),
            mob_density=float(lua_wp.get('mob_density', 0.0)),
            radius=float(lua_wp.get('radius', 0.0)),
            min_mob_count=int(lua_wp.get('min_mob_count', 0)),
            wait_time=float(lua_wp.get('wait_time', 0.0))
        )

    async def get_next_waypoint(self) -> Optional[Waypoint]:
        """Rotadaki bir sonraki waypoint'i al"""
        if not self.current_route:
            return None

        waypoints = (self.alternative_route or self.current_route)['waypoints']

        if self.current_waypoint_index >= len(waypoints):
            self.current_waypoint_index = 0

        waypoint = waypoints[self.current_waypoint_index]
        return self._convert_lua_waypoint(waypoint)

    async def advance_to_next_waypoint(self):
        """Bir sonraki waypoint'e geç"""
        self.current_waypoint_index += 1
        waypoints = (self.alternative_route or self.current_route)['waypoints']

        if self.current_waypoint_index >= len(waypoints):
            self.current_waypoint_index = 0

    async def check_route_conditions(self, player_status: Dict) -> bool:
        """Rota koşullarını kontrol et"""
        if not self.current_route:
            return False

        try:
            requirements = self.current_route.conditions.requirements()

            # Temel gereksinimleri kontrol et
            if (player_status.get('level', 0) < requirements['min_level'] or
                    player_status.get('ap', 0) < requirements['min_ap'] or
                    player_status.get('dp', 0) < requirements['min_dp']):
                return False

            return True

        except Exception as e:
            self.logger.error(f"Rota koşul kontrolü hatası: {e}")
            return False

    async def should_switch_route(self, current_position: Position,
                                  mob_count: int,
                                  player_status: Dict) -> Optional[str]:
        """Rota değiştirme koşullarını kontrol et"""
        if not self.current_route:
            return None

        try:
            # Lua switch_route fonksiyonunu çağır
            new_route = self.current_route.conditions.switch_route(
                {'x': current_position.x, 'y': current_position.y, 'z': current_position.z},
                mob_count,
                player_status
            )

            return new_route

        except Exception as e:
            self.logger.error(f"Rota değiştirme kontrolü hatası: {e}")
            return None

    async def should_loot_item(self, item_info: Dict) -> bool:
        """Öğenin toplanıp toplanmayacağını kontrol et"""
        if not self.current_route:
            return False

        try:
            return self.current_route.functions.should_loot(item_info)
        except Exception as e:
            self.logger.error(f"Loot kontrolü hatası: {e}")
            return False

    async def get_mob_priority(self, mob_info: Dict) -> int:
        """Mob öncelik değerini al"""
        if not self.current_route:
            return 0

        try:
            return self.current_route.functions.prioritize_mob(mob_info)
        except Exception as e:
            self.logger.error(f"Mob önceliklendirme hatası: {e}")
            return 0

    async def get_nearest_special_point(self,
                                        current_position: Position,
                                        point_type: str) -> Optional[Position]:
        """En yakın özel noktayı bul"""
        if not self.current_route:
            return None

        try:
            special_points = self.current_route['special_points']
            points = []

            # İstenen tipteki noktaları topla
            for category in special_points.values():
                points.extend([p for p in category if p['type'] == point_type])

            if not points:
                return None

            # En yakın noktayı bul
            nearest_point = min(
                points,
                key=lambda p: current_position.distance_to(
                    self._convert_lua_position(p['position'])
                )
            )

            return self._convert_lua_position(nearest_point['position'])

        except Exception as e:
            self.logger.error(f"Özel nokta bulma hatası: {e}")
            return None

    async def update_position(self, current_position: Position):
        """Mevcut pozisyonu güncelle ve sıkışma kontrolü yap"""
        if self.last_position:
            distance = current_position.distance_to(self.last_position)

            # Sıkışma kontrolü
            if distance < 1.0:  # 1 birimden az hareket
                self.stuck_counter += 1
            else:
                self.stuck_counter = 0

        self.last_position = current_position

    async def is_stuck(self) -> bool:
        """Karakterin sıkışıp sıkışmadığını kontrol et"""
        return self.stuck_counter > 10  # 10 kontrol sonrası hala hareket yoksa

    async def reset_stuck_counter(self):
        """Sıkışma sayacını sıfırla"""
        self.stuck_counter = 0

    def cleanup(self):
        """Kaynakları temizle"""
        self.current_route = None
        self.alternative_route = None
        self.last_position = None
        self.stuck_counter = 0
        self.visited_points.clear()