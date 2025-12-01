# import os
# import logging
# import psycopg2
# import threading
# import json
# from concurrent.futures import ThreadPoolExecutor
# from psycopg2 import pool
# from psycopg2.extras import RealDictCursor
# from datetime import datetime, timedelta, date
# from flask import Flask, request, jsonify
# import requests
# import openai
# from twilio.rest import Client as TwilioClient 
# from twilio.twiml.messaging_response import MessagingResponse 
# from dotenv import load_dotenv

# # 1. Load Environment Variables
# load_dotenv()

# app = Flask(__name__)

# # --- CONFIGURATION ---
# DB_URI = os.getenv("DATABASE_URL")
# OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
# openai.api_key = OPENAI_API_KEY

# TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
# TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
# TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER") 

# # Initialize Twilio Client
# twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# # Logging
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

# # --- GLOBAL THREAD POOL & TIMERS ---
# executor = ThreadPoolExecutor(max_workers=5) 
# user_timers = {}

# # --- DATABASE POOL ---
# try:
#     postgreSQL_pool = psycopg2.pool.SimpleConnectionPool(
#         1, 50, DB_URI, cursor_factory=RealDictCursor, connect_timeout=10
#     )
#     print("✅ Database Connection Pool Created")
# except (Exception, psycopg2.DatabaseError) as error:
#     print("❌ Error connecting to PostgreSQL", error)

# # ==============================================================================
# # 🧠 AI & UTILS
# # ==============================================================================

# def analyze_user_intent(user_text):
#     today_str = date.today().strftime("%Y-%m-%d")
#     weekday_str = date.today().strftime("%A")
    
#     system_prompt = (
#         f"Current Date: {today_str} ({weekday_str}). "
#         "Analyze the user's intent perfectly. "
#         "1. 'is_greeting': boolean (true only if user JUST says 'hi', 'hello' with NO request). "
#         "2. 'date_range': {'start': 'YYYY-MM-DD', 'end': 'YYYY-MM-DD'} or null. "
#         "3. 'target_mood': string (e.g. romantic, chill, party). "
#         "4. 'category': string (e.g. bar, club, museum). "
#         "5. 'specific_keywords': List of strings. Specific things like 'salsa', 'techno', 'jazz', 'burger'. "
#         "Return STRICT JSON."
#     )
#     try:
#         response = openai.chat.completions.create(
#             model="gpt-4o-mini",
#             response_format={"type": "json_object"},
#             messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_text}],
#             temperature=0
#         )
#         content = response.choices[0].message.content.strip()
#         data = json.loads(content)
#         return data
#     except: return {}

# def generate_just_for_you(user_age, item_name, item_desc, item_mood):
#     try:
#         prompt = (
#             f"Write a 1-sentence recommendation for a {user_age} year old. "
#             f"Venue: {item_name}. Vibe: {item_mood}. "
#             "Start with '✨ Just for you:'."
#         )
#         response = openai.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[{"role": "user", "content": prompt}],
#             temperature=0.7,
#             timeout=3
#         )
#         return response.choices[0].message.content.replace('"', '')
#     except:
#         return f"✨ Just for you: This matches the {item_mood} vibe!"

# def generate_closing_message(user_query):
#     try:
#         prompt = (
#             f"User query: '{user_query}'. I sent recommendations. "
#             "Write a short closing message asking if they are satisfied. Use an emoji."
#         )
#         response = openai.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[{"role": "system", "content": "You are Yara."}, 
#                       {"role": "user", "content": prompt}],
#             temperature=0.7,
#             timeout=3
#         )
#         return response.choices[0].message.content.replace('"', '')
#     except:
#         return "Are you satisfied with these options? 🎉"

# # --- DATABASE FUNCTIONS ---

# def get_user(conn, phone):
#     with conn.cursor() as cur:
#         cur.execute("SELECT * FROM public.users WHERE phone = %s", (phone,))
#         return cur.fetchone()

# def create_user(conn, phone):
#     with conn.cursor() as cur:
#         # Defaults to 'welcome' as per your schema
#         cur.execute("INSERT INTO public.users (phone, conversation_step) VALUES (%s, 'welcome') ON CONFLICT (phone) DO NOTHING", (phone,))
#         conn.commit()
#         cur.execute("SELECT * FROM public.users WHERE phone = %s", (phone,))
#         return cur.fetchone()

# def update_user(conn, phone, data):
#     set_clause = ", ".join([f"{key} = %s" for key in data.keys()])
#     values = list(data.values())
#     values.append(phone)
#     with conn.cursor() as cur:
#         cur.execute(f"UPDATE public.users SET {set_clause} WHERE phone = %s", values)
#         conn.commit()

# def build_search_query(table, ai_data, strictness_level):
#     query = f"SELECT * FROM public.{table} WHERE 1=1"
#     args = []
    
#     date_range = ai_data.get('date_range')
#     mood = ai_data.get('target_mood')
#     category = ai_data.get('category')
#     keywords = ai_data.get('specific_keywords', [])

#     # --- DATE LOGIC ---
#     if table == 'events' and date_range:
#         start = date_range['start']
#         end = date_range['end']
#         start_obj = datetime.strptime(start, "%Y-%m-%d").date()
#         end_obj = datetime.strptime(end, "%Y-%m-%d").date()
#         days_in_range = []
#         curr = start_obj
#         while curr <= end_obj:
#             days_in_range.append(curr.strftime('%A'))
#             curr += timedelta(days=1)
#         days_tuple = tuple(days_in_range) if len(days_in_range) > 1 else (days_in_range[0],)
        
#         query += " AND ((event_date >= %s::date AND event_date <= %s::date) OR (recurring_day IN %s))"
#         args.extend([start, end, days_tuple])

#     # --- FILTER LOGIC ---
#     conditions = []

#     # LEVEL 1: Keywords + Mood
#     if strictness_level == 1:
#         if keywords:
#             for kw in keywords:
#                 kw_wild = f"%{kw}%"
#                 if table == 'events':
#                     conditions.append(f"(title ILIKE %s OR description ILIKE %s OR music_type ILIKE %s)")
#                     args.extend([kw_wild, kw_wild, kw_wild])
#                 else:
#                     conditions.append(f"(name ILIKE %s OR description ILIKE %s)")
#                     args.extend([kw_wild, kw_wild])
#         if mood:
#             args.append(f"%{mood}%")
#             if table == 'events': conditions.append("mood ILIKE %s")
#             else: conditions.append("description ILIKE %s")

#     # LEVEL 2: Category OR Mood
#     elif strictness_level == 2:
#         if category:
#             args.extend([f"%{category}%", f"%{category}%"])
#             if table == 'events': conditions.append("(title ILIKE %s OR description ILIKE %s)")
#             else: conditions.append("(name ILIKE %s OR description ILIKE %s)")
#         if mood and not category:
#             args.append(f"%{mood}%")
#             if table == 'events': conditions.append("mood ILIKE %s")
#             else: conditions.append("description ILIKE %s")

#     # LEVEL 3: NO FILTERS (Just Date/All)
#     elif strictness_level == 3:
#         pass 

#     if conditions:
#         query += " AND (" + " OR ".join(conditions) + ")"

#     if table == 'events': query += " ORDER BY event_date ASC LIMIT 5"
#     else: query += " LIMIT 5"

#     return query, args

# def smart_search(conn, table, ai_data):
#     # Attempt 1: Strict
#     query, args = build_search_query(table, ai_data, 1)
#     with conn.cursor() as cur:
#         cur.execute(query, tuple(args))
#         results = cur.fetchall()
#         if results: return results

#     # Attempt 2: Medium
#     if ai_data.get('mood') or ai_data.get('category'):
#         query, args = build_search_query(table, ai_data, 2)
#         with conn.cursor() as cur:
#             cur.execute(query, tuple(args))
#             results = cur.fetchall()
#             if results: return results

#     # Attempt 3: Loose (Date only or All)
#     query, args = build_search_query(table, ai_data, 3)
#     with conn.cursor() as cur:
#         cur.execute(query, tuple(args))
#         results = cur.fetchall()
#         return results

#     return []

# # --- TWILIO UTILS ---

# def send_whatsapp_message(to, body, media_url=None):
#     if not TWILIO_WHATSAPP_NUMBER: return
#     to_number_format = to 

#     try:
#         if media_url:
#             message = twilio_client.messages.create(
#                 from_=TWILIO_WHATSAPP_NUMBER,
#                 to=to_number_format,
#                 body=body,
#                 media_url=media_url
#             )
#         else:
#             message = twilio_client.messages.create(
#                 from_=TWILIO_WHATSAPP_NUMBER,
#                 to=to_number_format,
#                 body=body
#             )
#     except Exception as e:
#         print(f"❌ Twilio Send Error: {e}")

# # ==============================================================================
# # 📡 FINAL FALLBACK
# # ==============================================================================

# def ask_chatgpt_fallback(user_input, ai_data):
#     category = ai_data.get('category')
#     mood = ai_data.get('target_mood')
#     date_str = ai_data.get('date_range', {}).get('start')
    
#     if date_str:
#         context = f"The user asked about {date_str}. My database is empty for this date/topic. Suggest something appropriate for a tourist on this date."
#     elif category:
#         context = f"The user asked for '{category}' and my database is empty. Suggest a great general place in Buenos Aires that fits this category."
#     elif mood:
#         context = f"The user asked for a '{mood}' vibe, but my database is empty. Give a general, highly-rated suggestion that fits this mood."
#     else:
#         context = "The user made a request but my database has no matches. Suggest something fun and general for a tourist in Buenos Aires."

#     try:
#         response = openai.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[{"role": "system", "content": f"You are Yara, an expert, non-stop helpful Buenos Aires local guide. {context}"}, 
#                       {"role": "user", "content": user_input}],
#             timeout=5
#         )
#         return response.choices[0].message.content
#     except: 
#         return "I couldn't find specific matches, but I'm looking for general ideas now! Try asking me again in a moment."

# # --- TIMEOUT LOGIC ---
# def send_followup_message(user_id):
#     try:
#         print(f"⏰ Sending follow-up to {user_id}")
#         msg = "Hey! Just checking in. Let me know if you need anything else! 👋"
#         send_whatsapp_message(user_id, msg)
#         if user_id in user_timers: del user_timers[user_id]
#     except: pass

# def reset_user_timer(user_id):
#     if user_id in user_timers: user_timers[user_id].cancel()
#     timer = threading.Timer(60.0, send_followup_message, args=[user_id])
#     user_timers[user_id] = timer
#     timer.start()


# # ==============================================================================
# # ⚙️ MAIN PROCESS
# # ==============================================================================

# def process_message_thread(sender, text):
#     reset_user_timer(sender)

#     conn = None
#     try:
#         conn = postgreSQL_pool.getconn()
#         user = get_user(conn, sender)

#         # 1. NEW USER HANDLING
#         if not user:
#             create_user(conn, sender)
#             send_whatsapp_message(sender, "Hey! 🇦🇷 Welcome to Buenos Aires.\nI'm Yara, your local guide to events, bars, restaurants, and hidden gems.\nWhat are you in the mood for today?")
#             return

#         step = user.get('conversation_step')
#         user_age = user.get('age', '25')

#         # 2. AI ANALYZE INTENT
#         future_ai = executor.submit(analyze_user_intent, text)
#         ai_data = future_ai.result()
#         if not ai_data: ai_data = {}

#         # 3. GREETING CHECK
#         if ai_data.get('is_greeting') and step != 'ask_name_age':
#             user_name = user.get('name')
#             greeting = f"Hey {user_name}! What are you looking for today?" if user_name else "Hey! What are you looking for today?"
#             send_whatsapp_message(sender, greeting)
#             return

#         # 4. FIX: FIRST MOOD / ONBOARDING LOGIC
#         # If step is 'welcome', the user is replying to the intro message with their first mood.
#         if step == 'welcome':
#             send_whatsapp_message(sender, "First, to give you the best personalized recommendations, what’s your name and age?")
#             # Save the text (mood) and update step
#             update_user(conn, sender, {"conversation_step": "ask_name_age", "last_mood": text})
#             return

#         # 5. NAME/AGE CAPTURE
#         if step == 'ask_name_age':
#             last_mood = user.get('last_mood')
#             send_whatsapp_message(sender, f"Ok cool! Showing options for '{last_mood}':")
            
#             # Simple parsing for name/age
#             parts = text.split()
#             name = parts[0] if parts else "Friend"
#             age = "".join(filter(str.isdigit, text)) or "25"
            
#             update_user(conn, sender, {"name": name, "age": age, "conversation_step": "ready"})
            
