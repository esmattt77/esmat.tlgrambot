# main_app.py

import json
import logging
import asyncio
import os
import threading
import sys  # لاستخدامه في الخروج الآمن إذا لم يتم العثور على التوكن
from uuid import uuid4
from flask import Flask, request, jsonify

# استيراد من python-telegram-bot
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
)

# تأكد من أن الملف sms_man_api.py موجود
from sms_man_api import SMSManAPI 

# --- الثوابت والتكوينات (تُقرأ من متغيرات البيئة) ---

# التعديل الرئيسي: الاعتماد كلياً على متغير البيئة
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    logging.error("FATAL: BOT_TOKEN environment variable is not set. Exiting.")
    sys.exit(1)
    
# باقي المتغيرات تستخدم قيم افتراضية آمنة في حال الفشل
ADMIN_ID = int(os.getenv("ADMIN_ID", "0")) # يجب أن تفشل الأوامر إذا لم يتم تعيينه
ADMIN_CHANNEL_ID = int(os.getenv("ADMIN_CHANNEL_ID", "-1000000000000"))
LOG_ADMIN_ID = int(os.getenv("LOG_ADMIN_ID", "0")) 

WEBHOOK_URL_BASE = os.getenv("WEBHOOK_URL_BASE") 
WEBHOOK_PATH = f'/{TOKEN}'
PORT = int(os.getenv('PORT', '8080'))

# --- تهيئة Logging ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- تهيئة تطبيق Telegram & Flask ---
application = Application.builder().token(TOKEN).updater(None).build()
app = Flask(__name__)

# --- دوال مساعدة لحفظ وتحميل البيانات ---
INFO_FILE = "info.json"

# ... (دوال load_info و save_info و get_main_keyboard لم تتغير) ...
def load_info():
    try:
        with open(INFO_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_info(info_data):
    try:
        with open(INFO_FILE, "w", encoding="utf-8") as f:
            json.dump(info_data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error saving info.json: {e}")

def get_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("اضافة دولة ➕", callback_data="add"),
         InlineKeyboardButton("حذف دولة 🗑️", callback_data="del")],
        [InlineKeyboardButton("رفع api key", callback_data="up"),
         InlineKeyboardButton("حذف api key", callback_data="rem")],
        [InlineKeyboardButton("الدول المضافة 📊", callback_data="all")],
    ])


# --- 🎯 منطق الـ Checker (شراء الأرقام) كـ Thread منفصل ---

# ... (دوال start_checker_thread و stop_checker_thread و check_and_buy_number_loop لم تتغير) ...

checker_thread = None

def start_checker_thread():
    """يبدأ تشغيل المهمة الخلفية للـ Checker."""
    global checker_thread
    if checker_thread is None or not checker_thread.is_alive():
        checker_thread = threading.Thread(target=asyncio.run, args=(check_and_buy_number_loop(),), daemon=True)
        checker_thread.start()
        logger.info("Checker thread started.")
    
def stop_checker_thread():
    """يوقف تشغيل المهمة الخلفية."""
    info = load_info()
    if info.get("status") == "work":
        info["status"] = "stopping" 
        save_info(info)
        logger.info("Checker status set to 'stopping'. Will exit loop soon.")


async def check_and_buy_number_loop():
    """حلقة الشراء اللاتزامنية التي تعمل في Thread الخلفي."""
    info = load_info()
    api_key = info.get("key")
    
    if not api_key:
        logger.warning("Checker cannot run: missing API key.")
        return

    api = SMSManAPI(api_key)
    bot = application.bot 

    while True:
        info_loop = load_info()
        
        if info_loop.get("status") != "work":
            logger.info("Checker loop exiting because status is not 'work'.")
            if info_loop.get("status") == "stopping":
                 info_loop["status"] = None
                 save_info(info_loop)
            break
            
        try:
            for country_code in info_loop.get("countries", {}).values():
                
                if load_info().get("status") != "work": break 
                
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
                        
                        await bot.send_message(
                            chat_id=ADMIN_CHANNEL_ID,
                            text=txt, parse_mode="Markdown", reply_markup=reply_markup
                        )
                        await asyncio.sleep(0.1)
                else:
                    logger.warning(f"Failed to get number for {country_code}. Error: {res.get('error')}")
                    await asyncio.sleep(0.5)
                    
        except Exception as e:
            logger.error(f"Error in checker loop: {e}")
            await asyncio.sleep(5)

        await asyncio.sleep(5) 

