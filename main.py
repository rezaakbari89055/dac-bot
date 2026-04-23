import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.client.session.aiohttp import AiohttpSession
from config import get_settings
from database import engine, Base
import handlers

settings = get_settings()

async def on_startup(bot: Bot):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.send_message(
        chat_id=settings.ADMIN_ID, 
        text="✅ ربات DAC با موفقیت روی سرور ایرانی روشن شد و از طریق پروکسی در حال کار است."
    )

async def background_checker(bot: Bot):
    """ این تابع هر ۱ ساعت ترافیک اکانت‌ها را چک می‌کند و به کاربران اخطار می‌دهد """
    while True:
        # اینجا باید با استفاده از XuiAPI ترافیک کاربران چک شود
        # مثلا اگر ترافیک کمتر از ۱ گیگ شد پیام بدهد
        await asyncio.sleep(3600) # ۱ ساعت

async def main():
    session = None
    if settings.PROXY_URL:
        session = AiohttpSession(proxy=settings.PROXY_URL)
        
    bot = Bot(
        token=settings.BOT_TOKEN, 
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session
    )
    
    dp = Dispatcher()
    dp.include_router(handlers.router)
    dp.startup.register(on_startup)
    
    # اجرای تسک پس‌زمینه چک کردن اکانت‌ها
    asyncio.create_task(background_checker(bot))
    
    logging.info("DAC Bot started in Long Polling mode...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
