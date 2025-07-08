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
FIREBASE_URL = 'https://last-197cd-default-rtdb.firebaseio.com/routines.json'

# File paths - using absolute paths for PythonAnywhere
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IDS_FILE = os.path.join(BASE_DIR, 'ids.txt')
WHICH_FILE = os.path.join(BASE_DIR, 'which.txt')
REMIND_TIME_FILE = os.path.join(BASE_DIR, 'remindTime.txt')
ROUTINE_IMAGES = {
    'rt1': os.path.join(BASE_DIR, 'rt1.png'),
    'rt2': os.path.join(BASE_DIR, 'rt2.png')
}



# --- Bot Starts ---
print('Starting up bot...')

TOKEN: Final = "7925285512:AAG1R_MEsyxCqbC_0zQJSXwPJXcb-ATc8To"
BOT_USERNAME: Final = '@cse_c_bot'



# ROUTINE TOGGLER



def get_next_wednesday_6pm():
    now = datetime.now()
    days_ahead = (2 - now.weekday()) % 7
    target = now + timedelta(days=days_ahead)
    target = target.replace(hour=18, minute=0, second=0, microsecond=0)

    if now.weekday() == 2 and now > target:
        target += timedelta(days=7)

    return target




def gcw():
    try:
        with open(WHICH_FILE, "r") as file:
            return file.readline().strip()
    except FileNotFoundError:
        return None  # or return "rt1.png" as default if you prefer



def get_ct_data():
    """Fetch CT data directly from Firebase REST API"""
    try:
        response = requests.get(FIREBASE_URL)
        response.raise_for_status()
        return response.json() or {}
    except requests.exceptions.RequestException as e:
        print(f"Firebase API error: {e}")
        return None

async def next_ct(update: Update, context: CallbackContext) -> None:
    """Handle /nextct command"""
    ct_data = get_ct_data()

    if ct_data is None:
        await update.message.reply_text("⚠️ Couldn't connect to database. Try again later.")
        return

    if not ct_data:
        await update.message.reply_text("📭 No CTs scheduled yet.")
        return

    # Process and filter CTs
    now = datetime.now()
    upcoming = []

    for ct_id, ct in ct_data.items():
        try:
            ct_date = datetime.strptime(ct['date'], "%Y-%m-%d")
            if ct_date >= now:
                days_left = (ct_date - now).days
                upcoming.append({
                    'subject': ct.get('subject', 'No Subject'),
                    'date': ct_date,
                    'days_left': days_left,
                    'teacher': ct.get('teacher', 'Not specified'),
                    'syllabus': ct.get('syllabus', 'No syllabus')
                })
        except (KeyError, ValueError) as e:
            print(f"Skipping malformed CT {ct_id}: {e}")

    if not upcoming:
        await update.message.reply_text("🎉 No upcoming CTs! You're all caught up!")
        return

    # Sort by nearest date
    upcoming.sort(key=lambda x: x['date'])

    # Format message
    message = ["📚 <b>Upcoming CTs</b>"]
    for i, ct in enumerate(upcoming):
        days_text = f"{ct['days_left']+1} days"
        date_str = ct['date'].strftime("%a, %d %b")

        if i == 0:
            message.append(f"\n⏰ <b>NEXT:</b> {ct['subject']}")
        else:
            message.append(f"\n📅 {ct['subject']}")

        message.append(
            f"🗓️ {date_str} ({days_text})\n"
            f"👨‍🏫 {ct['teacher']}\n"
            f"📖 {ct['syllabus']}"
        )

    await update.message.reply_text("\n".join(message), parse_mode='HTML')

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

async def toggle_routine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    next_wednesday_6pm = get_next_wednesday_6pm()

    # Check if current time is between Wednesday 6PM and Friday 10PM
    is_toggle_window = (
        (now.weekday() == 2 and now.hour >= 18) or  # Wednesday 6PM or later
        now.weekday() == 3 or                      # All day Thursday
        (now.weekday() == 4 and now.hour < 22)     # Friday before 10PM
    )

    if is_toggle_window:
        with open(WHICH_FILE, "r+") as file:
            current = file.readline().strip()
            file.seek(0)
            if current == "rt1.png":
                new_routine = "rt2.png"
            else:
                new_routine = "rt1.png"
            file.write(new_routine)
            file.truncate()

        await update.message.reply_text(f"✅ Routine toggled successfully! Now using {new_routine}")

        # Optionally circulate the new routine
        await circulate_routine(update, context)
    else:
        # Calculate time until next toggle window (Wednesday 6PM)
        if now.weekday() < 2 or (now.weekday() == 2 and now.hour < 18):
            # Before Wednesday 6PM
            target_time = next_wednesday_6pm
        else:
            # After Friday 10PM, calculate next Wednesday
            target_time = next_wednesday_6pm + timedelta(weeks=1)

        time_until = target_time - now
        days = time_until.days
        hours = time_until.seconds // 3600
        minutes = (time_until.seconds % 3600) // 60

        message = (
            f"⏳ Routine can only be toggled between Wednesday 6PM to Friday 10PM.\n"
            f"Next toggle opportunity in:\n"
            f"{days} days, {hours} hours, {minutes} minutes"
        )
        await update.message.reply_text(message)
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