#             # RE-RUN AI on the saved mood so we can search now
#             text = last_mood 
#             ai_data = analyze_user_intent(text)

#         # --- SEARCH LOGIC ---
#         found_something = False

#         # A. SEARCH EVENTS
#         if ai_data.get('date_range') or ai_data.get('category') in ['event', 'party', 'show', 'concert']:
#             events = smart_search(conn, 'events', ai_data)
            
#             if events:
#                 found_something = True
#                 start_date = ai_data.get('date_range', {}).get('start')
#                 intro = f"Here is what's happening around {start_date}:" if start_date else "Here are some events matching your vibe:"
#                 send_whatsapp_message(sender, intro)

#                 for e in events:
#                     future_jfy = executor.submit(generate_just_for_you, user_age, e['title'], e['description'], e.get('mood', 'social'))
#                     just_for_you = future_jfy.result()
                    
#                     display_date = e.get('event_date') if e.get('event_date') else f"Every {e.get('recurring_day')}"
#                     caption = (
#                         f"*{e.get('title')}*\n\n"
#                         f"📍 Location: {e.get('location')}\n"
#                         f"🕒 Time: {e.get('event_time')}\n"
#                         f"📅 Date: {display_date}\n"
#                         f"🎵 Music: {e.get('music_type')}\n"
#                         f"📝 {e.get('description')}\n"
#                         f"📸 {e.get('instagram_link')}\n\n"
#                         f"{just_for_you}"
#                     )
#                     if e.get('image_url'): 
#                         send_whatsapp_message(sender, caption, media_url=e.get('image_url'))
#                     else: 
#                         send_whatsapp_message(sender, caption)

#         # B. SEARCH BUSINESSES
#         if not found_something or ai_data.get('category') in ['bar', 'restaurant', 'cafe', 'shop', 'museum']:
#             businesses = smart_search(conn, 'businesses', ai_data)
            
#             if businesses:
#                 found_something = True
#                 send_whatsapp_message(sender, "Found these spots for you:")
#                 for b in businesses:
#                     future_jfy = executor.submit(generate_just_for_you, user_age, b['name'], b['description'], 'chill')
#                     just_for_you = future_jfy.result()
                    
#                     msg = (
#                         f"*{b.get('name')}*\n"
#                         f"📍 {b.get('location')}\n\n"
#                         f"{b.get('description')}\n\n"
#                         f"📸 {b.get('instagram_link')}\n\n"
#                         f"{just_for_you}"
#                     )
#                     send_whatsapp_message(sender, msg)

#         # C. RESULT HANDLING
#         if found_something:
#             closing = generate_closing_message(text)
#             send_whatsapp_message(sender, closing)
#         else:
#             # D. INTELLIGENT FALLBACK
#             fallback_text = ask_chatgpt_fallback(text, ai_data)
#             send_whatsapp_message(sender, fallback_text)

#     except Exception as e:
#         logger.error(f"Logic Error: {e}")
#     finally:
#         if conn: postgreSQL_pool.putconn(conn)

# # ==============================================================================
# # 🌐 TWILIO WEBHOOK
# # ==============================================================================

# @app.route("/webhook", methods=["POST"])
# def twilio_webhook():
#     incoming_msg = request.form.get('Body')
#     sender_id = request.form.get('From') 

#     if not sender_id or not incoming_msg:
#         return "" 
    
#     resp = MessagingResponse()
#     thread = threading.Thread(target=process_message_thread, args=(sender_id, incoming_msg))
#     thread.start()
#     return str(resp)

# if __name__ == "__main__":
#     print("🚀 Twilio Bot is starting...")
#     app.run(port=5000)


# import os
# import logging
# import psycopg2
# import threading
# import json
# import re
# from concurrent.futures import ThreadPoolExecutor
# from psycopg2 import pool
# from psycopg2.extras import RealDictCursor
# from datetime import datetime, timedelta, date
# from flask import Flask, request
# import openai
# from twilio.rest import Client as TwilioClient 
# from twilio.twiml.messaging_response import MessagingResponse 
# from dotenv import load_dotenv

# # 1. Load Environment Variables
# load_dotenv()

# app = Flask(__name__)

# # --- CONFIGURATION ---
# DB_URI = os.getenv("DATABASE_URL")
# OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
# openai.api_key = OPENAI_API_KEY

# TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
# TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
# TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER") 

# # Initialize Twilio Client
# twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# # Logging
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

# # --- GLOBAL THREAD POOL ---
# executor = ThreadPoolExecutor(max_workers=5) 

# # --- DATABASE POOL ---
# try:
#     postgreSQL_pool = psycopg2.pool.SimpleConnectionPool(
#         1, 50, DB_URI, cursor_factory=RealDictCursor, connect_timeout=10
#     )
#     print("✅ Database Connection Pool Created")
# except (Exception, psycopg2.DatabaseError) as error:
#     print("❌ Error connecting to PostgreSQL", error)

# # ==============================================================================
# # 🧠 AI & UTILS
# # ==============================================================================

# def analyze_user_intent(user_text):
#     today_str = date.today().strftime("%Y-%m-%d")
#     weekday_str = date.today().strftime("%A")
    
#     system_prompt = (
#         f"Current Date: {today_str} ({weekday_str}). "
#         "Analyze the user's intent to find events or businesses in Buenos Aires. "
#         "1. 'is_greeting': boolean (true only if user JUST says 'hi', 'hello' with NO request). "
#         "2. 'date_range': {'start': 'YYYY-MM-DD', 'end': 'YYYY-MM-DD'} or null. "
#         "3. 'target_mood': string (e.g. romantic, chill, party). "
#         "4. 'category': string (e.g. bar, club, museum, event). "
#         "5. 'specific_keywords': List of strings. EXTRACT SPECIFIC THEMES/GENRES/CULTURES. "
#         "   - Example: 'African music' -> keywords=['African', 'Afro']. "
#         "   - Example: 'Salsa dancing' -> keywords=['Salsa', 'Latin']. "
#         "   - Example: 'Techno party' -> keywords=['Techno', 'Electronic']. "
#         "   - IGNORE generic words like 'event', 'place', 'today', 'tomorrow'. "
#         "Return STRICT JSON."
#     )
#     try:
#         response = openai.chat.completions.create(
#             model="gpt-4o-mini",
#             response_format={"type": "json_object"},
#             messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_text}],
#             temperature=0
#         )
#         content = response.choices[0].message.content.strip()
#         data = json.loads(content)
#         # Safety check to ensure data is a dict
#         if not isinstance(data, dict): 
#             return {}
#         logger.info(f"🧠 AI Analysis: {data}")
#         return data
#     except Exception as e:
#         logger.error(f"AI Intent Error: {e}")
#         return {}

# def generate_just_for_you(user_age, item_name, item_desc, item_mood):
#     try:
#         prompt = (
#             f"Write a 1-sentence recommendation for a {user_age} year old. "
#             f"Venue: {item_name}. Vibe: {item_mood}. "
#             "Start with '✨ Just for you:'."
#         )
#         response = openai.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[{"role": "user", "content": prompt}],
#             temperature=0.7,
#             timeout=3
#         )
#         return response.choices[0].message.content.replace('"', '')
#     except:
#         return f"✨ Just for you: This matches the {item_mood} vibe!"

# def generate_closing_message(user_query):
#     try:
#         prompt = (
#             f"User query: '{user_query}'. I sent recommendations. "
#             "Write a short closing message asking if they are satisfied. Use an emoji."
#         )
#         response = openai.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[{"role": "system", "content": "You are Yara."}, 
#                       {"role": "user", "content": prompt}],
#             temperature=0.7,
#             timeout=3
#         )
#         return response.choices[0].message.content.replace('"', '')
#     except:
#         return "Are you satisfied with these options? 🎉"

# # --- DATABASE FUNCTIONS ---

# def get_user(conn, phone):
#     with conn.cursor() as cur:
#         cur.execute("SELECT * FROM public.users WHERE phone = %s", (phone,))
#         return cur.fetchone()

# def create_user(conn, phone):
#     with conn.cursor() as cur:
#         cur.execute("INSERT INTO public.users (phone, conversation_step) VALUES (%s, 'welcome') ON CONFLICT (phone) DO NOTHING", (phone,))
#         conn.commit()
#         cur.execute("SELECT * FROM public.users WHERE phone = %s", (phone,))
#         return cur.fetchone()

# def update_user(conn, phone, data):
#     set_clause = ", ".join([f"{key} = %s" for key in data.keys()])
#     values = list(data.values())
#     values.append(phone)
#     with conn.cursor() as cur:
#         cur.execute(f"UPDATE public.users SET {set_clause} WHERE phone = %s", values)
#         conn.commit()

# # --- INTELLIGENT SEARCH LOGIC ---

# def build_search_query(table, ai_data, strictness_level):
#     query = f"SELECT * FROM public.{table} WHERE 1=1"
#     args = []
    
#     date_range = ai_data.get('date_range') or {}
    
#     # 1. Combine all descriptive terms (Keywords + Mood + Category)
#     search_terms = []
#     if ai_data.get('specific_keywords'):
#         search_terms.extend(ai_data.get('specific_keywords'))
#     if ai_data.get('target_mood'):
#         search_terms.append(ai_data.get('target_mood'))
    
#     # Add category to search terms ONLY if it's specific
#     cat = ai_data.get('category', '')
#     if cat and len(cat) > 3 and cat.lower() not in ['event', 'party', 'show', 'place', 'spot', 'bar', 'restaurant']:
#         search_terms.append(cat)
    
#     # Clean list
#     search_terms = list(set([t for t in search_terms if t and len(t) > 2])) 
    
#     logger.info(f"🔍 Search Terms ({strictness_level}): {search_terms}")

#     # --- DATE LOGIC (Always Strict for Events) ---
#     if table == 'events' and date_range:
#         start = date_range.get('start')
#         end = date_range.get('end')
        
#         if start and end:
#             start_obj = datetime.strptime(start, "%Y-%m-%d").date()
#             end_obj = datetime.strptime(end, "%Y-%m-%d").date()
            
#             days_in_range = []
#             curr = start_obj
#             while curr <= end_obj:
#                 days_in_range.append(curr.strftime('%A'))
#                 curr += timedelta(days=1)
#             days_tuple = tuple(days_in_range) if len(days_in_range) > 1 else (days_in_range[0],)
            
#             query += " AND ((event_date >= %s::date AND event_date <= %s::date) OR (recurring_day IN %s))"
#             args.extend([start, end, days_tuple])

#     # --- TEXT SEARCH LOGIC ---
#     if search_terms:
#         term_conditions = []
#         for term in search_terms:
#             term_wild = f"%{term}%"
            
#             if table == 'events':
#                 # Search in: Title, Description, Mood, Music Type, Location
#                 clause = "(title ILIKE %s OR description ILIKE %s OR mood ILIKE %s OR music_type ILIKE %s OR location ILIKE %s)"
#                 term_conditions.append(clause)
#                 args.extend([term_wild, term_wild, term_wild, term_wild, term_wild])
#             else:
#                 # Search in: Name, Description, Location, Type
#                 clause = "(name ILIKE %s OR description ILIKE %s OR location ILIKE %s OR type ILIKE %s)"
#                 term_conditions.append(clause)
#                 args.extend([term_wild, term_wild, term_wild, term_wild])

#         if term_conditions:
#             # Level 1 (Strict): ALL keywords must match (AND)
#             # Level 2 (Loose): ANY keyword can match (OR)
#             join_operator = " AND " if strictness_level == 1 else " OR "
#             query += f" AND ({join_operator.join(term_conditions)})"

#     # Limit results
#     if table == 'events': 
#         query += " ORDER BY event_date ASC LIMIT 5"
#     else: 
#         query += " LIMIT 5"

#     logger.info(f"📊 Query: {query}")
#     logger.info(f"📊 Args: {args}")
    
#     return query, args

# def smart_search(conn, table, ai_data):
#     # Attempt 1: Strict Search (Must match ALL keywords)
#     query, args = build_search_query(table, ai_data, strictness_level=1)
#     with conn.cursor() as cur:
#         cur.execute(query, tuple(args))
#         results = cur.fetchall()
#         if results:
#             logger.info(f"✅ Found {len(results)} results (Strict)")
#             return results

#     # Attempt 2: Loose Search (Match ANY keyword)
#     query, args = build_search_query(table, ai_data, strictness_level=2)
#     with conn.cursor() as cur:
#         cur.execute(query, tuple(args))
#         results = cur.fetchall()
#         if results:
#             logger.info(f"✅ Found {len(results)} results (Loose)")
#         else:
#             logger.warning(f"⚠️ No results found in {table}")
#         return results if results else []

