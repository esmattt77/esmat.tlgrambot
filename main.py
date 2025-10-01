import os
import json
import sqlite3
import telegram
import logging
import asyncio # للحفاظ على استقرار Webhook
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters
)

# ==============================================================================
# 1. إعدادات البوت والبيئة
# ==============================================================================

TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0")) 
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
PORT = int(os.environ.get("PORT", "5000")) 
SECRET_TOKEN = os.environ.get("SECRET_TOKEN", "fallback_secret_must_be_changed") 
REQUIRED_CHANNELS = os.environ.get("REQUIRED_CHANNELS", "").split(', ')
SUPPORT_USERNAME = os.environ.get("SUPPORT_USERNAME", "support_user")

REFERRAL_BONUS = 0.5  
DATABASE_NAME = 'bot_data.db'

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# حالات المحادثة
AWAITING_FILE_NAME, AWAITING_FILE_PRICE, AWAITING_FILE_LINK = range(3)
AWAITING_TRANSFER_AMOUNT, AWAITING_TRANSFER_TARGET = range(3, 5)

# ==============================================================================
# 2. دوال قاعدة البيانات (Database Functions)
# ==============================================================================
# (بقية الدوال كما هي، لم يتم تعديلها هنا للتأكد من استقرار قاعدة البيانات)

def init_db():
    """إنشاء الجداول اللازمة."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    
    # جدول المستخدمين
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0,
            referral_count INTEGER DEFAULT 0,
            referrer_id INTEGER DEFAULT 0,
            is_subscribed INTEGER DEFAULT 0
        )
    ''')

    # جدول الملفات
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            price REAL NOT NULL,
            file_link TEXT NOT NULL,
            is_available INTEGER DEFAULT 1
        )
    ''')

    conn.commit()
    conn.close()

def get_user(user_id):
    """جلب بيانات مستخدم أو إنشائه."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, balance, referral_count, referrer_id FROM users WHERE user_id=?", (user_id,))
    user_data = cursor.fetchone()
    
    if user_data:
        conn.close()
        return {'user_id': user_data[0], 'balance': user_data[1], 'referral_count': user_data[2], 'referrer_id': user_data[3]}
    else:
        cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        conn.close()
        return {'user_id': user_id, 'balance': 0, 'referral_count': 0, 'referrer_id': 0}

def update_user_balance(user_id, amount):
    """تحديث رصيد المستخدم (يمكن أن يكون موجباً أو سالباً)."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def add_referral(user_id, referrer_id):
    """تسجيل الإحالة وإضافة الرصيد للمُحيل."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET referrer_id = ? WHERE user_id = ?", (referrer_id, user_id))
    cursor.execute("UPDATE users SET balance = balance + ?, referral_count = referral_count + 1 WHERE user_id = ?", 
                   (REFERRAL_BONUS, referrer_id))
    conn.commit()
    conn.close()

def get_all_files():
    """جلب قائمة الملفات المعروضة للبيع."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT name, price, file_link FROM files WHERE is_available = 1")
    files = cursor.fetchall()
    conn.close()
    return files

def add_file_to_db(name, price, file_link):
    """إضافة ملف جديد بواسطة المشرف."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO files (name, price, file_link) VALUES (?, ?, ?)",
                       (name, price, file_link))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()
        