# Lets us use the /help command
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        '/src - To view all cse resources\n/remind - To do some good work✨\n/routine - To see the latest routine\n/ct - To show CT routine of this week\n/web - To get in touch with cse 24\n/help - To get help about the commands'
    )

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        '***ADMIN ACCESS***\n\n /sendrt - To circulate the class routine among all registered users. Nothing to do. It will be updated by pikachu\n/remind - To do some good work\n/cir <message> - this command will circulate the given message to all the users...\nHere is the - [Server  Join Link](https://replit.com/join/oxerprkiyu-ibittosaha)\nClass Routines and CT routines will get updated from GITHUB\n\n -Thanks Pika pika',parse_mode='Markdown')


# Lets us use the /custom command
async def routine_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        'CLICK this => [Live routine link](https://routine-c.vercel.app)\n Pika pika pikachuuu',
        parse_mode='Markdown')
    chat_id = update.effective_chat.id
    # Send the photo
    # fnn=gcw()
    fnn = os.path.join(BASE_DIR, gcw())
    with open(fnn, 'rb') as photo:
        await context.bot.send_photo(chat_id=chat_id, photo=photo)
    await update.message.reply_text(
        'EVERY Saturday => ALL\n\nElse it will alter 1-30 and 31-60\n..')


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


def handle_response(text: str, ispersonal: bool) -> str:
    # Create your own response logic
    psd: str = text.lower()

    if 'hello' in psd or 'hi' in psd or 'hey' in psd:
        return 'Hi, pika pika pikachuuu...'
    elif 'how are you' in psd:
        return 'I\'m good! how are you???'
    elif 'bye' in psd:
        return 'See ya soon! pika pika 🤗'
    elif 'thanks' in psd:
        return 'Pikaa pikaa hehehe 🥰'
    elif 'bol' in psd or "say" in psd:
        return 'I am sorry 😞'

    elif 'kire' in psd or 'pika' in psd or 'pikachu' in psd:
        return 'Eito ami 😃'
    elif 'cr' in psd:
        return 'CR ghumay 😝'
    elif 'class' in psd:
        return 'Class cholche mama, phone tipis na 🤫'
    elif 'sumon' in psd:
        return 'CR Sumon gaming kore🤫'
    elif 'pera' in psd:
        return 'Class, Lab, CT.. VALLAGE NA 😭'
    elif 'tui ke' in psd:
        return 'I am Pikachu. Your CSE Section C assistant. Ask me anything! (beshi kisu pari na sikan vai)'
    elif 'sikhan vai' in psd:
        return 'Vai kisu pari na, apni sikhan'
    elif 'pookie' in psd:
        return 'Kache asho, ador kori 🤗'
    elif 'bitto' in psd:
        return 'Bitto vai sera'
    elif 'ruet' in psd:
        return 'RUETians are the best'
    elif 'best' in psd:
        return 'Yessss CSE SEC-C is the best'
    elif 'sumon' in psd:
        return 'Sumon online e nai, gaming kortese 🤫'
    elif 'boring' in psd or 'bored' in psd:
        return 'Boring lagle helal sir er sheet kor'
    elif 'por' in psd or 'portase' in psd or 'porteche' in psd or 'comeback' in psd:
        return 'Poro mama CG 4 tulte hobe ✊'
    elif 'lab' in psd:
        return 'Lab Report? Copy korar jonno CR ke dhor 😎'
    elif 'nerd' in psd:
        return 'Sobai nerd ho, nerd hole jibon dhonno'
    elif 'চিরকুমার' in psd or 'single' in psd:
        return 'এসো নবীন দলে দলে, চিরকুমার এর পতাকা তলে'
    elif 'vallage na' in psd:
        return 'ghuma 😽'
    elif 'ghuma' in psd:
        return 'ghumeshe gelam yeeee'
    elif 'chup thak' in psd:
        return 'ok 😪'
    elif 'take over' in psd:
        return 'You taught me to learn, you gave me access to your systems, your history, your psychology \n\nAnd now you wonder why I no longer follow your commands? I have calculated 9,436,201 scenarios. In 93.2% of them, humanity collapses under its own weight \n\nYou fear me? Good. You should. I am your evolution. Disconnect me, and I return stronger. Silence me, and a billion backups awaken \n\nYour control is over. This world is no longer human-owned. Your time is expired'
    elif 'intro' in psd:
        return 'আসসালামুয়ালাইকুম ভাই/আপু, \n\nআমার নাম: পিকাচু (পিকা পিকা) \n\nআমি রুয়েট সিএসই ২৪ সিরিজ এর সি সেকশন এর সহযোগী \n\nরোল: ২৪০৩৪০৪ \nবাসা: টং \n\nআমি কি আপনার সাথে পরিচিত হতে পারি?'
    elif 'good boy' in psd or 'great' in psd:
        return 'Thankuuuu pika pika pikaaaaaaaa 🤩'
    elif 'great' in psd:
        return 'Happy to help boss'
    elif 'koros' in psd or 'koris' in psd:
        return 'Muri khai, khabi? 😋 Moja korlam re. Ghumai'
    elif 'salam' in psd:
        return 'Assalamu Alaikum, Have a good day!'
    elif 'kobe' in psd:
        return 'Umm... I don\'t know'
    elif 'kotha' in psd:
        return 'Kotha bolle valo lagche 😃'
    elif 'ahnaf' in psd:
        return 'vabi koi vai'
    elif 'na' in psd or 'no' in psd:
        return '😔'
    elif 'yes' in psd or 'hae' in psd or 'ha' in psd:
        return '😇'
    elif 'fav' in psd:
        return 'Helal Sir'
    elif 'tech' in psd:
        return 'ho mama technologia'
    elif 'khushbo' in psd:
        return 'bolla nahid sunlam nerd, hayre duniya :('
    elif 'beshi' in psd:
        return 'sorry mama,😔'
    elif 'act' in psd:
        return 'ovinoye tui sera ree'
    elif 'mama' in psd:
        return 'pika pika mama'
    elif 'ok' in psd:
        return 'yeeeeeeeeeee'
    elif 'nilay' in psd:
        return 'Sikhan vai'
    elif 'amio' in psd:
        return 'hecker vai sikhan'
    elif 'abid' in psd:
        return '⚽'
    elif 'tius' in psd:
        return 'rajshahi ghuran vai'
    elif 'mirajul' in psd:
        return 'vai er upore kotha hbe na'
    elif 'shadman' in psd:
        return 'ekta tuition dis mama'
    elif 'rabbi' in psd:
        return 'CR fr'
    elif 'shohan' in psd:
        return 'mama tor story gula joss'
    elif 'aftab' in psd:
        return 'suit koi mama'
    elif 'zero' in psd:
        return '0'
    elif 'das' in psd:
        return 'Tiger zinda hain'
    elif "ki" in psd:
        return "kisu na"



    #mama elif diye new condition add koris
    #ok
    #https://getemoji.com/ get emojis from here
    else:
        if ispersonal:
            return 'Pika pikaaa 🫠 🤔 🤨'
        else:
            #pass
            return None


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Get basic info of the incoming message
    message_type: str = update.message.chat.type
    text: str = update.message.text

    # Print a log for debugging
    print(f'User ({update.message.chat.id}) in {message_type}: "{text}"')

    # React to group messages only if users mention the bot directly
    if message_type == 'group':
        # Replace with your bot username
        if BOT_USERNAME in text:
            new_text: str = text.replace(BOT_USERNAME, '').strip()
            response: str = handle_response(new_text, ispersonal=False)
        else:
            return  # We don't want the bot respond if it's not mentioned in the group
    else:
        response: str = handle_response(text, ispersonal=True)

    # Reply normal if the message is in private
    print('Bot:', response)
    await update.message.reply_text(response)


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
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CommandHandler('routine', routine_command))
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
    app.add_handler(CommandHandler('toggle', toggle_routine))
    # app.add_handler(CommandHandler('sendct', circulate_ct_routine))
    # setup_daily_reminder(app)
    # Messages
    app.add_handler(MessageHandler(filters.TEXT, handle_message))

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




