import os
from telegram.ext import Application, MessageHandler, CommandHandler, filters

from app.telegram_image_handler import handle_photo
from app.telegram_query_handler import handle_find_command, handle_next_command
from app.telegram_folder_choice_handler import (
    handle_choose_command,
    handle_pending_command,
)


def main():
    token = os.environ["TELEGRAM_BOT_TOKEN"]

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("find", handle_find_command))
    app.add_handler(CommandHandler("next", handle_next_command))
    app.add_handler(CommandHandler("choose", handle_choose_command))
    app.add_handler(CommandHandler("pending", handle_pending_command))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    print("Telegram bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
