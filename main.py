#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Virtual Number bot for Telegram
# Sends random virtual numbers to user
# Service: OnlineSim.io
# SourceCode (https://github.com/Kourva/OnlineSimBot)

# Standard library imports
import json
import random
import time
from typing import ClassVar, NoReturn, Any, Union, List, Dict

# Related third party module imports
import telebot
import phonenumbers
import countryflag
from googletrans import Translator

# Local application module imports
import utils
from utils import User
from vneng import VNEngine

# Initialize the bot token
bot: ClassVar[Any] = telebot.TeleBot(utils.get_token())
print(f"\33[1;36m::\33[m Bot is running with ID: {bot.get_me().id}")


def is_subscribed(user_id):
    try:
        # Check channel membership using the correct channel ID
        channel_id = -1001158537466
        channel_status = bot.get_chat_member(channel_id, user_id).status
        
        # Check group membership
        group_id = '@wwesmaat'
        group_status = bot.get_chat_member(group_id, user_id).status
        
        # This will print the user's status to your Termux console.
        # It helps to verify if the bot is correctly checking the membership.
        print(f"User {user_id} status in channel: {channel_status}")
        print(f"User {user_id} status in group: {group_status}")
        
        if channel_status in ['member', 'creator', 'administrator'] and group_status in ['member', 'creator', 'administrator']:
            return True
        else:
            return False
    except Exception as e:
        print(f"Error checking subscription status: {e}")
        return False

@bot.message_handler(commands=["start", "restart"])
def start_command_handler(message: ClassVar[Any]) -> NoReturn:
    """
    Function to handle start commands in bot
    Shows welcome messages to users

    Parameters:
        message (typing.ClassVar[Any]): Incoming message object

    Returns:
        None (typing.NoReturn)
    """

    # Fetch user's data
    user: ClassVar[Union[str, int]] = User(message.from_user)

    if not is_subscribed(user.id):
        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.add(telebot.types.InlineKeyboardButton(text="اشترك في القناة", url="https://t.me/+RQ3g-myV5Y6Ea0cY"))
        keyboard.add(telebot.types.InlineKeyboardButton(text="انضم للجروب", url="https://t.me/wwesmaat"))
        bot.send_message(
            chat_id=message.chat.id,
            text="أهلاً بك في بوت عالم الأرقام لتقديم الأرقام المجانية، للاستفادة من خدمات البوت يرجى الاشتراك في القناة والجروب أولاً ثم أعد تشغيل البوت.",
            reply_markup=keyboard
        )
        return

    # Send welcome message
    bot.send_chat_action(chat_id=message.chat.id, action="typing")
    bot.reply_to(
        message=message,
        text=(
            f"⁀➴ أهلاً {user.pn}\n"
            "أهلاً بك في بوت عالم الأرقام لتقديم الأرقام المجانية.\n\n"
        )
    )

    # Show buttons for /help and /number as inline buttons
    keyboard = telebot.types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        telebot.types.InlineKeyboardButton(text="مساعدة", callback_data="help_command"),
        telebot.types.InlineKeyboardButton(text="احصل على رقم", callback_data="number_command")
    )
    bot.send_message(message.chat.id, "اختر أحد الأوامر:", reply_markup=keyboard)


@bot.callback_query_handler(func=lambda call: call.data in ["help_command", "number_command"])
def handle_inline_commands(call):
    if call.data == "help_command":
        # Simulate a help command message
        message = call.message
        message.text = "/help"
        help_command_handler(message)
    elif call.data == "number_command":
        # Simulate a number command message
        message = call.message
        message.text = "/number"
        number_command_handler(message)
    
    bot.answer_callback_query(call.id)


