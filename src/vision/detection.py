import cv2
import numpy as np
import logging
from pathlib import Path
import pickle
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import time


@dataclass
class DetectionResult:
    mob_type: str
    confidence: float
    bbox: Tuple[int, int, int, int]  # x, y, width, height
    keypoints: List[Tuple[float, float]]
    is_elite: bool = False


@dataclass
class MobTemplate:
    name: str
    images: List[np.ndarray]
    features: Dict[str, np.ndarray]
    keypoints: List[cv2.KeyPoint]
    descriptors: np.ndarray
    size_range: Tuple[Tuple[int, int], Tuple[int, int]]  # ((min_w, min_h), (max_w, max_h))
    color_ranges: List[Tuple[np.ndarray, np.ndarray]]  # [(lower_bound, upper_bound), ...]
    template_points: List[Tuple[int, int]]  # Önemli noktalar (baş, gövde, vs.)


class FeatureBasedDetector:
    def __init__(self, template_dir: str):
        self.logger = logging.getLogger("FeatureDetector")
        self.template_dir = Path(template_dir)
        self.mob_templates: Dict[str, MobTemplate] = {}

        # SIFT özellik dedektörü
        self.feature_detector = cv2.SIFT_create(
            nfeatures=100,
            nOctaveLayers=3,
            contrastThreshold=0.04,
            edgeThreshold=10,
            sigma=1.6
        )

        # FLANN özellik eşleştirici
        FLANN_INDEX_KDTREE = 1
        index_params = dict(algorithm=FLANN_INDEX_KDTREE, trees=5)
        search_params = dict(checks=50)
        self.matcher = cv2.FlannBasedMatcher(index_params, search_params)

        # Bazı optimizasyon parametreleri
        self.min_match_count = 10
        self.min_confidence = 0.6
        self.last_frame_time = time.time()

        # Mob veritabanını yükle
        self.load_mob_database()

    def load_mob_database(self):
        """Mob veritabanını yükle"""
        try:
            db_file = self.template_dir / "mob_database.pkl"
            if db_file.exists():
                with open(db_file, 'rb') as f:
                    self.mob_templates = pickle.load(f)
                self.logger.info(f"{len(self.mob_templates)} mob template yüklendi")
        except Exception as e:
            self.logger.error(f"Veritabanı yükleme hatası: {e}")

    def add_mob_template(self, mob_type: str, images: List[np.ndarray],
                         is_elite: bool = False):
        """Yeni bir mob şablonu ekle"""
        try:
            all_keypoints = []
            all_descriptors = []
            color_ranges = []
            template_points = []

            for img in images:
                # Görüntü ön işleme
                processed = self._preprocess_image(img)

                # SIFT özellikleri çıkar
                keypoints, descriptors = self.feature_detector.detectAndCompute(
                    processed, None
                )

                if keypoints and descriptors is not None:
                    all_keypoints.extend(keypoints)
                    all_descriptors.append(descriptors)

                    # Renk aralıklarını belirle
                    color_range = self._extract_color_range(img)
                    color_ranges.append(color_range)

                    # Önemli noktaları belirle
                    points = self._detect_template_points(img)
                    template_points.extend(points)

            if all_descriptors:
                combined_descriptors = np.vstack(all_descriptors)

                # Boyut aralığını hesapla
                heights = [img.shape[0] for img in images]
                widths = [img.shape[1] for img in images]
                size_range = (
                    (min(widths), min(heights)),
                    (max(widths), max(heights))
                )

                # Template oluştur
                template = MobTemplate(
                    name=mob_type,
                    images=images,
                    features=self._extract_features(images),
                    keypoints=all_keypoints,
                    descriptors=combined_descriptors,
                    size_range=size_range,
                    color_ranges=color_ranges,
                    template_points=template_points
                )

                self.mob_templates[mob_type] = template
                self._save_database()
                self.logger.info(f"Mob template eklendi: {mob_type}")

            else:
                self.logger.error(f"Özellik çıkarılamadı: {mob_type}")

        except Exception as e:
            self.logger.error(f"Template ekleme hatası: {e}")

    def _preprocess_image(self, image: np.ndarray) -> np.ndarray:
        """Görüntü ön işleme"""
        # Griye çevir
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        # Gürültü azalt
        denoised = cv2.fastNlMeansDenoising(gray)

        # Kontrast artır
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(denoised)

        return enhanced

    def _extract_color_range(self, image: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Görüntüden renk aralığı çıkar"""
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

        # Ortalama ve standart sapma hesapla
        mean = np.mean(hsv, axis=(0, 1))
        std = np.std(hsv, axis=(0, 1))

        # Renk aralığını belirle
        lower = np.array([
            max(0, mean[0] - std[0]),
            max(0, mean[1] - std[1]),
            max(0, mean[2] - std[2])
        ])

        upper = np.array([
            min(180, mean[0] + std[0]),
            min(255, mean[1] + std[1]),
            min(255, mean[2] + std[2])
        ])

        return (lower, upper)

    def _detect_template_points(self, image: np.ndarray) -> List[Tuple[int, int]]:
        """Şablondaki önemli noktaları tespit et"""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        corners = cv2.goodFeaturesToTrack(gray, 25, 0.01, 10)
        corners = np.int0(corners)

        return [(x[0][0], x[0][1]) for x in corners]

    def _extract_features(self, images: List[np.ndarray]) -> Dict[str, np.ndarray]:
        """Özel özellikler çıkar"""
        features = {}

        for img in images:
            # HOG özellikleri
            hog = cv2.HOGDescriptor()
            hog_features = hog.compute(img)
            if 'hog' not in features:
                features['hog'] = []
            features['hog'].append(hog_features)

            # LBP özellikleri
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            lbp = self._compute_lbp(gray)
            if 'lbp' not in features:
                features['lbp'] = []
            features['lbp'].append(lbp)

        return features

    def _compute_lbp(self, image: np.ndarray) -> np.ndarray:
        """LBP özelliklerini hesapla"""
        rows = image.shape[0]
        cols = image.shape[1]
        lbp = np.zeros_like(image)

        for i in range(1, rows - 1):
            for j in range(1, cols - 1):
                center = image[i, j]
                code = 0
                code |= (image[i - 1, j - 1] >= center) << 7
                code |= (image[i - 1, j] >= center) << 6
                code |= (image[i - 1, j + 1] >= center) << 5
                code |= (image[i, j + 1] >= center) << 4
                code |= (image[i + 1, j + 1] >= center) << 3
                code |= (image[i + 1, j] >= center) << 2
                code |= (image[i + 1, j - 1] >= center) << 1
                code |= (image[i, j - 1] >= center) << 0
                lbp[i, j] = code

        return lbp

    async def detect_mobs(self, frame: np.ndarray,
                          confidence_threshold: float = 0.6) -> List[DetectionResult]:
        """Frame'deki mobları tespit et"""
        try:
            detections = []
            processed = self._preprocess_image(frame)

            # Frame'den özellik çıkar
            frame_keypoints, frame_descriptors = self.feature_detector.detectAndCompute(
                processed, None
            )

            if not frame_keypoints or frame_descriptors is None:
                return []

            # Her mob template'i için kontrol
            for mob_type, template in self.mob_templates.items():
                # Özellik eşleştirme
                matches = self.matcher.knnMatch(
                    template.descriptors,
                    frame_descriptors,
                    k=2
                )

                # İyi eşleşmeleri filtrele
                good_matches = []
                for m, n in matches:
                    if m.distance < 0.7 * n.distance:
                        good_matches.append(m)

                if len(good_matches) > self.min_match_count:
                    # Eşleşen noktaları al
                    src_pts = np.float32([template.keypoints[m.queryIdx].pt
                                          for m in good_matches]).reshape(-1, 1, 2)
                    dst_pts = np.float32([frame_keypoints[m.trainIdx].pt
                                          for m in good_matches]).reshape(-1, 1, 2)

                    # Homografi hesapla
                    H, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)

                    if H is not None:
                        # Template boyutlarını al
                        h, w = template.images[0].shape[:2]
                        pts = np.float32([[0, 0], [0, h - 1], [w - 1, h - 1], [w - 1, 0]]
                                         ).reshape(-1, 1, 2)

                        # Noktaları transform et
                        dst = cv2.perspectiveTransform(pts, H)

                        # Sınırlayıcı kutuyu hesapla
                        x, y, w, h = cv2.boundingRect(dst)

                        # Boyut kontrolü
                        min_size, max_size = template.size_range
                        if (min_size[0] <= w <= max_size[0] and
                                min_size[1] <= h <= max_size[1]):

                            # Eşleşme kalitesi
                            match_quality = len(good_matches) / len(matches)

                            if match_quality > confidence_threshold:
                                detection = DetectionResult(
                                    mob_type=mob_type,
                                    confidence=match_quality,
                                    bbox=(x, y, w, h),
                                    keypoints=dst.reshape(-1, 2).tolist(),
                                    is_elite=self._check_if_elite(frame[y:y + h, x:x + w])
                                )
                                detections.append(detection)

            return detections

        except Exception as e:
            self.logger.error(f"Mob tespiti hatası: {e}")
            return []

    def _check_if_elite(self, mob_image: np.ndarray) -> bool:
        """Mobun elite olup olmadığını kontrol et"""
        try:
            # Elite mob belirteçlerini kontrol et (örn: altın renkli aura)
            hsv = cv2.cvtColor(mob_image, cv2.COLOR_BGR2HSV)

            # Altın renk aralığı
            lower_gold = np.array([20, 100, 100])
            upper_gold = np.array([30, 255, 255])

            gold_mask = cv2.inRange(hsv, lower_gold, upper_gold)
            gold_ratio = np.sum(gold_mask > 0) / (mob_image.shape[0] * mob_image.shape[1])

            return gold_ratio > 0.1  # %10'dan fazla altın rengi varsa elite

        except Exception:
            return False

    def _save_database(self):
        """Mob veritabanını kaydet"""
        try:
            db_file = self.template_dir / "mob_database.pkl"
            with open(db_file, 'wb') as f:
                pickle.dump(self.mob_templates, f)
        except Exception as e:
            self.logger.error(f"Veritabanı kaydetme hatası: {e}")

    def cleanup(self):
        """Kaynakları temizle"""
        self.mob_templates.clear()