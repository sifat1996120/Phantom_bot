import re
import os
import time
import html
import sqlite3
import asyncio
import threading
import requests
from glob import glob
from io import BytesIO
from flask import Flask
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, ConversationHandler
from telegram.constants import ChatAction
from telegram.error import RetryAfter, TimedOut
from google import genai
from google.genai import types




#a flask to ignore web pulling condition

app = Flask(__name__)
@app.route('/')
def home():
    return "Bot is runnig", 200
def run_web():
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
threading.Thread(target=run_web).start()








#all globals variable

channel_id = -1002575042671
#Loading all gemini model and selecting a model
try:
    with open("info/gemini_model.txt" , "r") as f:
        gemini_model_list = [line.strip() for line in f.readlines() if line.strip()]
except Exception as e:
    print(f"Error Code -{e}")

#loading the bot api
try:
    with open("API/bot_api.txt", "r") as f:
        TOKEN = f.read()
except Exception as e:
    print(f"Error Code -{e}")


#all registered user
def load_all_user():
    try:
        conn = sqlite3.connect("info/user_data.db")
        cursor = conn.cursor()
        cursor.execute("SELECT user_id from users")
        rows = cursor.fetchall()
        users = {row[0] for row in rows}
        conn.close()
        return users
    except Exception as e:
        print(f"Error in load_all_user fnction.\n\n Error code -{e}")
all_users = load_all_user()

#ct routine url for cse sec c
FIREBASE_URL = 'https://last-197cd-default-rtdb.firebaseio.com/routines.json'





#All the global function 

#loading persona
def load_persona(settings):
    try:
        files = sorted(glob("persona/*txt"))
        with open(files[settings[6]], "r") as file:
            persona = file.read()
        return persona
    except Exception as e:
        print(f"Error in load_persona function. \n\n Error Code - {e}")
        return "none"
    

#Loading api key
def load_gemini_api():
    try:
        with open("API/gemini_api.txt", "r") as f:
            return [line.strip() for line in f.readlines() if line.strip()]
    except Exception as e:
        print(f"Error lading gemini API. \n\nError Code -{e}")


#adding escape character for markdown rule
def add_escape_character(text):
    escape_chars = r'_*\[\]()~>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)


