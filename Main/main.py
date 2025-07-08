from typing import Final
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackContext, ApplicationBuilder
import os
import datetime
import json
from telegram.constants import ParseMode
from datetime import datetime, timedelta, time
import requests
from flask import Flask


ROUTINE = ''

# File paths - using absolute paths for PythonAnywhere
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IDS_FILE = os.path.join(BASE_DIR, 'ids.txt')
REMIND_TIME_FILE = os.path.join(BASE_DIR, 'remindTime.txt')


# --- Bot Starts ---
print('Starting up bot...')

TOKEN: Final = "7925285512:AAG1R_MEsyxCqbC_0zQJSXwPJXcb-ATc8To"
BOT_USERNAME: Final = '@cse_c_bot'




    

async def inform_all(update: Update, context: CallbackContext) -> None:
    """Manual command to send CT reminders to all users with 5-hour cooldown"""
    # Check cooldown first
    try:
        if os.path.exists(REMIND_TIME_FILE ):
            with open(REMIND_TIME_FILE, 'r') as f:
                last_run_str = f.read().strip()
                last_run = datetime.strptime(last_run_str, "%Y-%m-%d %H:%M:%S")

                if datetime.now() - last_run < timedelta(hours=3):
                    remaining_time = (last_run + timedelta(hours=3)) - datetime.now()
                    hours, remainder = divmod(remaining_time.seconds, 3600)
                    minutes = remainder // 60
                    await update.message.reply_text(
                        f"⏳ Command on cooldown. Try again in {hours}h {minutes}m"
                    )
                    return
    except Exception as e:
        print(f"Error reading cooldown file: {e}")

    # Proceed with normal execution
    ct_data = get_ct_data()

    if ct_data is None or not ct_data:
        await update.message.reply_text("⚠️ Couldn't connect to database or no CT data available.")
        return

    now = datetime.now()
    tomorrow = now.date() + timedelta(days=1)
    tomorrow_cts = []

    for ct_id, ct in ct_data.items():
        try:
            ct_date = datetime.strptime(ct['date'], "%Y-%m-%d").date()
            if ct_date == tomorrow:
                tomorrow_cts.append({
                    'subject': ct.get('subject', 'No Subject'),
                    'teacher': ct.get('teacher', 'Not specified'),
                    'syllabus': ct.get('syllabus', 'No syllabus')
                })
        except (KeyError, ValueError) as e:
            print(f"Skipping malformed CT {ct_id}: {e}")

    if not tomorrow_cts:
        await update.message.reply_text("ℹ️ No CTs scheduled for tomorrow.")
        return

    # Format the reminder message
    message = ["🔔 <b>CT Reminder: Tomorrow's Tests</b>"]
    for ct in tomorrow_cts:
        message.append(
            f"\n📚 <b>{ct['subject']}</b>\n"
            f"👨‍🏫 {ct['teacher']}\n"
            f"📖 {ct['syllabus']}\n"
        )
    full_message = "\n".join(message)

    # Read user IDs from file and send notifications
    try:
        with open(IDS_FILE , 'r') as f:
            user_ids = [line.strip() for line in f.readlines() if line.strip()]

        success_count = 0
        fail_count = 0

        for user_id in user_ids:
            try:
                await context.bot.send_message(chat_id=user_id, text=full_message, parse_mode='HTML')
                success_count += 1
            except Exception as e:
                print(f"Failed to send to {user_id}: {e}")
                fail_count += 1

        # Update last run time
        with open('remindTime.txt', 'w') as f:
            f.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        # Send report to admin who triggered the command
        report = (
            f"📊 Notification sent to {success_count} users\n"
            f"⚠️ Failed to send to {fail_count} users\n"
            f"⏳ Next available in 5 hours"
        )
        await update.message.reply_text(report)

    except FileNotFoundError:
        await update.message.reply_text("❌ Error: ids.txt not found")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
# Add this to your command handlers:
# application.add_handler(CommandHandler("informall", inform_all))
# Lets us use the /start command


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.message.chat.type != "private":
        await update.message.reply_text(
            "Please run /start in private chat: https://t.me/cse_c_bot")
        return
    chat_id = update.effective_chat.id
    with open(os.path.join(BASE_DIR, 'Td9n.gif'), 'rb') as animation:
        await context.bot.send_animation(chat_id=chat_id, animation=animation)

    user = update.effective_user
    if not user:
        await update.message.reply_text("Error: No user info.")
        return

    user_id = str(user.id)

    # Read existing IDs to avoid duplicates
    try:
        with open(IDS_FILE, "r") as f:
            existing_ids = set(line.strip() for line in f)
    except FileNotFoundError:
        existing_ids = set()

    if user_id in existing_ids:
        await update.message.reply_text("You are already registered.")
    else:
        with open(IDS_FILE, "a") as f:
            f.write(user_id + "\n")
        await update.message.reply_text(
            "You have been registered successfully!")
    await update.message.reply_text(
        'Hello there! I\'m pikachu known as pika pika your section assistant. How can i help you today? Enter /help to know every command i can help you with <3.'
    )