def get_file_details(file_name):
    """جلب تفاصيل ملف معين."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT price, file_link FROM files WHERE name = ?", (file_name,))
    details = cursor.fetchone()
    conn.close()
    return details
    
# ==============================================================================
# 3. دوال الواجهة (UI & Check Functions)
# ==============================================================================

async def check_subscription(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    for channel_username in REQUIRED_CHANNELS:
        channel = channel_username.strip()
        if not channel: continue
        try:
            member = await context.bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status not in ["member", "administrator", "creator"]:
                return False
        except Exception:
            return False 
    return True

async def prompt_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message 
    
    buttons = []
    for channel in REQUIRED_CHANNELS:
        if channel.strip():
            buttons.append([InlineKeyboardButton(f"اشترك في {channel.strip()}", url=f"https://t.me/{channel.strip('@')}")])

    buttons.append([InlineKeyboardButton("✅ تم الاشتراك، تحقق الآن", callback_data='check_and_main_menu')])

    reply_markup = InlineKeyboardMarkup(buttons)
    await message.reply_text(
        "🛑 **للوصول إلى البوت، يجب عليك الاشتراك في القنوات التالية:**",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

async def get_main_menu_markup(user_id):
    user = get_user(user_id)
    balance = user['balance']
    
    keyboard = [
        [InlineKeyboardButton("💰 شراء ملف", callback_data='buy_file'),
         InlineKeyboardButton("🎁 ربح روبل", callback_data='earn_ruble')],
        [InlineKeyboardButton(f"💳 رصيد حسابك : {balance:.2f} روبل", callback_data='balance_info'),
         InlineKeyboardButton("📥 تحويل روبل", callback_data='transfer_ruble')],
        [InlineKeyboardButton("⚙️ معلوماتك", callback_data='user_info'),
         InlineKeyboardButton("➕ شراء نقاط", callback_data='buy_points')],
        [InlineKeyboardButton("📞 الدعم الفني", url=f"t.me/{SUPPORT_USERNAME}")],
        [InlineKeyboardButton("☁️ شراء استضافة", callback_data='buy_hosting'),
         InlineKeyboardButton("🆓 روبل مجاني", callback_data='free_ruble')],
        [InlineKeyboardButton("✅ اثبات التسليم", callback_data='proof_channel')]
    ]
    return InlineKeyboardMarkup(keyboard)

async def get_main_menu_text(user_id):
    user = get_user(user_id)
    balance = user['balance']
    
    bot_info = await application.bot.get_me()
    
    return (
        f"مرحبا بك في بوت خدمات PHP!\n\n"
        f"اجمع نقاط واستبدلها بملفات php متطورة.\n\n"
        f"**- رصيدك = {balance:.2f} روبل**\n\n"
        f"**{user_id}** = الأيدي\n\n"
        f"اضغط هنا لإنشاء بوت المتجر @{bot_info.username}"
    )
    
async def edit_to_main_menu(message: telegram.Message, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    markup = await get_main_menu_markup(user_id)
    text = await get_main_menu_text(user_id)
    
    try:
        await message.edit_text(text, reply_markup=markup, parse_mode='HTML')
    except telegram.error.BadRequest:
        await message.reply_text(text, reply_markup=markup, parse_mode='HTML')

# ==============================================================================
# 4. معالجات المستخدم (User Handlers)
# ==============================================================================
# (دوال register_pending_referral و start و show_files_menu و show_earn_ruble_menu و prompt_buy_file و confirm_buy_file كما هي)

async def register_pending_referral(user_id, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(user_id)
    
    if 'pending_referrer' in context.user_data and user.get('referrer_id') == 0:
        referrer_id = context.user_data.pop('pending_referrer')
        
        referrer_user = get_user(referrer_id)
        if referrer_user['user_id'] != user_id: 
            add_referral(user_id, referrer_id)
            await context.bot.send_message(
                chat_id=referrer_id, 
                text=f"🎁 **مبروك!** انضم مستخدم جديد عبر رابط الإحالة الخاص بك. تم إضافة **{REFERRAL_BONUS} روبل** إلى رصيدك.",
                parse_mode='HTML'
            )
            return True
    return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    message = update.message
    
    user = get_user(user_id)
    
    if context.args:
        referrer_id_str = context.args[0]
        try:
            referrer_id = int(referrer_id_str)
            if referrer_id != user_id and user.get('referrer_id') == 0:
                context.user_data['pending_referrer'] = referrer_id
        except ValueError:
            pass

    is_subscribed = await check_subscription(user_id, context)
    
    if not is_subscribed:
        await prompt_subscription(update, context)
        return
        
    await register_pending_referral(user_id, context)

    markup = await get_main_menu_markup(user_id)
    text = await get_main_menu_text(user_id)
    
    await message.reply_text(text, reply_markup=markup, parse_mode='HTML')


async def show_files_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    available_files = get_all_files()

    file_keyboard = []
    for file_name, price, _ in available_files:
        # هنا يتم عرض اسم الملف كاملاً (الذي أصبح يحتوي على الوصف)
        button_text = f"ملف: {file_name.splitlines()[0]} ({price:.2f} روبل)"
        file_keyboard.append([InlineKeyboardButton(button_text, callback_data=f'buy_file_{file_name.replace(" ", "_").splitlines()[0]}')]) # نأخذ السطر الأول فقط للـ Callback Data

    file_keyboard.append([InlineKeyboardButton("↩️ العودة للقائمة الرئيسية", callback_data='check_and_main_menu')])

    reply_markup = InlineKeyboardMarkup(file_keyboard)

    await query.edit_message_text(
        text="العروض التي يمكنك شرائها - (اضغط على الملف للشراء أو لمعرفة التفاصيل):",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

# ... (بقية دوال المستخدم)

async def show_earn_ruble_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    bot_username = (await context.bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start={user_id}"
    
    user = get_user(user_id)
    
    message_text = (
        "**🎁 اربح روبل مجاني عن طريق نظام الإحالة:**\n\n"
        f"✅ ستحصل على **{REFERRAL_BONUS} روبل** لكل مستخدم ينضم عبر رابطك ويشترك في القنوات.\n\n"
        f"🔗 **رابط الإحالة الخاص بك:**\n`{referral_link}`\n\n"
        f"👥 **إجمالي الإحالات:** {user['referral_count']}\n"
    )
    
    keyboard = [
        [InlineKeyboardButton("📤 مشاركة الرابط", url=f"tg://msg?text=انضم%20إلى%20البوت%20واكسب%20الروبل!%20{referral_link}")],
        [InlineKeyboardButton("↩️ العودة للقائمة الرئيسية", callback_data='check_and_main_menu')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='HTML')


async def prompt_buy_file(update: Update, context: ContextTypes.DEFAULT_TYPE, file_name: str) -> None:
    """تأكيد عملية الشراء. (هنا file_name هو السطر الأول فقط من اسم الملف الأصلي)"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user(user_id)
    
    # نحتاج للبحث في قاعدة البيانات باستخدام جزء من الاسم أو الوصف
    # الأفضل تغيير طريقة حفظ البيانات لتخزين الاسم المختصر والوصف بشكل منفصل
    
    # ***تعديل مؤقت***: للأسف، نظام قاعدة البيانات الحالي لا يدعم البحث بالاسم المختصر.
    # للحفاظ على وظيفة الشراء، يجب تمرير الاسم الكامل. 
    # سنفترض أننا سنستخدم الاسم الكامل (الوصف) في هذه الخطوة لتبسيط الحل.
    
    # **للتشغيل الصحيح:** يجب أن يكون 'file_name' في هذا الجزء هو الاسم/الوصف الكامل للملف.
    # بما أننا نستخدم .splitlines()[0] في show_files_menu، يجب تعديل آلية البحث في DB
    # ولكن للتسهيل الآن، سنستخدم ما تم تمريره:
    
    # ***ملاحظة للمستخدم: عند إضافة ملف، يجب أن يكون السطر الأول من الاسم فريداً***
    # سنحاول البحث باستخدام LIKE
    
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT name, price, file_link FROM files WHERE name LIKE ? LIMIT 1", (file_name + '%',))
    details_full = cursor.fetchone()
    conn.close()
    
    if not details_full:
        await query.edit_message_text("❌ الملف غير موجود حالياً.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ العودة", callback_data='buy_file')]]))
        return
        
    full_name, price, _ = details_full
    
    if user['balance'] < price:
        await query.edit_message_text(
            f"❌ **عذراً، رصيدك غير كافٍ!**\n\nرصيدك: {user['balance']:.2f} روبل\nسعر الملف: {price:.2f} روبل",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ شحن الرصيد", callback_data='buy_points'), InlineKeyboardButton("↩️ العودة", callback_data='buy_file')]]),
            parse_mode='HTML'
        )
        return

    # رسالة تأكيد
    keyboard = [
        [InlineKeyboardButton(f"✅ تأكيد الشراء ({price:.2f} روبل)", callback_data=f'confirm_buy_{full_name.replace(" ", "_").splitlines()[0]}')],
        [InlineKeyboardButton("❌ إلغاء", callback_data='buy_file')]
    ]
    await query.edit_message_text(
        f"**هل أنت متأكد من شراء ملف '{full_name.splitlines()[0]}'؟**\n\n{full_name.splitlines()[1:]}\n\nسيتم خصم {price:.2f} روبل من رصيدك.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def confirm_buy_file(update: Update, context: ContextTypes.DEFAULT_TYPE, file_name: str) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user(user_id)
    
    # نحتاج لـ Name الكامل
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT name, price, file_link FROM files WHERE name LIKE ? LIMIT 1", (file_name + '%',))
    details_full = cursor.fetchone()
    conn.close()
    
    if not details_full:
        await query.edit_message_text("❌ عملية فاشلة: الملف غير موجود.", reply_markup=await get_main_menu_markup(user_id))
        return
        
    full_name, price, file_link = details_full
    
    if user['balance'] < price:
        await query.edit_message_text("❌ عملية فاشلة: رصيدك أصبح غير كافٍ.", reply_markup=await get_main_menu_markup(user_id))
        return

    update_user_balance(user_id, -price)
    
    await context.bot.send_message(
        chat_id=user_id,
        text=f"✅ **مبروك! تم الشراء بنجاح.**\n\n**ملف: {full_name.splitlines()[0]}**\n\n**تفاصيل:**\n{full_name.splitlines()[1:]}\n\n**رابط التحميل:**\n`{file_link}`\n\nيرجى حفظ الرابط.",
        parse_mode='HTML'
    )
    
    await query.edit_message_text(
        f"تم خصم {price:.2f} روبل من رصيدك. تحقق من رسالتك الخاصة لاستلام الملف.",
        reply_markup=await get_main_menu_markup(user_id),
        parse_mode='HTML'
    )


# ==============================================================================
# 5. معالجات تحويل الروبل (Transfer Handlers)
# ==============================================================================
# (بقية دوال التحويل كما هي)

async def transfer_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    user = get_user(query.from_user.id)
    
    await query.edit_message_text(
        f"**📥 تحويل روبل**\n\nرصيدك الحالي: **{user['balance']:.2f} روبل**\n\nأدخل **المبلغ** الذي تود تحويله:",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data='cancel_transfer')]])
    )
    return AWAITING_TRANSFER_AMOUNT

