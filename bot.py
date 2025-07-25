import os
import logging
import asyncio
from datetime import datetime, timedelta
import pytz  # Добавляем поддержку часовых поясов
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler
import aiohttp
import json
from models import Session, User, Notification

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

# Add logging for telegram
logging.getLogger('telegram').setLevel(logging.DEBUG)
logging.getLogger('httpx').setLevel(logging.DEBUG)

# Constants from environment variables
GOSPLAN_API_URL = os.getenv('GOSPLAN_API_URL', 'https://v2test.gosplan.info/fz44')
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', 60))
TIMEZONE = pytz.timezone('Europe/Moscow')  # Добавляем константу для часового пояса

def format_datetime(dt):
    """Convert UTC datetime to local timezone and format it."""
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    local_dt = dt.astimezone(TIMEZONE)
    return local_dt.strftime('%d.%m.%Y %H:%M')

# Conversation states
MAIN_MENU, WAITING_FOR_OKVED, REMOVE_OKVED_MENU = range(3)

# Callback data
ADD_OKVED = 'add_okved'
REMOVE_OKVED = 'remove_okved'
CHECK_STATUS = 'check_status'
BACK_TO_MENU = 'back_to_menu'
ADD_MORE_OKVED = 'add_more_okved'
FINISH_ADDING = 'finish_adding'

async def get_or_create_user(telegram_id: int, session: Session) -> User:
    """Get existing user or create new one."""
    user = session.query(User).filter_by(telegram_id=telegram_id).first()
    if not user:
        user = User(telegram_id=telegram_id)
        session.add(user)
        session.commit()
    return user