async def circulate(update: Update, context: CallbackContext):
    if not context.args:
        await update.message.reply_text("Usage: /cir <message to send>")
        return

    message_text = ' '.join(context.args)

    try:
        with open(IDS_FILE, "r") as f:
            user_ids = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        await update.message.reply_text("No recipients registered yet.")
        return

    if not user_ids:
        await update.message.reply_text("No recipients registered yet.")
        return

    sent_to = []
    failed_to = []

    for uid in user_ids:
        try:
            await context.bot.send_message(
                chat_id=int(uid),
                text="*** IMPORTANT NOTICE *** : \n\n" + message_text,
                parse_mode=ParseMode.MARKDOWN)
            sent_to.append(uid)
        except Exception as e:
            print(f"Failed to send to {uid}: {e}")
            failed_to.append(uid)

    reply_text = f"Message sent to {len(sent_to)} recipients."
    # if sent_to:
    # reply_text += "\nRecipients:\n" + ", ".join(sent_to)
    if failed_to:
        reply_text += f"\nFailed to send to {len(failed_to)} recipients."

    await update.message.reply_text(reply_text)

async def msg(update: Update, context: CallbackContext):
    if not context.args:
        await update.message.reply_text("Usage: /cir <message to send>")
        return

    message_text = ' '.join(context.args)

    try:
        with open(IDS_FILE, "r") as f:
            user_ids = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        await update.message.reply_text("No recipients registered yet.")
        return

    if not user_ids:
        await update.message.reply_text("No recipients registered yet.")
        return

    sent_to = []
    failed_to = []

    for uid in user_ids:
        try:
            await context.bot.send_message(
                chat_id=int(uid),
                text=message_text,
                parse_mode=ParseMode.MARKDOWN)
            sent_to.append(uid)
        except Exception as e:
            print(f"Failed to send to {uid}: {e}")
            failed_to.append(uid)

    reply_text = f"Message sent to {len(sent_to)} recipients."
    # if sent_to:
    # reply_text += "\nRecipients:\n" + ", ".join(sent_to)
    if failed_to:
        reply_text += f"\nFailed to send to {len(failed_to)} recipients."

    await update.message.reply_text(reply_text)


async def circulate_routine(update: Update, context: CallbackContext):
    # if not context.args:
    #     await update.message.reply_text("Usage: /cir <message to send>")
    #     return

    # message_text = ' '.join(context.args)

    try:
        with open(IDS_FILE, "r") as f:
            user_ids = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        await update.message.reply_text("No recipients registered yet.")
        return

    if not user_ids:
        await update.message.reply_text("No recipients registered yet.")
        return

    sent_to = []
    failed_to = []

    for uid in user_ids:
        try:
            # fn = gcw()
            fn = os.path.join(BASE_DIR, gcw())
            with open(fn, "rb") as photo:
                await context.bot.send_photo(chat_id=int(uid), photo=photo)
            sent_to.append(uid)
        except Exception as e:
            print(f"Failed to send to {uid}: {e}")
            failed_to.append(uid)

    reply_text = f"Routine sent to {len(sent_to)} recipients."
    # if sent_to:
    # reply_text += "\nRecipients:\n" + ", ".join(sent_to)
    if failed_to:
        reply_text += f"\nFailed to send to {len(failed_to)} recipients."

    await update.message.reply_text(reply_text)





async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        '***ADMIN ACCESS***\n\n /sendrt - To circulate the class routine among all registered users. Nothing to do. It will be updated by pikachu\n/remind - To do some good work\n/cir <message> - this command will circulate the given message to all the users...\nHere is the - [Server  Join Link](https://replit.com/join/oxerprkiyu-ibittosaha)\nClass Routines and CT routines will get updated from GITHUB\n\n -Thanks Pika pika',parse_mode='Markdown')





async def web_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        '*** CSE 24 in the air ***\n\n\n CLICK this => [Website](https://ruetcse24.vercel.app/)\n\nCLICK this => [Facebook Page](https://www.facebook.com/profile.php?id=61574730479807)\n\nCLICK this => [Profiles](https://ruetcse24.vercel.app/profiles)\n\n Pika pika pikachuuu',
        parse_mode='Markdown')


async def src_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        '***RESOURCES***\n\n\nCSE 1-1 => [Drive link](https://drive.google.com/drive/folders/1xbyCdj3XQ9AsCCF8ImI13HCo25JEhgUJ)\n CSE syllabus => [Drive link](https://drive.google.com/file/d/1pVF40-E0Oe8QI-EZp9S7udjnc0_Kquav/view?usp=drive_link) \n Orientation files => [Drive link](https://drive.google.com/drive/folders/10_-xTV-FsXnndtDiw_StqH2Zy9tQcWq0)  \n Resources provided by our humble seniors <3\n\n\nCSE G. classroom code: ***2o2ea2k3***\n\nMath G. Classroom code: ***aq4vazqi***\n\nChemistry G. Classroom code: ***wnlwjtbg***\n\n Have a good day\n\n That\'s all i have now.\n pika pika pikachuuu',
        parse_mode='Markdown')