async def receive_transfer_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    text = update.message.text
    user = get_user(user_id)
    
    try:
        amount = float(text)
        if amount <= 0.01:
            await update.message.reply_text("❌ يجب أن يكون المبلغ أكبر من 0.01 روبل. أدخل مبلغاً صحيحاً.")
            return AWAITING_TRANSFER_AMOUNT
        
        if amount > user['balance']:
            await update.message.reply_text(f"❌ رصيدك ({user['balance']:.2f}) لا يكفي لتحويل {amount:.2f} روبل. أدخل مبلغاً صحيحاً.")
            return AWAITING_TRANSFER_AMOUNT
            
        context.user_data['transfer_amount'] = amount
        await update.message.reply_text("✅ تم قبول المبلغ. الآن، أرسل **آيدي** المستخدم الذي تود تحويل الروبل إليه:")
        return AWAITING_TRANSFER_TARGET
        
    except ValueError:
        await update.message.reply_text("❌ المبلغ غير صحيح. أدخل رقماً فقط.")
        return AWAITING_TRANSFER_AMOUNT

async def receive_transfer_target(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    sender_id = update.effective_user.id
    amount = context.user_data.get('transfer_amount')
    text = update.message.text
    
    try:
        receiver_id = int(text)
        if receiver_id == sender_id:
            await update.message.reply_text("❌ لا يمكنك التحويل إلى نفسك. أرسل آيدي مستخدم آخر.")
            return AWAITING_TRANSFER_TARGET
        
        get_user(receiver_id) 

        update_user_balance(sender_id, -amount)
        update_user_balance(receiver_id, amount)
        
        await update.message.reply_text(f"✅ **تم التحويل بنجاح!** تم خصم {amount:.2f} روبل من رصيدك وتحويلها للمستخدم **{receiver_id}**.")
        await context.bot.send_message(
            chat_id=receiver_id,
            text=f"🎉 **مبروك!** وصلك تحويل بقيمة **{amount:.2f} روبل** من المستخدم **{sender_id}**."
        )

        context.user_data.clear()
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text("❌ آيدي المستخدم غير صحيح. أدخل رقماً صحيحاً.")
        return AWAITING_TRANSFER_TARGET

async def cancel_transfer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    context.user_data.clear()
    await query.edit_message_text("✅ تم إلغاء عملية التحويل.", reply_markup=await get_main_menu_markup(query.from_user.id))
    return ConversationHandler.END

# ==============================================================================
# 6. معالجات المشرف (Admin Handlers) - تحسين لوحة التحكم وإضافة الملف
# ==============================================================================

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """عرض لوحة تحكم المشرف بخيارات مميزة."""
    
    keyboard = [
        [InlineKeyboardButton("➕ إضافة ملف PHP جديد", callback_data='admin_add_file')],
        [InlineKeyboardButton("📝 إدارة/تعديل الملفات", callback_data='admin_list_files')],
        [InlineKeyboardButton("💰 تعديل رصيد مستخدم", callback_data='admin_edit_balance')],
        [InlineKeyboardButton("📊 إحصائيات البوت", callback_data='admin_stats')],
        [InlineKeyboardButton("📣 إرسال رسالة جماعية", callback_data='admin_broadcast')],
        [InlineKeyboardButton("🔙 رجوع لقائمة المستخدم", callback_data='check_and_main_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🛠 **لوحة تحكم المشرف - الخيارات المتقدمة**\nاختر الإجراء الذي تريده:",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

async def admin_prompt_add_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """الخطوة 1: طلب اسم الملف ووصفه المفصل."""
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "أدخل **اسم الملف ووصفه الكامل** (مثال:\n• ملف انشاء كروبات 💎\n• ينشأ بليوم 50 كروب\n\n**نوع الملف** php أو py)",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data='cancel_admin')]])
    )
    return AWAITING_FILE_NAME