def get_main_keyboard():
    """Create main menu keyboard."""
    keyboard = [
        [InlineKeyboardButton("📝 Добавить код ОКВЭД", callback_data=ADD_OKVED)],
        [InlineKeyboardButton("❌ Удалить код ОКВЭД", callback_data=REMOVE_OKVED)],
        [InlineKeyboardButton("📊 Текущие настройки", callback_data=CHECK_STATUS)]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_okved_action_keyboard():
    """Create keyboard for OKVED actions."""
    keyboard = [
        [InlineKeyboardButton("➕ Добавить ещё код", callback_data=ADD_MORE_OKVED)],
        [InlineKeyboardButton("✅ Завершить добавление", callback_data=FINISH_ADDING)],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_remove_okved_keyboard(okved_codes):
    """Create keyboard for removing OKVED codes."""
    keyboard = []
    if okved_codes:
        codes = okved_codes.split(',')
        for code in codes:
            keyboard.append([InlineKeyboardButton(f"❌ {code.strip()}", callback_data=f"del_{code.strip()}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад в меню", callback_data=BACK_TO_MENU)])
    return InlineKeyboardMarkup(keyboard)

def get_start_keyboard():
    """Create start menu keyboard."""
    keyboard = [[KeyboardButton("🚀 Старт"), KeyboardButton("🔄 Перезапустить")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message with main menu when the command /start is issued."""
    session = Session()
    try:
        user = await get_or_create_user(update.effective_user.id, session)
        welcome_message = (
            "👋 Добро пожаловать в бот мониторинга госзакупок!\n\n"
            "Я помогу вам отслеживать интересующие вас закупки по кодам ОКВЭД.\n\n"
            "Выберите действие:"
        )
        await update.message.reply_text(welcome_message, reply_markup=get_start_keyboard())
        await update.message.reply_text("Основное меню:", reply_markup=get_main_keyboard())
        return MAIN_MENU
    finally:
        session.close()

async def handle_okved_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle OKVED code input."""
    okved_code = update.message.text.strip()
    
    # Basic validation of OKVED format
    if not okved_code.replace('.', '').isdigit():
        await update.message.reply_text(
            "❌ Неверный формат кода ОКВЭД. Используйте формат XX.XX",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад в меню", callback_data=BACK_TO_MENU)
            ]])
        )
        return WAITING_FOR_OKVED

    session = Session()
    try:
        user = await get_or_create_user(update.effective_user.id, session)
        # Get existing codes
        existing_codes = set(user.okved_codes.split(',')) if user.okved_codes else set()
        # Add new code
        existing_codes.add(okved_code)
        # Remove empty strings
        existing_codes.discard('')
        # Save updated codes
        user.okved_codes = ','.join(existing_codes)
        session.commit()
        
        codes_list = '\n'.join([f"- {code}" for code in existing_codes])
        await update.message.reply_text(
            f"✅ Код ОКВЭД {okved_code} успешно добавлен!\n\nВаши текущие коды:\n{codes_list}",
            reply_markup=get_okved_action_keyboard()
        )
        return WAITING_FOR_OKVED
    finally:
        session.close()

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages."""
    text = update.message.text
    if text == "🚀 Старт" or text == "🔄 Перезапустить":
        return await start(update, context)
    return MAIN_MENU

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button presses."""
    query = update.callback_query
    await query.answer()  # Acknowledge the button press

    if query.data == ADD_OKVED:
        await query.message.edit_text(
            "Пожалуйста, введите код ОКВЭД в формате XX.XX\n"
            "Например: 62.01",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад в меню", callback_data=BACK_TO_MENU)
            ]])
        )
        return WAITING_FOR_OKVED
    
    elif query.data == REMOVE_OKVED:
        session = Session()
        try:
            user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
            if user and user.okved_codes:
                await query.message.edit_text(
                    "Выберите коды ОКВЭД для удаления:",
                    reply_markup=get_remove_okved_keyboard(user.okved_codes)
                )
                return REMOVE_OKVED_MENU
            else:
                await query.message.edit_text(
                    "❌ У вас не установлены коды ОКВЭД для мониторинга.",
                    reply_markup=get_main_keyboard()
                )
                return MAIN_MENU
        finally:
            session.close()
    
    elif query.data == CHECK_STATUS:
        session = Session()
        try:
            user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
            if user and user.okved_codes:
                # Get the latest notification
                latest_notification = session.query(Notification).filter_by(
                    user_id=user.id
                ).order_by(Notification.created_at.desc()).first()

                status_text = "📊 Текущие настройки:\n"
                status_text += "Коды ОКВЭД:\n"
                status_text += "\n".join([f"- {code}" for code in user.okved_codes.split(',')])
                
                if latest_notification:
                    status_text += f"\n\n🕒 Последняя проверка: {format_datetime(latest_notification.created_at)}"
                else:
                    status_text += "\n\n🕒 Проверки еще не выполнялись"
                
                status_text += f"\n⏱ Интервал проверки: {CHECK_INTERVAL} секунд"
                
                await query.message.edit_text(
                    status_text,
                    reply_markup=get_main_keyboard()
                )
            else:
                await query.message.edit_text(
                    "❌ У вас не установлены коды ОКВЭД для мониторинга.",
                    reply_markup=get_main_keyboard()
                )
        finally:
            session.close()
        return MAIN_MENU
    
    elif query.data == BACK_TO_MENU:
        await query.message.edit_text(
            "Выберите действие:",
            reply_markup=get_main_keyboard()
        )
        return MAIN_MENU

    elif query.data.startswith("del_"):
        code_to_remove = query.data.replace("del_", "")
        session = Session()
        try:
            user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
            if user and user.okved_codes:
                codes = user.okved_codes.split(',')
                if code_to_remove in codes:
                    codes.remove(code_to_remove)
                    user.okved_codes = ','.join(codes)
                    session.commit()
                    await query.message.edit_text(
                        f"✅ Код ОКВЭД '{code_to_remove}' удален из мониторинга.",
                        reply_markup=get_remove_okved_keyboard(user.okved_codes)
                    )
                else:
                    await query.message.edit_text(
                        f"❌ Код ОКВЭД '{code_to_remove}' не найден в ваших настройках.",
                        reply_markup=get_remove_okved_keyboard(user.okved_codes)
                    )
            else:
                await query.message.edit_text(
                    "❌ У вас не установлены коды ОКВЭД для мониторинга.",
                    reply_markup=get_main_keyboard()
                )
        finally:
            session.close()
        return REMOVE_OKVED_MENU

    elif query.data == ADD_MORE_OKVED:
        await query.message.edit_text(
            "Пожалуйста, введите код ОКВЭД в формате XX.XX\n"
            "Например: 62.01",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад в меню", callback_data=BACK_TO_MENU)
            ]])
        )
        return WAITING_FOR_OKVED
    
    elif query.data == FINISH_ADDING:
        await query.message.edit_text(
            "Выберите действие:",
            reply_markup=get_main_keyboard()
        )
        return MAIN_MENU