# # --- TWILIO UTILS ---

# def send_whatsapp_message(to, body, media_url=None):
#     if not TWILIO_WHATSAPP_NUMBER: return
#     to_number_format = to 

#     try:
#         if media_url:
#             message = twilio_client.messages.create(
#                 from_=TWILIO_WHATSAPP_NUMBER,
#                 to=to_number_format,
#                 body=body,
#                 media_url=media_url
#             )
#         else:
#             message = twilio_client.messages.create(
#                 from_=TWILIO_WHATSAPP_NUMBER,
#                 to=to_number_format,
#                 body=body
#             )
#     except Exception as e:
#         logger.error(f"❌ Twilio Send Error: {e}")

# # ==============================================================================
# # 📡 FINAL FALLBACK
# # ==============================================================================

# def ask_chatgpt_fallback(user_input, ai_data):
#     category = ai_data.get('category')
#     mood = ai_data.get('target_mood')
#     date_range = ai_data.get('date_range') or {}
#     date_str = date_range.get('start')
    
#     if date_str:
#         context = f"The user asked about {date_str}. My database is empty for this date/topic. Suggest something appropriate for a tourist on this date."
#     elif category:
#         context = f"The user asked for '{category}' and my database is empty. Suggest a great general place in Buenos Aires that fits this category."
#     elif mood:
#         context = f"The user asked for a '{mood}' vibe, but my database is empty. Give a general, highly-rated suggestion that fits this mood."
#     else:
#         context = "The user made a request but my database has no matches. Suggest something fun and general for a tourist in Buenos Aires."

#     try:
#         response = openai.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[{"role": "system", "content": f"You are Yara, an expert, non-stop helpful Buenos Aires local guide. {context}"}, 
#                       {"role": "user", "content": user_input}],
#             timeout=5
#         )
#         return response.choices[0].message.content
#     except: 
#         return "I couldn't find specific matches, but I'm looking for general ideas now! Try asking me again in a moment."

# # ==============================================================================
# # ⚙️ MAIN PROCESS
# # ==============================================================================

# def process_message_thread(sender, text):
#     conn = None
#     try:
#         conn = postgreSQL_pool.getconn()
#         user = get_user(conn, sender)

#         # 1. NEW USER HANDLING
#         if not user:
#             create_user(conn, sender)
#             send_whatsapp_message(sender, "Hey! 🇦🇷 Welcome to Buenos Aires.\nI'm Yara, your local guide to events, bars, restaurants, and hidden gems.\nWhat are you in the mood for today?")
#             return

#         step = user.get('conversation_step')
#         user_age = user.get('age', '25')

#         # 2. AI ANALYZE INTENT
#         future_ai = executor.submit(analyze_user_intent, text)
#         ai_data = future_ai.result()
        
#         # FIX: CRITICAL CRASH PREVENTION
#         if not ai_data or not isinstance(ai_data, dict): 
#             ai_data = {}

#         # 3. GREETING CHECK
#         if ai_data.get('is_greeting') and step != 'ask_name_age':
#             user_name = user.get('name')
#             greeting_name = user_name if user_name else "there"
#             greeting = f"Hey {greeting_name}! What are you looking for today?"
#             send_whatsapp_message(sender, greeting)
#             return

#         # 4. FIRST MOOD / ONBOARDING LOGIC
#         if step == 'welcome':
#             send_whatsapp_message(sender, "First, to give you the best personalized recommendations, what's your name and age?")
#             update_user(conn, sender, {"conversation_step": "ask_name_age", "last_mood": text})
#             return

#         # 5. NAME/AGE CAPTURE
#         if step == 'ask_name_age':
#             last_mood = user.get('last_mood')
#             send_whatsapp_message(sender, f"Ok cool! Showing options for '{last_mood}':")
            
#             # FIX: Better Name Parsing
#             parts = text.split()
#             raw_name = parts[0] if parts else "Friend"
#             clean_name = re.sub(r'[^a-zA-Z]', '', raw_name)
#             if not clean_name: clean_name = "Friend"
            
#             age = "".join(filter(str.isdigit, text)) or "25"
            
#             update_user(conn, sender, {"name": clean_name, "age": age, "conversation_step": "ready"})
#             text = last_mood 
#             ai_data = analyze_user_intent(text)
#             if not ai_data or not isinstance(ai_data, dict): 
#                 ai_data = {}

#         # --- SEARCH LOGIC ---
#         found_something = False

#         # PRIORITY 1: CHECK EVENTS
#         should_check_events = (
#             ai_data.get('date_range') or 
#             ai_data.get('specific_keywords') or 
#             ai_data.get('target_mood') or
#             ai_data.get('category') in ['event', 'party', 'show', 'concert', 'exhibition']
#         )

#         if should_check_events:
#             events = smart_search(conn, 'events', ai_data)
            
#             if events:
#                 found_something = True
#                 date_range = ai_data.get('date_range') or {}
#                 start_date = date_range.get('start')
#                 intro = f"Here is what's happening around {start_date}:" if start_date else "Here are some events matching your vibe:"
#                 send_whatsapp_message(sender, intro)

#                 for e in events:
#                     future_jfy = executor.submit(generate_just_for_you, user_age, e['title'], e['description'], e.get('mood', 'social'))
#                     just_for_you = future_jfy.result()
                    
#                     display_date = e.get('event_date') if e.get('event_date') else f"Every {e.get('recurring_day')}"
#                     caption = (
#                         f"*{e.get('title')}*\n\n"
#                         f"📍 Location: {e.get('location')}\n"
#                         f"🕒 Time: {e.get('event_time')}\n"
#                         f"📅 Date: {display_date}\n"
#                         f"🎵 Music: {e.get('music_type')}\n"
#                         f"📝 {e.get('description')}\n"
#                         f"📸 {e.get('instagram_link')}\n\n"
#                         f"{just_for_you}"
#                     )
#                     if e.get('image_url'): 
#                         send_whatsapp_message(sender, caption, media_url=e.get('image_url'))
#                     else: 
#                         send_whatsapp_message(sender, caption)

#         # PRIORITY 2: CHECK BUSINESSES (Fallback or Explicit)
#         if not found_something or ai_data.get('category') in ['bar', 'restaurant', 'cafe', 'shop', 'museum']:
#             businesses = smart_search(conn, 'businesses', ai_data)
            
#             if businesses:
#                 found_something = True
#                 send_whatsapp_message(sender, "Found these spots for you:")
#                 for b in businesses:
#                     future_jfy = executor.submit(generate_just_for_you, user_age, b['name'], b['description'], 'chill')
#                     just_for_you = future_jfy.result()
                    
#                     msg = (
#                         f"*{b.get('name')}*\n"
#                         f"📍 {b.get('location')}\n\n"
#                         f"{b.get('description')}\n\n"
#                         f"📸 {b.get('instagram_link')}\n\n"
#                         f"{just_for_you}"
#                     )
#                     send_whatsapp_message(sender, msg)

#         # C. RESULT HANDLING
#         if found_something:
#             closing = generate_closing_message(text)
#             send_whatsapp_message(sender, closing)
#         else:
#             # D. INTELLIGENT FALLBACK
#             fallback_text = ask_chatgpt_fallback(text, ai_data)
#             send_whatsapp_message(sender, fallback_text)

#     except Exception as e:
#         logger.error(f"Logic Error: {e}", exc_info=True)
#         send_whatsapp_message(sender, "Sorry, something went wrong. Let me try again - what are you looking for?")
#     finally:
#         if conn: postgreSQL_pool.putconn(conn)

# # ==============================================================================
# # 🌐 TWILIO WEBHOOK
# # ==============================================================================

# @app.route("/webhook", methods=["POST"])
# def twilio_webhook():
#     incoming_msg = request.form.get('Body')
#     sender_id = request.form.get('From') 

#     if not sender_id or not incoming_msg:
#         return "" 
    
#     resp = MessagingResponse()
#     thread = threading.Thread(target=process_message_thread, args=(sender_id, incoming_msg))
#     thread.start()
#     return str(resp)

# if __name__ == "__main__":
#     print("🚀 Twilio Bot is starting...")
#     app.run(port=5000)

# # reccommnedations giving but bars and all arew erros
# import os
# import logging
# import psycopg2
# import threading
# import json
# import re
# from concurrent.futures import ThreadPoolExecutor
# from psycopg2 import pool
# from psycopg2.extras import RealDictCursor
# from datetime import datetime, timedelta, date
# from flask import Flask, request
# import openai
# from twilio.rest import Client as TwilioClient 
# from twilio.twiml.messaging_response import MessagingResponse 
# from dotenv import load_dotenv

# # 1. Load Environment Variables
# load_dotenv()

# app = Flask(__name__)

# # --- CONFIGURATION ---
# DB_URI = os.getenv("DATABASE_URL")
# OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
# openai.api_key = OPENAI_API_KEY

# TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
# TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
# TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER") 

# # Initialize Twilio Client
# twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# # Logging
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

# # --- GLOBAL THREAD POOL ---
# executor = ThreadPoolExecutor(max_workers=5) 

# # --- DATABASE POOL ---
# try:
#     postgreSQL_pool = psycopg2.pool.SimpleConnectionPool(
#         1, 50, DB_URI, cursor_factory=RealDictCursor, connect_timeout=10
#     )
#     print("✅ Database Connection Pool Created")
# except (Exception, psycopg2.DatabaseError) as error:
#     print("❌ Error connecting to PostgreSQL", error)

# # ==============================================================================
# # 🧠 ENHANCED AI & UTILS
# # ==============================================================================

# def analyze_user_intent(user_text):
#     """
#     ENHANCED: Now understands context, multi-language, and social situations
#     """
#     today_str = date.today().strftime("%Y-%m-%d")
#     weekday_str = date.today().strftime("%A")
    
#     system_prompt = (
#         f"Current Date: {today_str} ({weekday_str}). "
#         "You are a multilingual AI that understands ALL languages (English, Spanish, Portuguese, French, etc.). "
#         "Analyze the user's intent to find events or businesses in Buenos Aires. "
        
#         "EXTRACT THE FOLLOWING (return as JSON):\n"
        
#         "1. 'is_greeting': boolean (true ONLY if user just says 'hi'/'hello'/'hola' with NO request)\n"
        
#         "2. 'date_range': {'start': 'YYYY-MM-DD', 'end': 'YYYY-MM-DD'} or null\n"
#         "   - 'today' = today's date\n"
#         "   - 'tomorrow' = tomorrow's date\n"
#         "   - 'this weekend' = upcoming Saturday-Sunday\n"
#         "   - 'tonight' = today after 6pm\n"
        
#         "3. 'target_mood': string (romantic, chill, energetic, party, relaxed, upscale, casual)\n"
        
#         "4. 'social_context': string - WHO is the user with?\n"
#         "   - 'date' (romantic date, anniversary, couple)\n"
#         "   - 'friends' (hanging out, group, buddies)\n"
#         "   - 'solo' (alone, by myself)\n"
#         "   - 'family' (parents, kids)\n"
#         "   - 'business' (work, colleagues, networking)\n"
#         "   - null if not specified\n"
        
#         "5. 'category': string\n"
#         "   - For events: 'event', 'concert', 'show', 'exhibition', 'party', 'festival'\n"
#         "   - For places: 'bar', 'restaurant', 'cafe', 'club', 'museum', 'park'\n"
        
#         "6. 'specific_keywords': List of SPECIFIC themes/genres/cultures\n"
#         "   - Examples:\n"
#         "     * 'African music' → ['African', 'Afro']\n"
#         "     * 'Salsa dancing' → ['Salsa', 'Latin']\n"
#         "     * 'Techno party' → ['Techno', 'Electronic']\n"
#         "     * 'Jazz bar' → ['Jazz']\n"
#         "     * 'Rooftop' → ['Rooftop', 'Terrace']\n"
#         "     * 'Live music' → ['Live', 'Band']\n"
#         "   - IGNORE generic words: 'event', 'place', 'today', 'bar', 'restaurant'\n"
        
#         "7. 'user_language': detected language code (en, es, pt, fr, etc.)\n"
        
#         "EXAMPLES:\n"
#         "User: 'Quiero ir a un bar tranquilo con amigos'\n"
#         "→ {social_context: 'friends', target_mood: 'chill', category: 'bar', user_language: 'es'}\n"
        
#         "User: 'Need a romantic place for date night'\n"
#         "→ {social_context: 'date', target_mood: 'romantic', category: 'restaurant', user_language: 'en'}\n"
        