# --- Handlers (معالجات أوامر البوت) ---

# ... (بقية الـ Handlers لم تتغير) ...

async def start_command(update: Update, context) -> None:
    if update.effective_user.id != ADMIN_ID: return
    info = load_info()
    info["admin"] = "" 
    save_info(info)
    text = "/work لجعل البوت يبدا الصيد\n/stop لجعل البوت يتوقف عن الصيد\nعند ايقاف الصيد لا يتوقف مباشرة وانما يتوقف بعد مرور دقيقة"
    await update.message.reply_text(text, reply_markup=get_main_keyboard())


async def work_command(update: Update, context) -> None:
    if update.effective_user.id != ADMIN_ID: return
    info = load_info()
    info["status"] = "work"
    save_info(info)
    
    start_checker_thread()
    await update.message.reply_text("تم تشغيل الصيد")


async def stop_command(update: Update, context) -> None:
    if update.effective_user.id != ADMIN_ID: return
    stop_checker_thread()
    await update.message.reply_text("تم ايقاف الصيد (سيتم التوقف بعد انتهاء الدورة الحالية)")


async def handle_text_input(update: Update, context) -> None:
    if update.effective_user.id != ADMIN_ID: return

    info = load_info()
    current_state = info.get("admin")
    text = update.message.text
    
    if not current_state: return

    if current_state == "add":
        code = str(uuid4())[:8] 
        info["countries"] = info.get("countries", {})
        info["countries"][code] = text
        await update.message.reply_text(f"تمت الاضافة بنجاح\nكود الدولة: `{code}`\n(يستخدم هذا الكود عند الرغبة بحذف الدولة)", parse_mode="Markdown")
    elif current_state == "del":
        if info.get("countries", {}).pop(text, None) is not None:
            await update.message.reply_text("تم الحذف بنجاح")
        else:
            await update.message.reply_text("لاتوجد دولة مضافة بهذا الكود")
    elif current_state == "up":
        info["key"] = text
        await update.message.reply_text("تم الحفظ بنجاح")
        
    info["admin"] = ""
    save_info(info)
    await update.message.reply_text("الرجوع إلى القائمة الرئيسية:", reply_markup=get_main_keyboard())