async def check_tenders(context: ContextTypes.DEFAULT_TYPE):
    """Periodically check for new tenders."""
    logger.info(f"Starting tender check at {format_datetime(datetime.utcnow())}")
    try:
        session = Session()
        try:
            users = session.query(User).filter(User.okved_codes.isnot(None)).all()
            logger.info(f"Found {len(users)} users with OKVED codes")
            
            if not users:
                logger.warning("No users with OKVED codes found!")
                return
                
            for user in users:
                if not user.okved_codes:
                    logger.warning(f"User {user.telegram_id} has no OKVED codes")
                    continue
                    
                okved_codes = user.okved_codes.split(',')
                logger.info(f"Checking tenders for user {user.telegram_id} with OKVED codes: {okved_codes}")
                
                # Get the latest notification time for this user
                latest_notification = session.query(Notification).filter_by(
                    user_id=user.id
                ).order_by(Notification.created_at.desc()).first()

                latest_check_time = latest_notification.created_at if latest_notification else datetime.min.replace(tzinfo=None)
                logger.info(f"Latest check time for user {user.telegram_id}: {format_datetime(latest_check_time)}")
                
                for okved_code in okved_codes:
                    try:
                        async with aiohttp.ClientSession() as http_session:
                            params = {
                                'okved2': okved_code.strip(),
                                'sortBy': 'UPDATE_DATE',
                                'sortDirection': 'DESC',
                                'pageSize': 20
                            }
                            logger.info(f"Making API request to {GOSPLAN_API_URL}/purchases with params: {params}")
                            
                            async with http_session.get(
                                f"{GOSPLAN_API_URL}/purchases",
                                params=params,
                                timeout=30
                            ) as response:
                                logger.info(f"API response status: {response.status}")
                                if response.status == 200:
                                    try:
                                        tenders = await response.json()
                                        logger.info(f"Received {len(tenders)} tenders for OKVED {okved_code}")
                                        
                                        if not tenders:
                                            logger.info(f"No tenders found for OKVED {okved_code}")
                                            continue

                                        new_tenders_count = 0
                                        for tender in tenders:
                                            # Convert tender published_at to datetime
                                            tender_date = datetime.fromisoformat(tender.get('published_at')).replace(tzinfo=None)
                                            logger.info(f"Checking tender {tender.get('purchase_number')} published at {tender_date}")
                                            
                                            # Check if tender is newer than our last check
                                            if tender_date > latest_check_time:
                                                existing_notification = session.query(Notification).filter_by(
                                                    user_id=user.id,
                                                    tender_number=tender.get('purchase_number')
                                                ).first()
                                                
                                                if not existing_notification:
                                                    new_tenders_count += 1
                                                    notification = Notification(
                                                        user_id=user.id,
                                                        tender_number=tender.get('purchase_number'),
                                                        tender_name=tender.get('object_info', 'Нет описания'),
                                                        tender_amount=tender.get('max_price', 0),
                                                        tender_url=f"https://zakupki.gov.ru/epz/order/notice/ea44/view/common-info.html?regNumber={tender.get('purchase_number')}"
                                                    )
                                                    session.add(notification)
                                                    session.commit()
                                                    
                                                    message = (
                                                        f"🔔 Новая закупка!\n\n"
                                                        f"📋 Номер: {tender.get('purchase_number')}\n"
                                                        f"📝 Название: {tender.get('object_info', 'Нет описания')}\n"
                                                        f"💰 Сумма: {tender.get('max_price', 0):,.2f} {tender.get('currency_code', 'RUB')}\n"
                                                        f"📅 Дата публикации: {datetime.fromisoformat(tender.get('published_at')).strftime('%d.%m.%Y %H:%M')}\n"
                                                        f"⏰ Прием заявок до: {datetime.fromisoformat(tender.get('collecting_finished_at')).strftime('%d.%m.%Y %H:%M')}\n"
                                                        f"🏢 Заказчик: {tender.get('customers', ['Не указан'])[0]}\n"
                                                        f"🔍 ОКВЭД: {okved_code}\n"
                                                    )
                                                    
                                                    keyboard = [[
                                                        InlineKeyboardButton(
                                                            "🔍 Подробнее",
                                                            url=notification.tender_url
                                                        )
                                                    ]]
                                                    
                                                    try:
                                                        await context.bot.send_message(
                                                            chat_id=user.telegram_id,
                                                            text=message,
                                                            reply_markup=InlineKeyboardMarkup(keyboard)
                                                        )
                                                        notification.is_sent = True
                                                        notification.sent_at = datetime.utcnow()
                                                        session.commit()
                                                        logger.info(f"Successfully sent notification for tender {tender.get('purchase_number')} to user {user.telegram_id}")
                                                    except Exception as e:
                                                        logger.error(f"Error sending message to user {user.telegram_id}: {e}")
                                                else:
                                                    logger.info(f"Tender {tender.get('purchase_number')} already notified")
                                            else:
                                                logger.info(f"Tender {tender.get('purchase_number')} is older than last check time")
                                        logger.info(f"Found {new_tenders_count} new tenders for user {user.telegram_id} with OKVED {okved_code}")
                                    except json.JSONDecodeError as e:
                                        logger.error(f"Error decoding JSON response: {e}")
                                else:
                                    logger.error(f"API request failed with status {response.status}")
                    except aiohttp.ClientError as e:
                        logger.error(f"HTTP request error: {e}")
                    except Exception as e:
                        logger.error(f"Unexpected error while processing OKVED {okved_code}: {e}")
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Error in check_tenders: {e}")
    logger.info("Tender check completed")

