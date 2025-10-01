import os
import json
import sqlite3
import telegram
import logging
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
REQUIRED_CHANNELS = [c.strip() for c in os.environ.get("REQUIRED_CHANNELS", "").split(',') if c.strip()]
SUPPORT_USERNAME = os.environ.get("SUPPORT_USERNAME", "support_user")

if not TOKEN:
    raise ValueError("❌ يجب تعيين BOT_TOKEN كمتغير بيئي.")
if ADMIN_ID == 0:
    logging.warning("⚠️ لم يتم تعيين ADMIN_ID. لن تعمل وظائف المشرف.")


REFERRAL_BONUS = 0.5  
DATABASE_NAME = 'bot_data.db'

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# حالات المحادثة
AWAITING_FILE_NAME, AWAITING_FILE_PRICE, AWAITING_FILE_LINK = range(3)
AWAITING_TRANSFER_AMOUNT, AWAITING_TRANSFER_TARGET = range(3, 5)
# حالات المشرف لإدارة المستخدمين
AWAITING_USER_ID, AWAITING_NEW_BALANCE, AWAITING_BALANCE_CHANGE = range(5, 8) 
AWAITING_BROADCAST_MESSAGE = 8

# ==============================================================================
# 2. دوال قاعدة البيانات (Database Functions)
# ==============================================================================
# (يتم الحفاظ عليها كما هي)
def init_db():
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0,
            referral_count INTEGER DEFAULT 0,
            referrer_id INTEGER DEFAULT 0,
            is_subscribed INTEGER DEFAULT 0
        )
    ''')

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
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def set_user_balance(user_id, new_balance):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_balance, user_id))
    conn.commit()
    conn.close()
    
def get_all_user_ids():
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users


# ... (بقية دوال DB)
def add_referral(user_id, referrer_id):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET referrer_id = ? WHERE user_id = ?", (referrer_id, user_id))
    cursor.execute("UPDATE users SET balance = balance + ?, referral_count = referral_count + 1 WHERE user_id = ?", 
                   (REFERRAL_BONUS, referrer_id))
    conn.commit()
    conn.close()

def get_all_files():
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT name, price, file_link FROM files WHERE is_available = 1")
    files = cursor.fetchall()
    conn.close()
    return files

def add_file_to_db(name, price, file_link):
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


# ==============================================================================
# 3. دوال الواجهة (UI & Check Functions)
# ==============================================================================
# (يتم الحفاظ عليها كما هي)
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
         InlineKeyboardButton("➕ شحن الرصيد", callback_data='buy_points')], # تم تغيير النص ليتناسب مع وظيفة الشحن
        [InlineKeyboardButton("📞 الدعم الفني", url=f"t.me/{SUPPORT_USERNAME}")],
        [InlineKeyboardButton("☁️ شراء استضافة", callback_data='buy_hosting'),
         InlineKeyboardButton("🆓 روبل مجاني", callback_data='free_ruble')],
        [InlineKeyboardButton("✅ اثبات التسليم", callback_data='proof_channel')]
    ]
    return InlineKeyboardMarkup(keyboard)

async def get_main_menu_text(user_id, application):
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
    text = await get_main_menu_text(user_id, context.application)
    
    try:
        await message.edit_text(text, reply_markup=markup, parse_mode='HTML')
    except telegram.error.BadRequest:
        await message.reply_text(text, reply_markup=markup, parse_mode='HTML')


# ==============================================================================
# 4. معالجات المستخدم (User Handlers) - (تم دمج كل الوظائف القديمة)
# ==============================================================================
# ... (دوال start, register_pending_referral, show_files_menu, show_earn_ruble_menu, 
#       prompt_buy_file, confirm_buy_file, transfer_start, receive_transfer_amount, 
#       receive_transfer_target, cancel_transfer)

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
    
    if user_id == ADMIN_ID:
        await admin_panel(update, context)
        return
        
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
    text = await get_main_menu_text(user_id, context.application)
    
    await update.message.reply_text(text, reply_markup=markup, parse_mode='HTML')

async def show_files_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    available_files = get_all_files()

    file_keyboard = []
    for file_name, price, _ in available_files:
        short_name_display = file_name.splitlines()[0]
        button_text = f"ملف: {short_name_display} ({price:.2f} روبل)"
        file_keyboard.append([InlineKeyboardButton(button_text, callback_data=f'buy_file_{file_name.replace(" ", "_")}')]) 

    file_keyboard.append([InlineKeyboardButton("↩️ العودة للقائمة الرئيسية", callback_data='check_and_main_menu')])

    reply_markup = InlineKeyboardMarkup(file_keyboard)

    await query.edit_message_text(
        text="العروض التي يمكنك شرائها - (اضغط على الملف للشراء أو لمعرفة التفاصيل):",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

async def show_earn_ruble_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    bot_username = (await context.application.bot.get_me()).username
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

async def prompt_buy_file(update: Update, context: ContextTypes.DEFAULT_TYPE, file_name_encoded: str) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user(user_id)
    
    file_name = file_name_encoded.replace('_', ' ')
    
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT name, price, file_link FROM files WHERE name = ? LIMIT 1", (file_name,))
    details_full = cursor.fetchone()
    conn.close()
    
    if not details_full:
        await query.edit_message_text("❌ الملف غير موجود حالياً.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ العودة", callback_data='buy_file')]]))
        return
        
    full_name, price, _ = details_full
    short_name = full_name.splitlines()[0]
    
    if user['balance'] < price:
        await query.edit_message_text(
            f"❌ **عذراً، رصيدك غير كافٍ!**\n\nرصيدك: {user['balance']:.2f} روبل\nسعر الملف: {price:.2f} روبل",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ شحن الرصيد", callback_data='buy_points'), InlineKeyboardButton("↩️ العودة", callback_data='buy_file')]]),
            parse_mode='HTML'
        )
        return

    keyboard = [
        [InlineKeyboardButton(f"✅ تأكيد الشراء ({price:.2f} روبل)", callback_data=f'confirm_buy_{file_name_encoded}')],
        [InlineKeyboardButton("❌ إلغاء", callback_data='buy_file')]
    ]
    await query.edit_message_text(
        f"**هل أنت متأكد من شراء ملف '{short_name}'؟**\n\n{' '.join(full_name.splitlines()[1:])}\n\nسيتم خصم {price:.2f} روبل من رصيدك.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def confirm_buy_file(update: Update, context: ContextTypes.DEFAULT_TYPE, file_name_encoded: str) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user(user_id)

    file_name = file_name_encoded.replace('_', ' ')
    
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT name, price, file_link FROM files WHERE name = ? LIMIT 1", (file_name,))
    details_full = cursor.fetchone()
    conn.close()
        
    if not details_full:
        await query.edit_message_text("❌ عملية فاشلة: الملف غير موجود.", reply_markup=await get_main_menu_markup(user_id))
        return
        
    full_name, price, file_link = details_full
    short_name = full_name.splitlines()[0]
    
    if user['balance'] < price:
        await query.edit_message_text("❌ عملية فاشلة: رصيدك أصبح غير كافٍ.", reply_markup=await get_main_menu_markup(user_id))
        return

    update_user_balance(user_id, -price)
    
    await context.bot.send_message(
        chat_id=user_id,
        text=f"✅ **مبروك! تم الشراء بنجاح.**\n\n**ملف: {short_name}**\n\n**تفاصيل:**\n{' '.join(full_name.splitlines()[1:])}\n\n**رابط التحميل:**\n`{file_link}`\n\nيرجى حفظ الرابط.",
        parse_mode='HTML'
    )
    
    await query.edit_message_text(
        f"تم خصم {price:.2f} روبل من رصيدك. تحقق من رسالتك الخاصة لاستلام الملف.",
        reply_markup=await get_main_menu_markup(user_id),
        parse_mode='HTML'
    )
    
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
# 5. معالجات المشرف (Admin Handlers)
# ==============================================================================

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """عرض لوحة تحكم المشرف بخيارات مميزة."""
    
    keyboard = [
        [InlineKeyboardButton("➕ إضافة ملف PHP جديد", callback_data='admin_add_file')],
        [InlineKeyboardButton("📝 إدارة/تعديل الملفات (غير مفعل)", callback_data='admin_list_files')],
        [InlineKeyboardButton("💰 تعديل رصيد مستخدم", callback_data='admin_edit_balance_start')],
        [InlineKeyboardButton("📊 إحصائيات البوت (غير مفعل)", callback_data='admin_stats')],
        [InlineKeyboardButton("📣 إرسال رسالة جماعية (غير مفعل)", callback_data='admin_broadcast')],
        [InlineKeyboardButton("❌ إغلاق لوحة المشرف", callback_data='admin_close_panel')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message = update.effective_message
    
    try:
        if update.callback_query:
            await update.callback_query.edit_message_text(
                "👑 **لوحة تحكم المشرف المتميزة** 👑\n\nاختر الإجراء الذي تريده:",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        else:
             await message.reply_text(
                "👑 **لوحة تحكم المشرف المتميزة** 👑\n\nاختر الإجراء الذي تريده:",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
    except Exception as e:
        logger.error(f"Failed to show admin panel: {e}")
        
# --- دوال إضافة ملف (Add File) ---

async def admin_prompt_add_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "أدخل **اسم الملف ووصفه الكامل** (مثال:\n• ملف انشاء كروبات 💎\n• ينشأ بليوم 50 كروب\n\n**نوع الملف** php أو py)",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء العملية", callback_data='cancel_admin')]])
    )
    return AWAITING_FILE_NAME

async def admin_receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['new_file_name'] = update.message.text 
    
    try:
        await update.message.reply_text(
            "أدخل **سعر الملف** بالروبل (عدد عشري/صحيح):", 
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Error in admin conversation: {e}")
        await update.message.reply_text("❌ حدث خطأ داخلي. تم إلغاء العملية. يرجى المحاولة مرة أخرى باستخدام /admin.")
        context.user_data.clear()
        return ConversationHandler.END 

    return AWAITING_FILE_PRICE

async def admin_receive_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        price = float(update.message.text)
        context.user_data['new_file_price'] = price
        await update.message.reply_text("أدخل **رابط الملف** (مثل رابط مباشر):", parse_mode='HTML')
        return AWAITING_FILE_LINK
    except ValueError:
        await update.message.reply_text("❌ السعر غير صحيح. أدخل رقماً فقط.")
        return AWAITING_FILE_PRICE

async def admin_receive_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    file_name = context.user_data['new_file_name']
    file_price = context.user_data['new_file_price']
    file_link = update.message.text

    if add_file_to_db(file_name, file_price, file_link):
        await update.message.reply_text(f"✅ تم إضافة الملف بنجاح!\nالاسم: {file_name.splitlines()[0]}\nالسعر: {file_price} روبل")
    else:
        await update.message.reply_text(f"❌ فشل الإضافة. ربما يكون الملف **{file_name.splitlines()[0]}** موجوداً بالفعل.")

    context.user_data.clear()
    await admin_panel(update, context)
    
    return ConversationHandler.END

# --- دوال إدارة الرصيد (Edit Balance) ---

async def admin_edit_balance_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "**💰 تعديل رصيد مستخدم**\n\nأرسل **آيدي (ID)** المستخدم الذي تود تعديل رصيده:",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء العملية", callback_data='cancel_admin')]])
    )
    return AWAITING_USER_ID

async def admin_receive_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    
    try:
        user_id_to_edit = int(text)
        user_data = get_user(user_id_to_edit) # سيضيفه إذا لم يكن موجوداً

        context.user_data['target_user_id'] = user_id_to_edit
        
        keyboard = [
            [InlineKeyboardButton("تعديل الرصيد إلى قيمة محددة", callback_data='admin_set_balance')],
            [InlineKeyboardButton("زيادة/نقصان من الرصيد الحالي", callback_data='admin_change_balance')],
            [InlineKeyboardButton("❌ إلغاء العملية", callback_data='cancel_admin')]
        ]
        
        await update.message.reply_text(
            f"✅ **المستخدم:** `{user_id_to_edit}`\n**الرصيد الحالي:** `{user_data['balance']:.2f} روبل`\n\nاختر طريقة التعديل:",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        # لا نخرج من ConversationHandler هنا، بل نبقى حتى يتم اختيار الطريقة
        return AWAITING_USER_ID 
        
    except ValueError:
        await update.message.reply_text("❌ آيدي المستخدم غير صحيح. أدخل رقماً صحيحاً.")
        return AWAITING_USER_ID

async def admin_prompt_set_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "أرسل **قيمة الرصيد الجديدة** (مثال: `10.5`):",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء العملية", callback_data='cancel_admin')]])
    )
    return AWAITING_NEW_BALANCE

async def admin_set_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    target_user_id = context.user_data.get('target_user_id')
    new_balance_text = update.message.text
    
    try:
        new_balance = float(new_balance_text)
        if new_balance < 0:
             await update.message.reply_text("❌ الرصيد يجب أن يكون رقماً موجباً أو صفراً. أعد المحاولة.")
             return AWAITING_NEW_BALANCE
             
        set_user_balance(target_user_id, new_balance)
        
        await update.message.reply_text(f"✅ **تم تحديث رصيد** المستخدم `{target_user_id}` إلى **{new_balance:.2f} روبل**.")
        
        context.user_data.clear()
        await admin_panel(update, context) # العودة للوحة المشرف
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text("❌ القيمة المدخلة غير صحيحة. أدخل رقماً فقط.")
        return AWAITING_NEW_BALANCE

async def admin_prompt_change_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "أرسل **قيمة التعديل** (لزيادة: `+5.0`، للنقصان: `-2.5`):",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء العملية", callback_data='cancel_admin')]])
    )
    return AWAITING_BALANCE_CHANGE

async def admin_change_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    target_user_id = context.user_data.get('target_user_id')
    change_value_text = update.message.text
    
    try:
        change_value = float(change_value_text)
        
        update_user_balance(target_user_id, change_value)
        
        current_balance = get_user(target_user_id)['balance']
        
        action = "زيادة" if change_value > 0 else "نقصان"
        
        await update.message.reply_text(f"✅ **تمت عملية {action} الرصيد** للمستخدم `{target_user_id}` بقيمة `{abs(change_value):.2f}` روبل. الرصيد الجديد: **{current_balance:.2f} روبل**.")
        
        context.user_data.clear()
        await admin_panel(update, context) 
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text("❌ القيمة المدخلة غير صحيحة. يجب أن تكون بصيغة `+رقم` أو `-رقم`.")
        return AWAITING_BALANCE_CHANGE


async def cancel_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """إلغاء عملية المشرف وضمان العودة للوحة التحكم."""
    context.user_data.clear()
    
    # يفضل استخدام الرسالة الأصلية إن أمكن
    if update.callback_query:
        message = update.callback_query.message
        await update.callback_query.answer("✅ تم إلغاء العملية.")
    else:
        message = update.message
        
    # محاولة تعديل الرسالة للعودة للوحة المشرف
    await admin_panel(message, context)
    
    return ConversationHandler.END

async def admin_close_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إغلاق لوحة المشرف وحذف الرسالة."""
    query = update.callback_query
    await query.answer("تم إغلاق اللوحة.")
    try:
        await query.message.delete()
    except Exception:
        await query.edit_message_text("✅ تم إغلاق لوحة المشرف.", reply_markup=None)

# ==============================================================================
# 6. معالج الأزرار الموحد (Callback Query Handler)
# ==============================================================================

async def main_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    message = query.message
    
    await query.answer()
    
    if data == 'check_and_main_menu' or data == 'check_sub':
        is_subscribed = await check_subscription(user_id, context)
        if is_subscribed:
            await register_pending_referral(user_id, context)
            await edit_to_main_menu(message, context, user_id)
            
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
        
    elif data == 'buy_points':
        await query.edit_message_text(
            "**لشحن رصيدك، يرجى التواصل مع الدعم الفني:**\n"
            f"@{SUPPORT_USERNAME}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ العودة للقائمة الرئيسية", callback_data='check_and_main_menu')]]),
            parse_mode='HTML'
        )
        
    elif data in ['buy_hosting', 'free_ruble', 'proof_channel', 'admin_list_files', 'admin_stats', 'admin_broadcast']:
        # تمت معالجة أزرار المشرف غير المنفذة هنا
        await query.answer("لم يتم تنفيذ هذه الوظيفة بعد. نعتذر للإزعاج.", show_alert=True)
        
async def buy_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    data = query.data
    
    if data.startswith('buy_file_'):
        file_name_encoded = data.replace('buy_file_', '')
        await prompt_buy_file(update, context, file_name_encoded)
        
    elif data.startswith('confirm_buy_'):
        file_name_encoded = data.replace('confirm_buy_', '')
        await confirm_buy_file(update, context, file_name_encoded)

# ==============================================================================
# 7. الإعداد والتشغيل (Long Polling)
# ==============================================================================

if __name__ == '__main__':
    init_db()
    application = Application.builder().token(TOKEN).build()

    # Conversation Handlers

    # 1. إضافة ملف (Add File)
    admin_add_file_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_prompt_add_file, pattern='^admin_add_file$')],
        states={
            AWAITING_FILE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(ADMIN_ID), admin_receive_name)],
            AWAITING_FILE_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(ADMIN_ID), admin_receive_price)],
            AWAITING_FILE_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(ADMIN_ID), admin_receive_link)],
        },
        fallbacks=[CommandHandler('cancel', cancel_admin_action), CallbackQueryHandler(cancel_admin_action, pattern='^cancel_admin$')],
        allow_reentry=True # يسمح بالدخول المتعدد للحالة (لزيادة الاستقرار)
    )
    application.add_handler(admin_add_file_conv)

    # 2. تحويل الروبل (Transfer Ruble)
    transfer_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(transfer_start, pattern='^transfer_ruble$')],
        states={
            AWAITING_TRANSFER_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_transfer_amount)],
            AWAITING_TRANSFER_TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_transfer_target)],
        },
        fallbacks=[CommandHandler('cancel', cancel_transfer), CallbackQueryHandler(cancel_transfer, pattern='^cancel_transfer$')],
        allow_reentry=True
    )
    application.add_handler(transfer_conv)
    
    # 3. تعديل رصيد المشرف (Admin Edit Balance) - NEW
    admin_edit_balance_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_edit_balance_start, pattern='^admin_edit_balance_start$')],
        states={
            AWAITING_USER_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(ADMIN_ID), admin_receive_user_id),
                CallbackQueryHandler(admin_prompt_set_balance, pattern='^admin_set_balance$'),
                CallbackQueryHandler(admin_prompt_change_balance, pattern='^admin_change_balance$'),
            ],
            AWAITING_NEW_BALANCE: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(ADMIN_ID), admin_set_balance)],
            AWAITING_BALANCE_CHANGE: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(ADMIN_ID), admin_change_balance)],
        },
        fallbacks=[CommandHandler('cancel', cancel_admin_action), CallbackQueryHandler(cancel_admin_action, pattern='^cancel_admin$')],
        allow_reentry=True
    )
    application.add_handler(admin_edit_balance_conv)


    # Command Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_panel, filters=filters.User(ADMIN_ID))) 
    
    # Callback Query Handlers (الأزرار)
    
    # معالج خاص لأزرار شراء الملفات وتأكيد الشراء
    application.add_handler(CallbackQueryHandler(buy_file_handler, pattern='^(buy_file_|confirm_buy_).*$'))

    # معالج لأزرار المشرف غير التفاعلية (حل مشكلة TypeError باستخدام .add_filters)
    if ADMIN_ID != 0:
        # معالج المشرف للعودة للوحة
        application.add_handler(
            CallbackQueryHandler(admin_panel, pattern='^show_admin_panel$').add_filters(filters.User(ADMIN_ID))
        )
        
        # معالج المشرف لإغلاق اللوحة
        application.add_handler(
            CallbackQueryHandler(admin_close_panel, pattern='^admin_close_panel$').add_filters(filters.User(ADMIN_ID))
        )

        # يتم معالجة باقي أزرار المشرف (غير المنفذة) في main_callback_handler
    
    # المعالج العام لبقية أزرار القائمة الرئيسية (يجب أن يكون الأخير)
    application.add_handler(CallbackQueryHandler(main_callback_handler))

    logger.info("🤖 البوت جاهز للتشغيل في وضع الاستطلاع الطويل (Long Polling)...")
    
    # تشغيل البوت في وضع الاستطلاع الطويل
    application.run_polling(poll_interval=1.0)