@bot.message_handler(commands=["help", "usage"])
def help_command_handler(message: ClassVar[Any]) -> NoReturn:
    """
    Function to handle help commands in bot
    Shows help messages to users

    Parameters:
        message (typing.ClassVar[Any]): Incoming message object

    Returns:
        None (typing.NoReturn)
    """

    # Fetch user's data
    user: ClassVar[Union[str, int]] = User(message.from_user)

    if not is_subscribed(user.id):
        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.add(telebot.types.InlineKeyboardButton(text="اشترك في القناة", url="https://t.me/+RQ3g-myV5Y6Ea0cY"))
        keyboard.add(telebot.types.InlineKeyboardButton(text="انضم للجروب", url="https://t.me/wwesmaat"))
        bot.send_message(
            chat_id=message.chat.id,
            text="أهلاً بك في بوت عالم الأرقام لتقديم الأرقام المجانية، للاستفادة من خدمات البوت يرجى الاشتراك في القناة والجروب أولاً ثم أعد تشغيل البوت.",
            reply_markup=keyboard
        )
        return

    # Send Help message
    bot.send_chat_action(chat_id=message.chat.id, action="typing")
    bot.reply_to(
        message=message,
        text=(
           "·ᴥ· بوت الأرقام الوهمية\n\n"
           "يستخدم هذا البوت واجهة برمجة تطبيقات من onlinesim.io ويجلب أرقاماً فعّالة ومتاحة.\n"
           "كل ما عليك فعله هو إرسال بعض الأوامر للبوت وسيقوم بالبحث عن رقم عشوائي لك.\n\n══════════════\n"
           "★ للحصول على رقم جديد، يمكنك ببساطة إرسال الأمر /number\n\n"
           "★ للحصول على الرسائل الواردة، استخدم الزر المضمن (الرسائل الواردة). سيعرض لك آخر 5 رسائل.\n\n"
           "★ يمكنك أيضاً التحقق من ملف تعريف الرقم على تليجرام باستخدام الزر المضمن (التحقق من ملف تعريف الرقم).\n══════════════\n\n"
           "هذا كل ما تحتاج معرفته عن هذا البوت!"
        )
    )


@bot.message_handler(commands=["number"])
def number_command_handler(message: ClassVar[Any]) -> NoReturn:
    """
    Function to handle number commands in bot
    Finds and sends new virtual number to user

    Parameters:
        message (typing.ClassVar[Any]): Incoming message object

    Returns:
        None (typing.NoReturn)
    """

    # Fetch user's data
    user: ClassVar[Union[str, int]] = User(message.from_user)

    if not is_subscribed(user.id):
        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.add(telebot.types.InlineKeyboardButton(text="اشترك في القناة", url="https://t.me/+RQ3g-myV5Y6Ea0cY"))
        keyboard.add(telebot.types.InlineKeyboardButton(text="انضم للجروب", url="https://t.me/wwesmaat"))
        bot.send_message(
            chat_id=message.chat.id,
            text="أهلاً بك في بوت عالم الأرقام لتقديم الأرقام المجانية، للاستفادة من خدمات البوت يرجى الاشتراك في القناة والجروب أولاً ثم أعد تشغيل البوت.",
            reply_markup=keyboard
        )
        return

    # Send waiting prompt
    bot.send_chat_action(chat_id=message.chat.id, action="typing")
    prompt: ClassVar[Any] = bot.reply_to(
        message=message,
        text=(
            "جاري الحصول على رقم عشوائي لك...\n\n"
            "⁀➴ جلب الدول المتاحة:"
        ),
    )

    try:
        # Initialize the Virtual Number engine
        engine: ClassVar[Any] = VNEngine()

        # Get the countries and shuffle them
        countries: List[Dict[str, str]] = engine.get_online_countries()
        random.shuffle(countries)

        # Update prompt based on current status
        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=prompt.message_id,
            text=(
                "جاري الحصول على رقم عشوائي لك...\n\n"
                "⁀➴ جلب الدول المتاحة:\n"
                f"تم الحصول على {len(countries)} دولة\n\n"
                "⁀➴ اختبار الأرقام النشطة:\n"
            ),
        )

        # Find online and active number
        for country in countries:
            # Get numbers in country
            numbers: List[Dict[str, str]] = engine.get_country_numbers(
                country=country['name']
            )

            # Format country name
            country_name: str = country["name"].replace("_", " ").title()

            # Check numbers for country and find first valid one
            for number in numbers:
                # Parse the country to find it's details
                parsed_number: ClassVar[Union[str, int]] = phonenumbers.parse(
                    number=f"+{number[1]}"
                )

                # Format number to make it readable for user
                formatted_number: str = phonenumbers.format_number(
                    numobj=parsed_number,
                    num_format=phonenumbers.PhoneNumberFormat.NATIONAL
                )

                # Find flag emoji for number
                flag: str = countryflag.getflag(
                    [
                        phonenumbers.region_code_for_country_code(
                            country_code=parsed_number.country_code
                        )
                    ]
                )

                # Update prompt based on current status
                bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=prompt.message_id,
                    text=(
                        "جاري الحصول على رقم عشوائي لك...\n\n"
                        "⁀➴ جلب الدول المتاحة:\n"
                        f"تم الحصول على {len(countries)} دولة\n\n"
                        "⁀➴ اختبار الأرقام النشطة:\n"
                        f"جاري تجربة {country_name} ({formatted_number})"
                    ),
                )

                if engine.get_number_inbox(country['name'], number[1]):
                    # Make keyboard markup for number
                    Markup: ClassVar[Any] = telebot.util.quick_markup(
                        {
                            "𖥸 الرسائل الواردة": {
                                "callback_data": f"msg&{country['name']}&{number[1]}"
                            },

                            "꩜ تجديد": {
                                "callback_data": f"new_phone_number"
                            },

                            "التحقق من ملف تعريف الرقم": {
                                "url": f"tg://resolve?phone=+{number[1]}"
                            }
                        },
                        row_width=2
                    )

                    # Update prompt based on current status
                    bot.edit_message_text(
                        chat_id=message.chat.id,
                        message_id=prompt.message_id,
                        text=(
                            "جاري الحصول على رقم عشوائي لك...\n\n"
                            "⁀➴ جلب الدول المتاحة:\n"
                            f"تم الحصول على {len(countries)} دولة\n\n"
                            "⁀➴ اختبار الأرقام النشطة:\n"
                            f"جاري تجربة {country_name} ({formatted_number})\n\n"
                            f"{flag} إليك رقمك: +{number[1]}\n\n"
                            f"آخر تحديث: {number[0]}"
                        ),
                        reply_markup=Markup
                    )

                    # Return the function
                    return 1

        # Send failure message when no number found
        else:
            # Update prompt based on current status
            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=prompt.message_id,
                text=(
                        "جاري الحصول على رقم عشوائي لك...\n\n"
                        "⁀➴ جلب الدول المتاحة:\n"
                        f"تم الحصول على {len(countries)} دولة\n\n"
                        "⁀➴ اختبار الأرقام النشطة:\n"
                        f"لا يوجد رقم متاح حالياً!"
                    ),
            )

            # Return the function
            return 0
    
    except Exception as e:
        print(f"Error in number_command_handler: {e}")
        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=prompt.message_id,
            text="عذرًا، حدث خطأ أثناء محاولة جلب رقم جديد. يرجى المحاولة مرة أخرى."
        )