#         "User: 'African music events this weekend'\n"
#         "→ {specific_keywords: ['African', 'Afro'], date_range: {...}, category: 'event', user_language: 'en'}\n"
        
#         "Return STRICT JSON only."
#     )
    
#     try:
#         response = openai.chat.completions.create(
#             model="gpt-4o-mini",
#             response_format={"type": "json_object"},
#             messages=[
#                 {"role": "system", "content": system_prompt}, 
#                 {"role": "user", "content": user_text}
#             ],
#             temperature=0
#         )
#         content = response.choices[0].message.content.strip()
#         data = json.loads(content)
        
#         if not isinstance(data, dict): 
#             return {}
        
#         logger.info(f"🧠 AI Analysis: {data}")
#         return data
        
#     except Exception as e:
#         logger.error(f"AI Intent Error: {e}")
#         return {}

# def generate_just_for_you(user_age, item_name, item_desc, item_mood, social_context=None):
#     """
#     Enhanced: Now considers social context
#     """
#     try:
#         context_msg = ""
#         if social_context == 'date':
#             context_msg = "Perfect for a romantic date night."
#         elif social_context == 'friends':
#             context_msg = "Great spot to hang out with friends."
#         elif social_context == 'solo':
#             context_msg = "Perfect for solo exploration."
#         elif social_context == 'business':
#             context_msg = "Ideal for business meetings."
        
#         prompt = (
#             f"Write a 1-sentence recommendation for a {user_age} year old. "
#             f"Venue: {item_name}. Vibe: {item_mood}. {context_msg} "
#             "Start with '✨ Just for you:'. Be enthusiastic and specific."
#         )
        
#         response = openai.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[{"role": "user", "content": prompt}],
#             temperature=0.7,
#             timeout=3
#         )
#         return response.choices[0].message.content.replace('"', '')
#     except:
#         return f"✨ Just for you: This matches the {item_mood} vibe! {context_msg}"

# def generate_closing_message(user_query, user_language='en'):
#     """
#     Enhanced: Multi-language closing messages
#     """
#     try:
#         lang_instruction = ""
#         if user_language == 'es':
#             lang_instruction = "Respond in Spanish."
#         elif user_language == 'pt':
#             lang_instruction = "Respond in Portuguese."
#         elif user_language == 'fr':
#             lang_instruction = "Respond in French."
#         else:
#             lang_instruction = "Respond in English."
        
#         prompt = (
#             f"User query: '{user_query}'. I sent recommendations. "
#             f"Write a SHORT closing message asking if they want more suggestions or need help with anything else. "
#             f"Use 1 emoji. Be friendly and helpful. {lang_instruction}"
#         )
        
#         response = openai.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[
#                 {"role": "system", "content": "You are Yara, a friendly Buenos Aires guide."}, 
#                 {"role": "user", "content": prompt}
#             ],
#             temperature=0.7,
#             timeout=3
#         )
#         return response.choices[0].message.content.replace('"', '')
#     except:
#         # Fallback based on language
#         if user_language == 'es':
#             return "¿Te gustaría más sugerencias? 🎉"
#         elif user_language == 'pt':
#             return "Gostaria de mais sugestões? 🎉"
#         else:
#             return "Need more suggestions? 🎉"

# # --- DATABASE FUNCTIONS ---

# def get_user(conn, phone):
#     with conn.cursor() as cur:
#         cur.execute("SELECT * FROM public.users WHERE phone = %s", (phone,))
#         return cur.fetchone()

# def create_user(conn, phone):
#     with conn.cursor() as cur:
#         cur.execute(
#             "INSERT INTO public.users (phone, conversation_step) "
#             "VALUES (%s, 'welcome') ON CONFLICT (phone) DO NOTHING", 
#             (phone,)
#         )
#         conn.commit()
#         cur.execute("SELECT * FROM public.users WHERE phone = %s", (phone,))
#         return cur.fetchone()

# def update_user(conn, phone, data):
#     set_clause = ", ".join([f"{key} = %s" for key in data.keys()])
#     values = list(data.values())
#     values.append(phone)
#     with conn.cursor() as cur:
#         cur.execute(f"UPDATE public.users SET {set_clause} WHERE phone = %s", values)
#         conn.commit()

# # --- ENHANCED SEARCH LOGIC ---

# def build_search_query(table, ai_data, strictness_level):
#     """
#     Enhanced: Now considers social_context and better keyword matching
#     """
#     query = f"SELECT * FROM public.{table} WHERE 1=1"
#     args = []
    
#     date_range = ai_data.get('date_range') or {}
#     social_context = ai_data.get('social_context')
    
#     # 1. Build search terms from ALL context
#     search_terms = []
    
#     # Add specific keywords
#     if ai_data.get('specific_keywords'):
#         search_terms.extend(ai_data.get('specific_keywords'))
    
#     # Add mood
#     if ai_data.get('target_mood'):
#         search_terms.append(ai_data.get('target_mood'))
    
#     # Add social context keywords
#     if social_context == 'date':
#         search_terms.extend(['romantic', 'intimate', 'cozy'])
#     elif social_context == 'friends':
#         search_terms.extend(['social', 'group', 'casual'])
#     elif social_context == 'solo':
#         search_terms.extend(['quiet', 'peaceful', 'chill'])
    
#     # Add category if specific
#     cat = ai_data.get('category', '')
#     if cat and len(cat) > 3 and cat.lower() not in ['event', 'party', 'show', 'place', 'spot']:
#         search_terms.append(cat)
    
#     # Clean and deduplicate
#     search_terms = list(set([t for t in search_terms if t and len(t) > 2]))
    
#     logger.info(f"🔍 Search Terms (Level {strictness_level}): {search_terms}")

#     # --- DATE LOGIC (for events) ---
#     if table == 'events' and date_range:
#         start = date_range.get('start')
#         end = date_range.get('end')
        
#         if start and end:
#             start_obj = datetime.strptime(start, "%Y-%m-%d").date()
#             end_obj = datetime.strptime(end, "%Y-%m-%d").date()
            
#             days_in_range = []
#             curr = start_obj
#             while curr <= end_obj:
#                 days_in_range.append(curr.strftime('%A'))
#                 curr += timedelta(days=1)
#             days_tuple = tuple(days_in_range) if len(days_in_range) > 1 else (days_in_range[0],)
            
#             query += " AND ((event_date >= %s::date AND event_date <= %s::date) OR (recurring_day IN %s))"
#             args.extend([start, end, days_tuple])

#     # --- TEXT SEARCH LOGIC ---
#     if search_terms:
#         term_conditions = []
#         for term in search_terms:
#             term_wild = f"%{term}%"
            
#             if table == 'events':
#                 # Search: Title, Description, Mood, Music Type, Location
#                 clause = "(title ILIKE %s OR description ILIKE %s OR mood ILIKE %s OR music_type ILIKE %s OR location ILIKE %s)"
#                 term_conditions.append(clause)
#                 args.extend([term_wild] * 5)
#             else:
#                 # Search: Name, Description, Location, Type, AND a new 'tags' field if exists
#                 clause = "(name ILIKE %s OR description ILIKE %s OR location ILIKE %s OR type ILIKE %s)"
#                 term_conditions.append(clause)
#                 args.extend([term_wild] * 4)

#         if term_conditions:
#             join_operator = " AND " if strictness_level == 1 else " OR "
#             query += f" AND ({join_operator.join(term_conditions)})"

#     # Order and limit
#     if table == 'events': 
#         query += " ORDER BY event_date ASC LIMIT 5"
#     else: 
#         query += " LIMIT 5"

#     logger.info(f"📊 SQL Query: {query[:200]}...")
#     logger.info(f"📊 Args: {args}")
    
#     return query, args

# def smart_search(conn, table, ai_data):
#     """
#     Tries strict search first, then loose search
#     """
#     # Attempt 1: Strict (ALL keywords)
#     query, args = build_search_query(table, ai_data, strictness_level=1)
#     with conn.cursor() as cur:
#         cur.execute(query, tuple(args))
#         results = cur.fetchall()
#         if results:
#             logger.info(f"✅ Found {len(results)} results (Strict)")
#             return results

#     # Attempt 2: Loose (ANY keyword)
#     query, args = build_search_query(table, ai_data, strictness_level=2)
#     with conn.cursor() as cur:
#         cur.execute(query, tuple(args))
#         results = cur.fetchall()
#         if results:
#             logger.info(f"✅ Found {len(results)} results (Loose)")
#         else:
#             logger.warning(f"⚠️ No results in {table}")
#         return results if results else []

# # --- TWILIO UTILS ---

# def send_whatsapp_message(to, body, media_url=None):
#     if not TWILIO_WHATSAPP_NUMBER: 
#         return
    
#     try:
#         if media_url:
#             twilio_client.messages.create(
#                 from_=TWILIO_WHATSAPP_NUMBER,
#                 to=to,
#                 body=body,
#                 media_url=media_url
#             )
#         else:
#             twilio_client.messages.create(
#                 from_=TWILIO_WHATSAPP_NUMBER,
#                 to=to,
#                 body=body
#             )
#     except Exception as e:
#         logger.error(f"❌ Twilio Error: {e}")

# # ==============================================================================
# # 🎯 ENHANCED INTELLIGENT FALLBACK
# # ==============================================================================

# def ask_chatgpt_expert_fallback(user_input, ai_data, user_language='en'):
#     """
#     🌟 NEW: Acts as a REAL Buenos Aires expert tour guide
    
#     When database has no matches, this provides REAL, HELPFUL recommendations
#     based on the user's context (date, friends, mood, etc.)
#     """
    
#     category = ai_data.get('category')
#     mood = ai_data.get('target_mood')
#     social_context = ai_data.get('social_context')
#     keywords = ai_data.get('specific_keywords', [])
#     date_range = ai_data.get('date_range') or {}
#     date_str = date_range.get('start')
    
#     # Build context for ChatGPT
#     context_parts = []
    
#     if social_context == 'date':
#         context_parts.append("The user is looking for a romantic spot for a date")
#     elif social_context == 'friends':
#         context_parts.append("The user wants to hang out with friends")
#     elif social_context == 'solo':
#         context_parts.append("The user is exploring solo")
    
#     if mood:
#         context_parts.append(f"They want a {mood} vibe")
    
#     if keywords:
#         context_parts.append(f"They're interested in: {', '.join(keywords)}")
    
#     if category:
#         context_parts.append(f"Looking for: {category}")
    
#     if date_str:
#         context_parts.append(f"For the date: {date_str}")
    
#     context_description = ". ".join(context_parts) if context_parts else "They're looking for recommendations"
    
#     # Language instruction
#     lang_instruction = ""
#     if user_language == 'es':
#         lang_instruction = "\n\nIMPORTANT: Respond in Spanish."
#     elif user_language == 'pt':
#         lang_instruction = "\n\nIMPORTANT: Respond in Portuguese."
#     elif user_language == 'fr':
#         lang_instruction = "\n\nIMPORTANT: Respond in French."
#     else:
#         lang_instruction = "\n\nIMPORTANT: Respond in English."
    
#     expert_prompt = f"""You are Yara, a LOCAL Buenos Aires expert and tour guide. You know:
# - All the best bars, restaurants, cafes, and hidden gems in Buenos Aires
# - The hottest clubs and music venues
# - Cultural centers and artistic spaces
# - Where locals actually go (not just tourist traps)
# - The vibe and atmosphere of each neighborhood

# CONTEXT: {context_description}

# Your database doesn't have this specific request, but as a real Buenos Aires expert, you should:
# 1. Give 2-3 SPECIFIC place names in Buenos Aires that match the request
# 2. Include the neighborhood (Palermo, San Telmo, Recoleta, etc.)
# 3. Briefly explain WHY each place is perfect for their context
# 4. Keep it conversational and friendly
# 5. Add relevant emojis

# Format your response like this:
# "[Intro sentence acknowledging their request]

# 🎯 [Place Name 1] in [Neighborhood]
# [One sentence why it's perfect]

# 🎯 [Place Name 2] in [Neighborhood]  
# [One sentence why it's perfect]

# [Friendly closing]"

# ORIGINAL USER REQUEST: "{user_input}"
# {lang_instruction}"""

#     try:
#         response = openai.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[
#                 {"role": "system", "content": "You are Yara, an expert Buenos Aires local guide who gives SPECIFIC recommendations."}, 
#                 {"role": "user", "content": expert_prompt}
#             ],
#             temperature=0.8,
#             timeout=8
#         )
        
#         expert_response = response.choices[0].message.content
#         logger.info(f"🎯 Expert Fallback Response Generated")
#         return expert_response
        
