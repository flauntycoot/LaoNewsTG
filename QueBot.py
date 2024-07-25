from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, ConversationHandler

TOKEN = '7379421430:AAFdz3CWwAlssEKPlOr2dw3ma3SyjDaK64k'
YOUR_CHAT_ID = '-1002244669392'  # Замените на ваш действительный Telegram ID или Group ID

# Определяем этапы разговора
NAME, CONTACT, DATE, REASON = range(4)

# Начальная команда /start
async def start(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text(
        "Здравствуйте! Добро пожаловать в наш сервис записи. Пожалуйста, введите ваше имя."
    )
    return NAME

# Получение имени
async def get_name(update: Update, context: CallbackContext) -> int:
    user = update.message.from_user
    context.user_data['name'] = update.message.text
    await update.message.reply_text(
        f"Спасибо, {context.user_data['name']}! Теперь введите ваш контактный номер."
    )
    return CONTACT

# Получение контакта
async def get_contact(update: Update, context: CallbackContext) -> int:
    context.user_data['contact'] = update.message.text
    await update.message.reply_text(
        "Отлично! Теперь укажите удобную дату и время для визита (в формате ММ-ДД ЧЧ:ММ)."
    )
    return DATE

# Получение даты
async def get_date(update: Update, context: CallbackContext) -> int:
    context.user_data['date'] = update.message.text
    await update.message.reply_text(
        "Пожалуйста, укажите причину обращения."
    )
    return REASON

# Получение причины
async def get_reason(update: Update, context: CallbackContext) -> int:
    context.user_data['reason'] = update.message.text
    name = context.user_data['name']
    contact = context.user_data['contact']
    date = context.user_data['date']
    reason = context.user_data['reason']
    
    await update.message.reply_text(
        f"Спасибо за предоставленную информацию!\nИмя: {name}\nКонтакт: {contact}\nДата и время: {date}\nПричина: {reason}\n\nМы свяжемся с вами для подтверждения записи."
    )

    # Отправка сообщения в ваш личный чат
    await context.bot.send_message(
        chat_id=YOUR_CHAT_ID,
        text=f"Новая заявка на посещение:\n\nИмя: {name}\nКонтакт: {contact}\nДата и время: {date}\nПричина: {reason}"
    )

    return ConversationHandler.END

# Команда отмены
async def cancel(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text(
        "Запись отменена. Если захотите попробовать снова, просто отправьте команду /start."
    )
    return ConversationHandler.END

def main():
    application = Application.builder().token(TOKEN).build()

    # Определение этапов разговора и команд
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_contact)],
            DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_date)],
            REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_reason)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    application.add_handler(conv_handler)

    application.run_polling()

if __name__ == '__main__':
    main()