@bot.callback_query_handler(func=lambda x:x.data.startswith("msg"))
def number_inbox_handler(call: ClassVar[Any]) -> NoReturn:
    """
    Callback query handler to handle inbox messages
    Sends last 5 messages in number's inbox

    Parameters:
        call (typing.ClassVar[Any]): incoming call object

    Returns:
        None (typing.NoReturn)
    """
    # Initialize the Virtual Number engine
    engine: ClassVar[Any] = VNEngine()

    # Get country name and number from call's data
    country: str
    number: str
    _, country, number = call.data.split("&")

    # Get all messages and select last 5 messages
    messages: List[Dict[str, str]] = engine.get_number_inbox(
        country=country,
        number=number
    )[:5]

    # Send messages to user
    for message in messages:
        for key, value in message.items():
            translator = Translator()
            original_message = value.split('received from OnlineSIM.io')[0]
            translated_message = translator.translate(original_message, dest='ar').text
            bot.send_message(
                chat_id=call.message.chat.id,
                reply_to_message_id=call.message.message_id,
                text=(
                    f"⚯͛ الوقت: {key}\n\n"
                    f"الرسالة الأصلية: {original_message}\n\n"
                    f"الرسالة المترجمة: {translated_message}"
                )
            )

    # Answer callback query
    bot.answer_callback_query(
        callback_query_id=call.id,
        text=(
            "⁀➴ إليك آخر 5 رسائل\n\n"
            "إذا لم تصلك الرسالة، حاول مرة أخرى بعد دقيقة واحدة!"
        ),
        show_alert=True
    )


