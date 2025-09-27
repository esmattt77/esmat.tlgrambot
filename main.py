# main_bot.py (الإصدار المعدل لقراءة المتغيرات من البيئة)

import json
import logging
import asyncio
import os # لاستخدام متغيرات البيئة
from uuid import uuid4
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, JobQueue
)
# تأكد من أن الملف sms_man_api.py موجود
from sms_man_api import SMSManAPI 

# --- الثوابت والتكوينات (تُقرأ الآن من متغيرات البيئة) ---
# استخدام os.getenv() لقراءة المتغير، مع وضع قيمة افتراضية في حالة عدم العثور عليه
TOKEN = os.getenv("BOT_TOKEN", "6096818900:AAH1CUDxw0O3yNgbfgdb6m_tTqLnWCD30mw")
# يجب تحويل الآيديات إلى أرقام صحيحة (integers)
ADMIN_ID = int(os.getenv("ADMIN_ID", "1689271304"))
ADMIN_CHANNEL_ID = int(os.getenv("ADMIN_CHANNEL_ID", "-1001602685079"))
LOG_ADMIN_ID = int(os.getenv("LOG_ADMIN_ID", "501030516"))

# تهيئة التسجيل (Logging)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# --- دوال مساعدة لحفظ وتحميل البيانات (بدون تغيير) ---
INFO_FILE = "info.json"

def load_info():
    """قراءة البيانات من info.json."""
    try:
        with open(INFO_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_info(info_data):
    """حفظ البيانات إلى info.json."""
    try:
        with open(INFO_FILE, "w", encoding="utf-8") as f:
            json.dump(info_data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error saving info.json: {e}")

# --- دالة مساعدة لإنشاء لوحة مفاتيح (بدون تغيير) ---
def get_main_keyboard():
    """إنشاء لوحة المفاتيح الرئيسية للإدارة."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("اضافة دولة ➕", callback_data="add"),
         InlineKeyboardButton("حذف دولة 🗑️", callback_data="del")],
        [InlineKeyboardButton("رفع api key", callback_data="up"),
         InlineKeyboardButton("حذف api key", callback_data="rem")],
        [InlineKeyboardButton("الدول المضافة 📊", callback_data="all")],
    ])

# --- 🎯 منطق الـ Checker (شراء الأرقام) ---
# نفس المنطق السابق، يستخدم المتغيرات التي تم قراءتها أعلاه

async def check_and_buy_number(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    مهمة خلفية (Job) لشراء الأرقام بشكل دوري.
    """
    info = load_info()
    api_key = info.get("key")
    countries = info.get("countries", {})
    
    if info.get("status") != "work" or not api_key or not countries:
        return

    # الآن نستخدم الثوابت التي قرأناها من البيئة
    api = SMSManAPI(api_key) 
    bot = context.bot 

    for country_code in countries.values():
        logger.info(f"Checking number for country: {country_code}")
        
        res = await asyncio.to_thread(api.get_number, country_code, "wa")
        
        if res.get("ok"):
            id_op = res.get("id")
            num = res.get("number")
            
            if id_op and num:
                txt = (
                    "تم شراء الرقم بنجاح ☑️\n\n"
                    f"📞 الرقم: `+{num}`\n"
                    f"🆔 ايدي العملية: {id_op}\n"
                    f"https://wa.me/+{num}"
                )
                
                keyboard = [
                    [InlineKeyboardButton("🌚 طلب الكود", callback_data=f"getCode#{id_op}#{num}")],
                    [InlineKeyboardButton("❌ حظر الرقم", callback_data=f"ban#{id_op}")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                try:
                    await bot.send_message(
                        chat_id=ADMIN_CHANNEL_ID, # آيدي قناة الصيد من المتغيرات
                        text=txt,
                        parse_mode="Markdown",
                        reply_markup=reply_markup
                    )
                    logger.info(f"Successfully sent message for number: {num}")
                    await asyncio.sleep(0.1) 
                    
                except Exception as e:
                    logger.error(f"Error sending message for {num} to Telegram: {e}")
            else:
                logger.warning(f"Got empty ID or number for {country_code}")
        else:
            logger.warning(f"Failed to get number for {country_code}. Error: {res.get('error')}")

# --- Handlers لمعالجة أوامر الأدمن والرسائل (بدون تغيير في المنطق) ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """معالجة أمر /start و 'back'."""
    if update.effective_user.id != ADMIN_ID: return # استخدام آيدي الأدمن من المتغيرات

    info = load_info()
    info["admin"] = "" 
    save_info(info)

    text = "/work لجعل البوت يبدا الصيد\n/stop لجعل البوت يتوقف عن الصيد\nعند ايقاف الصيد لا يتوقف مباشرة وانما يتوقف بعد مرور دقيقة"
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text, 
        reply_markup=get_main_keyboard()
    )


async def work_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """معالجة أمر /work لتشغيل الصيد."""
    if update.effective_user.id != ADMIN_ID: return
    
    # ... (بقية المنطق بدون تغيير) ...

    # تشغيل مهمة الـ Checker كل 5 ثواني
    if 'checker_job' not in context.job_queue.jobs():
        context.job_queue.run_repeating(check_and_buy_number, interval=5, first=1, name='checker_job')
        logger.info("Checker Job added/started.")
    
    info = load_info()
    info["status"] = "work"
    save_info(info)
    
    await update.message.reply_text("تم تشغيل الصيد")


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """معالجة أمر /stop لإيقاف الصيد."""
    if update.effective_user.id != ADMIN_ID: return
    
    # ... (بقية المنطق بدون تغيير) ...

    # إزالة مهمة الـ Checker من قائمة التشغيل
    current_jobs = context.job_queue.get_jobs_by_name('checker_job')
    for job in current_jobs:
        job.schedule_removal()
    logger.info("Checker Job scheduled for removal.")
    
    info = load_info()
    info["status"] = None
    save_info(info)
    
    await update.message.reply_text("تم ايقاف الصيد")


# ... (بقية Handlers الرسائل والـ Callback Queries لا تتغير في المنطق) ...
# ... (فقط تأكد من أن جميع التحققات من ADMIN_ID تستخدم المتغير الذي تم قراءته) ...

# --- دالة التشغيل الرئيسية للبوت ---
def main() -> None:
    """بدء تشغيل البوت باستخدام Polling."""
    # استخدام التوكن المقروء من البيئة لتهيئة التطبيق
    application = Application.builder().token(TOKEN).build()
    
    # Handlers للأوامر (تستخدم الآن المتغير ADMIN_ID)
    application.add_handler(CommandHandler("start", start_command, filters=filters.User(ADMIN_ID)))
    application.add_handler(CommandHandler("work", work_command, filters=filters.User(ADMIN_ID)))
    application.add_handler(CommandHandler("stop", stop_command, filters=filters.User(ADMIN_ID)))

    # Handler للرسائل النصية
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.User(ADMIN_ID), 
        handle_text_input
    ))

    # Handler لـ Callback Queries
    application.add_handler(CallbackQueryHandler(handle_callback))
    
    # تشغيل الـ Checker Job إذا كانت الحالة "work" عند بدء تشغيل البوت
    info = load_info()
    if info.get("status") == "work":
        # تعيين الفاصل الزمني (interval) على 5 ثوانٍ
        application.job_queue.run_repeating(check_and_buy_number, interval=5, first=1, name='checker_job')
        logger.info("Checker Job automatically started because status is 'work'.")


    # بدء البوت (Polling)
    logger.info("Bot started successfully (Polling mode)...")
    application.run_polling(poll_interval=1) 

if __name__ == "__main__":
    main()