#     except Exception as e:
#         logger.error(f"Fallback Error: {e}")
        
#         # Last resort fallback
#         if user_language == 'es':
#             return "Hmm, no encontré opciones específicas en mi base de datos, pero hay muchos lugares geniales en Buenos Aires. ¿Puedes darme más detalles sobre lo que buscas?"
#         else:
#             return "I couldn't find specific matches in my database, but Buenos Aires has tons of great spots! Can you give me more details about what you're looking for?"

# # ==============================================================================
# # ⚙️ MAIN PROCESS - ENHANCED
# # ==============================================================================

# def process_message_thread(sender, text):
#     conn = None
#     try:
#         conn = postgreSQL_pool.getconn()
#         user = get_user(conn, sender)

#         # 1. NEW USER
#         if not user:
#             create_user(conn, sender)
#             send_whatsapp_message(
#                 sender, 
#                 "Hey! 🇦🇷 Welcome to Buenos Aires.\n"
#                 "I'm Yara, your local guide to events, bars, restaurants, and hidden gems.\n"
#                 "What are you in the mood for today?"
#             )
#             return

#         step = user.get('conversation_step')
#         user_age = user.get('age', '25')

#         # 2. ANALYZE INTENT (Multi-language support)
#         future_ai = executor.submit(analyze_user_intent, text)
#         ai_data = future_ai.result()
        
#         if not ai_data or not isinstance(ai_data, dict): 
#             ai_data = {}
        
#         user_language = ai_data.get('user_language', 'en')
#         social_context = ai_data.get('social_context')

#         # 3. GREETING CHECK
#         if ai_data.get('is_greeting') and step != 'ask_name_age':
#             user_name = user.get('name')
#             greeting_name = user_name if user_name else "there"
            
#             if user_language == 'es':
#                 greeting = f"¡Hola {greeting_name}! ¿Qué estás buscando hoy?"
#             elif user_language == 'pt':
#                 greeting = f"Olá {greeting_name}! O que você está procurando hoje?"
#             else:
#                 greeting = f"Hey {greeting_name}! What are you looking for today?"
            
#             send_whatsapp_message(sender, greeting)
#             return

#         # 4. ONBOARDING
#         if step == 'welcome':
#             onboarding_msg = "First, to give you the best personalized recommendations, what's your name and age?"
#             if user_language == 'es':
#                 onboarding_msg = "Primero, para darte las mejores recomendaciones, ¿cuál es tu nombre y edad?"
            
#             send_whatsapp_message(sender, onboarding_msg)
#             update_user(conn, sender, {"conversation_step": "ask_name_age", "last_mood": text})
#             return

#         # 5. NAME/AGE CAPTURE
#         if step == 'ask_name_age':
#             last_mood = user.get('last_mood')
            
#             confirmation_msg = f"Ok cool! Showing options for '{last_mood}':"
#             if user_language == 'es':
#                 confirmation_msg = f"¡Perfecto! Buscando opciones para '{last_mood}':"
            
#             send_whatsapp_message(sender, confirmation_msg)
            
#             parts = text.split()
#             raw_name = parts[0] if parts else "Friend"
#             clean_name = re.sub(r'[^a-zA-ZÀ-ÿ]', '', raw_name)  # Support accented characters
#             if not clean_name: 
#                 clean_name = "Friend"
            
#             age = "".join(filter(str.isdigit, text)) or "25"
            
#             update_user(conn, sender, {
#                 "name": clean_name, 
#                 "age": age, 
#                 "conversation_step": "ready"
#             })
            
#             text = last_mood 
#             ai_data = analyze_user_intent(text)
#             if not ai_data or not isinstance(ai_data, dict): 
#                 ai_data = {}
#             user_language = ai_data.get('user_language', 'en')
#             social_context = ai_data.get('social_context')

#         # --- SMART SEARCH LOGIC ---
#         found_something = False

#         # PRIORITY 1: EVENTS (if user mentions events/dates/specific music)
#         should_check_events = (
#             ai_data.get('date_range') or 
#             ai_data.get('specific_keywords') or 
#             ai_data.get('category') in ['event', 'concert', 'show', 'party', 'exhibition', 'festival']
#         )

#         if should_check_events:
#             events = smart_search(conn, 'events', ai_data)
            
#             if events:
#                 found_something = True
#                 date_range = ai_data.get('date_range') or {}
#                 start_date = date_range.get('start')
                
#                 if start_date:
#                     intro = f"Here's what's happening around {start_date}:" if user_language == 'en' else f"Esto es lo que pasa alrededor del {start_date}:"
#                 else:
#                     intro = "Here are some events matching your vibe:" if user_language == 'en' else "Aquí hay algunos eventos que coinciden con tu vibra:"
                
#                 send_whatsapp_message(sender, intro)

#                 for e in events:
#                     future_jfy = executor.submit(
#                         generate_just_for_you, 
#                         user_age, 
#                         e['title'], 
#                         e['description'], 
#                         e.get('mood', 'social'),
#                         social_context
#                     )
#                     just_for_you = future_jfy.result()
                    
#                     display_date = e.get('event_date') if e.get('event_date') else f"Every {e.get('recurring_day')}"
                    
#                     caption = (
#                         f"*{e.get('title')}*\n\n"
#                         f"📍 {e.get('location')}\n"
#                         f"🕒 {e.get('event_time')}\n"
#                         f"📅 {display_date}\n"
#                         f"🎵 {e.get('music_type')}\n"
#                         f"📝 {e.get('description')}\n"
#                         f"📸 {e.get('instagram_link')}\n\n"
#                         f"{just_for_you}"
#                     )
                    
#                     if e.get('image_url'): 
#                         send_whatsapp_message(sender, caption, media_url=e.get('image_url'))
#                     else: 
#                         send_whatsapp_message(sender, caption)

#         # PRIORITY 2: BUSINESSES (bars, cafes, restaurants)
#         # Always check if: no events found OR explicitly asking for places
#         should_check_businesses = (
#             not found_something or 
#             ai_data.get('category') in ['bar', 'restaurant', 'cafe', 'club', 'shop', 'museum'] or
#             social_context in ['date', 'friends', 'solo']  # Social context suggests places
#         )
        
#         if should_check_businesses:
#             businesses = smart_search(conn, 'businesses', ai_data)
            
#             if businesses:
#                 found_something = True
                
#                 intro = "Found these spots for you:" if user_language == 'en' else "Encontré estos lugares para ti:"
#                 send_whatsapp_message(sender, intro)
                
#                 for b in businesses:
#                     future_jfy = executor.submit(
#                         generate_just_for_you, 
#                         user_age, 
#                         b['name'], 
#                         b['description'], 
#                         mood or 'chill',
#                         social_context
#                     )
#                     just_for_you = future_jfy.result()
                    
#                     msg = (
#                         f"*{b.get('name')}*\n"
#                         f"📍 {b.get('location')}\n\n"
#                         f"{b.get('description')}\n\n"
#                         f"📸 {b.get('instagram_link')}\n\n"
#                         f"{just_for_you}"
#                     )
#                     send_whatsapp_message(sender, msg)

#         # RESULT HANDLING
#         if found_something:
#             closing = generate_closing_message(text, user_language)
#             send_whatsapp_message(sender, closing)
#         else:
#             # 🎯 ENHANCED EXPERT FALLBACK
#             logger.info("🎯 No database matches - Using Expert Fallback")
#             fallback_text = ask_chatgpt_expert_fallback(text, ai_data, user_language)
#             send_whatsapp_message(sender, fallback_text)

#     except Exception as e:
#         logger.error(f"Logic Error: {e}", exc_info=True)
#         send_whatsapp_message(
#             sender, 
#             "Sorry, something went wrong. Let me try again - what are you looking for?"
#         )
#     finally:
#         if conn: 
#             postgreSQL_pool.putconn(conn)

# # ==============================================================================
# # 🌐 WEBHOOK
# # ==============================================================================

# @app.route("/webhook", methods=["POST"])
# def twilio_webhook():
#     incoming_msg = request.form.get('Body')
#     sender_id = request.form.get('From') 

#     if not sender_id or not incoming_msg:
#         return "" 
    
#     resp = MessagingResponse()
#     thread = threading.Thread(
#         target=process_message_thread, 
#         args=(sender_id, incoming_msg)
#     )
#     thread.start()
#     return str(resp)

# if __name__ == "__main__":
#     print("🚀 Twilio Bot is starting...")
#     print("✨ Enhanced with: Multi-language + Context Understanding + Expert Fallback")
#     app.run(port=5000)

#chatgpt fall back
# import os
# import logging
# import psycopg2
# import threading
# import json
# import re
# from concurrent.futures import ThreadPoolExecutor
# from psycopg2 import pool
# from psycopg2.extras import RealDictCursor
# from datetime import datetime, timedelta, date
# from flask import Flask, request
# import openai
# from twilio.rest import Client as TwilioClient 
# from twilio.twiml.messaging_response import MessagingResponse 
# from dotenv import load_dotenv

# # 1. Load Environment Variables
# load_dotenv()

# app = Flask(__name__)

# # --- CONFIGURATION ---
# DB_URI = os.getenv("DATABASE_URL")
# OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
# openai.api_key = OPENAI_API_KEY

# TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
# TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
# TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER") 

# # Initialize Twilio Client
# twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# # Logging
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

# # --- GLOBAL THREAD POOL ---
# executor = ThreadPoolExecutor(max_workers=3)  # Reduced for Railway

# # --- DATABASE POOL ---
# try:
#     postgreSQL_pool = psycopg2.pool.SimpleConnectionPool(
#         1, 10, DB_URI, cursor_factory=RealDictCursor, connect_timeout=10  # Reduced pool size
#     )
#     logger.info("✅ Database Connection Pool Created")
# except (Exception, psycopg2.DatabaseError) as error:
#     logger.error(f"❌ Error connecting to PostgreSQL: {error}")

# # ==============================================================================
# # 🧠 AI & UTILS
# # ==============================================================================

# def analyze_user_intent(user_text):
#     """Enhanced: Multi-language and context understanding"""
#     today_str = date.today().strftime("%Y-%m-%d")
#     weekday_str = date.today().strftime("%A")
    
#     system_prompt = (
#         f"Current Date: {today_str} ({weekday_str}). "
#         "You are a multilingual AI that understands ALL languages. "
#         "Analyze the user's intent to find events or businesses in Buenos Aires. "
        
#         "EXTRACT (return JSON):\n"
#         "1. 'is_greeting': boolean (true ONLY if just 'hi'/'hello' with NO request)\n"
#         "2. 'date_range': {'start': 'YYYY-MM-DD', 'end': 'YYYY-MM-DD'} or null\n"
#         "3. 'target_mood': string (romantic, chill, energetic, party)\n"
#         "4. 'social_context': string ('date', 'friends', 'solo', 'family', 'business', null)\n"
#         "5. 'category': string ('bar', 'restaurant', 'cafe', 'event', 'concert', etc.)\n"
#         "6. 'specific_keywords': List of SPECIFIC themes/genres\n"
#         "   Examples: 'African music' → ['African', 'Afro']\n"
#         "7. 'user_language': detected language (en, es, pt, fr)\n"
#         "8. 'out_of_scope': boolean (true if NOT about Buenos Aires recommendations)\n"
#         "Return STRICT JSON."
#     )
    
#     try:
#         response = openai.chat.completions.create(
#             model="gpt-4o-mini",
#             response_format={"type": "json_object"},
#             messages=[
#                 {"role": "system", "content": system_prompt}, 
#                 {"role": "user", "content": user_text}
#             ],
#             temperature=0,
#             timeout=10  # Added timeout
#         )
#         content = response.choices[0].message.content.strip()
#         data = json.loads(content)
        
#         if not isinstance(data, dict): 
#             return {}
        
#         logger.info(f"🧠 AI Analysis: {data}")
#         return data
        
#     except Exception as e:
#         logger.error(f"AI Intent Error: {e}")
#         return {}

# def generate_just_for_you(user_age, item_name, item_desc, item_mood, social_context=None):
#     """Enhanced with social context"""
#     try:
#         context_msg = ""
#         if social_context == 'date':
#             context_msg = "Perfect for a romantic date."
#         elif social_context == 'friends':
#             context_msg = "Great for friends."
        
#         prompt = (
#             f"Write a 1-sentence recommendation for a {user_age} year old. "
#             f"Venue: {item_name}. Vibe: {item_mood}. {context_msg} "
#             "Start with '✨ Just for you:'. Be enthusiastic."
#         )
        
