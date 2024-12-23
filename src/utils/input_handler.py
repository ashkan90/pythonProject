import platform

import pyautogui
import random
import time
import asyncio
if platform.system() == "Windows":
    import win32gui
    import win32con
import logging
from typing import Tuple, Optional, List
import numpy as np
from dataclasses import dataclass


@dataclass
class MouseMovement:
    start: Tuple[int, int]
    end: Tuple[int, int]
    duration: float
    curve_points: List[Tuple[int, int]]


class InputHandler:
    def __init__(self, window_name: str):
        self.logger = logging.getLogger("InputHandler")
        self.window_name = window_name
        self.window_handle = None

        # Güvenlik ayarları
        self.min_delay = 0.05
        self.max_delay = 0.15
        self.last_action_time = 0
        self.action_count = 0

        # Fare hareketi için spline noktaları
        self.spline_points = 50

        # PyAutoGUI güvenlik limitleri
        pyautogui.MINIMUM_DURATION = 0.05
        pyautogui.MINIMUM_SLEEP = 0.05
        pyautogui.PAUSE = 0.1

        self.find_game_window()

    def find_game_window(self):
        """Oyun penceresini bul"""
        try:
            self.window_handle = win32gui.FindWindow(None, self.window_name)
            if not self.window_handle:
                self.logger.error(f"Oyun penceresi bulunamadı: {self.window_name}")
                raise Exception("Game window not found")
        except Exception as e:
            self.logger.error(f"Pencere arama hatası: {e}")
            raise

    def is_window_active(self) -> bool:
        """Oyun penceresinin aktif olup olmadığını kontrol et"""
        try:
            return self.window_handle == win32gui.GetForegroundWindow()
        except Exception:
            return False

    def activate_window(self):
        """Oyun penceresini aktif hale getir"""
        try:
            if not self.is_window_active():
                win32gui.SetForegroundWindow(self.window_handle)
                time.sleep(0.1)  # Pencerenin aktif olmasını bekle
        except Exception as e:
            self.logger.error(f"Pencere aktivasyon hatası: {e}")

    async def _add_human_delay(self):
        """İnsan benzeri gecikme ekle"""
        # Son işlemden bu yana geçen süreyi kontrol et
        current_time = time.time()
        time_diff = current_time - self.last_action_time

        # Çok hızlı işlem yapılıyorsa ek gecikme ekle
        if time_diff < self.min_delay:
            delay = random.uniform(self.min_delay, self.max_delay)
            await asyncio.sleep(delay)

        self.last_action_time = time.time()
        self.action_count += 1

        # Belirli sayıda işlem sonrası uzun mola
        if self.action_count > 50:
            await asyncio.sleep(random.uniform(0.5, 1.0))
            self.action_count = 0

    def _generate_bezier_curve(self,
                               start: Tuple[int, int],
                               end: Tuple[int, int],
                               control_points: int = 2) -> List[Tuple[int, int]]:
        """Bezier eğrisi oluştur"""
        # Kontrol noktalarını rastgele oluştur
        control_pts = []
        for _ in range(control_points):
            x = random.randint(min(start[0], end[0]), max(start[0], end[0]))
            y = random.randint(min(start[1], end[1]), max(start[1], end[1]))
            control_pts.append((x, y))

        # Bezier eğrisi noktalarını hesapla
        points = []
        for t in np.linspace(0, 1, self.spline_points):
            point = start
            for i in range(control_points):
                point = (
                    point[0] * (1 - t) + control_pts[i][0] * t,
                    point[1] * (1 - t) + control_pts[i][1] * t
                )
            points.append((int(point[0]), int(point[1])))

        return points

    async def move_mouse(self, x: int, y: int, duration: Optional[float] = None):
        """Fareyi belirtilen konuma insan benzeri hareketle götür"""
        try:
            if not self.is_window_active():
                self.activate_window()

            await self._add_human_delay()

            # Mevcut fare konumunu al
            start_x, start_y = pyautogui.position()

            # Hareket süresi belirtilmemişse mesafeye göre hesapla
            if duration is None:
                distance = ((x - start_x) ** 2 + (y - start_y) ** 2) ** 0.5
                duration = min(0.5, distance / 2000.0 + 0.2)

            # Bezier eğrisi oluştur
            curve_points = self._generate_bezier_curve(
                (start_x, start_y),
                (x, y)
            )

            # Eğri üzerinde hareket et
            time_per_point = duration / len(curve_points)
            for point in curve_points:
                pyautogui.moveTo(point[0], point[1], _pause=False)
                await asyncio.sleep(time_per_point)

        except Exception as e:
            self.logger.error(f"Fare hareketi hatası: {e}")

    async def click(self, button: str = 'left'):
        """Fare tıklaması yap"""
        try:
            await self._add_human_delay()
            pyautogui.click(button=button)
        except Exception as e:
            self.logger.error(f"Tıklama hatası: {e}")

    async def press_key(self, key: str, duration: Optional[float] = None):
        """Tuşa bas"""
        try:
            if not self.is_window_active():
                self.activate_window()

            await self._add_human_delay()

            if duration:
                pyautogui.keyDown(key)
                await asyncio.sleep(duration)
                pyautogui.keyUp(key)
            else:
                pyautogui.press(key)

        except Exception as e:
            self.logger.error(f"Tuş basma hatası: {e}")

    async def hold_key(self, key: str):
        """Tuşu basılı tut"""
        try:
            await self._add_human_delay()
            pyautogui.keyDown(key)
        except Exception as e:
            self.logger.error(f"Tuş basılı tutma hatası: {e}")

    async def release_key(self, key: str):
        """Tuşu bırak"""
        try:
            await self._add_human_delay()
            pyautogui.keyUp(key)
        except Exception as e:
            self.logger.error(f"Tuş bırakma hatası: {e}")

    async def type_string(self, text: str, interval: Optional[float] = None):
        """Metin yaz"""
        try:
            if not self.is_window_active():
                self.activate_window()

            if interval is None:
                interval = random.uniform(0.1, 0.3)

            for char in text:
                await self._add_human_delay()
                pyautogui.press(char)
                await asyncio.sleep(interval)

        except Exception as e:
            self.logger.error(f"Metin yazma hatası: {e}")

    def get_pixel_color(self, x: int, y: int) -> Tuple[int, int, int]:
        """Belirtilen pikselin rengini al"""
        try:
            return pyautogui.pixel(x, y)
        except Exception as e:
            self.logger.error(f"Piksel rengi alma hatası: {e}")
            return (0, 0, 0)

    def cleanup(self):
        """Tüm tuşları ve fare düğmelerini bırak"""
        try:
            # Tüm modifier tuşları bırak
            for key in ['shift', 'ctrl', 'alt']:
                pyautogui.keyUp(key)

            # Fare düğmelerini bırak
            pyautogui.mouseUp(button='left')
            pyautogui.mouseUp(button='right')

        except Exception as e:
            self.logger.error(f"Cleanup hatası: {e}")