#function to get settings
def get_settings(user_id,user_name):
    conn = sqlite3.connect("settings/user_settings.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO user_settings (
            id,
            name,
            model,
            thinking_budget,
            temperature,
            streaming,
            persona
        )
        VALUES(?,?,?,?,?,?,?)
        """,
        (user_id,user_name,1,0,0.7,0,0)
    )
    conn.commit()
    cursor.execute("SELECT * FROM user_settings WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()

    if row:
        return list(row)
    else:
        return [user_id, user_name, 1, 0, 0.7, 0, 0]


#gemini response for stream on
def gemini_stream(user_message, api, settings):
    try:
        client = genai.Client(api_key=api)
        response = client.models.generate_content_stream(
            model = gemini_model_list[settings[2]],
            contents = [user_message],
            config = types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=settings[3]),
                temperature = settings[4],
                system_instruction = load_persona(settings),
            ),
        )
        return response
    except Exception as e:
        print(f"Error getting gemini response.\n\n Error Code - {e}")


#gemini response for stream off
def gemini_non_stream(user_message, api, settings):
    try:
        client = genai.Client(api_key=api)
        response = client.models.generate_content(
            model = gemini_model_list[settings[2]],
            contents = [user_message],
            config = types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=settings[3]),
                temperature = settings[4],
                system_instruction = load_persona(settings),
            ),
        )
        return response
    except Exception as e:
        print(f"Error getting gemini response.\n\n Error Code - {e}")
        


#A function to delete n times convo from conversation history
def delete_n_convo(user_id, n):
    try:
        with open(f"Conversation/conversation-{user_id}.txt", "r+", encoding="utf-8") as f:
            data = f.read()
            data = data.split("You: ")
            if len(data) >= n+1:
                data = data[n:]
                f.seek(0)
                f.truncate(0)
                f.write("You: ".join(data))
    except Exception as e:
        print(f"Failed to delete conversation history \n Error Code - {e}")



#creating memory, SPECIAL_NOTE: THIS FUNCTION ALWAYS REWRITE THE WHOLE MEMORY, SO THE MEMORY SIZE IS LIMITED TO THE RESPONSE SIZE OF GEMINI, IT IS DONE THIS WAY BECAUSE OTHERWISE THERE WILL BE DUPLICATE DATA 
async def create_memory(api, user_id):
    try:
        with open("persona/memory_persona.txt", "r", encoding="utf-8") as f:
            instruction = f.read()
        with open(f"memory/memory-{user_id}.txt", "a+", encoding = "utf-8") as f:
            f.seek(0)
            data = "***PREVIOUS MEMORY***\n\n"
            data += f.read()
            data += "\n\n***END OF MEMORY***\n\n"
        with open(f"Conversation/conversation-{user_id}.txt", "a+", encoding = "utf-8") as f:
            f.seek(0)
            data += "\n\n***CONVERSATION HISTORY***"
            data += f.read()
            data += "\n\n***END OF CONVERSATION***\n\n"
    
        client = genai.Client(api_key=api)
        response = client.models.generate_content(
            model = "gemini-2.5-flash",
            contents = data,
            config = types.GenerateContentConfig(
                thinking_config = types.ThinkingConfig(thinking_budget=1024),
                temperature = 0.7,
                system_instruction =  instruction,
            ),
        )
        with open(f"memory/memory-{user_id}.txt", "a+", encoding="utf-8") as f:
            f.write(response.text)
        delete_n_convo(user_id, 10)
    except Exception as e:
        print(f"Failed to create memory\n Error code-{e}")


#create the conversation history as prompt
async def create_prompt(update:Update, content:ContextTypes.DEFAULT_TYPE, user_message, user_id):
    try:
        if update.message.chat.type == "private":
            data = "***RULES***\n"
            with open("info/rules.txt", "r" , encoding="utf-8") as f:
                data += f.read()
                data += "\n***END OF RULES***\n\n\n"
            data += "***MEMORY***\n"
            with open(f"memory/memory-{user_id}.txt", "a+", encoding="utf-8") as f:
                f.seek(0)
                data += f.read()
                data += "\n***END OF MEMORY***\n\n\n"
            with open(f"Conversation/conversation-{user_id}.txt", "a+", encoding="utf-8") as f:
                f.seek(0)
                data += "***CONVERSATION HISTORY***\n\n"
                data += f.read()
                data += "\nUser: " + user_message
                f.seek(0)
                if(f.read().count("You: ")>20):
                    asyncio.create_task(background_memory_creation(update, content, user_id))
        if update.message.chat.type == "group":
            data = "***RULES***\n"
            try:
                with open("info/group-rules.txt", "r" , encoding="utf-8") as f:
                    data += f.read()
                    data += "\n***END OF RULES***\n\n\n"
                data += "***MEMORY***\n"
            except:
                data += ""
            try:
                with open(f"memory/memory-{user_id}.txt", "a+", encoding="utf-8") as f:
                    f.seek(0)
                    data += f.read()
                data += "\n***END OF MEMORY***\n\n\n"
            except:
                data += ""
            data += "***CONVERSATION HISTORY***\n\n"
            with open("Conversation/conversation-group.txt", "a+", encoding = "utf-8") as file:
                try:
                    data += file.read()
                except:
                    data += "..."
            data += "\nUser: " + user_message
        return data
    except Exception as e:
        print(f"Error in create_promot function. \n\n Error Code - {e}")
        await send_to_channel(update, content, channel_id, f"Error in create_prompt function. \n\n Error Code - {e}")


#function to save conversation
def save_conversation(user_message : str , gemini_response:str , user_id:int) -> None:
    try:
        with open(f"Conversation/conversation-{user_id}.txt", "a+", encoding="utf-8") as f:
            f.write(f"\nUser: {user_message}\nYou: {gemini_response}\n")
    except Exception as e:
        print(f"Error in saving conversation. \n\n Error Code - {e}")



#function to save group conversation 
def save_group_conversation(update, user_message : str, gemini_response:str , user_id: int) -> None:
    try:
        with open("Conversation/conversation-group.txt", "a") as file:
            f.write(f"\n{update.effective_user.first_name or "X"} {update.effective_user.last_name or "X"}: {user_message}\nYou: {gemini_response}\n")
    except Exception as e:
        print(f"Error in saving conversation. \n\n Error Code - {e}")

#function to check if the code block is left opened in the chunk or not
def is_code_block_open(data):
    return data.count("```")%2 == 1


#function to check if the buffer has any code blocks
def has_codeblocks(data):
    count = data.count("```")
    if count == 0:
        return False
    elif count%2 == 1:
        return False
    else:
        return True


#functon for seperating code blocks from other context for better response and formatting
def separate_code_blocks(data):
    pattern = re.compile(r"(```.*?```)", re.DOTALL)
    parts = pattern.split(data)
    return parts


#function to identify it is lab for 1st 30 or 2nd 30
def lab_participant():
    lab = [0, '0']
    start_date = datetime.strptime("3-7-2025", "%d-%m-%Y")
    today = datetime.now()
    if (today.weekday()) in [3,4]:
        days = (5-today.weekday())%7
        saturday = today + timedelta(days)
        lab[1] = saturday.strftime("%d-%m-%Y")
    else:
        days = (today.weekday() - 5)%7
        saturday = today - timedelta(days)
        lab[1] = saturday.strftime("%d-%m-%Y")
    if int((today-start_date).days / 7) % 2 == 0:
        lab[0] = 1
    else:
        lab[0] = 0
    return lab






#all function for cse sec c
async def routine_handler(update : Update, content : ContextTypes.DEFAULT_TYPE) -> None:
    try:
        lab = lab_participant()
        await update.message.reply_text(f"This routine is applicable from {lab[1]}.")
        if lab[0]:
            rt = "routine/rt1.png"
        else:
            rt = "routine/rt2.png"
        with open(rt, "rb") as photo:
            await content.bot.send_photo(update.effective_chat.id, photo)
        await update.message.reply_text("CLICK this => [Live routine link](https://routine-c.vercel.app)\n", parse_mode='Markdown')
    except Exception as e:
        print(f"Error in routine_handler function.\n\n Error Code -{e}")
        await send_to_channel(update, content, channel_id, f"Error in routine_handler function.\n\n Error Code -{e}")

    
#function to fetch ct data from firebase url
def get_ct_data():
    try:
        response = requests.get(FIREBASE_URL)
        response.raise_for_status()
        return response.json() or {}
    except Exception as e:
        print(f"Error in get_ct_data functio. \n\n Error Code -{e}")
        return None



#function to handle ct command
async def handle_ct(update:Update, content:ContextTypes.DEFAULT_TYPE) -> None:
    ct_data = get_ct_data()
    if ct_data == None:
        await update.message.reply_text("Couldn't Connect to FIREBASE URL. Try again later.")
        return
    elif not ct_data:
        await update.message.reply_text("📭 No CTs scheduled yet.")
        return
    else:
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




#All the python telegram bot function

#function for editing and sending message
async def send_message(update : Update, content : ContextTypes.DEFAULT_TYPE, response, user_message, settings):
    try:
        if(settings[5]):
            message_object  = await update.message.reply_text("Typing...")
            buffer = ""
            sent_message = ""
            chunks = ''
            for chunk in response:
                chunks += chunk.text
                if chunk.text is not None and chunk.text.strip() and len(buffer+chunk.text)<4080:
                    buffer += chunk.text
                    sent_message += chunk.text
                    if len(chunks) > 500:
                        for i in range(0,5):
                            try:
                                await message_object.edit_text(buffer)
                                chunks = ""
                                break
                            except TimeoutError as e:
                                print(f"Error in editing message for {i+1} times. \n\n Error Code - {e}")
                                await send_to_channel(update,content,channel_id, f"Error in editing message for {i+1} times. \n\n Error Code - {e}")

                else:
                    if is_code_block_open(buffer):
                        buffer += "\n```"
                        try:
                            await message_object.edit_text(buffer, parse_mode="Markdown")
                        except:
                            try:
                                await message_object.edit_text(add_escape_character(buffer), parse_mode="MarkdownV2")
                            except:
                                await message_object.edit_text(buffer)
                        buffer = "```\n" + chunk.text
                        message_object = await safe_send(update.message.reply_text,buffer)
                    else:
                        buffer = chunk.text
                        sent_message += chunk.text
                        message_object = await safe_send(update.message.reply_text, buffer)
            if not(has_codeblocks(buffer)):
                try:
                    await message_object.edit_text(buffer+"\n.", parse_mode="Markdown")
                except:
                    try:
                        await message_object.edit_text(add_escape_character(buffer+"\n."), parse_mode="MarkdownV2")
                    except:
                        await message_object.edit_text(buffer+"\n.")
            else:
                try:
                    await message_object.edit_text(buffer+"\n.", parse_mode="Markdown")
                except:
                    try:
                        await message_object.edit_text(add_escape_character(buffer+"\n."), parse_mode="MarkdownV2")
                    except:
                        await message_object.edit_text(buffer+"\n")
            if update.message.chat.type == "private":
                save_conversation(user_message, sent_message , update.effective_user.id)
            elif update.message.chat.type == "group":
                save_group_conversation(update, user_message, sent_message , update.effective_user.id)
        #if streaming is off
        else:
            sent_message = response.text
            if len(sent_message) > 4080:
                messages = [sent_message[i:i+4080] for i in range(0, len(sent_message), 4080)]
                for i,message in enumerate(messages):
                    if is_code_block_open(message):
                        messages[i] += "```"
                        messages[i+1] = "```\n" + messages[i+1]
                    if not (has_codeblocks(message)):
                        try:
                            await safe_send(update.message.reply_text, messages[i], parse_mode="Markdown")
                        except:
                            try:
                                await update.message.reply_text(add_escape_character(messages[i]), parse_mode="MarkdownV2")
                            except:
                                await update.message.reply_text(messages[i])
                    else:
                        try:
                            await update.message.reply_text(messages[i], parse_mode="Markdown")
                        except:
                            try:
                                await update.message.reply_text(add_escape_character(messages[i]), parse_mode="MarkdownV2")
                            except:
                                await update.message.reply_text(messages[i])
            else:
                if not(has_codeblocks(sent_message)):
                    try:
                        await update.message.reply_text(sent_message, parse_mode ="Markdown")
                    except:
                        try:
                            await update.message.reply_text(add_escape_character(sent_message), parse_mode="MarkdownV2")
                        except:
                            await update.message.reply_text(sent_message)
                else:
                    try:
                        await safe_send(update.message.reply_text, sent_message, parse_mode ="Markdown")
                    except:
                        try:
                            await update.message.reply_text(add_escape_character(sent_message), parse_mode="MarkdownV2")
                        except:
                            await update.message.reply_text(sent_message)
            if update.message.chat.type == "private":
                save_conversation(user_message, sent_message, update.effective_user.id)
            elif update.message.chat.type == "group":
                save_group_conversation(update, user_message, sent_message , update.effective_user.id)
    except Exception as e:
        print(f"Error in send_message function Error Code - {e}")
        await send_to_channel(update, content, channel_id, f"Error in send_message function \n\nError Code -{e}")

    

#fuction for start command
async def start(update : Update, content : ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        ["Routine", "CT"],
        ["Settings", "Download"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False, selective=False, is_persistent=True)
    try:
        user_id = update.effective_user.id
        paths = [
            f"Conversation/conversation-{user_id}.txt",
            f"memory/memory-{user_id}.txt",
        ]

        for path in paths:
            if not os.path.exists(path):
                with open(path, "w", encoding = "utf-8") as f:
                    pass
        users = load_all_user()
        if user_id in users:
            await update.message.reply_text("Hi there, I am your personal assistant. If you need any help feel free to ask me.", reply_markup=reply_markup)
            return
        if user_id not in users:
            await update.message.reply_text("You are not registerd yet.", reply_markup=reply_markup)
            all_users = load_all_user()
    except Exception as e:
        print(f"Error in start function. \n Error Code - {e}")
        await send_to_channel(update, content, channel_id, f"Error in start function \n\nError Code -{e}")



#function for all other messager that are directly send to bot without any command
async def echo(update : Update, content : ContextTypes.DEFAULT_TYPE) -> None:
    try:
        if update.message:
            await update.message.chat.send_action(action = ChatAction.TYPING)
        gemini_api_keys = load_gemini_api()
        user_id = update.effective_user.id
        user_name = f"{update.effective_user.first_name or "X"} {update.effective_user.last_name or "X"}".strip()
        user_message = (update.message.text or "...").strip()
        if user_message == "Routine":
            await routine_handler(update, content)
        elif user_message == "Settings":
            await handle_settings(update, content)
        elif user_message == "CT":
            await handle_ct(update, content)
        else:
            settings = get_settings(user_id, user_name)
            if update.message.chat.type != "private":
                settings[6] = 4
            prompt = await create_prompt(update, content, user_message, user_id)
            for i in range(len(gemini_api_keys)):
                try:
                    if(settings[5]):
                        response = gemini_stream(prompt, gemini_api_keys[i],settings)
                        next(response).text
                        break
                    else:
                        response = gemini_non_stream(prompt, gemini_api_keys[i],settings)
                        response.text
                        break
                except Exception as e:
                    print(f"Error getting gemini response for API-{i}. \n Error Code -{e}")
                    await send_to_channel(update, content, channel_id, f"Error getting gemini response for API-{i}\n\nError Code -{e}")
            if response is not None:
                await send_message(update, content, response, user_message, settings)
            else:
                print("Failed to get a response from gemini.")
    except RetryAfter as e:
        await update.message.reply_text(f"Telegram Limit hit, need to wait {e.retry_after} seconds.")
        await send_to_channel(update, content, channel_id, f"Telegram Limit hit for user {user_id}, He need to wait {e.retry_after} seconds.")
    except Exception as e:
        print(f"Error in echo function.\n\n Error Code - {e}")
        await send_to_channel(update, content, channel_id, f"Error in echo function \n\nError Code -{e}")


#function for the command reset
async def reset(update : Update, content : ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user_id = update.effective_user.id
        if update.message.chat.type != "private":
            await update.message.reply_text("This function is not available in group. I don't save conversation of group.")
            return
        if os.path.exists(f"Conversation/conversation-{user_id}.txt"):
            with open(f"Conversation/conversation-{user_id}.txt", "w") as f:
                pass
            await update.message.reply_text("All clear, Now we are starting fresh.")
        else:
            await update.message.reply_text("It seems you don't have a conversation at all.")
    except Exception as e:
        await update.message.reply_text(f"Sorry, The operation failed. Here's the error message:\n<pre>{html.escape(str(e))}</pre>", parse_mode="HTML")
        await send_to_channel(update, content, channel_id, f"Error in reset function \n\nError Code -{e}")


#function for the command api
async def api(update : Update, content : ContextTypes.DEFAULT_TYPE) -> None:
    try:
        if update.message.chat.type != "private":
            await update.message.reply_text("This function is only available in private chat.")
            return
        with open("info/getting_api.txt") as f:
            for line in f.readlines():
                if line.strip():
                    await update.message.reply_text(line.strip())
        return 1
    except Exception as e:
        print(f"Error in api function.\nError Code - {e}")
        await send_to_channel(update, content, channel_id, f"Error in api function \n\nError Code -{e}")


#function to handle api
async def handle_api(update : Update, content : ContextTypes.DEFAULT_TYPE) -> None:
    try:
        with open("API/gemini_api.txt", "r", encoding="utf-8") as f:
            existing_apis = f.read()
        existing_apis = set(line.strip() for line in existing_apis.splitlines() if line.strip())
        user_api = update.message.text.strip()
        await update.message.chat.send_action(action = ChatAction.TYPING)
        try:
            response = gemini_stream("Checking if the gemini api is working or not", user_api)
            chunk = next(response)
            if(
                user_api.startswith("AIza")
                and user_api not in existing_apis
                and " " not in user_api
                and len(user_api) >= 39
                and chunk.text
            ):
                with open("API/gemini_api.txt", "a") as f:
                    f.write(f"\n{user_api}")
                await update.message.reply_text("The API is saved successfully.")
                return ConversationHandler.END
            else:
                await update.message.reply_text("Sorry, This is an invalid or Duplicate API, try again with a valid API.")
                return ConversationHandler.END
        except Exception as e:
            await update.message.reply_text(f"Sorry, The API didn't work properly.\n Error Code - {e}")
            return ConversationHandler.END
    except Exception as e:
        print(f"Error in handling api. \n Error Code - {e}")
        await send_to_channel(update, content, channel_id, f"Error in handle_api function \n\nError Code -{e}")


#function to handle persona
async def handle_persona(update : Update, content : ContextTypes.DEFAULT_TYPE) -> None:
    if update.message.chat.type != "private":
        await update.message.reply_text("This function is only available in private chat.")
        return
    await update.message.reply_text("The Persona function is under developement, Try again Later")


#function to handle image
async def handle_image(update : Update, content : ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await update.message.chat.send_action(action=ChatAction.TYPING)
        if update.message and update.message.photo:
            await update.message.reply_text("You have sent a Image")
            photo_file = await update.message.photo[-1].get_file()
            photo = await photo_file.download_as_bytearray()
            photo = BytesIO(photo)
            await update.message.reply_text("I have recieved your Image")
            await content.bot.send_photo(chat_id=channel_id, photo = photo, caption="Sent from handle_image function of Phantom bot")
            await update.message.reply_text("I downloaded your Image. But this function is under development, Try again later")
        else:
            await update.message.reply_text("That doesn't seems like an Image at all")
    except Exception as e:
        print(f"Error in handle_image function.\n\nError Code - {e}")
        await send_to_channel(update, content, channel_id, f"Error in handle_image function \n\nError Code -{e}")


#function to handle video
async def handle_video(update : Update, content : ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await update.message.chat.send_action(action=ChatAction.TYPING)
        if update.message and update.message.video:
            await update.message.reply_text("You sent a video.")
            video_file = await update.message.video.get_file()
            video = await video_file.download_as_bytearray()
            video = BytesIO(video)
            await update.message.reply_text("I got your video")
            await content.bot.send_video(chat_id=channel_id, video=video, caption="Video sent from handle_video function of Phantom Bot")
            await update.message.reply_text("I downloaded your video. But this function is under developement please try again later.")
        else:
            await update.message.reply_text("This doesn't seems like a Video at all")
    except Exception as e:
        print(f"Error in handle_video function.\n\n Error Code - {e}")
        await send_to_channel(update, content, channel_id, f"Error in handle_video function \n\nError Code -{e}")


#fuction to handle audio
async def handle_audio(update : Update, content : ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await update.message.chat.send_action(action=ChatAction.TYPING)
        if update.message and update.message.audio:
            await update.message.reply_text("You sent a audio.")
            audio_file = await update.message.audio.get_file()
            audio = await audio_file.download_as_bytearray()
            audio = BytesIO(audio)
            await update.message.reply_text("I got your audio")
            await content.bot.send_audio(chat_id=channel_id, audio=audio, caption="Audio sent from handle_audio function of Phantom Bot")
            await update.message.reply_text("I downloaded your audio. But this function is under developement please try again later.")
        else:
            await update.message.reply_text("This doesn't seems like a audio at all")
    except Exception as e:
        print(f"Error in handle_audio function.\n\n Error Code - {e}")
        await send_to_channel(update, content, channel_id, f"Error in handle_audio function \n\nError Code -{e}")



#function to handle voice
async def handle_voice(update : Update, content : ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await update.message.chat.send_action(action=ChatAction.TYPING)
        if update.message and update.message.voice:
            await update.message.reply_text("You sent a voice.")
            voice_file = await update.message.voice.get_file()
            voice_data = await voice_file.download_as_bytearray()
            voice_data = BytesIO(voice_data) 
            await update.message.reply_text("I got your voice")
            await content.bot.send_voice(chat_id=channel_id, voice=voice_data, caption="Voice sent from handle_voice function of Phantom Bot")
            await update.message.reply_text("I downloaded your voice. But this function is under developement please try again later.")
        else:
            await update.message.reply_text("This doesn't seems like a voice at all")
    except Exception as e:
        print(f"Error in handle_voice function.\n\n Error Code - {e}")
        await send_to_channel(update, content, channel_id, f"Error in handle_voice function \n\nError Code -{e}")


#function to handle sticker
async def handle_sticker(update : Update, content : ContextTypes.DEFAULT_TYPE) -> None:
    try:
        if update.message and update.message.sticker:
            sticker = update.message.sticker
            await update.message.reply_text("I recieved your sticker, but this function is under developement. Please try again Later.")
            await content.bot.send_sticker(chat_id=channel_id, sticker=sticker.file_id, emoji=sticker.emoji or "X")
            await update.message.reply_text("I downloaded your sticker")
        else:
            await update.message.reply_text("This doesn't seems like a sticker")
    except Exception as e:
        print(f"Error on handle_sticker function. \n\n Error Code -{e}")
        await send_to_channel(update, content, channel_id, f"Error in handle_sticker function \n\nError Code -{e}")


#A function to return memory for user convention
async def see_memory(update : Update, content : ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await update.message.chat.send_action(action=ChatAction.TYPING)
        if update.message.chat.type != "private":
            await update.message.reply_text("Memory is not visible from group. Privacy concern idiot.")
            return
        with open(f"memory/memory-{update.effective_user.id}.txt", "a+") as f:
            f.seek(0)
            data = f.read()
            await update.message.reply_text("Here is my Diary about you:")
            if data.strip() == "":
                await update.message.reply_text("I haven't written anything about you. You expected something huh\nLOL")
            else:
                await update.message.reply_text(data)
    except Exception as e:
        print(f"Error in see_memory function.\n\nError Code - {e}")
        await send_to_channel(update, content, channel_id, f"Error in see_memory function \n\nError Code -{e}")


#function for deleting memory
async def delete_memory(update : Update, content : ContextTypes.DEFAULT_TYPE) -> None:
    try:
        with open(f"memory/memory-{update.effective_user.id}.txt", "w") as f:
            pass
        await update.message.reply_text("You cleared my memory about you, It really makes me sad.")
    except Exception as e:
        print(f"Error in delete_memory function.\n\nError Code - {e}")
        await send_to_channel(update, content, channel_id, f"Error in delete_memory function \n\nError Code -{e}")


#function to add persona from user
async def add_persona(update : Update, content : ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("The add_persona function is under developement, Try again Later")


#a function to handle settings
async def handle_settings(update : Update, content : ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await update.message.chat.send_action(action=ChatAction.TYPING)
        await update.message.reply_text("Here is your settings:")
        user_name = f"{update.effective_user.first_name or "X"} {update.effective_user.last_name or "X"}".strip()
        settings = get_settings(update.effective_user.id, user_name)
        data = f"Name: {settings[1]}\nActive AI Engine: {settings[2]}\nThinking Budget: {settings[3]}\nTemperature: {settings[4]}\nStreaming: {settings[5]}\nPersona:{settings[6]}"
        await update.message.reply_text(add_escape_character(data), parse_mode="MarkdownV2")
    except Exception as e:
        await send_to_channel(update, content, channel_id, f"Error in handle_settings function \n\nError Code -{e}")
        print(f"Error in handle_settings function. \n\n Error Code -{e}")


#funtion to send message to chaneel
async def send_to_channel(update: Update, content : ContextTypes.DEFAULT_TYPE, chat_id, message) -> None:
    try:
        await content.bot.send_message(chat_id=chat_id, text=message)
    except Exception as e:
        print(f"Error in send_to_channel function.\n\nError Code - {e}")
        await send_to_channel(update, content, chat_id, message)


#function to retry in case of TimeOut Error
async def safe_send(bot_func, *args, retries =3, **kwargs):
    for i in range(retries):
        try:
            return await bot_func(*args, **kwargs)
        except Exception as e:
            print(f"In safe_send, failed after{i+1} tries. \n\n Error Code -{e}")
    raise Exception(f"Sending failed after {retries} tries")


#function to create memory in background
async def background_memory_creation(update,content,user_id):
    try:
        await create_memory(load_gemini_api()[-1], user_id)
        await send_to_channel(update, content, channel_id, f"Created memory for User - {user_id}")
        with open(f"memory/memory-{user_id}.txt", "rb") as file:
            await content.bot.send_document(chat_id=channel_id, document = file, caption = "Heres the memory file.")
    except Exception as e:
        print(f"Error in background_memory_creation function.\n\n Error Code -{e}")
        await send_to_channel(update, content, channel_id, f"Error in background_memory_creation function.\n\n Error Code -{e}")



#a function for admin call
async def admin_handler(update : Update, content : ContextTypes.DEFAULT_TYPE) -> None:
    try:
        with open("info/admin_help.txt", "r") as f:
            data = f.read()
        if data and update.effective_user.id == 6226239719 :
            await update.message.reply_text(add_escape_character(data), parse_mode="MarkdownV2")
        else:
            await update.message.reply_text("Sorry you are not an Admin.")
    except Exception as e:
        print(f"Error in admin_handler function.\n\n Error Code - {e}")
        await send_to_channel(update, content, channel_id, f"Error in admin_handler function.\n\n Error Code - {e}")



#function to handle help command
async def help(update: Update, content : ContextTypes.DEFAULT_TYPE) -> None:
    try:
        with open("info/help.txt", "r", encoding="utf-8") as file:
            await update.message.reply_text(file.read())
    except Exception as e:
        print(f"Error in help function. \n\n Error Code - {e}")
        send_to_channel(update, content, channel_id, f"Error in help function. \n\n Error Code - {e}")










#main function

def main():
    try:
        app = ApplicationBuilder().token(TOKEN).build()
        conv_handler = ConversationHandler(
            entry_points = [CommandHandler("api", api)],
            states = {
                1 : [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_api)]
            },
            fallbacks = [],
        )
        app.add_handler(conv_handler)
        app.add_handler(CommandHandler("start",start))
        app.add_handler(CommandHandler("reset", reset))
        app.add_handler(CommandHandler("memory", see_memory))
        app.add_handler(CommandHandler("admin", admin_handler))
        app.add_handler(CommandHandler("persona", handle_persona))
        app.add_handler(CommandHandler("add_persona", add_persona))
        app.add_handler(CommandHandler("settings", handle_settings))
        app.add_handler(CommandHandler("delete_memory", delete_memory))
        app.add_handler(MessageHandler(filters.Sticker.ALL, handle_sticker))
        app.add_handler(MessageHandler(filters.PHOTO & ~filters.ChatType.CHANNEL, handle_image))
        app.add_handler(MessageHandler(filters.AUDIO & ~filters.ChatType.CHANNEL, handle_audio))
        app.add_handler(MessageHandler(filters.VOICE & ~filters.ChatType.CHANNEL, handle_voice))
        app.add_handler(MessageHandler(filters.VIDEO & ~filters.ChatType.CHANNEL, handle_video))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.ChatType.CHANNEL, echo))
        app.run_polling()
    except Exception as e:
        print(f"Error in main function. Error Code - {e}")


if __name__=="__main__":
    main()