#         response = openai.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[{"role": "user", "content": prompt}],
#             temperature=0.7,
#             timeout=5
#         )
#         return response.choices[0].message.content.replace('"', '')
#     except Exception as e:
#         logger.error(f"JFY Error: {e}")
#         return f"✨ Just for you: This matches the {item_mood} vibe! {context_msg}"

# def generate_closing_message(user_query, user_language='en'):
#     """Multi-language closing"""
#     try:
#         lang_instruction = "Respond in Spanish." if user_language == 'es' else "Respond in English."
        
#         prompt = (
#             f"User query: '{user_query}'. I sent recommendations. "
#             f"Write SHORT closing asking if they need more help. "
#             f"Use 1 emoji. {lang_instruction}"
#         )
        
#         response = openai.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[
#                 {"role": "system", "content": "You are Yara."}, 
#                 {"role": "user", "content": prompt}
#             ],
#             temperature=0.7,
#             timeout=5
#         )
#         return response.choices[0].message.content.replace('"', '')
#     except Exception as e:
#         logger.error(f"Closing Error: {e}")
#         return "Need more help? 🎉" if user_language == 'en' else "¿Necesitas más ayuda? 🎉"

# # --- DATABASE FUNCTIONS ---

# def get_user(conn, phone):
#     try:
#         with conn.cursor() as cur:
#             cur.execute("SELECT * FROM public.users WHERE phone = %s", (phone,))
#             return cur.fetchone()
#     except Exception as e:
#         logger.error(f"Get user error: {e}")
#         return None

# def create_user(conn, phone):
#     try:
#         with conn.cursor() as cur:
#             cur.execute(
#                 "INSERT INTO public.users (phone, conversation_step) "
#                 "VALUES (%s, 'welcome') ON CONFLICT (phone) DO NOTHING", 
#                 (phone,)
#             )
#             conn.commit()
#             cur.execute("SELECT * FROM public.users WHERE phone = %s", (phone,))
#             return cur.fetchone()
#     except Exception as e:
#         logger.error(f"Create user error: {e}")
#         return None

# def update_user(conn, phone, data):
#     try:
#         set_clause = ", ".join([f"{key} = %s" for key in data.keys()])
#         values = list(data.values())
#         values.append(phone)
#         with conn.cursor() as cur:
#             cur.execute(f"UPDATE public.users SET {set_clause} WHERE phone = %s", values)
#             conn.commit()
#     except Exception as e:
#         logger.error(f"Update user error: {e}")

# # --- SEARCH LOGIC ---

# def build_search_query(table, ai_data, strictness_level):
#     """Enhanced search with context"""
#     query = f"SELECT * FROM public.{table} WHERE 1=1"
#     args = []
    
#     date_range = ai_data.get('date_range') or {}
#     social_context = ai_data.get('social_context')
    
#     search_terms = []
    
#     if ai_data.get('specific_keywords'):
#         search_terms.extend(ai_data.get('specific_keywords'))
    
#     if ai_data.get('target_mood'):
#         search_terms.append(ai_data.get('target_mood'))
    
#     if social_context == 'date':
#         search_terms.extend(['romantic', 'intimate', 'cozy'])
#     elif social_context == 'friends':
#         search_terms.extend(['social', 'casual'])
    
#     cat = ai_data.get('category', '')
#     if cat and len(cat) > 3 and cat.lower() not in ['event', 'party', 'show', 'place', 'spot']:
#         search_terms.append(cat)
    
#     search_terms = list(set([t for t in search_terms if t and len(t) > 2]))
    
#     logger.info(f"🔍 Search Terms: {search_terms}")

#     # Date logic for events
#     if table == 'events' and date_range:
#         start = date_range.get('start')
#         end = date_range.get('end')
        
#         if start and end:
#             try:
#                 start_obj = datetime.strptime(start, "%Y-%m-%d").date()
#                 end_obj = datetime.strptime(end, "%Y-%m-%d").date()
                
#                 days_in_range = []
#                 curr = start_obj
#                 while curr <= end_obj:
#                     days_in_range.append(curr.strftime('%A'))
#                     curr += timedelta(days=1)
#                 days_tuple = tuple(days_in_range) if len(days_in_range) > 1 else (days_in_range[0],)
                
#                 query += " AND ((event_date >= %s::date AND event_date <= %s::date) OR (recurring_day IN %s))"
#                 args.extend([start, end, days_tuple])
#             except Exception as e:
#                 logger.error(f"Date parsing error: {e}")

#     # Text search
#     if search_terms:
#         term_conditions = []
#         for term in search_terms:
#             term_wild = f"%{term}%"
            
#             if table == 'events':
#                 clause = "(title ILIKE %s OR description ILIKE %s OR mood ILIKE %s OR music_type ILIKE %s OR location ILIKE %s)"
#                 term_conditions.append(clause)
#                 args.extend([term_wild] * 5)
#             else:
#                 clause = "(name ILIKE %s OR description ILIKE %s OR location ILIKE %s OR type ILIKE %s)"
#                 term_conditions.append(clause)
#                 args.extend([term_wild] * 4)

#         if term_conditions:
#             join_operator = " AND " if strictness_level == 1 else " OR "
#             query += f" AND ({join_operator.join(term_conditions)})"

#     if table == 'events': 
#         query += " ORDER BY event_date ASC LIMIT 5"
#     else: 
#         query += " LIMIT 5"
    
#     return query, args

# def smart_search(conn, table, ai_data):
#     """Two-tier search"""
#     try:
#         # Strict search
#         query, args = build_search_query(table, ai_data, 1)
#         with conn.cursor() as cur:
#             cur.execute(query, tuple(args))
#             results = cur.fetchall()
#             if results:
#                 logger.info(f"✅ Found {len(results)} (Strict)")
#                 return results

#         # Loose search
#         query, args = build_search_query(table, ai_data, 2)
#         with conn.cursor() as cur:
#             cur.execute(query, tuple(args))
#             results = cur.fetchall()
#             if results:
#                 logger.info(f"✅ Found {len(results)} (Loose)")
#             return results if results else []
#     except Exception as e:
#         logger.error(f"Search error: {e}")
#         return []

# # --- TWILIO ---

# def send_whatsapp_message(to, body, media_url=None):
#     if not TWILIO_WHATSAPP_NUMBER: 
#         return
    
#     try:
#         if media_url:
#             twilio_client.messages.create(
#                 from_=TWILIO_WHATSAPP_NUMBER,
#                 to=to,
#                 body=body,
#                 media_url=media_url
#             )
#         else:
#             twilio_client.messages.create(
#                 from_=TWILIO_WHATSAPP_NUMBER,
#                 to=to,
#                 body=body
#             )
#     except Exception as e:
#         logger.error(f"❌ Twilio Error: {e}")

# # --- EXPERT FALLBACK ---

# def ask_chatgpt_expert_fallback(user_input, ai_data, user_language='en'):
#     """Expert guide fallback"""
    
#     category = ai_data.get('category')
#     mood = ai_data.get('target_mood')
#     social_context = ai_data.get('social_context')
#     keywords = ai_data.get('specific_keywords', [])
    
#     context_parts = []
    
#     if social_context == 'date':
#         context_parts.append("romantic spot for a date")
#     elif social_context == 'friends':
#         context_parts.append("hang out with friends")
    
#     if mood:
#         context_parts.append(f"{mood} vibe")
    
#     if keywords:
#         context_parts.append(f"interested in: {', '.join(keywords)}")
    
#     if category:
#         context_parts.append(f"looking for: {category}")
    
#     context_description = ". ".join(context_parts) if context_parts else "looking for recommendations"
    
#     lang_instruction = "\nRespond in Spanish." if user_language == 'es' else "\nRespond in English."
    
#     expert_prompt = f"""You are Yara, a Buenos Aires expert guide. 

# CONTEXT: {context_description}

# Give 2-3 SPECIFIC place names in Buenos Aires with neighborhoods.
# Format:
# "[Intro]

# 🎯 [Place] in [Neighborhood]
# [Why it's perfect]

# [Closing]"

# USER: "{user_input}"
# {lang_instruction}"""

#     try:
#         response = openai.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[
#                 {"role": "system", "content": "You are Yara, Buenos Aires expert."}, 
#                 {"role": "user", "content": expert_prompt}
#             ],
#             temperature=0.8,
#             timeout=10
#         )
        
#         return response.choices[0].message.content
        
#     except Exception as e:
#         logger.error(f"Fallback Error: {e}")
#         return "I couldn't find matches. Can you give me more details?" if user_language == 'en' else "No encontré opciones. ¿Puedes darme más detalles?"

# # --- MAIN PROCESS ---

# def process_message_thread(sender, text):
#     conn = None
#     try:
#         conn = postgreSQL_pool.getconn()
#         if not conn:
#             logger.error("Failed to get DB connection")
#             send_whatsapp_message(sender, "Sorry, having technical issues. Please try again in a moment.")
#             return
            
#         user = get_user(conn, sender)

#         # New user
#         if not user:
#             create_user(conn, sender)
#             send_whatsapp_message(
#                 sender, 
#                 "Hey! 🇦🇷 Welcome to Buenos Aires.\n"
#                 "I'm Yara, your local guide.\n"
#                 "What are you in the mood for today?"
#             )
#             return

#         step = user.get('conversation_step', 'welcome')
#         user_age = user.get('age', '25')

#         # Analyze intent
#         ai_data = analyze_user_intent(text)
        
#         if not ai_data or not isinstance(ai_data, dict): 
#             ai_data = {}
        
#         user_language = ai_data.get('user_language', 'en')
#         social_context = ai_data.get('social_context')
#         target_mood = ai_data.get('target_mood', 'chill')

#         # Out of scope check
#         if ai_data.get('out_of_scope'):
#             msg = "Sorry, I only help with Buenos Aires recommendations. What would you like to do here?" if user_language == 'en' else "Lo siento, solo ayudo con recomendaciones de Buenos Aires. ¿Qué te gustaría hacer?"
#             send_whatsapp_message(sender, msg)
#             return

#         # Greeting
#         if ai_data.get('is_greeting') and step != 'ask_name_age':
#             user_name = user.get('name', 'there')
#             greeting = f"Hey {user_name}! What are you looking for?" if user_language == 'en' else f"¡Hola {user_name}! ¿Qué buscas?"
#             send_whatsapp_message(sender, greeting)
#             return

#         # Onboarding
#         if step == 'welcome':
#             msg = "First, what's your name and age?" if user_language == 'en' else "Primero, ¿tu nombre y edad?"
#             send_whatsapp_message(sender, msg)
#             update_user(conn, sender, {"conversation_step": "ask_name_age", "last_mood": text})
#             return

#         # Name/age capture
#         if step == 'ask_name_age':
#             last_mood = user.get('last_mood', '')
            
#             msg = f"Ok cool! Showing options for '{last_mood}':" if user_language == 'en' else f"¡Perfecto! Buscando '{last_mood}':"
#             send_whatsapp_message(sender, msg)
            
#             parts = text.split()
#             raw_name = parts[0] if parts else "Friend"
#             clean_name = re.sub(r'[^a-zA-ZÀ-ÿ]', '', raw_name)
#             if not clean_name: 
#                 clean_name = "Friend"
            
#             age = "".join(filter(str.isdigit, text)) or "25"
            
#             update_user(conn, sender, {
#                 "name": clean_name, 
#                 "age": age, 
#                 "conversation_step": "ready"
#             })
            
#             text = last_mood 
#             ai_data = analyze_user_intent(text)
#             if not ai_data: 
#                 ai_data = {}
#             user_language = ai_data.get('user_language', 'en')
#             social_context = ai_data.get('social_context')
#             target_mood = ai_data.get('target_mood', 'chill')

#         # --- SEARCH ---
#         found_something = False
#         messages_to_send = []

#         # Check events
#         should_check_events = (
#             ai_data.get('date_range') or 
#             ai_data.get('specific_keywords') or 
#             ai_data.get('category') in ['event', 'concert', 'show', 'party']
#         )

#         if should_check_events:
#             events = smart_search(conn, 'events', ai_data)
            
#             if events:
#                 found_something = True
#                 intro = "Here are events:" if user_language == 'en' else "Aquí hay eventos:"
#                 messages_to_send.append({"type": "text", "content": intro})

#                 for e in events:
#                     try:
#                         jfy = generate_just_for_you(user_age, e.get('title', 'Event'), e.get('description', ''), e.get('mood', 'social'), social_context)
                        
#                         display_date = e.get('event_date', e.get('recurring_day', 'N/A'))
                        
