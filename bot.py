# import necessary libraries and modules
import time
import random
import logging
from secrets import token_hex

from telebot.async_telebot import AsyncTeleBot
from telebot.types import (
    InlineKeyboardMarkup as IM, InlineKeyboardButton as IB,
    InputFile, InputMediaPhoto, ChatAdministratorRights, Message
)
from captcha.image import ImageCaptcha
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import TOKEN
from database import DB

# initialize bot, captcha generator and database
bot = AsyncTeleBot(TOKEN, parse_mode='html')
cap = ImageCaptcha()
db = DB('database.db')

from translator import *  # translator for multilanguage support


# generate random secret code of specific length (default 24 symbols)
def create_secret_code(len=24):
    return token_hex(len//2)


# check if bot has enough permissions to mute and delete messages
async def check_permissions(chat_id):
    my_member = await bot.get_chat_member(chat_id, bot.user.id)
    if my_member.can_restrict_members and my_member.can_delete_messages:
        return True
    return False


# /start command handler for private messages
@bot.message_handler(['start'])
async def _start_pm(msg: Message):
    _ = tr(msg)
    await bot.send_message(msg.chat.id, _('start_text'))


# handler for new chat members (triggered when someone joins the group)
@bot.message_handler(content_types=['new_chat_members'])
async def _new_members(msg: Message):
    _ = tr(msg)  # translate function for this chat

    for member in msg.new_chat_members:
        _ = get_translator(member.language_code if member.language_code in get_langs() else _.lang)

        # if bot itself was added
        if member.id == bot.user.id: 
            await bot.send_message(msg.chat.id, _('thx_add_chat'))

            # check bot permissions and notify admin
            if not await check_permissions(msg.chat.id):
                await bot.send_message(msg.chat.id, _('no_rights'))
            else:
                await bot.send_message(msg.chat.id, _('will_check'))
            continue
        
        # skip other bots (do not captcha bots)
        if member.is_bot:
            continue
        
        # if bot has no rights, do nothing
        if not await check_permissions(msg.chat.id):
            await bot.send_message(msg.chat.id, _('cant_show_captcha'))
            continue

        # create user mention link
        user_link = f"<a href='{f't.me/{member.username}' if member.username else f'tg://user?id={member.id}'}'>{member.full_name}</a>"

        # **NEW: Send welcome message with security warning**
        welcome_message = _(
            "👋 Welcome, {user_link}!\n\n"
            "This group uses a simple yet effective CAPTCHA system developed by <b>Stupidmoni-dev</b> "
            "to ensure that only real users can participate. 🚀\n\n"
            "⚠️ Beware! Many Telegram groups use fake verification bots that might steal your data "
            "or try to scam you. Our system ensures security without unnecessary risks.\n\n"
            "Please solve the CAPTCHA below to verify yourself."
        ).format(user_link=user_link)

        await bot.send_message(msg.chat.id, welcome_message, disable_web_page_preview=True)

        # get default chat permissions and temporarily mute new user
        perms = (await bot.get_chat(msg.chat.id)).permissions
            
        perms.can_send_messages = False
        perms.can_send_audios = False
        perms.can_send_documents = False 
        perms.can_send_photos = False 
        perms.can_send_videos = False 
        perms.can_send_video_notes = False 
        perms.can_send_voice_notes = False 
        perms.can_send_polls = False 
        perms.can_send_other_messages = False
    
        await bot.restrict_chat_member(msg.chat.id, member.id, until_date=time.time(),
            permissions=perms, use_independent_chat_permissions=True)
        
        # generate captcha code and store it in DB
        captcha_code = create_secret_code(6)
        await db.set_captcha(msg.from_user.id, captcha_code, chat_id=msg.chat.id, kick_at=time.time()+600, message_id=msg.id)

        # generate fake captcha buttons + real code, and shuffle them
        captcha_codes = [create_secret_code(6) for _ in range(8)] + [captcha_code]
        random.shuffle(captcha_codes)
        rm = IM()
        rm.add(*[IB(ccode, callback_data=f'captcha:{msg.from_user.id}:{ccode}') for ccode in captcha_codes])

        # send captcha image with buttons to chat
        await bot.send_photo(
            msg.chat.id,
            InputFile(cap.generate(captcha_code)),
            _('hello_solve_captcha').format(user_link=user_link),
            reply_markup=rm,
            show_caption_above_media=True, has_spoiler=True, 
            reply_to_message_id=msg.id,
        )


# handler when user presses captcha button
@bot.callback_query_handler(func=lambda c: c.data.startswith('captcha'))
async def _captcha(c):
    _, user_id, code = c.data.split(':')
    _ = tr(c)

    # if another user clicks, show error
    if c.from_user.id != int(user_id):
        return await bot.answer_callback_query(c.id, _("not_yours"), True)

    # if captcha solved
    if await db.get_captcha(c.from_user.id) == code:
        await bot.send_message(c.message.chat.id, _('captcha_solved'))
        await db.dont_kick(c.message.chat.id, c.from_user.id)
        await bot.answer_callback_query(c.id)
        
        # give back default chat permissions
        perms = (await bot.get_chat(c.message.chat.id)).permissions
        await bot.restrict_chat_member(c.message.chat.id, c.from_user.id, permissions=perms, use_independent_chat_permissions=True)

        # delete captcha message
        await bot.delete_message(c.message.chat.id, c.message.id)

    else:  # if captcha failed
        await bot.answer_callback_query(c.id, _("incorrect"), True)

        # generate new captcha and update DB
        captcha_code = create_secret_code(6)
        await db.set_captcha(c.from_user.id, captcha_code, chat_id=c.message.chat.id, kick_at=time.time()+600)

        # generate fake codes + real one
        captcha_codes = [create_secret_code(6) for _ in range(8)] + [captcha_code]
        random.shuffle(captcha_codes)
        rm = IM()
        rm.add(*[IB(ccode, callback_data=f'captcha:{c.from_user.id}:{ccode}') for ccode in captcha_codes])

        # update captcha image in message
        await bot.edit_message_media(
            InputMediaPhoto(InputFile(cap.generate(captcha_code)),
            _('solve_captcha'), show_caption_above_media=True, has_spoiler=True),
            c.message.chat.id, c.message.id, reply_markup=rm
        )


# periodic job to kick users who didn't pass captcha
async def _kick(bot: AsyncTeleBot, db):
    async for chat_id, user_id, message_id in db.iter_users_to_kick():
        try:
            member = await bot.get_chat_member(chat_id, user_id)
            await bot.ban_chat_member(chat_id, user_id, time.time()+31)
            _ = tr(member.user, True)
            user_link = f"<a href='{f't.me/{member.user.username}' if member.user.username else f'tg://user?id={member.user.id}'}'>{member.user.full_name}</a>"
            await bot.send_message(chat_id, _('kicked_user').format(user_link=user_link), disable_web_page_preview=True)
            await db.dont_kick(chat_id, user_id)
            await bot.delete_message(chat_id, message_id)
        except:
            import traceback
            traceback.print_exc()


# main function to start bot and scheduler
async def start():
    logger = logging.getLogger('TeleBot')
    logger.setLevel(logging.INFO)

    await db.bootstrap()
    await db.sql("""
        CREATE TABLE IF NOT EXISTS captcha (
            user_id INTEGER,
            code TEXT,
            chat_id INTEGER,
            kick_at NUMERIC,
            message_id INTEGER
        );
    """)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(_kick, 'interval', seconds=10, args=[bot, db])
    scheduler.start()

    await bot.polling(non_stop=True)
    await db.teardown()
