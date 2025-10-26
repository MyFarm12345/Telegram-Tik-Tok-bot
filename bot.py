import asyncio
import requests
import re
import os
import threading
from flask import Flask
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, BufferedInputFile
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


logging_enabled = True


app = Flask(__name__)


@app.route('/')
@app.route('/health')
@app.route('/healthz')
def health_check():
    return "Telegram TikTok Bot is running! 🎬", 200


def run_flask():
    """Запуск Flask сервера в отдельном потоке"""
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)


class TikTokDownloader:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

    def extract_video_id(self, url: str) -> str:
        try:
            if 'vm.tiktok.com' in url or 'vt.tiktok.com' in url:
                response = requests.head(url, allow_redirects=True, timeout=10)
                url = response.url

            patterns = [
                r'tiktok\.com/@[\w\.-]+/video/(\d+)',
                r'tiktok\.com/t/(\w+)',
                r'/video/(\d+)',
                r'vm\.tiktok\.com/(\w+)',
                r'vt\.tiktok\.com/(\w+)'
            ]

            for pattern in patterns:
                match = re.search(pattern, str(url))
                if match:
                    return match.group(1)
            return None
        except:
            return None

    def get_video_info(self, url: str) -> dict:
        apis = [
            {
                'url': f'https://tikwm.com/api/?url={url}',
                'video_key': 'play'
            },
            {
                'url': f'https://api.tiklydown.eu.org/api/download?url={url}',
                'video_key': 'video'
            },
            {
                'url': f'https://www.tikdown.org/api/getAjax?url={url}',
                'video_key': 'video'
            }
        ]

        for api in apis:
            try:
                if logging_enabled:
                    logger.info(f"Пробуем API: {api['url']}")

                response = requests.get(api['url'], headers=self.headers, timeout=15)

                if response.status_code == 200:
                    data = response.json()
                    if logging_enabled:
                        logger.info(f"Ответ API: {data}")

                    if data.get('code') == 0 and data.get('data'):
                        video_url = data['data'].get(api['video_key']) or data['data'].get('play') or data['data'].get(
                            'video')
                        if video_url:
                            return {
                                'video_url': video_url,
                            }

                    if data.get('video') or data.get('play'):
                        video_url = data.get('video') or data.get('play')
                        return {
                            'video_url': video_url,
                        }

            except Exception as e:
                continue

        return None

    def download_video(self, video_url: str) -> bytes:
        try:
            response = requests.get(video_url, headers=self.headers, timeout=30)
            if response.status_code == 200:
                return response.content
        except Exception as e:
            if logging_enabled:
                logger.error(f"Ошибка при скачивании: {e}")
        return None


downloader = TikTokDownloader()


@dp.message(CommandStart())
async def start_command(message: Message):
    welcome_text = """
🎬 **Tik-Tok video downloader**

Привет! Я бот @TikTokInstallMyFarmbot и я помогу
скачать видео из TikTok без водяных знаков.


📝 **Как использовать:**
1. Отправьте мне ссылку на TikTok видео
2. Я обработаю видео и отправлю вам

Отправьте ссылку! 
    """
    await message.answer(welcome_text, parse_mode="Markdown")


@dp.message(F.text.contains("tiktok.com") | F.text.contains("vm.tiktok.com") | F.text.contains("vt.tiktok.com"))
async def handle_tiktok_url(message: Message):
    url = message.text.strip()

    if not url.startswith(('http://', 'https://')):
        await message.answer("❌ Пожалуйста, отправьте полную ссылку (начинающуюся с http:// или https://)")
        return

    processing_msg = await message.answer("🔄 Обрабатываю видео...")

    try:
        video_info = downloader.get_video_info(url)

        if not video_info:
            await processing_msg.edit_text(
                "❌ Не удалось получить видео. Возможно:\n• Видео приватное\n• Ссылка неверная\n• Сервис временно недоступен")
            return

        await processing_msg.edit_text("⬇️ Скачиваю видео...")

        video_bytes = downloader.download_video(video_info['video_url'])
        if not video_bytes:
            await processing_msg.edit_text("❌ Не удалось скачать видео")
            return

        if len(video_bytes) > 50 * 1024 * 1024:
            await processing_msg.edit_text("❌ Видео слишком большое для отправки в Telegram (>50MB)")
            return

        await processing_msg.edit_text("📤 Отправляю видео...")

        filename = f"tiktok_video.mp4"
        video_file = BufferedInputFile(video_bytes, filename=filename)

        await message.answer_video(
            video=video_file,
            parse_mode="Markdown"
        )

        await processing_msg.delete()

    except Exception as e:
        if logging_enabled:
            logger.error(f"Ошибка: {e}")
        await processing_msg.edit_text(f"❌ Произошла ошибка: {str(e)}")


@dp.message()
async def handle_other_messages(message: Message):
    await message.answer(
        "🤔 Отправьте мне ссылку на TikTok видео!\n\n"
        "Примеры:\n"
        "• https://www.tiktok.com/@username/video/1234567890\n"
        "• https://vm.tiktok.com/ZMxxxxxxx/\n"
        "• https://vt.tiktok.com/ZSxxxxxxx/"
    )


async def main():
    logger.info("Запуск бота...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        logger.info("Flask HTTP сервер запущен для Render")

       
        asyncio.run(main())
    except KeyboardInterrupt:

        logger.info("Бот остановлен")