async def admin_receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال الاسم والوصف الكامل وطلب السعر."""
    # حفظ النص كاملاً كـ 'name' في قاعدة البيانات
    context.user_data['new_file_name'] = update.message.text 
    await update.message.reply_text("أدخل **سعر الملف** بالروبل (عدد عشري/صحيح):", parse_mode='HTML')
    return AWAITING_FILE_PRICE

async def admin_receive_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال السعر وطلب الرابط."""
    try:
        price = float(update.message.text)
        context.user_data['new_file_price'] = price
        await update.message.reply_text("أدخل **رابط الملف** (مثل رابط مباشر):", parse_mode='HTML')
        return AWAITING_FILE_LINK
    except ValueError:
        await update.message.reply_text("❌ السعر غير صحيح. أدخل رقماً فقط.")
        return AWAITING_FILE_PRICE

async def admin_receive_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال الرابط وحفظ الملف."""
    file_name = context.user_data['new_file_name']
    file_price = context.user_data['new_file_price']
    file_link = update.message.text

    if add_file_to_db(file_name, file_price, file_link):
        # عرض السطر الأول فقط كاسم في رسالة التأكيد
        await update.message.reply_text(f"✅ تم إضافة الملف بنجاح!\nالاسم: {file_name.splitlines()[0]}\nالسعر: {file_price} روبل")
    else:
        await update.message.reply_text(f"❌ فشل الإضافة. ربما يكون الملف **{file_name.splitlines()[0]}** موجوداً بالفعل.")

    context.user_data.clear()
    return ConversationHandler.END

async def cancel_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """إلغاء عملية المشرف (ملف، تحويل رصيد... إلخ)."""
    user_id = update.effective_user.id
    context.user_data.clear()
    
    # إصلاح لضمان عمل زر الإلغاء بشكل صحيح
    if update.callback_query:
        await update.callback_query.answer("✅ تم إلغاء العملية.")
        await update.callback_query.edit_message_text("✅ تم إلغاء عملية المشرف.", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🛠️ العودة للوحة المشرف", callback_data='show_admin_panel')]
        ]))
    elif update.message:
        await update.message.reply_text("✅ تم إلغاء عملية المشرف.", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🛠️ العودة للوحة المشرف", callback_data='show_admin_panel')]
        ]))
    
    return ConversationHandler.END

# ==============================================================================
# 7. معالج الأزرار الموحد (Callback Query Handler)
# ==============================================================================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    message = query.message
    
    await query.answer()

    # 1. التحقق من الاشتراك والرجوع للقائمة الرئيسية
    if data == 'check_and_main_menu' or data == 'check_sub':
        is_subscribed = await check_subscription(user_id, context)
        if is_subscribed:
            await register_pending_referral(user_id, context)
            await edit_to_main_menu(message, context, user_id)
        # إذا لم يكن مشتركاً، تم الرد بـ query.answer() في البداية
            
    # 2. وظائف لوحة المشرف المضافة
    elif data == 'show_admin_panel':
        # هذا الزر مخصص لزر الإلغاء أو الرجوع من المحادثات الفرعية
        if user_id == ADMIN_ID:
            await admin_panel(Update(update_id=0, message=message), context)
        else:
            await query.answer("❌ لا تملك صلاحية.", show_alert=True)
            
    # 3. وظائف القائمة الرئيسية
    elif data == 'buy_file':
        await show_files_menu(update, context)
        
    elif data == 'earn_ruble':
        await show_earn_ruble_menu(update, context)
        
    elif data == 'balance_info':
        user = get_user(user_id)
        await query.answer(f"رصيدك الحالي هو: {user['balance']:.2f} روبل", show_alert=True)
        
    elif data == 'user_info':
        user = get_user(user_id)
        referrer_info = f"بواسطة {user['referrer_id']}" if user['referrer_id'] != 0 else "لا يوجد"
        await query.answer(f"معلوماتك:\nالآيدي: {user_id}\nالرصيد: {user['balance']:.2f} روبل\nالإحالات: {user['referral_count']}\nالمُحيل: {referrer_info}", show_alert=True)
        
    elif data in ['buy_points', 'buy_hosting', 'free_ruble', 'proof_channel', 'admin_list_files', 'admin_stats', 'admin_edit_balance', 'admin_broadcast']:
        # تم تفعيل الأزرار المتبقية برسالة مؤقتة
        await query.answer("لم يتم تنفيذ هذه الوظيفة بعد. نعتذر للإزعاج.", show_alert=True)

    # 4. شراء الملفات
    elif data.startswith('buy_file_'):
        file_name = data.replace('buy_file_', '').replace('_', ' ')
        await prompt_buy_file(update, context, file_name)
        
    elif data.startswith('confirm_buy_'):
        file_name = data.replace('confirm_buy_', '').replace('_', ' ')
        await confirm_buy_file(update, context, file_name)

    # 5. إلغاء المشرف
    elif data == 'cancel_admin':
        await cancel_admin_action(update, context)


# ==============================================================================
# 8. إعداد Flask و Webhook
# ==============================================================================

init_db()

app = Flask(__name__)
application = Application.builder().token(TOKEN).updater(None).build()

# إضافة جميع الـ Handlers

# ConversationHandler لإضافة ملفات المشرف
admin_add_file_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(admin_prompt_add_file, pattern='^admin_add_file$')],
    states={
        AWAITING_FILE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(ADMIN_ID), admin_receive_name)],
        AWAITING_FILE_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(ADMIN_ID), admin_receive_price)],
        AWAITING_FILE_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(ADMIN_ID), admin_receive_link)],
    },
    # تم تعديل fallbacks لاستخدام دالة الإلغاء الجديدة
    fallbacks=[CommandHandler('cancel', cancel_admin_action), CallbackQueryHandler(cancel_admin_action, pattern='^cancel_admin$')],
)
application.add_handler(admin_add_file_conv)

# ConversationHandler لتحويل الروبل
transfer_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(transfer_start, pattern='^transfer_ruble$')],
    states={
        AWAITING_TRANSFER_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_transfer_amount)],
        AWAITING_TRANSFER_TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_transfer_target)],
    },
    fallbacks=[CommandHandler('cancel', cancel_transfer), CallbackQueryHandler(cancel_transfer, pattern='^cancel_transfer$')],
)
application.add_handler(transfer_conv)


# معالجات الأوامر الرئيسية
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("admin", admin_panel, filters=filters.User(ADMIN_ID))) 

# معالج الأزرار المضمنة
application.add_handler(CallbackQueryHandler(button_handler))


@app.route('/', methods=['GET'])
def index():
    return "Telegram Bot Webhook is running!", 200

@app.route('/set_webhook', methods=['GET', 'POST'])
async def set_webhook():
    if not WEBHOOK_URL:
        return jsonify({"status": "error", "message": "WEBHOOK_URL not set in environment variables."}), 500
    
    await application.initialize() 
    
    await application.bot.set_webhook(url=WEBHOOK_URL, secret_token=SECRET_TOKEN)
    return jsonify({"status": "ok", "message": f"تم ضبط خطاف الويب على: {WEBHOOK_URL}"}), 200

@app.route('/telegram', methods=['POST'])
def telegram_webhook(): 
    
    if request.headers.get('X-Telegram-Bot-Api-Secret-Token') != SECRET_TOKEN:
        logger.warning("Unauthorized access attempt to webhook.")
        return 'Unauthorized', 403

    try:
        data = request.get_json(force=True)
        update = Update.de_json(data, application.bot)
        
        asyncio.run(application.process_update(update))

    except Exception as e:
        logger.error(f"Error processing update: {e}")

    return 'OK', 200


if __name__ == "__main__":
    if not TOKEN or ADMIN_ID == 0 or not WEBHOOK_URL:
        logger.error("Configuration missing: Check BOT_TOKEN, ADMIN_ID, and WEBHOOK_URL environment variables.")
    
    print(f"Flask App running on port {PORT}. Webhook URL: {WEBHOOK_URL}")
    app.run(host='0.0.0.0', port=PORT)