@bot.callback_query_handler(func=lambda x:x.data == "new_phone_number")
def new_number_handler(call):
    """
    Callback query handler to re-new number
    Find new phone number and updates the message

    Parameters:
        call (typing.ClassVar[Any]): incoming call object

    Returns:
        None (typing.NoReturn)
    """
    # Get chat id and message id from call object
    chat_id = call.message.chat.id
    message_id = call.message.message_id

    # Edit message based on current status
    bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=(
            "جاري الحصول على رقم عشوائي لك...\n\n"
            "⁀➴ جلب الدول المتاحة:"
        ),
    )

    try:
        # Initialize the Virtual Number engine
        engine: ClassVar[Any] = VNEngine()

        # Get the countries and shuffle them
        countries: List[Dict[str, str]] = engine.get_online_countries()
        random.shuffle(countries)

        # Update prompt based on current status
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=(
                "جاري الحصول على رقم عشوائي لك...\n\n"
                "⁀➴ جلب الدول المتاحة:\n"
                f"تم الحصول على {len(countries)} دولة\n\n"
                "⁀➴ اختبار الأرقام النشطة:\n"
            ),
        )

        # Find online and active number
        for country in countries:
            # Get numbers in country
            numbers: List[Dict[str, str]] = engine.get_country_numbers(
                country=country['name']
            )

            # Format country name
            country_name: str = country["name"].replace("_", " ").title()

            # Check numbers for country and find first valid one
            for number in numbers:
                # Parse the country to find it's details
                parsed_number: ClassVar[Union[str, int]] = phonenumbers.parse(
                    number=f"+{number[1]}"
                )

                # Format number to make it readable for user
                formatted_number: str = phonenumbers.format_number(
                    numobj=parsed_number,
                    num_format=phonenumbers.PhoneNumberFormat.NATIONAL
                )

                # Find flag emoji for number
                flag: str = countryflag.getflag(
                    [
                        phonenumbers.region_code_for_country_code(
                            country_code=parsed_number.country_code
                        )
                    ]
                )

                # Update prompt based on current status
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=(
                        "جاري الحصول على رقم عشوائي لك...\n\n"
                        "⁀➴ جلب الدول المتاحة:\n"
                        f"تم الحصول على {len(countries)} دولة\n\n"
                        "⁀➴ اختبار الأرقام النشطة:\n"
                        f"جاري تجربة {country_name} ({formatted_number})"
                    ),
                )

                if engine.get_number_inbox(country['name'], number[1]):
                    # Make keyboard markup for number
                    Markup: ClassVar[Any] = telebot.util.quick_markup(
                        {
                            "𖥸 الرسائل الواردة": {
                                "callback_data": f"msg&{country['name']}&{number[1]}"
                            },

                            "꩜ تجديد": {
                                "callback_data": f"new_phone_number"
                            },

                            "التحقق من ملف تعريف الرقم": {
                                "url": f"tg://resolve?phone=+{number[1]}"
                            }
                        },
                        row_width=2
                    )

                    # Update prompt based on current status
                    bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=(
                            "جاري الحصول على رقم عشوائي لك...\n\n"
                            "⁀➴ جلب الدول المتاحة:\n"
                            f"تم الحصول على {len(countries)} دولة\n\n"
                            "⁀➴ اختبار الأرقام النشطة:\n"
                            f"جاري تجربة {country_name} ({formatted_number})\n\n"
                            f"{flag} إليك رقمك: +{number[1]}\n\n"
                            f"آخر تحديث: {number[0]}"
                        ),
                        reply_markup=Markup
                    )

                    # Answer callback query
                    bot.answer_callback_query(
                        callback_query_id=call.id,
                        text="⁀➴ تم تحديث طلبك",
                        show_alert=False
                    )

                    # Return the function
                    return 1

        # Send failure message when no number found
        else:
            # Update prompt based on current status
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=(
                        "جاري الحصول على رقم عشوائي لك...\n\n"
                        "⁀➴ جلب الدول المتاحة:\n"
                        f"تم الحصول على {len(countries)} دولة\n\n"
                        "⁀➴ اختبار الأرقام النشطة:\n"
                        f"لا يوجد رقم متاح حالياً!"
                    ),
            )

            # Return the function
            return 0
    
    except Exception as e:
        print(f"Error in new_number_handler: {e}")
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="عذرًا، حدث خطأ أثناء محاولة جلب رقم جديد. يرجى المحاولة مرة أخرى."
        )


# Run the bot on polling mode
if __name__ == '__main__':
    try:
        bot.infinity_polling(
            skip_pending=True
        )
    except KeyboardInterrupt:
        raise SystemExit("\n\33[1;31m::\33[m تم الإيقاف بواسطة المستخدم")