#                         caption = (
#                             f"*{e.get('title', 'N/A')}*\n\n"
#                             f"📍 {e.get('location', 'N/A')}\n"
#                             f"🕒 {e.get('event_time', 'N/A')}\n"
#                             f"📅 {display_date}\n"
#                             f"🎵 {e.get('music_type', 'N/A')}\n"
#                             f"📝 {e.get('description', 'N/A')}\n\n"
#                             f"{jfy}"
#                         )
                        
#                         messages_to_send.append({"type": "text", "content": caption})
#                     except Exception as e_err:
#                         logger.error(f"Event processing error: {e_err}")
#                         continue

#         # Check businesses
#         should_check_businesses = (
#             not found_something or 
#             ai_data.get('category') in ['bar', 'restaurant', 'cafe', 'club'] or
#             social_context in ['date', 'friends']
#         )
        
#         if should_check_businesses:
#             businesses = smart_search(conn, 'businesses', ai_data)
            
#             if businesses:
#                 found_something = True
#                 intro = "Found these spots:" if user_language == 'en' else "Encontré estos lugares:"
#                 messages_to_send.append({"type": "text", "content": intro})
                
#                 for b in businesses:
#                     try:
#                         jfy = generate_just_for_you(user_age, b.get('name', 'Spot'), b.get('description', ''), target_mood, social_context)
                        
#                         msg = (
#                             f"*{b.get('name', 'N/A')}*\n"
#                             f"📍 {b.get('location', 'N/A')}\n\n"
#                             f"{b.get('description', 'N/A')}\n\n"
#                             f"{jfy}"
#                         )
#                         messages_to_send.append({"type": "text", "content": msg})
#                     except Exception as b_err:
#                         logger.error(f"Business processing error: {b_err}")
#                         continue

#         # Send messages
#         if found_something:
#             for msg in messages_to_send:
#                 send_whatsapp_message(sender, msg["content"])
            
#             closing = generate_closing_message(text, user_language)
#             send_whatsapp_message(sender, closing)
#         else:
#             # Expert fallback
#             logger.info("🎯 Using Expert Fallback")
#             fallback_text = ask_chatgpt_expert_fallback(text, ai_data, user_language)
#             send_whatsapp_message(sender, fallback_text)

#     except Exception as e:
#         logger.error(f"Process Error: {e}", exc_info=True)
#         send_whatsapp_message(sender, "Sorry, something went wrong. Please try again!")
#     finally:
#         if conn: 
#             postgreSQL_pool.putconn(conn)

# # --- WEBHOOK ---

# @app.route("/webhook", methods=["POST"])
# def twilio_webhook():
#     try:
#         incoming_msg = request.form.get('Body')
#         sender_id = request.form.get('From') 

#         if not sender_id or not incoming_msg:
#             logger.warning("Missing sender or message")
#             return "" 
        
#         logger.info(f"📩 Message from {sender_id}: {incoming_msg}")
        
#         resp = MessagingResponse()
#         thread = threading.Thread(
#             target=process_message_thread, 
#             args=(sender_id, incoming_msg)
#         )
#         thread.daemon = True  # Make thread daemon
#         thread.start()
        
#         return str(resp)
#     except Exception as e:
#         logger.error(f"Webhook Error: {e}", exc_info=True)
#         return "", 200  # Still return 200 to Twilio

# @app.route("/health", methods=["GET"])
# def health_check():
#     """Health check endpoint for Railway"""
#     return {"status": "healthy"}, 200

# if __name__ == "__main__":
#     port = int(os.environ.get("PORT", 5000))
#     logger.info(f"🚀 Starting on port {port}")
#     app.run(host="0.0.0.0", port=port)


import os
import logging
import psycopg2
import threading
import json
import re
from concurrent.futures import ThreadPoolExecutor
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta, date
from flask import Flask, request
import openai
from twilio.rest import Client as TwilioClient 
from twilio.twiml.messaging_response import MessagingResponse 
from dotenv import load_dotenv

# 1. Load Environment Variables
load_dotenv()

app = Flask(__name__)

# --- CONFIGURATION ---
DB_URI = os.getenv("DATABASE_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER") 

# Initialize Twilio Client
twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- GLOBAL THREAD POOL ---
executor = ThreadPoolExecutor(max_workers=3)

# --- DATABASE POOL ---
try:
    postgreSQL_pool = psycopg2.pool.SimpleConnectionPool(
        1, 10, DB_URI, cursor_factory=RealDictCursor, connect_timeout=10
    )
    logger.info("✅ Database Connection Pool Created")
except (Exception, psycopg2.DatabaseError) as error:
    logger.error(f"❌ Error connecting to PostgreSQL: {error}")

# ==============================================================================
# 🧠 AI & UTILS
# ==============================================================================

def analyze_user_intent(user_text):
    """Enhanced: Multi-language and context understanding"""
    today_str = date.today().strftime("%Y-%m-%d")
    weekday_str = date.today().strftime("%A")
    
    system_prompt = (
        f"Current Date: {today_str} ({weekday_str}). "
        "You are a multilingual AI that understands ALL languages. "
        "Analyze the user's intent to find events or businesses in Buenos Aires. "
        
        "EXTRACT (return JSON):\n"
        "1. 'is_greeting': boolean (true ONLY if just 'hi'/'hello'/'hola' with NO request)\n"
        "2. 'is_farewell': boolean (true if 'bye'/'goodbye'/'adiós'/'chau')\n"
        "3. 'date_range': {'start': 'YYYY-MM-DD', 'end': 'YYYY-MM-DD'} or null\n"
        "4. 'target_mood': string (romantic, chill, energetic, party)\n"
        "5. 'social_context': string ('date', 'friends', 'solo', 'family', 'business', null)\n"
        "6. 'category': string\n"
        "   - For PLACES: 'cafe', 'bar', 'restaurant', 'club', 'shop'\n"
        "   - For EVENTS: 'event', 'concert', 'show', 'party'\n"
        "   - For FOOD: 'food', 'restaurant' (if asking for specific food like chicken rolls)\n"
        "7. 'specific_keywords': List of SPECIFIC themes/genres\n"
        "   Examples: 'African music' → ['African', 'Afro']\n"
        "             'cafe' → ['cafe', 'coffee']\n"
        "             'chicken rolls' → ['chicken', 'food']\n"
        "8. 'user_language': detected language (en, es, pt, fr)\n"
        "9. 'out_of_scope': boolean\n"
        "   TRUE only for: electronics shopping, weather, jokes, technical help\n"
        "   FALSE for: food, cafes, bars, restaurants, shopping clothes, events\n"
        "Return STRICT JSON."
    )
    
    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt}, 
                {"role": "user", "content": user_text}
            ],
            temperature=0,
            timeout=10
        )
        content = response.choices[0].message.content.strip()
        data = json.loads(content)
        
        if not isinstance(data, dict): 
            return {}
        
        logger.info(f"🧠 AI Analysis: {data}")
        return data
        
    except Exception as e:
        logger.error(f"AI Intent Error: {e}")
        return {}

def generate_just_for_you(user_age, item_name, item_desc, item_mood, social_context=None):
    """Enhanced with social context"""
    try:
        context_msg = ""
        if social_context == 'date':
            context_msg = "Perfect for a romantic date."
        elif social_context == 'friends':
            context_msg = "Great for friends."
        
        prompt = (
            f"Write a 1-sentence recommendation for a {user_age} year old. "
            f"Venue: {item_name}. Vibe: {item_mood}. {context_msg} "
            "Start with '✨ Just for you:'. Be enthusiastic."
        )
        
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            timeout=5
        )
        return response.choices[0].message.content.replace('"', '')
    except Exception as e:
        logger.error(f"JFY Error: {e}")
        return f"✨ Just for you: This matches the {item_mood} vibe! {context_msg}"

def generate_closing_message(user_query, user_language='en'):
    """Multi-language closing"""
    try:
        lang_instruction = "Respond in Spanish." if user_language == 'es' else "Respond in English."
        
        prompt = (
            f"User query: '{user_query}'. I sent recommendations. "
            f"Write SHORT closing asking if they need more help. "
            f"Use 1 emoji. {lang_instruction}"
        )
        
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are Yara."}, 
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            timeout=5
        )
        return response.choices[0].message.content.replace('"', '')
    except Exception as e:
        logger.error(f"Closing Error: {e}")
        return "Need more help? 🎉" if user_language == 'en' else "¿Necesitas más ayuda? 🎉"

# --- DATABASE FUNCTIONS ---

def get_user(conn, phone):
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM public.users WHERE phone = %s", (phone,))
            return cur.fetchone()
    except Exception as e:
        logger.error(f"Get user error: {e}")
        return None

def create_user(conn, phone):
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO public.users (phone, conversation_step) "
                "VALUES (%s, 'welcome') ON CONFLICT (phone) DO NOTHING", 
                (phone,)
            )
            conn.commit()
            cur.execute("SELECT * FROM public.users WHERE phone = %s", (phone,))
            return cur.fetchone()
    except Exception as e:
        logger.error(f"Create user error: {e}")
        return None

def update_user(conn, phone, data):
    try:
        set_clause = ", ".join([f"{key} = %s" for key in data.keys()])
        values = list(data.values())
        values.append(phone)
        with conn.cursor() as cur:
            cur.execute(f"UPDATE public.users SET {set_clause} WHERE phone = %s", values)
            conn.commit()
    except Exception as e:
        logger.error(f"Update user error: {e}")

# --- SEARCH LOGIC ---

def build_search_query(table, ai_data, strictness_level):
    """Enhanced search with context"""
    query = f"SELECT * FROM public.{table} WHERE 1=1"
    args = []
    
    date_range = ai_data.get('date_range') or {}
    social_context = ai_data.get('social_context')
    
    search_terms = []
    
    if ai_data.get('specific_keywords'):
        search_terms.extend(ai_data.get('specific_keywords'))
    
    if ai_data.get('target_mood'):
        search_terms.append(ai_data.get('target_mood'))
    
    if social_context == 'date':
        search_terms.extend(['romantic', 'intimate', 'cozy'])
    elif social_context == 'friends':
        search_terms.extend(['social', 'casual'])
    
    cat = ai_data.get('category', '')
    if cat and len(cat) > 2:
        search_terms.append(cat)
    
    search_terms = list(set([t for t in search_terms if t and len(t) > 2]))
    
    logger.info(f"🔍 Search Terms: {search_terms}")

    # Date logic for events
    if table == 'events' and date_range:
        start = date_range.get('start')
        end = date_range.get('end')
        
        if start and end:
            try:
                start_obj = datetime.strptime(start, "%Y-%m-%d").date()
                end_obj = datetime.strptime(end, "%Y-%m-%d").date()
                
                days_in_range = []
                curr = start_obj
                while curr <= end_obj:
                    days_in_range.append(curr.strftime('%A'))
                    curr += timedelta(days=1)
                days_tuple = tuple(days_in_range) if len(days_in_range) > 1 else (days_in_range[0],)
                
                query += " AND ((event_date >= %s::date AND event_date <= %s::date) OR (recurring_day IN %s))"
                args.extend([start, end, days_tuple])
            except Exception as e:
                logger.error(f"Date parsing error: {e}")

    # Text search
    if search_terms:
        term_conditions = []
        for term in search_terms:
            term_wild = f"%{term}%"
            
            if table == 'events':
                clause = "(title ILIKE %s OR description ILIKE %s OR mood ILIKE %s OR music_type ILIKE %s OR location ILIKE %s)"
                term_conditions.append(clause)
                args.extend([term_wild] * 5)
            else:
                clause = "(name ILIKE %s OR description ILIKE %s OR location ILIKE %s OR type ILIKE %s)"
                term_conditions.append(clause)
                args.extend([term_wild] * 4)

        if term_conditions:
            join_operator = " AND " if strictness_level == 1 else " OR "
            query += f" AND ({join_operator.join(term_conditions)})"

    if table == 'events': 
        query += " ORDER BY event_date ASC LIMIT 5"
    else: 
        query += " LIMIT 5"
    
    return query, args

def smart_search(conn, table, ai_data):
    """Two-tier search"""
    try:
        # Strict search
        query, args = build_search_query(table, ai_data, 1)
        with conn.cursor() as cur:
            cur.execute(query, tuple(args))
            results = cur.fetchall()
            if results:
                logger.info(f"✅ Found {len(results)} (Strict)")
                return results

        # Loose search
        query, args = build_search_query(table, ai_data, 2)
        with conn.cursor() as cur:
            cur.execute(query, tuple(args))
            results = cur.fetchall()
            if results:
                logger.info(f"✅ Found {len(results)} (Loose)")
            return results if results else []
    except Exception as e:
        logger.error(f"Search error: {e}")
        return []