# async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

#     day = datetime.datetime.today().strftime('%A').lower()

#     # print("Today is:", day.lower())
#     with open('routine.json', 'r') as file:
#         data = json.load(file)

#     # Print the data (now it's a Python dictionary)
#     # day="monday"
#     if day == "thursday" or day == "friday":
#         await update.message.reply_text("Chuti chuti yeeeee!")
#     else:
#         rout = (data["days"][day[0].upper() + day[1:]])
#         frmtd_str = "***Today's Routine("+day+")***\n\n\n"
#         for i in rout:
#             if rout[i] is not None:
#                 frmtd_str += f"\n\n{i}  {data['time_slots'][i]} => {rout[i]['subject']} (Room - {rout[i]['room']})  {rout[i]['teacher']}\n"
#             else:
#                 frmtd_str += f"\n\n{i}  {data['time_slots'][i]} => off\n"
#         frmtd_str += "\n\nPardon my mistakes. If you find any, please inform me.\n"

#         await update.message.reply_text(frmtd_str, parse_mode='Markdown')
#         await update.message.reply_text(
#             'CLICK this => [Live routine link](https://routine-c.vercel.app)\n Pika pika pikachuuu',
#             parse_mode='Markdown')



# async def tomorrow_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     day = datetime.datetime.today().strftime('%A').lower()

#     # print("Today is:", day.lower())
#     with open('routine.json', 'r') as file:
#         data = json.load(file)
#     dys = ["saturday", "sunday", "monday", "tuesday", "wednesday", "thursday","friday"]
#     day = dys[(dys.index(day) + 1) % 7]
#     # await update.message.reply_text(day)

#     # Print the data (now it's a Python dictionary)
#     # day="monday"
#     if day == "thursday" or day == "friday":
#         await update.message.reply_text("Chuti chuti yeeeee!")
#     else:
#         rout = (data["days"][day[0].upper() + day[1:]])
#         frmtd_str = "***Tomorrow's Routine ("+day+")***\n\n\n"
#         for i in rout:
#             if rout[i] is not None:
#                 frmtd_str += f"\n\n{i}  {data['time_slots'][i]} => {rout[i]['subject']} (Room - {rout[i]['room']})  {rout[i]['teacher']}\n"
#             else:
#                 frmtd_str += f"\n\n{i}  {data['time_slots'][i]} => off\n"
#         frmtd_str += "\n\nPardon my mistakes. If you find any, please inform me.\n"

#         await update.message.reply_text(frmtd_str, parse_mode='Markdown')
#         if day=='saturday':
#             await update.message.reply_text("\n### BOTH LABS => ALL 60\n")
#             await update.message.reply_text(
#                 'CLICK this => [Live routine link](https://routine-c.vercel.app)\n Pika pika pikachuuu',
#                 parse_mode='Markdown')


# async def latest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     await update.message.reply_text(
#         'Sumon & Rabbi will tell you. Pika pika I\'m working on it...')


async def ct_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        'wait few moments... let me see the database :)')
    chat_id = update.effective_chat.id
    # Send the photo
    with open("ct.png", 'rb') as photo:
        await context.bot.send_photo(chat_id=chat_id, photo=photo)
    await update.message.reply_text(
        'for any query \ncontact with Sumon or Rabbi\nHave a great day!')





# Log errors
async def error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f'Update {update} caused error {context.error}')


flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Bot is running!"

# Run the program
if __name__ == '__main__':

    # Create and configure bot
    # app = Application.builder().token(TOKEN).build()
    app = Application.builder().token(TOKEN).build()
    # Commands
    app.add_handler(CommandHandler('start', start_command))
    # app.add_handler(CommandHandler('ct', ct_command))
    app.add_handler(CommandHandler('admin', admin))
    # app.add_handler(CommandHandler('tomorrow', tomorrow_command))
    # app.add_handler(CommandHandler('today', today_command))
    # app.add_handler(CommandHandler('latest', latest_command))
    app.add_handler(CommandHandler("remind", inform_all))
    app.add_handler(CommandHandler('src', src_command))
    app.add_handler(CommandHandler('web', web_command))
    app.add_handler(CommandHandler('cir', circulate))
    app.add_handler(CommandHandler('sendrt', circulate_routine))
    app.add_handler(CommandHandler('ct', next_ct))
    app.add_handler(CommandHandler('msg', msg))
    # app.add_handler(CommandHandler('sendct', circulate_ct_routine))
    # setup_daily_reminder(app)
    # Messages

    # WEBHOOK_URL = "https://biittosaha.pythonanywhere.com/" + TOKEN
    # app.run_webhook(
    #     listen="0.0.0.0",
    #     port=5000,
    #     webhook_url=WEBHOOK_URL,
    #     cert=None  # Only if using HTTPS
    # )


    # Log all errors
    app.add_error_handler(error)

    print('Polling...')
    # Run the bot
    app.run_polling()