async def handle_callback(update: Update, context) -> None:
    """معالجة ضغط الأزرار المضمنة."""
    query = update.callback_query
    
    # التعديل: الرد الفوري على الاستعلام لتجنب خطأ 'Event loop is closed'
    try:
        await query.answer() 
    except Exception as e:
        logger.error(f"Failed to answer callback query (Continuing execution): {e}")

    data = query.data
    chat_id = query.message.chat_id
    message_id = query.message.message_id
    ex = data.split("#")
    
    info = load_info()
    api_key = info.get("key")
    api = SMSManAPI(api_key)
    
    if query.from_user.id == ADMIN_ID:
        
        if data == "back":
            info["admin"] = ""
            save_info(info)
            await query.edit_message_text("أوامر الإدارة:\n/work لتشغيل الصيد\n/stop لإيقاف الصيد", reply_markup=get_main_keyboard())
            return

        elif data == "all":
            countries_dict = info.get("countries", {})
            display_text = "\n".join([f"[{code}] : {country}" for code, country in countries_dict.items()]) if countries_dict else "لا توجد دول مضافة"
            await query.answer(text=display_text, show_alert=True)
            return
            
        elif data in ["add", "del", "up"]:
            if data == "up" and api_key is not None:
                await query.answer(text="لايمكنك اضافة api key جديد الا بعد حذف القديم", show_alert=True)
                return
            
            text_msg = "قم بارسال رمز الدولة في موقع sms-man" if data == "add" else \
                       "قم بارسال كود الدولة" if data == "del" else \
                       "قم بارسال api key الخاص بحسابك"
            
            await query.edit_message_text(text_msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("رجوع🔙", callback_data="back")]]))
            info["admin"] = data
            save_info(info)
            return

        elif data == "rem":
            if "key" in info: del info["key"]
            save_info(info)
            await query.edit_message_text("تم الحذف بنجاح", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("رجوع🔙", callback_data="back")]]))
            return
            
    # معالجة أوامر الـ Callback العامة (getCode و ban)
    if ex[0] == "getCode":
        operation_id = ex[1]; number = ex[2]
        res = await asyncio.to_thread(api.get_code, operation_id)
        code = res.get("code")

        if res.get("ok") and code and code != "0": 
            await query.edit_message_text(f"تم وصول الكود بنجاح:\n📞 الرقم: {number}\n🔒 الكود: {code}", message_id=message_id, chat_id=chat_id)
        else:
            # يجب الإجابة على الاستعلام حتى لو لم يصل الكود، لكن هذا تم بالفعل في البداية
            await query.edit_message_text(f"🚫 لم يصل الكود بعد للرقم {number}", message_id=message_id, chat_id=chat_id)
            
    elif ex[0] == "ban":
        operation_id = ex[1]
        res = await asyncio.to_thread(api.cancel, operation_id)
        
        if res.get("ok"):
            await query.edit_message_text("تم حظر الرقم بنجاح", message_id=message_id, chat_id=chat_id)
        else:
            await query.edit_message_text(f"فشل حظر الرقم. الخطأ: {res.get('error')}", message_id=message_id, chat_id=chat_id)


# --- تعريف الـ Handlers في تطبيق Telegram ---
application.add_handler(CommandHandler("start", start_command, filters.User(ADMIN_ID)))
application.add_handler(CommandHandler("work", work_command, filters.User(ADMIN_ID)))
application.add_handler(CommandHandler("stop", stop_command, filters.User(ADMIN_ID)))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(ADMIN_ID), handle_text_input))
application.add_handler(CallbackQueryHandler(handle_callback))


# --- 🌐 مسارات Flask (Webhooks) ---

@app.route('/set_webhook')
async def set_webhook_route(): 
    if not WEBHOOK_URL_BASE:
        return jsonify({"status": "error", "message": "WEBHOOK_URL_BASE environment variable is not set."}), 500

    s = await application.bot.set_webhook(url=WEBHOOK_URL_BASE + WEBHOOK_PATH)
    
    if s:
        logger.info(f"Webhook set successfully to {WEBHOOK_URL_BASE + WEBHOOK_PATH}")
        return jsonify({"status": "ok", "message": "Webhook set"}), 200
    else:
        logger.error("Webhook setup failed.")
        return jsonify({"status": "error", "message": "Webhook setup failed"}), 500

@app.route(WEBHOOK_PATH, methods=['POST'])
async def telegram_webhook():
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), application.bot)
        await application.process_update(update)
    return 'ok'

@app.route('/')
def index():
    return 'Bot is running via Webhook.'

# --- نقطة التشغيل الرئيسية ---
def main() -> None:
    
    try:
        async def init_application():
            await application.initialize() 
        
        asyncio.run(init_application())
        logger.info("Telegram Application initialized successfully.")
        
    except Exception as e:
        logger.error(f"FATAL: Error during Telegram application initialization: {e}")
        return

    info = load_info()
    if info.get("status") == "work":
        start_checker_thread()
        logger.info("Checker thread auto-started.")
        
    app.run(host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
