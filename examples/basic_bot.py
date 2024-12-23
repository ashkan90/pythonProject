import asyncio
import sys
import os

# Ana dizini ekle
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.bot import BDOBot
from src.utils.config_manager import ConfigManager
from src.utils.logger import BotLogger


async def main():
    try:
        # Logger'ı başlat
        logger = BotLogger()
        logger_instance = logger.get_debug_logger("MainBot")

        # Ayarları yükle
        config = ConfigManager()
        if not config.validate_configs():
            logger_instance.error("Yapılandırma doğrulanamadı!")
            return

        # Bot instance'ını oluştur
        bot = BDOBot(config.settings)

        # Sınıf ve rota yükle
        class_name = config.get_setting("game_settings.class_name")
        route_name = config.get_setting("game_settings.route_name")

        await bot.load_class(class_name)
        await bot.load_route(route_name)

        # İstatistik dosyasını oluştur
        stats_file = logger.create_stat_logger()
        session_file = logger.create_session_log()

        # Bot'u başlat
        logger_instance.info("Bot başlatılıyor...")
        await bot.start()

        try:
            while True:
                # Her 5 dakikada bir istatistikleri kaydet
                stats = await bot.get_statistics()
                logger.log_stats(stats_file, stats)

                # Her önemli olayı session log'a kaydet
                events = await bot.get_events()
                for event in events:
                    logger.log_session_event(
                        session_file,
                        event["type"],
                        event["data"]
                    )

                await asyncio.sleep(300)  # 5 dakika bekle

        except KeyboardInterrupt:
            logger_instance.info("Bot kapatılıyor...")
            await bot.cleanup()

    except Exception as e:
        logger_instance.error(f"Kritik hata: {e}")
        if 'bot' in locals():
            await bot.cleanup()


if __name__ == "__main__":
    asyncio.run(main())