def main():
    """Start the bot."""
    # Initialize application with job queue
    application = Application.builder().token(os.getenv('TELEGRAM_TOKEN')).build()

    # Create conversation handler
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            MessageHandler(filters.Regex('^(🚀 Старт|🔄 Перезапустить)$'), start)
        ],
        states={
            MAIN_MENU: [
                CallbackQueryHandler(button_handler),
                MessageHandler(filters.Regex('^(🚀 Старт|🔄 Перезапустить)$'), start)
            ],
            WAITING_FOR_OKVED: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex('^(🚀 Старт|🔄 Перезапустить)$'), handle_okved_input),
                CallbackQueryHandler(button_handler),
                MessageHandler(filters.Regex('^(🚀 Старт|🔄 Перезапустить)$'), start)
            ],
            REMOVE_OKVED_MENU: [
                CallbackQueryHandler(button_handler),
                MessageHandler(filters.Regex('^(🚀 Старт|🔄 Перезапустить)$'), start)
            ]
        },
        fallbacks=[
            CommandHandler('start', start),
            MessageHandler(filters.Regex('^(🚀 Старт|🔄 Перезапустить)$'), start)
        ],
        per_message=False
    )

    # Add conversation handler
    application.add_handler(conv_handler)

    # Add error handler
    application.add_error_handler(error_handler)

    # Start the periodic check with job queue
    job_queue = application.job_queue
    job_queue.run_repeating(check_tenders, interval=CHECK_INTERVAL, first=1)

    # Start the Bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors in the bot."""
    logger.error(f"Exception while handling an update: {context.error}")
    
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "😔 Произошла ошибка при обработке запроса. Пожалуйста, попробуйте еще раз или начните сначала с помощью команды /start"
        )

if __name__ == '__main__':
    main() 