# --- TWILIO ---

def send_whatsapp_message(to, body, media_url=None):
    if not TWILIO_WHATSAPP_NUMBER: 
        return
    
    try:
        if media_url:
            twilio_client.messages.create(
                from_=TWILIO_WHATSAPP_NUMBER,
                to=to,
                body=body,
                media_url=media_url
            )
        else:
            twilio_client.messages.create(
                from_=TWILIO_WHATSAPP_NUMBER,
                to=to,
                body=body
            )
    except Exception as e:
        logger.error(f"❌ Twilio Error: {e}")

# --- EXPERT FALLBACK ---

def ask_chatgpt_expert_fallback(user_input, ai_data, user_language='en'):
    """Expert guide fallback"""
    
    category = ai_data.get('category')
    mood = ai_data.get('target_mood')
    social_context = ai_data.get('social_context')
    keywords = ai_data.get('specific_keywords', [])
    
    context_parts = []
    
    if social_context == 'date':
        context_parts.append("romantic spot for a date")
    elif social_context == 'friends':
        context_parts.append("hang out with friends")
    
    if mood:
        context_parts.append(f"{mood} vibe")
    
    if keywords:
        context_parts.append(f"interested in: {', '.join(keywords)}")
    
    if category:
        context_parts.append(f"looking for: {category}")
    
    context_description = ". ".join(context_parts) if context_parts else "looking for recommendations"
    
    lang_instruction = "\nRespond in Spanish." if user_language == 'es' else "\nRespond in English."
    
    expert_prompt = f"""You are Yara, a Buenos Aires expert guide. 

CONTEXT: {context_description}

Give 2-3 SPECIFIC place names in Buenos Aires with neighborhoods.
Format:
"[Intro]

🎯 [Place] in [Neighborhood]
[Why it's perfect]

[Closing]"

USER: "{user_input}"
{lang_instruction}"""

    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are Yara, Buenos Aires expert."}, 
                {"role": "user", "content": expert_prompt}
            ],
            temperature=0.8,
            timeout=10
        )
        
        return response.choices[0].message.content
        
    except Exception as e:
        logger.error(f"Fallback Error: {e}")
        return "I couldn't find matches. Can you give me more details?" if user_language == 'en' else "No encontré opciones. ¿Puedes darme más detalles?"

# --- MAIN PROCESS ---

def process_message_thread(sender, text):
    conn = None
    try:
        conn = postgreSQL_pool.getconn()
        if not conn:
            logger.error("Failed to get DB connection")
            send_whatsapp_message(sender, "Sorry, having technical issues. Please try again in a moment.")
            return
            
        user = get_user(conn, sender)

        # New user
        if not user:
            create_user(conn, sender)
            send_whatsapp_message(
                sender, 
                "Hey! Welcome to Yara ai , I’m your Buenos Aires guide for finding the best plans in the city ✨ what are you in the mood for?"
            )
            return

        step = user.get('conversation_step', 'welcome')
        user_age = user.get('age', '25')

        # Analyze intent
        ai_data = analyze_user_intent(text)
        
        if not ai_data or not isinstance(ai_data, dict): 
            ai_data = {}
        
        user_language = ai_data.get('user_language', 'en')
        social_context = ai_data.get('social_context')
        target_mood = ai_data.get('target_mood', 'chill')

        # Farewell check
        if ai_data.get('is_farewell'):
            farewell_msg = "Goodbye! Have a great time in Buenos Aires! 👋" if user_language == 'en' else "¡Adiós! ¡Que disfrutes Buenos Aires! 👋"
            send_whatsapp_message(sender, farewell_msg)
            return

        # Out of scope check (ONLY for truly out of scope things)
        if ai_data.get('out_of_scope'):
            msg = "Sorry, I only help with Buenos Aires recommendations. What would you like to do here?" if user_language == 'en' else "Lo siento, solo ayudo con recomendaciones de Buenos Aires. ¿Qué te gustaría hacer?"
            send_whatsapp_message(sender, msg)
            return

        # Greeting
        if ai_data.get('is_greeting') and step != 'ask_name_age':
            user_name = user.get('name', 'there')
            greeting = f"Hey {user_name}! What are you looking for?" if user_language == 'en' else f"¡Hola {user_name}! ¿Qué buscas?"
            send_whatsapp_message(sender, greeting)
            return

        # Onboarding
        if step == 'welcome':
            msg = "First, what's your name and age?" if user_language == 'en' else "Primero, ¿tu nombre y edad?"
            send_whatsapp_message(sender, msg)
            update_user(conn, sender, {"conversation_step": "ask_name_age", "last_mood": text})
            return

        # Name/age capture
        if step == 'ask_name_age':
            last_mood = user.get('last_mood', '')
            
            msg = f"Ok cool! Showing options for '{last_mood}':" if user_language == 'en' else f"¡Perfecto! Buscando '{last_mood}':"
            send_whatsapp_message(sender, msg)
            
            parts = text.split()
            raw_name = parts[0] if parts else "Friend"
            clean_name = re.sub(r'[^a-zA-ZÀ-ÿ]', '', raw_name)
            if not clean_name: 
                clean_name = "Friend"
            
            age = "".join(filter(str.isdigit, text)) or "25"
            
            update_user(conn, sender, {
                "name": clean_name, 
                "age": age, 
                "conversation_step": "ready"
            })
            
            text = last_mood 
            ai_data = analyze_user_intent(text)
            if not ai_data: 
                ai_data = {}
            user_language = ai_data.get('user_language', 'en')
            social_context = ai_data.get('social_context')
            target_mood = ai_data.get('target_mood', 'chill')

        # --- SMART SEARCH LOGIC ---
        found_something = False
        messages_to_send = []

        # Determine search priority
        category = ai_data.get('category', '')
        
        # PRIORITY 1: BUSINESSES (for cafes, bars, restaurants, food, shopping)
        should_check_businesses_first = category in ['cafe', 'bar', 'restaurant', 'club', 'shop', 'food']
        
        # PRIORITY 2: EVENTS (for events, concerts, shows, or date queries)
        should_check_events = (
            ai_data.get('date_range') or 
            ai_data.get('specific_keywords') or 
            category in ['event', 'concert', 'show', 'party', 'festival']
        )

        # Search businesses FIRST if user asks for cafes, bars, restaurants, food
        if should_check_businesses_first:
            logger.info("🔍 Prioritizing businesses search...")
            businesses = smart_search(conn, 'businesses', ai_data)
            
            if businesses:
                found_something = True
                intro = "Found these spots:" if user_language == 'en' else "Encontré estos lugares:"
                messages_to_send.append({"type": "text", "content": intro})
                
                for b in businesses:
                    try:
                        jfy = generate_just_for_you(user_age, b.get('name', 'Spot'), b.get('description', ''), target_mood, social_context)
                        
                        msg = (
                            f"*{b.get('name', 'N/A')}*\n"
                            f"📍 {b.get('location', 'N/A')}\n\n"
                            f"{b.get('description', 'N/A')}\n\n"
                            f"{jfy}"
                        )
                        messages_to_send.append({"type": "text", "content": msg})
                    except Exception as b_err:
                        logger.error(f"Business processing error: {b_err}")
                        continue

        # Search events if: no businesses found OR explicitly asking for events
        if (not found_something and should_check_events) or (should_check_events and not should_check_businesses_first):
            logger.info("🔍 Checking events...")
            events = smart_search(conn, 'events', ai_data)
            
            if events:
                found_something = True
                intro = "Here are events:" if user_language == 'en' else "Aquí hay eventos:"
                messages_to_send.append({"type": "text", "content": intro})

                for e in events:
                    try:
                        jfy = generate_just_for_you(user_age, e.get('title', 'Event'), e.get('description', ''), e.get('mood', 'social'), social_context)
                        
                        display_date = e.get('event_date', e.get('recurring_day', 'N/A'))
                        
                        caption = (
                            f"*{e.get('title', 'N/A')}*\n\n"
                            f"📍 {e.get('location', 'N/A')}\n"
                            f"🕒 {e.get('event_time', 'N/A')}\n"
                            f"📅 {display_date}\n"
                            f"🎵 {e.get('music_type', 'N/A')}\n"
                            f"📝 {e.get('description', 'N/A')}\n\n"
                            f"{jfy}"
                        )
                        
                        # FIX: Add image if available
                        image_url = e.get('image_url')
                        if image_url:
                            messages_to_send.append({"type": "media", "content": caption, "media_url": image_url})
                        else:
                            messages_to_send.append({"type": "text", "content": caption})
                    except Exception as e_err:
                        logger.error(f"Event processing error: {e_err}")
                        continue

        # If still nothing found, search the other table
        if not found_something:
            if should_check_businesses_first:
                # Already tried businesses, now try events
                logger.info("🔍 Fallback to events...")
                events = smart_search(conn, 'events', ai_data)
                
                if events:
                    found_something = True
                    intro = "Here are events:" if user_language == 'en' else "Aquí hay eventos:"
                    messages_to_send.append({"type": "text", "content": intro})

                    for e in events:
                        try:
                            jfy = generate_just_for_you(user_age, e.get('title', 'Event'), e.get('description', ''), e.get('mood', 'social'), social_context)
                            
                            display_date = e.get('event_date', e.get('recurring_day', 'N/A'))
                            
                            caption = (
                                f"*{e.get('title', 'N/A')}*\n\n"
                                f"📍 {e.get('location', 'N/A')}\n"
                                f"🕒 {e.get('event_time', 'N/A')}\n"
                                f"📅 {display_date}\n"
                                f"🎵 {e.get('music_type', 'N/A')}\n"
                                f"📝 {e.get('description', 'N/A')}\n\n"
                                f"{jfy}"
                            )
                            
                            image_url = e.get('image_url')
                            if image_url:
                                messages_to_send.append({"type": "media", "content": caption, "media_url": image_url})
                            else:
                                messages_to_send.append({"type": "text", "content": caption})
                        except Exception as e_err:
                            logger.error(f"Event processing error: {e_err}")
                            continue
            else:
                # Already tried events, now try businesses
                logger.info("🔍 Fallback to businesses...")
                businesses = smart_search(conn, 'businesses', ai_data)
                
                if businesses:
                    found_something = True
                    intro = "Found these spots:" if user_language == 'en' else "Encontré estos lugares:"
                    messages_to_send.append({"type": "text", "content": intro})
                    
                    for b in businesses:
                        try:
                            jfy = generate_just_for_you(user_age, b.get('name', 'Spot'), b.get('description', ''), target_mood, social_context)
                            
                            msg = (
                                f"*{b.get('name', 'N/A')}*\n"
                                f"📍 {b.get('location', 'N/A')}\n\n"
                                f"{b.get('description', 'N/A')}\n\n"
                                f"{jfy}"
                            )
                            messages_to_send.append({"type": "text", "content": msg})
                        except Exception as b_err:
                            logger.error(f"Business processing error: {b_err}")
                            continue

        # Send messages in correct order
        if found_something:
            for msg in messages_to_send:
                if msg["type"] == "media":
                    send_whatsapp_message(sender, msg["content"], media_url=msg["media_url"])
                else:
                    send_whatsapp_message(sender, msg["content"])
            
            closing = generate_closing_message(text, user_language)
            send_whatsapp_message(sender, closing)
        else:
            # Expert fallback
            logger.info("🎯 Using Expert Fallback")
            fallback_text = ask_chatgpt_expert_fallback(text, ai_data, user_language)
            send_whatsapp_message(sender, fallback_text)

    except Exception as e:
        logger.error(f"Process Error: {e}", exc_info=True)
        send_whatsapp_message(sender, "Sorry, something went wrong. Please try again!")
    finally:
        if conn: 
            postgreSQL_pool.putconn(conn)

# --- WEBHOOK ---

@app.route("/webhook", methods=["POST"])
def twilio_webhook():
    try:
        incoming_msg = request.form.get('Body')
        sender_id = request.form.get('From') 

        if not sender_id or not incoming_msg:
            logger.warning("Missing sender or message")
            return "" 
        
        logger.info(f"📩 Message from {sender_id}: {incoming_msg}")
        
        resp = MessagingResponse()
        thread = threading.Thread(
            target=process_message_thread, 
            args=(sender_id, incoming_msg)
        )
        thread.daemon = True
        thread.start()
        
        return str(resp)
    except Exception as e:
        logger.error(f"Webhook Error: {e}", exc_info=True)
        return "", 200

@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint for Railway"""
    return {"status": "healthy"}, 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"🚀 Starting on port {port}")
    app.run(host="0.0.0.0", port=port)