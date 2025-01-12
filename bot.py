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





# инициализируем все что надо
bot = AsyncTeleBot(TOKEN, parse_mode='html')
cap = ImageCaptcha()
db = DB('database.db')



def create_secret_code(len=24):
    return token_hex(len//2)


async def check_permissions(chat_id):

    my_member = await bot.get_chat_member(chat_id, bot.user.id)

    if my_member.can_restrict_members and my_member.can_delete_messages:
        return True
    
    return False


# /start
@bot.message_handler(['start'])
async def _start_pm(msg):
    await bot.send_message(msg.chat.id, "Привет! Я капча бот! Добавь меня в чат и дай права администратора чтобы я мог проверять новых участников чата!")


# При новых участниках чата
@bot.message_handler(content_types=['new_chat_members'])
async def _new_members(msg: Message):

    for member in msg.new_chat_members:

        # если добавили самого бота
        if member.id == bot.user.id: 
            await bot.send_message(msg.chat.id, "Благодарю что добавили меня в чат!")

            # проверяем наличие прав у бота
            if not await check_permissions(msg.chat.id):
                await bot.send_message(msg.chat.id, "Только у меня нет прав ограничивать пользователей и удалять сообщения! Дай мне права, иначе я не смогу показывать капчу!")
            else:
                await bot.send_message(msg.chat.id, "Теперь я буду проверять новых участников на человечность!")
            
            continue

        
        # не показываем капчу для ботов
        if member.is_bot:
            continue

        
        # проверяем наличие прав у бота
        if not await check_permissions(msg.chat.id):
            await bot.send_message(msg.chat.id, "Упс! У меня нет прав ограничивать пользователей и удалять сообщения! Я не могу показать капчу!")
            continue

        


        user_link = f"<a href='{f't.me/{member.username}' if member.username else f'tg://user?id={member.id}'}'>{member.full_name}</a>"
        

        # получаем стандартные права чата, и изменяем их для определенного пользователя (мутим)
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
        
        # генерируем код для капчи
        captcha_code = create_secret_code(6)

        # записываем в БД
        await db.set_captcha(msg.from_user.id, captcha_code, chat_id=msg.chat.id, kick_at=time.time()+600, message_id=msg.id)

        # генерируем остальные кнопки и добавляем в клавиатуру
        captcha_codes = [create_secret_code(6) for _ in range(8)] + [captcha_code]
        random.shuffle(captcha_codes)
        rm = IM()
        rm.add(*[IB(ccode, callback_data=f'captcha:{msg.from_user.id}:{ccode}') for ccode in captcha_codes])

        # отправляем фотку с капчей
        await bot.send_photo(
            msg.chat.id,
            InputFile(cap.generate(captcha_code)),
            f'Привет, {user_link}! Реши капчу!',
            reply_markup=rm,
            show_caption_above_media=True, has_spoiler=True, 
            reply_to_message_id=msg.id,
        )


# при нажатии кнопки
@bot.callback_query_handler(func=lambda c: c.data.startswith('captcha'))
async def _captcha(c):
    code = c.data.split(':')[-1]

    # если код совпадает
    if await db.get_captcha(c.from_user.id) == code:
        await bot.send_message(c.message.chat.id, "капча решена!")
        await db.dont_kick(c.message.chat.id, c.from_user.id)
        await bot.answer_callback_query(c.id)
        
        # возвращаем права
        perms = (await bot.get_chat(c.message.chat.id)).permissions
        await bot.restrict_chat_member(c.message.chat.id, c.from_user.id, permissions=perms, use_independent_chat_permissions=True)

        # удаляем сообщение с капчей
        await bot.delete_message(c.message.chat.id, c.message.id)

    
    else: # если неверно
        await bot.answer_callback_query(c.id, "Неверно!", True)

        # генерируем новую капчу
        captcha_code = create_secret_code(6)
        await db.set_captcha(c.from_user.id, captcha_code, chat_id=c.message.chat.id, kick_at=time.time()+600)
        captcha_codes = [create_secret_code(6) for _ in range(8)] + [captcha_code]
        random.shuffle(captcha_codes)
        rm = IM()
        rm.add(*[IB(ccode, callback_data=f'captcha:{c.from_user.id}:{ccode}') for ccode in captcha_codes])

        # изменяем соо
        await bot.edit_message_media(
            InputMediaPhoto(InputFile(cap.generate(captcha_code)),
            "Реши капчу!", show_caption_above_media=True, has_spoiler=True),
            c.message.chat.id, c.message.id, reply_markup=rm
        )


# хендлер для кика тех, кно не прошел капчу
async def _kick(bot, db):
    async for chat_id, user_id, message_id in db.iter_users_to_kick():

        # кикаем бота
        await bot.ban_chat_member(chat_id, user_id, time.time()+31) # 31 сек - минимальное время бана
        member = await bot.get_chat_member(chat_id, user_id)
        user_link = f"<a href='{f't.me/{member.user.username}' if member.user.username else f'tg://user?id={member.user.id}'}'>{member.user.full_name}</a>"
        await bot.send_message(chat_id, f"{user_link} не прошел капчу и был кикнут!", disable_web_page_preview=True)
        await db.dont_kick(chat_id, user_id)
        await bot.delete_message(chat_id, message_id)
    



async def start():

    # врубаем логирование
    logger = logging.getLogger('TeleBot')
    logger.setLevel(logging.DEBUG)

    # подключаемся к бд и создаем таблицу
    await db.bootstrap()
    await db.sql("""
        CREATE TABLE IF NOT EXISTS captcha (
            user_id    INTEGER,
            code       TEXT,
            chat_id    INTEGER,
            kick_at    NUMERIC,
            message_id INTEGER
        );
    """)

    # настраиваем шедулер
    scheduler = AsyncIOScheduler()
    scheduler.add_job(_kick, 'interval', minutes=1, args=[bot, db])
    scheduler.start()

    # устанавливаем права бота по умолчанию (удаление сообщений и ограничивание пользователей)
    await bot.set_my_default_administrator_rights(
        ChatAdministratorRights(
            is_anonymous = False,
            can_manage_chat = False,
            can_delete_messages = True,
            can_manage_video_chats = False,
            can_restrict_members = True,
            can_promote_members = False,
            can_change_info = False,
            can_invite_users = False,
            can_post_messages = False,
            can_edit_messages = False,
            can_pin_messages = False,
            can_manage_topics = False,
            can_post_stories = False,
            can_edit_stories = False,
            can_delete_stories = False,
        )
    )

    # запускаем бота
    await bot.polling(non_stop=True)

    # если бот прекращает работу, отключаемся от БД
    await db.teardown()