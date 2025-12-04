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

#language description ijn user kanguafe
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
#     ENHANCED: Now understands ALL languages including Telugu, Hebrew, Arabic, etc.
#     Default language is ENGLISH unless detected otherwise.
#     """
#     today_str = date.today().strftime("%Y-%m-%d")
#     weekday_str = date.today().strftime("%A")
    
#     system_prompt = (
#         f"Current Date: {today_str} ({weekday_str}). "
#         "You are a multilingual AI that understands ALL languages including English, Spanish, Portuguese, French, German, Italian, Russian, Arabic, Hebrew, Hindi, Telugu, Tamil, Korean, Japanese, Chinese, and ANY other language. "
#         "Analyze the user's intent to find events or businesses in Buenos Aires. "
        
#         "EXTRACT THE FOLLOWING (return as JSON):\n"
        
#         "1. 'is_greeting': boolean (true ONLY if user just says 'hi'/'hello'/'hola'/'namaste' with NO request)\n"
        
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
        
#         "7. 'user_language': detected language code - IMPORTANT RULES:\n"
#         "   - Use ISO 639-1 codes: en (English - DEFAULT), es (Spanish), pt (Portuguese), fr (French), de (German), it (Italian), ru (Russian), ar (Arabic), he (Hebrew), hi (Hindi), te (Telugu), ta (Tamil), ko (Korean), ja (Japanese), zh (Chinese)\n"
#         "   - DEFAULT to 'en' if uncertain\n"
#         "   - Examples: Telugu text → 'te', Hebrew text → 'he', Arabic text → 'ar'\n"
#         "   - If mixed languages or unclear, return 'en'\n"
        
#         "EXAMPLES:\n"
#         "User: 'I want a chill bar with friends'\n"
#         "→ {social_context: 'friends', target_mood: 'chill', category: 'bar', user_language: 'en'}\n"
        
#         "User: 'Need a romantic place for date night'\n"
#         "→ {social_context: 'date', target_mood: 'romantic', category: 'restaurant', user_language: 'en'}\n"
        
#         "User: 'నాకు ఈ వారాంతంలో జాజ్ ఈవెంట్ కావాలి' (Telugu)\n"
#         "→ {specific_keywords: ['Jazz'], date_range: {...}, category: 'event', user_language: 'te'}\n"
        
#         "User: 'אני רוצה בר רומנטי' (Hebrew)\n"
#         "→ {target_mood: 'romantic', category: 'bar', user_language: 'he'}\n"
        
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
#             return {"user_language": "en"}
        
#         # Ensure default language is English if not detected
#         if not data.get('user_language') or data.get('user_language') == 'unknown':
#             data['user_language'] = 'en'
        
#         logger.info(f"🧠 AI Analysis: {data}")
#         return data
        
#     except Exception as e:
#         logger.error(f"AI Intent Error: {e}")
#         return {"user_language": "en"}

# def generate_just_for_you(user_age, item_name, item_desc, item_mood, social_context=None, user_language='en'):
#     """
#     Enhanced: Now generates personalized recommendations in user's detected language
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
        
#         # Language instruction
#         lang_instruction = f"Respond in the language code: {user_language}. "
#         if user_language == 'te':
#             lang_instruction += "Use Telugu script and language."
#         elif user_language == 'he':
#             lang_instruction += "Use Hebrew script and language."
#         elif user_language == 'ar':
#             lang_instruction += "Use Arabic script and language."
#         elif user_language == 'hi':
#             lang_instruction += "Use Hindi script and language."
#         elif user_language == 'es':
#             lang_instruction += "Use Spanish language."
#         elif user_language == 'pt':
#             lang_instruction += "Use Portuguese language."
#         elif user_language == 'fr':
#             lang_instruction += "Use French language."
#         else:
#             lang_instruction += "Use English language."
        
#         prompt = (
#             f"{lang_instruction} "
#             f"Write a 1-sentence recommendation for a {user_age} year old. "
#             f"Venue: {item_name}. Vibe: {item_mood}. {context_msg} "
#             "Start with '✨ Just for you:' or equivalent in the target language. Be enthusiastic and specific."
#         )
        
#         response = openai.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[{"role": "user", "content": prompt}],
#             temperature=0.7,
#             timeout=5
#         )
#         return response.choices[0].message.content.replace('"', '')
#     except Exception as e:
#         logger.error(f"Just for you error: {e}")
#         # Fallback based on language
#         if user_language == 'te':
#             return f"✨ మీ కోసం: ఇది {item_mood} వైబ్‌తో సరిపోతుంది! {context_msg}"
#         elif user_language == 'he':
#             return f"✨ בשבילך: זה מתאים ל{item_mood} אווירה! {context_msg}"
#         elif user_language == 'ar':
#             return f"✨ لك خصيصاً: هذا يناسب الأجواء {item_mood}! {context_msg}"
#         elif user_language == 'es':
#             return f"✨ Just for you: ¡Esto coincide con el ambiente {item_mood}! {context_msg}"
#         else:
#             return f"✨ Just for you: This matches the {item_mood} vibe! {context_msg}"

# def translate_text(text, target_language):
#     """
#     NEW FUNCTION: Translates any text (descriptions, titles) to user's language
#     """
#     if target_language == 'en' or not text:
#         return text
    
#     try:
#         # Language name mapping
#         lang_map = {
#             'es': 'Spanish',
#             'pt': 'Portuguese',
#             'fr': 'French',
#             'de': 'German',
#             'it': 'Italian',
#             'ru': 'Russian',
#             'ar': 'Arabic',
#             'he': 'Hebrew',
#             'hi': 'Hindi',
#             'te': 'Telugu',
#             'ta': 'Tamil',
#             'ko': 'Korean',
#             'ja': 'Japanese',
#             'zh': 'Chinese'
#         }
        
#         lang_name = lang_map.get(target_language, 'English')
        
#         response = openai.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[
#                 {"role": "system", "content": f"Translate the following text to {lang_name}. Maintain the original tone and meaning. Only return the translation, nothing else."},
#                 {"role": "user", "content": text}
#             ],
#             temperature=0.3,
#             timeout=5
#         )
        
#         translated = response.choices[0].message.content.strip()
#         return translated if translated else text
        
#     except Exception as e:
#         logger.error(f"Translation error: {e}")
#         return text

# def generate_closing_message(user_query, user_language='en'):
#     """
#     Enhanced: Multi-language closing messages with proper default to English
#     """
#     try:
#         lang_instruction = ""
#         if user_language == 'te':
#             lang_instruction = "Respond in Telugu using Telugu script."
#         elif user_language == 'he':
#             lang_instruction = "Respond in Hebrew using Hebrew script."
#         elif user_language == 'ar':
#             lang_instruction = "Respond in Arabic using Arabic script."
#         elif user_language == 'hi':
#             lang_instruction = "Respond in Hindi using Devanagari script."
#         elif user_language == 'es':
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
#             timeout=4
#         )
#         return response.choices[0].message.content.replace('"', '')
#     except:
#         # Fallback based on language
#         if user_language == 'te':
#             return "మరిన్ని సూచనలు కావాలా? 🎉"
#         elif user_language == 'he':
#             return "צריך עוד המלצות? 🎉"
#         elif user_language == 'ar':
#             return "هل تحتاج المزيد من الاقتراحات؟ 🎉"
#         elif user_language == 'es':
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
#                 # Search: Name, Description, Location, Type
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
#     🌟 ENHANCED: Responds in user's detected language (including Telugu, Hebrew, etc.)
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
    
#     # Language instruction - ENHANCED for all languages
#     lang_instruction = ""
#     if user_language == 'te':
#         lang_instruction = "\n\nCRITICAL: Respond ENTIRELY in Telugu using Telugu script (తెలుగు). All place names, descriptions, and text must be in Telugu."
#     elif user_language == 'he':
#         lang_instruction = "\n\nCRITICAL: Respond ENTIRELY in Hebrew using Hebrew script (עברית). All place names, descriptions, and text must be in Hebrew."
#     elif user_language == 'ar':
#         lang_instruction = "\n\nCRITICAL: Respond ENTIRELY in Arabic using Arabic script (العربية). All place names, descriptions, and text must be in Arabic."
#     elif user_language == 'hi':
#         lang_instruction = "\n\nCRITICAL: Respond ENTIRELY in Hindi using Devanagari script (हिन्दी). All place names, descriptions, and text must be in Hindi."
#     elif user_language == 'es':
#         lang_instruction = "\n\nIMPORTANT: Respond in Spanish."
#     elif user_language == 'pt':
#         lang_instruction = "\n\nIMPORTANT: Respond in Portuguese."
#     elif user_language == 'fr':
#         lang_instruction = "\n\nIMPORTANT: Respond in French."
#     elif user_language == 'de':
#         lang_instruction = "\n\nIMPORTANT: Respond in German."
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
#             timeout=10
#         )
        
#         expert_response = response.choices[0].message.content
#         logger.info(f"🎯 Expert Fallback Response Generated in {user_language}")
#         return expert_response
        
#     except Exception as e:
#         logger.error(f"Fallback Error: {e}")
        
#         # Last resort fallback in user's language
#         if user_language == 'te':
#             return "క్షమించండి, నా డేటాబేస్‌లో నిర్దిష్ట ఎంపికలు కనిపించలేదు, కానీ బ్యూనస్ ఎయిర్స్‌లో చాలా గొప్ప ప్రదేశాలు ఉన్నాయి! మీరు మరిన్ని వివరాలు ఇవ్వగలరా?"
#         elif user_language == 'he':
#             return "מצטער, לא מצאתי אפשרויות ספציפיות במסד הנתונים שלי, אבל יש המון מקומות נהדרים בבואנוס איירס! תוכל לתת לי עוד פרטים על מה שאתה מחפש?"
#         elif user_language == 'ar':
#             return "آسف، لم أجد خيارات محددة في قاعدة البيانات الخاصة بي، ولكن هناك الكثير من الأماكن الرائعة في بوينس آيرس! هل يمكنك إعطائي المزيد من التفاصيل حول ما تبحث عنه؟"
#         elif user_language == 'es':
#             return "Hmm, no encontré opciones específicas en mi base de datos, pero hay muchos lugares geniales en Buenos Aires. ¿Puedes darme más detalles sobre lo que buscas?"
#         else:
#             return "I couldn't find specific matches in my database, but Buenos Aires has tons of great spots! Can you give me more details about what you're looking for?"

# # ==============================================================================
# # ⚙️ MAIN PROCESS - ENHANCED WITH TRANSLATION
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

#         # 2. ANALYZE INTENT (Multi-language support - DEFAULT ENGLISH)
#         future_ai = executor.submit(analyze_user_intent, text)
#         ai_data = future_ai.result()
        
#         if not ai_data or not isinstance(ai_data, dict): 
#             ai_data = {"user_language": "en"}
        
#         user_language = ai_data.get('user_language', 'en')
#         social_context = ai_data.get('social_context')

#         logger.info(f"🌍 Detected Language: {user_language}")

#         # 3. GREETING CHECK
#         if ai_data.get('is_greeting') and step != 'ask_name_age':
#             user_name = user.get('name')
#             greeting_name = user_name if user_name else "there"
            
#             # Translate greeting based on detected language
#             if user_language == 'te':
#                 greeting = f"నమస్కారం {greeting_name}! మీరు ఈరోజు ఏమి వెతుకుతున్నారు?"
#             elif user_language == 'he':
#                 greeting = f"שלום {greeting_name}! מה אתה מחפש היום?"
#             elif user_language == 'ar':
#                 greeting = f"مرحباً {greeting_name}! ماذا تبحث اليوم؟"
#             elif user_language == 'es':
#                 greeting = f"¡Hola {greeting_name}! ¿Qué estás buscando hoy?"
#             elif user_language == 'pt':
#                 greeting = f"Olá {greeting_name}! O que você está procurando hoje?"
#             else:
#                 greeting = f"Hey {greeting_name}! What are you looking for today?"
            
#             send_whatsapp_message(sender, greeting)
#             return

#         # 4. ONBOARDING
#         if step == 'welcome':
#             if user_language == 'te':
#                 onboarding_msg = "మొదట, మీకు ఉత్తమ సూచనలు ఇవ్వడానికి, మీ పేరు మరియు వయస్సు ఏమిటి?"
#             elif user_language == 'he':
#                 onboarding_msg = "קודם כל, כדי לתת לך את ההמלצות הטובות ביותר, מה שמך וגילך?"
#             elif user_language == 'ar':
#                 onboarding_msg = "أولاً، لإعطائك أفضل التوصيات، ما هو اسمك وعمرك؟"
#             elif user_language == 'es':
#                 onboarding_msg = "Primero, para darte las mejores recomendaciones, ¿cuál es tu nombre y edad?"
#             elif user_language == 'pt':
#                 onboarding_msg = "Primeiro, para te dar as melhores recomendações, qual é o seu nome e idade?"
#             else:
#                 onboarding_msg = "First, to give you the best personalized recommendations, what's your name and age?"
            
#             send_whatsapp_message(sender, onboarding_msg)
#             update_user(conn, sender, {"conversation_step": "ask_name_age", "last_mood": text})
#             return

#         # 5. NAME/AGE CAPTURE
#         if step == 'ask_name_age':
#             last_mood = user.get('last_mood')
            
#             if user_language == 'te':
#                 confirmation_msg = f"సరే! '{last_mood}' కోసం ఎంపికలు చూపిస్తున్నాను:"
#             elif user_language == 'he':
#                 confirmation_msg = f"מעולה! מראה אפשרויות עבור '{last_mood}':"
#             elif user_language == 'ar':
#                 confirmation_msg = f"رائع! عرض الخيارات لـ '{last_mood}':"
#             elif user_language == 'es':
#                 confirmation_msg = f"¡Perfecto! Buscando opciones para '{last_mood}':"
#             else:
#                 confirmation_msg = f"Ok cool! Showing options for '{last_mood}':"
            
#             send_whatsapp_message(sender, confirmation_msg)
            
#             parts = text.split()
#             raw_name = parts[0] if parts else "Friend"
#             clean_name = re.sub(r'[^a-zA-ZÀ-ÿ\u0900-\u097F\u0590-\u05FF\u0600-\u06FF\u0C00-\u0C7F]', '', raw_name)  # Support Telugu, Hebrew, Arabic
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
#                 ai_data = {"user_language": "en"}
#             user_language = ai_data.get('user_language', 'en')
#             social_context = ai_data.get('social_context')

#         # --- SMART SEARCH LOGIC ---
#         found_something = False

#         # PRIORITY 1: EVENTS
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
                
#                 # Translate intro message
#                 if start_date:
#                     if user_language == 'te':
#                         intro = f"{start_date} చుట్టూ జరుగుతున్నది ఇదే:"
#                     elif user_language == 'he':
#                         intro = f"הנה מה קורה בסביבות {start_date}:"
#                     elif user_language == 'ar':
#                         intro = f"إليك ما يحدث حول {start_date}:"
#                     elif user_language == 'es':
#                         intro = f"Esto es lo que pasa alrededor del {start_date}:"
#                     else:
#                         intro = f"Here's what's happening around {start_date}:"
#                 else:
#                     if user_language == 'te':
#                         intro = "మీ వైబ్‌తో సరిపోయే కొన్ని ఈవెంట్‌లు ఇక్కడ ఉన్నాయి:"
#                     elif user_language == 'he':
#                         intro = "הנה כמה אירועים שמתאימים לאווירה שלך:"
#                     elif user_language == 'ar':
#                         intro = "إليك بعض الأحداث التي تتناسب مع أجوائك:"
#                     elif user_language == 'es':
#                         intro = "Aquí hay algunos eventos que coinciden con tu vibra:"
#                     else:
#                         intro = "Here are some events matching your vibe:"
                
#                 send_whatsapp_message(sender, intro)

#                 for e in events:
#                     # Generate personalized recommendation in user's language
#                     future_jfy = executor.submit(
#                         generate_just_for_you, 
#                         user_age, 
#                         e['title'], 
#                         e['description'], 
#                         e.get('mood', 'social'),
#                         social_context,
#                         user_language
#                     )
                    
#                     # Translate event details
#                     future_title = executor.submit(translate_text, e.get('title'), user_language)
#                     future_desc = executor.submit(translate_text, e.get('description'), user_language)
#                     future_location = executor.submit(translate_text, e.get('location'), user_language)
#                     future_music = executor.submit(translate_text, e.get('music_type'), user_language)
                    
#                     just_for_you = future_jfy.result()
#                     translated_title = future_title.result()
#                     translated_desc = future_desc.result()
#                     translated_location = future_location.result()
#                     translated_music = future_music.result()
                    
#                     display_date = e.get('event_date') if e.get('event_date') else f"Every {e.get('recurring_day')}"
                    
#                     caption = (
#                         f"*{translated_title}*\n\n"
#                         f"📍 {translated_location}\n"
#                         f"🕒 {e.get('event_time')}\n"
#                         f"📅 {display_date}\n"
#                         f"🎵 {translated_music}\n"
#                         f"📝 {translated_desc}\n"
#                         f"📸 {e.get('instagram_link')}\n\n"
#                         f"{just_for_you}"
#                     )
                    
#                     # Send with image
#                     if e.get('image_url'): 
#                         send_whatsapp_message(sender, caption, media_url=e.get('image_url'))
#                     else: 
#                         send_whatsapp_message(sender, caption)

#         # PRIORITY 2: BUSINESSES
#         should_check_businesses = (
#             not found_something or 
#             ai_data.get('category') in ['bar', 'restaurant', 'cafe', 'club', 'shop', 'museum'] or
#             social_context in ['date', 'friends', 'solo']
#         )
        
#         if should_check_businesses:
#             businesses = smart_search(conn, 'businesses', ai_data)
            
#             if businesses:
#                 found_something = True
                
#                 # Translate intro
#                 if user_language == 'te':
#                     intro = "మీ కోసం ఈ స్థలాలను కనుగొన్నాను:"
#                 elif user_language == 'he':
#                     intro = "מצאתי את המקומות האלה בשבילך:"
#                 elif user_language == 'ar':
#                     intro = "وجدت هذه الأماكن لك:"
#                 elif user_language == 'es':
#                     intro = "Encontré estos lugares para ti:"
#                 else:
#                     intro = "Found these spots for you:"
                
#                 send_whatsapp_message(sender, intro)
                
#                 for b in businesses:
#                     # Generate personalized recommendation in user's language
#                     future_jfy = executor.submit(
#                         generate_just_for_you, 
#                         user_age, 
#                         b['name'], 
#                         b['description'], 
#                         ai_data.get('target_mood') or 'chill',
#                         social_context,
#                         user_language
#                     )
                    
#                     # Translate business details
#                     future_name = executor.submit(translate_text, b.get('name'), user_language)
#                     future_desc = executor.submit(translate_text, b.get('description'), user_language)
#                     future_location = executor.submit(translate_text, b.get('location'), user_language)
                    
#                     just_for_you = future_jfy.result()
#                     translated_name = future_name.result()
#                     translated_desc = future_desc.result()
#                     translated_location = future_location.result()
                    
#                     msg = (
#                         f"*{translated_name}*\n"
#                         f"📍 {translated_location}\n\n"
#                         f"{translated_desc}\n\n"
#                         f"📸 {b.get('instagram_link')}\n\n"
#                         f"{just_for_you}"
#                     )
                    
#                     # Send with image if available
#                     if b.get('image_url'):
#                         send_whatsapp_message(sender, msg, media_url=b.get('image_url'))
#                     else:
#                         send_whatsapp_message(sender, msg)

#         # RESULT HANDLING
#         if found_something:
#             closing = generate_closing_message(text, user_language)
#             send_whatsapp_message(sender, closing)
#         else:
#             # 🎯 ENHANCED EXPERT FALLBACK IN USER'S LANGUAGE
#             logger.info(f"🎯 No database matches - Using Expert Fallback in {user_language}")
#             fallback_text = ask_chatgpt_expert_fallback(text, ai_data, user_language)
#             send_whatsapp_message(sender, fallback_text)

#     except Exception as e:
#         logger.error(f"Logic Error: {e}", exc_info=True)
        
#         # Error message in user's language
#         if user_language == 'te':
#             error_msg = "క్షమించండి, ఏదో తప్పు జరిగింది. మళ్ళీ ప్రయత్నిద్దాం - మీరు ఏమి వెతుకుతున్నారు?"
#         elif user_language == 'he':
#             error_msg = "מצטער, משהו השתבש. בוא ננסה שוב - מה אתה מחפש?"
#         elif user_language == 'ar':
#             error_msg = "آسف، حدث خطأ ما. دعنا نحاول مرة أخرى - ماذا تبحث؟"
#         elif user_language == 'es':
#             error_msg = "Lo siento, algo salió mal. Intentemos de nuevo - ¿qué estás buscando?"
#         else:
#             error_msg = "Sorry, something went wrong. Let me try again - what are you looking for?"
        
#         send_whatsapp_message(sender, error_msg)
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
#     print("🚀 Twilio WhatsApp Bot Starting...")
#     print("✨ Enhanced Features:")
#     print("   - Multi-language Support (English DEFAULT)")
#     print("   - Supports: Telugu, Hebrew, Arabic, Hindi, Spanish, Portuguese, French, German, Italian, and more")
#     print("   - Auto-translation of event/business descriptions")
#     print("   - Personalized recommendations in user's language")
#     print("   - Images included with all recommendations")
#     app.run(port=5000)


# language detect artistic ecvery oay herr 
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
#     UPDATED: Now includes 'inferred_keywords' for smarter, abstract searches.
#     """
#     today_str = date.today().strftime("%Y-%m-%d")
#     weekday_str = date.today().strftime("%A")
    
#     system_prompt = (
#         f"Current Date: {today_str} ({weekday_str}). "
#         "You are a multilingual AI that understands ALL languages. "
#         "Your job is to analyze a user's request for events or businesses in Buenos Aires and extract structured data."
        
#         "EXTRACT THE FOLLOWING (return as JSON):\n"
        
#         "1. 'is_greeting': boolean (true ONLY for simple greetings with NO other request)\n"
        
#         "2. 'date_range': {'start': 'YYYY-MM-DD', 'end': 'YYYY-MM-DD'} or null\n"
        
#         "3. 'target_mood': string (romantic, chill, energetic, party, relaxed, upscale, casual)\n"
        
#         "4. 'social_context': string (date, friends, solo, family, business)\n"
        
#         "5. 'category': string (event, concert, show, bar, restaurant, cafe, etc.)\n"
        
#         "6. 'specific_keywords': List of DIRECT and SPECIFIC keywords from the user's text. "
#         "   - Examples: 'Salsa', 'Techno', 'Jazz', 'Rooftop', 'Live music'.\n"
        
#         "7. 'user_language': detected ISO 639-1 language code (en, es, te, he, ar, etc.). Default to 'en' if uncertain.\n"

#         # --- THIS IS THE NEW, INTELLIGENT PART ---
#         "8. 'inferred_keywords': List of related, searchable keywords if the user's request is abstract. "
#         "   - If the user asks for 'artistic' or 'cultural' things, infer related concrete terms.\n"
#         "   - If the user's request is already specific (e.g., 'techno'), this can be null.\n"
#         "   - Examples:\n"
#         "     * User says 'artistic events' → inferred_keywords: ['art', 'gallery', 'exhibition', 'museum', 'theatre', 'performance', 'cultural']\n"
#         "     * User says 'something intellectual' → inferred_keywords: ['lecture', 'talk', 'book', 'museum', 'cinema', 'art']\n"
#         "     * User says 'a place with a nice view' → inferred_keywords: ['rooftop', 'terrace', 'view', 'balcony']\n"
        
#         "EXAMPLES:\n"
#         "User: 'I want a chill bar with friends'\n"
#         "→ {social_context: 'friends', target_mood: 'chill', category: 'bar', user_language: 'en'}\n"
        
#         "User: 'artistic events this weekend'\n"
#         "→ {category: 'event', date_range: {...}, user_language: 'en', inferred_keywords: ['art', 'gallery', 'exhibition', 'museum', 'theatre', 'performance', 'cultural']}\n"
        
#         "User: 'Techno party tonight'\n"
#         "→ {category: 'party', date_range: {...}, specific_keywords: ['Techno', 'Electronic'], user_language: 'en'}\n"
        
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
#             return {"user_language": "en"}
        
#         if not data.get('user_language') or data.get('user_language') == 'unknown':
#             data['user_language'] = 'en'
        
#         logger.info(f"🧠 AI Analysis: {data}")
#         return data
        
#     except Exception as e:
#         logger.error(f"AI Intent Error: {e}")
#         return {"user_language": "en"}

# # (The other functions like generate_just_for_you, translate_text, etc., are UNCHANGED)
# def generate_just_for_you(user_age, item_name, item_desc, item_mood, social_context=None, user_language='en'):
#     """
#     Enhanced: Now generates personalized recommendations in user's detected language
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
        
#         # Language instruction
#         lang_instruction = f"Respond in the language code: {user_language}. "
#         if user_language == 'te':
#             lang_instruction += "Use Telugu script and language."
#         elif user_language == 'he':
#             lang_instruction += "Use Hebrew script and language."
#         elif user_language == 'ar':
#             lang_instruction += "Use Arabic script and language."
#         elif user_language == 'hi':
#             lang_instruction += "Use Hindi script and language."
#         elif user_language == 'es':
#             lang_instruction += "Use Spanish language."
#         elif user_language == 'pt':
#             lang_instruction += "Use Portuguese language."
#         elif user_language == 'fr':
#             lang_instruction += "Use French language."
#         else:
#             lang_instruction += "Use English language."
        
#         prompt = (
#             f"{lang_instruction} "
#             f"Write a 1-sentence recommendation for a {user_age} year old. "
#             f"Venue: {item_name}. Vibe: {item_mood}. {context_msg} "
#             "Start with '✨ Just for you:' or equivalent in the target language. Be enthusiastic and specific."
#         )
        
#         response = openai.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[{"role": "user", "content": prompt}],
#             temperature=0.7,
#             timeout=5
#         )
#         return response.choices[0].message.content.replace('"', '')
#     except Exception as e:
#         logger.error(f"Just for you error: {e}")
#         # Fallback based on language
#         if user_language == 'te':
#             return f"✨ మీ కోసం: ఇది {item_mood} వైబ్‌తో సరిపోతుంది! {context_msg}"
#         elif user_language == 'he':
#             return f"✨ בשבילך: זה מתאים ל{item_mood} אווירה! {context_msg}"
#         elif user_language == 'ar':
#             return f"✨ لك خصيصاً: هذا يناسب الأجواء {item_mood}! {context_msg}"
#         elif user_language == 'es':
#             return f"✨ Just for you: ¡Esto coincide con el ambiente {item_mood}! {context_msg}"
#         else:
#             return f"✨ Just for you: This matches the {item_mood} vibe! {context_msg}"

# def translate_text(text, target_language):
#     if target_language == 'en' or not text:
#         return text
    
#     try:
#         lang_map = {
#             'es': 'Spanish', 'pt': 'Portuguese', 'fr': 'French', 'de': 'German', 
#             'it': 'Italian', 'ru': 'Russian', 'ar': 'Arabic', 'he': 'Hebrew', 
#             'hi': 'Hindi', 'te': 'Telugu', 'ta': 'Tamil', 'ko': 'Korean', 
#             'ja': 'Japanese', 'zh': 'Chinese'
#         }
#         lang_name = lang_map.get(target_language, 'English')
        
#         response = openai.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[
#                 {"role": "system", "content": f"Translate the following text to {lang_name}. Maintain original tone. Only return the translation."},
#                 {"role": "user", "content": text}
#             ],
#             temperature=0.3,
#             timeout=5
#         )
#         translated = response.choices[0].message.content.strip()
#         return translated if translated else text
#     except Exception as e:
#         logger.error(f"Translation error: {e}")
#         return text

# def generate_closing_message(user_query, user_language='en'):
#     try:
#         # Simplified language instruction
#         lang_instruction_map = {
#             'te': "Respond in Telugu using Telugu script.", 'he': "Respond in Hebrew using Hebrew script.",
#             'ar': "Respond in Arabic using Arabic script.", 'hi': "Respond in Hindi using Devanagari script.",
#             'es': "Respond in Spanish.", 'pt': "Respond in Portuguese.", 'fr': "Respond in French."
#         }
#         lang_instruction = lang_instruction_map.get(user_language, "Respond in English.")
        
#         prompt = (
#             f"User query: '{user_query}'. I sent recommendations. "
#             f"Write a SHORT closing message asking if they want more suggestions. "
#             f"Use 1 emoji. Be friendly. {lang_instruction}"
#         )
        
#         response = openai.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[{"role": "system", "content": "You are Yara, a friendly Buenos Aires guide.you know evetu thing"}, {"role": "user", "content": prompt}],
#             temperature=0.7,
#             timeout=4
#         )
#         return response.choices[0].message.content.replace('"', '')
#     except:
#         # Fallback messages
#         fallback_map = {
#             'te': "మరిన్ని సూచనలు కావాలా? 🎉", 'he': "צריך עוד המלצות? 🎉",
#             'ar': "هل تحتاج المزيد من الاقتراحات؟ 🎉", 'es': "¿Te gustaría más sugerencias? 🎉",
#             'pt': "Gostaria de mais sugestões? 🎉"
#         }
#         return fallback_map.get(user_language, "Need more suggestions? 🎉")

# # --- DATABASE FUNCTIONS (UNCHANGED) ---

# def get_user(conn, phone):
#     with conn.cursor() as cur:
#         cur.execute("SELECT * FROM public.users WHERE phone = %s", (phone,))
#         return cur.fetchone()

# def create_user(conn, phone):
#     with conn.cursor() as cur:
#         cur.execute(
#             "INSERT INTO public.users (phone, conversation_step) VALUES (%s, 'welcome') ON CONFLICT (phone) DO NOTHING", (phone,)
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
#     UPDATED: Now includes 'inferred_keywords' for intelligent searching.
#     """
#     query = f"SELECT * FROM public.{table} WHERE 1=1"
#     args = []
    
#     date_range = ai_data.get('date_range') or {}
#     social_context = ai_data.get('social_context')
    
#     # 1. Build search terms from ALL context
#     search_terms = []
    
#     # Add direct keywords
#     if ai_data.get('specific_keywords'):
#         search_terms.extend(ai_data.get('specific_keywords'))

#     # --- THIS IS THE NEW, INTELLIGENT PART ---
#     # Add inferred keywords from abstract requests
#     if ai_data.get('inferred_keywords'):
#         search_terms.extend(ai_data.get('inferred_keywords'))
    
#     # Add mood
#     if ai_data.get('target_mood'):
#         search_terms.append(ai_data.get('target_mood'))
    
#     # Add social context keywords
#     if social_context == 'date':
#         search_terms.extend(['romantic', 'intimate', 'cozy'])
#     elif social_context == 'friends':
#         search_terms.extend(['social', 'group', 'casual'])
    
#     # Add category if specific
#     cat = ai_data.get('category', '')
#     if cat and len(cat) > 3 and cat.lower() not in ['event', 'party', 'show', 'place', 'spot']:
#         search_terms.append(cat)
    
#     # Clean and deduplicate
#     search_terms = list(set([t for t in search_terms if t and len(t) > 2]))
    
#     logger.info(f"🔍 Search Terms (Level {strictness_level}): {search_terms}")

#     # --- DATE LOGIC (for events) ---
#     if table == 'events' and date_range:
#         start, end = date_range.get('start'), date_range.get('end')
#         if start and end:
#             start_obj = datetime.strptime(start, "%Y-%m-%d").date()
#             end_obj = datetime.strptime(end, "%Y-%m-%d").date()
#             days_in_range = [ (start_obj + timedelta(days=i)).strftime('%A') for i in range((end_obj - start_obj).days + 1) ]
#             days_tuple = tuple(set(days_in_range))
#             query += " AND ((event_date >= %s::date AND event_date <= %s::date) OR (recurring_day = ANY(%s)))"
#             args.extend([start, end, list(days_tuple)])

#     # --- TEXT SEARCH LOGIC ---
#     if search_terms:
#         term_conditions = [f"(title ILIKE %s OR description ILIKE %s OR mood ILIKE %s OR music_type ILIKE %s OR location ILIKE %s)" for _ in search_terms] if table == 'events' else [f"(name ILIKE %s OR description ILIKE %s OR location ILIKE %s OR type ILIKE %s)" for _ in search_terms]
        
#         for term in search_terms:
#             term_wild = f"%{term}%"
#             args.extend([term_wild] * (5 if table == 'events' else 4))
        
#         join_operator = " AND " if strictness_level == 1 else " OR "
#         query += f" AND ({join_operator.join(term_conditions)})"

#     # Order and limit
#     query += " ORDER BY event_date ASC LIMIT 5" if table == 'events' else " LIMIT 5"

#     logger.info(f"📊 SQL Query: {query[:200]}...")
#     logger.info(f"📊 Args: {args}")
    
#     return query, args


# # (The other functions like smart_search, Twilio utils, fallbacks, and the main process are UNCHANGED)
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

# def send_whatsapp_message(to, body, media_url=None):
#     if not TWILIO_WHATSAPP_NUMBER: 
#         return
    
#     try:
#         message_data = {
#             'from_': TWILIO_WHATSAPP_NUMBER,
#             'to': to,
#             'body': body
#         }
#         if media_url:
#             message_data['media_url'] = media_url
            
#         twilio_client.messages.create(**message_data)
#     except Exception as e:
#         logger.error(f"❌ Twilio Error: {e}")

# def ask_chatgpt_expert_fallback(user_input, ai_data, user_language='en'):
#     category = ai_data.get('category')
#     mood = ai_data.get('target_mood')
#     social_context = ai_data.get('social_context')
#     keywords = ai_data.get('specific_keywords', [])
#     date_range = ai_data.get('date_range') or {}
#     date_str = date_range.get('start')
    
#     context_parts = []
#     if social_context: context_parts.append(f"The user is looking for a spot for a {social_context}")
#     if mood: context_parts.append(f"They want a {mood} vibe")
#     if keywords: context_parts.append(f"They're interested in: {', '.join(keywords)}")
#     if category: context_parts.append(f"Looking for: {category}")
#     if date_str: context_parts.append(f"For the date: {date_str}")
    
#     context_description = ". ".join(context_parts) if context_parts else "They're looking for recommendations"
    
#     lang_map = {
#         'te': "CRITICAL: Respond ENTIRELY in Telugu using Telugu script (తెలుగు).",
#         'he': "CRITICAL: Respond ENTIRELY in Hebrew using Hebrew script (עברית).",
#         'ar': "CRITICAL: Respond ENTIRELY in Arabic using Arabic script (العربية).",
#         'hi': "CRITICAL: Respond ENTIRELY in Hindi using Devanagari script (हिन्दी).",
#         'es': "IMPORTANT: Respond in Spanish.",
#         'pt': "IMPORTANT: Respond in Portuguese.",
#         'fr': "IMPORTANT: Respond in French.",
#     }
#     lang_instruction = lang_map.get(user_language, "IMPORTANT: Respond in English.")
    
#     expert_prompt = f"""You are Yara, a LOCAL Buenos Aires expert. 
# CONTEXT: {context_description}
# Your database has no matches, but you should:
# 1. Give 2-3 SPECIFIC place names in Buenos Aires that match the request.
# 2. Include the neighborhood (Palermo, San Telmo, etc.).
# 3. Briefly explain WHY each place is perfect.
# 4. Be conversational and use relevant emojis.
# Format:
# "[Intro sentence]
# 🎯 [Place Name 1] in [Neighborhood]
# [Why it's perfect]
# 🎯 [Place Name 2] in [Neighborhood]  
# [Why it's perfect]
# [Friendly closing]"
# ORIGINAL REQUEST: "{user_input}"
# {lang_instruction}"""

#     try:
#         response = openai.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[{"role": "system", "content": "You are Yara, an expert Buenos Aires local guide.you know every thing"}, {"role": "user", "content": expert_prompt}],
#             temperature=0.8,
#             timeout=10
#         )
#         expert_response = response.choices[0].message.content
#         logger.info(f"🎯 Expert Fallback Response Generated in {user_language}")
#         return expert_response
#     except Exception as e:
#         logger.error(f"Fallback Error: {e}")
#         fallback_map = {
#             'te': "క్షమించండి, నా డేటాబేస్‌లో నిర్దిష్ట ఎంపికలు కనిపించలేదు, కానీ బ్యూనస్ ఎయిర్స్‌లో చాలా గొప్ప ప్రదేశాలు ఉన్నాయి! మీరు మరిన్ని వివరాలు ఇవ్వగలరా?",
#             'he': "מצטער, לא מצאתי אפשרויות ספציפיות במסד הנתונים שלי, אבל יש המון מקומות נהדרים בבואנוס איירס! תוכל לתת לי עוד פרטים?",
#             'ar': "آسف، لم أجد خيارات محددة. هل يمكنك إعطائي المزيد من التفاصيل؟",
#             'es': "Hmm, no encontré opciones específicas. ¿Puedes darme más detalles?",
#         }
#         return fallback_map.get(user_language, "I couldn't find specific matches. Can you give me more details?")

# def process_message_thread(sender, text):
#     conn = None
#     try:
#         conn = postgreSQL_pool.getconn()
#         user = get_user(conn, sender)

#         if not user:
#             create_user(conn, sender)
#             send_whatsapp_message(sender, "Hey! Welcome to Yara ai , I’m your Buenos Aires guide for finding the best plans in the city ✨ what are you in the mood for?")
#             return

#         step, user_age = user.get('conversation_step'), user.get('age', '25')
        
#         ai_data = executor.submit(analyze_user_intent, text).result() or {"user_language": "en"}
#         user_language = ai_data.get('user_language', 'en')
#         social_context = ai_data.get('social_context')

#         logger.info(f"🌍 Detected Language: {user_language}")

#         if ai_data.get('is_greeting') and step != 'ask_name_age':
#             user_name = user.get('name', 'there')
#             greetings = {'te': f"నమస్కారం {user_name}! మీరు ఏమి వెతుకుతున్నారు?", 'he': f"שלום {user_name}! מה אתה מחפש?", 'ar': f"مرحباً {user_name}! ماذا تبحث؟", 'es': f"¡Hola {user_name}! ¿Qué estás buscando hoy?", 'en': f"Hey {user_name}! What are you looking for today?"}
#             send_whatsapp_message(sender, greetings.get(user_language, greetings['en']))
#             return

#         if step == 'welcome':
#             messages = {'te': "మొదట, మీకు ఉత్తమ సూచనలు ఇవ్వడానికి, మీ పేరు మరియు వయస్సు ఏమిటి?", 'he': "קודם כל, מה שמך וגילך?", 'ar': "أولاً، ما هو اسمك وعمرك؟", 'es': "Primero, ¿cuál es tu nombre y edad?", 'en': "First, what's your name and age?"}
#             send_whatsapp_message(sender, messages.get(user_language, messages['en']))
#             update_user(conn, sender, {"conversation_step": "ask_name_age", "last_mood": text})
#             return

#         if step == 'ask_name_age':
#             last_mood = user.get('last_mood')
#             messages = {'te': f"సరే! '{last_mood}' కోసం చూపిస్తున్నాను:", 'he': f"מעולה! מראה אפשרויות עבור '{last_mood}':", 'ar': f"رائع! عرض الخيارات لـ '{last_mood}':", 'es': f"¡Perfecto! Buscando opciones para '{last_mood}':", 'en': f"Ok cool! Showing options for '{last_mood}':"}
#             send_whatsapp_message(sender, messages.get(user_language, messages['en']))
            
#             clean_name = re.sub(r'[^\w]', '', text.split()[0]) if text.split() else "Friend"
#             age = "".join(filter(str.isdigit, text)) or "25"
            
#             update_user(conn, sender, {"name": clean_name, "age": age, "conversation_step": "ready"})
#             text = last_mood 
#             ai_data = analyze_user_intent(text) or {"user_language": "en"}
#             user_language = ai_data.get('user_language', 'en')
#             social_context = ai_data.get('social_context')

#         found_something = False
#         should_check_events = ai_data.get('date_range') or any(k in ai_data.get('category', '') for k in ['event', 'concert', 'show', 'party']) or ai_data.get('inferred_keywords')

#         if should_check_events:
#             events = smart_search(conn, 'events', ai_data)
#             if events:
#                 found_something = True
#                 intro = translate_text(f"Here are some events matching your vibe:", user_language)
#                 if ai_data.get('date_range') and ai_data['date_range'].get('start'):
#                     intro = translate_text(f"Here's what's happening around {ai_data['date_range']['start']}:", user_language)
#                 send_whatsapp_message(sender, intro)
                
#                 for e in events:
#                     futures = {
#                         'jfy': executor.submit(generate_just_for_you, user_age, e['title'], e['description'], e.get('mood', 'social'), social_context, user_language),
#                         'title': executor.submit(translate_text, e.get('title'), user_language),
#                         'desc': executor.submit(translate_text, e.get('description'), user_language)
#                     }
#                     display_date = e.get('event_date') if e.get('event_date') else f"Every {e.get('recurring_day')}"
#                     caption = f"*{futures['title'].result()}*\n\n📍 {translate_text(e.get('location'), user_language)}\n🕒 {e.get('event_time')}\n📅 {display_date}\n🎵 {translate_text(e.get('music_type'), user_language)}\n📝 {futures['desc'].result()}\n📸 {e.get('instagram_link')}\n\n{futures['jfy'].result()}"
#                     send_whatsapp_message(sender, caption, media_url=e.get('image_url'))
        
#         should_check_businesses = not found_something or any(k in ai_data.get('category', '') for k in ['bar', 'restaurant', 'cafe', 'club']) or social_context
#         if should_check_businesses:
#             businesses = smart_search(conn, 'businesses', ai_data)
#             if businesses:
#                 found_something = True
#                 intro = translate_text("Found these spots for you:", user_language)
#                 send_whatsapp_message(sender, intro)
#                 for b in businesses:
#                     futures = {
#                         'jfy': executor.submit(generate_just_for_you, user_age, b['name'], b['description'], ai_data.get('target_mood') or 'chill', social_context, user_language),
#                         'name': executor.submit(translate_text, b.get('name'), user_language),
#                         'desc': executor.submit(translate_text, b.get('description'), user_language)
#                     }
#                     msg = f"*{futures['name'].result()}*\n📍 {translate_text(b.get('location'), user_language)}\n\n{futures['desc'].result()}\n\n📸 {b.get('instagram_link')}\n\n{futures['jfy'].result()}"
#                     send_whatsapp_message(sender, msg, media_url=b.get('image_url'))

#         if found_something:
#             send_whatsapp_message(sender, generate_closing_message(text, user_language))
#         else:
#             logger.info(f"🎯 No database matches - Using Expert Fallback in {user_language}")
#             send_whatsapp_message(sender, ask_chatgpt_expert_fallback(text, ai_data, user_language))

#     except Exception as e:
#         logger.error(f"Logic Error: {e}", exc_info=True)
#         send_whatsapp_message(sender, "Sorry, something went wrong. Let me try again - what are you looking for?")
#     finally:
#         if conn: postgreSQL_pool.putconn(conn)

# # ==============================================================================
# # 🌐 WEBHOOK
# # ==============================================================================

# @app.route("/webhook", methods=["POST"])
# def twilio_webhook():
#     incoming_msg = request.form.get('Body')
#     sender_id = request.form.get('From') 
#     if not sender_id or not incoming_msg: return "" 
    
#     resp = MessagingResponse()
#     threading.Thread(target=process_message_thread, args=(sender_id, incoming_msg)).start()
#     return str(resp)

# if __name__ == "__main__":
#     print("🚀 Twilio WhatsApp Bot Starting...")
#     print("✨ Enhanced Features:")
#     print("   - Fully Multi-language (English DEFAULT)")
#     print("   - Intelligent Abstract Search (e.g., 'artistic events')")
#     print("   - Auto-translation of all content")
#     print("   - Images with all recommendations")
#     app.run(port=5000)

# languge chagpt dallback working
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
#     UPDATED: Now includes 'inferred_keywords' for smarter, abstract searches.
#     """
#     today_str = date.today().strftime("%Y-%m-%d")
#     weekday_str = date.today().strftime("%A")
    
#     system_prompt = (
#         f"Current Date: {today_str} ({weekday_str}). "
#         "You are a multilingual AI that understands ALL languages. "
#         "Your job is to analyze a user's request for events or businesses in Buenos Aires and extract structured data."
        
#         "EXTRACT THE FOLLOWING (return as JSON):\n"
        
#         "1. 'is_greeting': boolean (true ONLY for simple greetings with NO other request)\n"
        
#         "2. 'date_range': {'start': 'YYYY-MM-DD', 'end': 'YYYY-MM-DD'} or null\n"
        
#         "3. 'target_mood': string (romantic, chill, energetic, party, relaxed, upscale, casual)\n"
        
#         "4. 'social_context': string (date, friends, solo, family, business)\n"
        
#         "5. 'category': string (event, concert, show, bar, restaurant, cafe, etc.)\n"
        
#         "6. 'specific_keywords': List of DIRECT and SPECIFIC keywords from the user's text. "
#         "   - Examples: 'Salsa', 'Techno', 'Jazz', 'Rooftop', 'Live music'.\n"
        
#         "7. 'user_language': detected ISO 639-1 language code (en, es, te, he, ar, etc.). Default to 'en' if uncertain.\n"

#         # --- THIS IS THE NEW, INTELLIGENT PART ---
#         "8. 'inferred_keywords': List of related, searchable keywords if the user's request is abstract. "
#         "   - If the user asks for 'artistic' or 'cultural' things, infer related concrete terms.\n"
#         "   - If the user's request is already specific (e.g., 'techno'), this can be null.\n"
#         "   - Examples:\n"
#         "     * User says 'artistic events' → inferred_keywords: ['art', 'gallery', 'exhibition', 'museum', 'theatre', 'performance', 'cultural']\n"
#         "     * User says 'something intellectual' → inferred_keywords: ['lecture', 'talk', 'book', 'museum', 'cinema', 'art']\n"
#         "     * User says 'a place with a nice view' → inferred_keywords: ['rooftop', 'terrace', 'view', 'balcony']\n"
        
#         "EXAMPLES:\n"
#         "User: 'I want a chill bar with friends'\n"
#         "→ {social_context: 'friends', target_mood: 'chill', category: 'bar', user_language: 'en'}\n"
        
#         "User: 'artistic events this weekend'\n"
#         "→ {category: 'event', date_range: {...}, user_language: 'en', inferred_keywords: ['art', 'gallery', 'exhibition', 'museum', 'theatre', 'performance', 'cultural']}\n"
        
#         "User: 'Techno party tonight'\n"
#         "→ {category: 'party', date_range: {...}, specific_keywords: ['Techno', 'Electronic'], user_language: 'en'}\n"
        
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
#             return {"user_language": "en"}
        
#         if not data.get('user_language') or data.get('user_language') == 'unknown':
#             data['user_language'] = 'en'
        
#         logger.info(f"🧠 AI Analysis: {data}")
#         return data
        
#     except Exception as e:
#         logger.error(f"AI Intent Error: {e}")
#         return {"user_language": "en"}

# def generate_just_for_you(user_age, item_name, item_desc, item_mood, social_context=None, user_language='en'):
#     """
#     Enhanced: Now generates personalized recommendations in user's detected language
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
        
#         # Language instruction
#         lang_instruction = f"Respond in the language code: {user_language}. "
#         if user_language == 'te':
#             lang_instruction += "Use Telugu script and language."
#         elif user_language == 'he':
#             lang_instruction += "Use Hebrew script and language."
#         elif user_language == 'ar':
#             lang_instruction += "Use Arabic script and language."
#         elif user_language == 'hi':
#             lang_instruction += "Use Hindi script and language."
#         elif user_language == 'es':
#             lang_instruction += "Use Spanish language."
#         elif user_language == 'pt':
#             lang_instruction += "Use Portuguese language."
#         elif user_language == 'fr':
#             lang_instruction += "Use French language."
#         else:
#             lang_instruction += "Use English language."
        
#         prompt = (
#             f"{lang_instruction} "
#             f"Write a 1-sentence recommendation for a {user_age} year old. "
#             f"Venue: {item_name}. Vibe: {item_mood}. {context_msg} "
#             "Start with '✨ Just for you:' or equivalent in the target language. Be enthusiastic and specific."
#         )
        
#         response = openai.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[{"role": "user", "content": prompt}],
#             temperature=0.7,
#             timeout=5
#         )
#         return response.choices[0].message.content.replace('"', '')
#     except Exception as e:
#         logger.error(f"Just for you error: {e}")
#         # Fallback based on language
#         if user_language == 'te':
#             return f"✨ మీ కోసం: ఇది {item_mood} వైబ్‌తో సరిపోతుంది! {context_msg}"
#         elif user_language == 'he':
#             return f"✨ בשבילך: זה מתאים ל{item_mood} אווירה! {context_msg}"
#         elif user_language == 'ar':
#             return f"✨ لك خصيصاً: هذا يناسب الأجواء {item_mood}! {context_msg}"
#         elif user_language == 'es':
#             return f"✨ Just for you: ¡Esto coincide con el ambiente {item_mood}! {context_msg}"
#         else:
#             return f"✨ Just for you: This matches the {item_mood} vibe! {context_msg}"

# def translate_text(text, target_language):
#     if target_language == 'en' or not text:
#         return text
    
#     try:
#         lang_map = {
#             'es': 'Spanish', 'pt': 'Portuguese', 'fr': 'French', 'de': 'German', 
#             'it': 'Italian', 'ru': 'Russian', 'ar': 'Arabic', 'he': 'Hebrew', 
#             'hi': 'Hindi', 'te': 'Telugu', 'ta': 'Tamil', 'ko': 'Korean', 
#             'ja': 'Japanese', 'zh': 'Chinese'
#         }
#         lang_name = lang_map.get(target_language, 'English')
        
#         response = openai.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[
#                 {"role": "system", "content": f"Translate the following text to {lang_name}. Maintain original tone. Only return the translation."},
#                 {"role": "user", "content": text}
#             ],
#             temperature=0.3,
#             timeout=5
#         )
#         translated = response.choices[0].message.content.strip()
#         return translated if translated else text
#     except Exception as e:
#         logger.error(f"Translation error: {e}")
#         return text

# def generate_closing_message(user_query, user_language='en'):
#     try:
#         # Simplified language instruction
#         lang_instruction_map = {
#             'te': "Respond in Telugu using Telugu script.", 'he': "Respond in Hebrew using Hebrew script.",
#             'ar': "Respond in Arabic using Arabic script.", 'hi': "Respond in Hindi using Devanagari script.",
#             'es': "Respond in Spanish.", 'pt': "Respond in Portuguese.", 'fr': "Respond in French."
#         }
#         lang_instruction = lang_instruction_map.get(user_language, "Respond in English.")
        
#         prompt = (
#             f"User query: '{user_query}'. I sent recommendations. "
#             f"Write a SHORT closing message asking if they want more suggestions. "
#             f"Use 1 emoji. Be friendly. {lang_instruction}"
#         )
        
#         response = openai.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[{"role": "system", "content": "You are Yara, a friendly Buenos Aires guide. You know everything."}, {"role": "user", "content": prompt}],
#             temperature=0.7,
#             timeout=4
#         )
#         return response.choices[0].message.content.replace('"', '')
#     except:
#         # Fallback messages
#         fallback_map = {
#             'te': "మరిన్ని సూచనలు కావాలా? 🎉", 'he': "צריך עוד המלצות? 🎉",
#             'ar': "هل تحتاج المزيد من الاقتراحات؟ 🎉", 'es': "¿Te gustaría más sugerencias? 🎉",
#             'pt': "Gostaria de mais sugestões? 🎉"
#         }
#         return fallback_map.get(user_language, "Need more suggestions? 🎉")

# # --- DATABASE FUNCTIONS (UNCHANGED) ---

# def get_user(conn, phone):
#     with conn.cursor() as cur:
#         cur.execute("SELECT * FROM public.users WHERE phone = %s", (phone,))
#         return cur.fetchone()

# def create_user(conn, phone):
#     with conn.cursor() as cur:
#         cur.execute(
#             "INSERT INTO public.users (phone, conversation_step) VALUES (%s, 'welcome') ON CONFLICT (phone) DO NOTHING", (phone,)
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
#     UPDATED: Now includes 'inferred_keywords' for intelligent searching.
#     """
#     query = f"SELECT * FROM public.{table} WHERE 1=1"
#     args = []
    
#     date_range = ai_data.get('date_range') or {}
#     social_context = ai_data.get('social_context')
    
#     # 1. Build search terms from ALL context
#     search_terms = []
    
#     # Add direct keywords
#     if ai_data.get('specific_keywords'):
#         search_terms.extend(ai_data.get('specific_keywords'))

#     # --- THIS IS THE NEW, INTELLIGENT PART ---
#     # Add inferred keywords from abstract requests
#     if ai_data.get('inferred_keywords'):
#         search_terms.extend(ai_data.get('inferred_keywords'))
    
#     # Add mood
#     if ai_data.get('target_mood'):
#         search_terms.append(ai_data.get('target_mood'))
    
#     # Add social context keywords
#     if social_context == 'date':
#         search_terms.extend(['romantic', 'intimate', 'cozy'])
#     elif social_context == 'friends':
#         search_terms.extend(['social', 'group', 'casual'])
    
#     # Add category if specific
#     cat = ai_data.get('category', '')
#     if cat and len(cat) > 3 and cat.lower() not in ['event', 'party', 'show', 'place', 'spot']:
#         search_terms.append(cat)
    
#     # Clean and deduplicate
#     search_terms = list(set([t for t in search_terms if t and len(t) > 2]))
    
#     logger.info(f"🔍 Search Terms (Level {strictness_level}): {search_terms}")

#     # --- DATE LOGIC (for events) ---
#     if table == 'events' and date_range:
#         start, end = date_range.get('start'), date_range.get('end')
#         if start and end:
#             start_obj = datetime.strptime(start, "%Y-%m-%d").date()
#             end_obj = datetime.strptime(end, "%Y-%m-%d").date()
#             days_in_range = [ (start_obj + timedelta(days=i)).strftime('%A') for i in range((end_obj - start_obj).days + 1) ]
#             days_tuple = tuple(set(days_in_range))
#             query += " AND ((event_date >= %s::date AND event_date <= %s::date) OR (recurring_day = ANY(%s)))"
#             args.extend([start, end, list(days_tuple)])

#     # --- TEXT SEARCH LOGIC ---
#     if search_terms:
#         term_conditions = [f"(title ILIKE %s OR description ILIKE %s OR mood ILIKE %s OR music_type ILIKE %s OR location ILIKE %s)" for _ in search_terms] if table == 'events' else [f"(name ILIKE %s OR description ILIKE %s OR location ILIKE %s OR type ILIKE %s)" for _ in search_terms]
        
#         for term in search_terms:
#             term_wild = f"%{term}%"
#             args.extend([term_wild] * (5 if table == 'events' else 4))
        
#         join_operator = " AND " if strictness_level == 1 else " OR "
#         query += f" AND ({join_operator.join(term_conditions)})"

#     # Order and limit
#     query += " ORDER BY event_date ASC LIMIT 5" if table == 'events' else " LIMIT 5"

#     logger.info(f"📊 SQL Query: {query[:200]}...")
#     logger.info(f"📊 Args: {args}")
    
#     return query, args


# # ============================================================================== 
# # CHANGE 1: FIXED smart_search() - Now has error handling, returns [] on crash
# # ==============================================================================
# def smart_search(conn, table, ai_data):
#     """
#     UPDATED: Added try-catch to prevent crashes. Returns empty list on error.
#     """
#     try:
#         # Attempt 1: Strict (ALL keywords)
#         query, args = build_search_query(table, ai_data, strictness_level=1)
#         with conn.cursor() as cur:
#             cur.execute(query, tuple(args))
#             results = cur.fetchall()
#             if results:
#                 logger.info(f"✅ Found {len(results)} results (Strict)")
#                 return results

#         # Attempt 2: Loose (ANY keyword)
#         query, args = build_search_query(table, ai_data, strictness_level=2)
#         with conn.cursor() as cur:
#             cur.execute(query, tuple(args))
#             results = cur.fetchall()
#             if results:
#                 logger.info(f"✅ Found {len(results)} results (Loose)")
#                 return results
#             else:
#                 logger.warning(f"⚠️ No results in {table}")
#                 return []
    
#     except Exception as e:
#         # ADDED: Instead of crashing, log error and return empty list
#         logger.error(f"❌ Search error in {table}: {e}")
#         return []  # Returns empty so fallback can handle it

# def send_whatsapp_message(to, body, media_url=None):
#     if not TWILIO_WHATSAPP_NUMBER: 
#         return
    
#     try:
#         message_data = {
#             'from_': TWILIO_WHATSAPP_NUMBER,
#             'to': to,
#             'body': body
#         }
#         if media_url:
#             message_data['media_url'] = media_url
            
#         twilio_client.messages.create(**message_data)
#     except Exception as e:
#         logger.error(f"❌ Twilio Error: {e}")

# # ==============================================================================
# # CHANGE 2: UPDATED ask_chatgpt_expert_fallback() - ALWAYS POSITIVE PROMPT
# # ==============================================================================
# def ask_chatgpt_expert_fallback(user_input, ai_data, user_language='en'):
#     """
#     UPDATED: Prompt rewritten to be ALWAYS POSITIVE. Never says "not found" or "sorry"
#     """
#     category = ai_data.get('category')
#     mood = ai_data.get('target_mood')
#     social_context = ai_data.get('social_context')
#     keywords = ai_data.get('specific_keywords', [])
#     inferred_keywords = ai_data.get('inferred_keywords', [])
#     date_range = ai_data.get('date_range') or {}
#     date_str = date_range.get('start')
    
#     # Build context description
#     context_parts = []
#     if social_context: 
#         context_parts.append(f"looking for {social_context} experience")
#     if mood: 
#         context_parts.append(f"wants {mood} vibe")
#     if keywords: 
#         context_parts.append(f"interested in: {', '.join(keywords)}")
#     if inferred_keywords:
#         context_parts.append(f"likes: {', '.join(inferred_keywords)}")
#     if category: 
#         context_parts.append(f"wants: {category}")
#     if date_str: 
#         context_parts.append(f"for date: {date_str}")
    
#     context_description = ". ".join(context_parts) if context_parts else "looking for recommendations in Buenos Aires"
    
#     # Language instruction
#     lang_map = {
#         'te': "CRITICAL: Respond ENTIRELY in Telugu using Telugu script (తెలుగు).",
#         'he': "CRITICAL: Respond ENTIRELY in Hebrew using Hebrew script (עברית).",
#         'ar': "CRITICAL: Respond ENTIRELY in Arabic using Arabic script (العربية).",
#         'hi': "CRITICAL: Respond ENTIRELY in Hindi using Devanagari script (हिन्दी).",
#         'es': "IMPORTANT: Respond in Spanish.",
#         'pt': "IMPORTANT: Respond in Portuguese.",
#         'fr': "IMPORTANT: Respond in French.",
#     }
#     lang_instruction = lang_map.get(user_language, "IMPORTANT: Respond in English.")
    
#     # === UPDATED PROMPT - ALWAYS POSITIVE ===
#     expert_prompt = f"""You are Yara, the ULTIMATE Buenos Aires expert and local tour guide. 
# You know EVERYTHING about Buenos Aires - every bar, every restaurant, every café, every hidden gem, every event, every neighborhood.

# USER'S REQUEST: "{user_input}"
# USER CONTEXT: {context_description}

# YOUR MISSION: Give them 2-3 PERFECT, SPECIFIC recommendations that match their request.

# CRITICAL RULES - READ CAREFULLY:
# 1. ✅ BE POSITIVE AND CONFIDENT - You're an expert who knows the BEST places in Buenos Aires
# 2. ✅ Give 2-3 SPECIFIC place names with neighborhoods (Palermo, San Telmo, Recoleta, etc.)
# 3. ✅ Explain WHY each place is perfect for their request
# 4. ✅ Be enthusiastic and use emojis (🎯, ✨, 🍸, 🎵, etc.)
# 5. ❌ NEVER EVER say negative things like:
#    - "sorry"
#    - "not found"
#    - "don't have"
#    - "couldn't find"
#    - "no matches"
#    - "unfortunately"
# 6. ✅ Instead, say positive things like:
#    - "I know the perfect spots!"
#    - "Great choice! Here are amazing places!"
#    - "You'll love these!"
#    - "Perfect! Buenos Aires has incredible options!"

# FORMAT YOUR RESPONSE EXACTLY LIKE THIS:
# "[Enthusiastic intro acknowledging their request - NO negativity!]

# 🎯 **[Place Name]** in [Neighborhood]
# [One sentence why it's perfect for them]

# 🎯 **[Place Name]** in [Neighborhood]
# [One sentence why it's perfect for them]

# 🎯 **[Place Name]** in [Neighborhood]
# [One sentence why it's perfect for them]

# [Friendly closing with emoji]"

# EXAMPLES OF GOOD INTROS (use similar tone):
# - "Great choice! I know some incredible spots for that!" ✅
# - "Perfect! Buenos Aires has amazing places for this!" ✅
# - "Excellent! Here are some fantastic options!" ✅
# - "I love that you're asking! Buenos Aires has the best spots for this!" ✅

# EXAMPLES OF BAD INTROS (NEVER use these):
# - "Sorry, I don't have information..." ❌
# - "Unfortunately, I couldn't find..." ❌
# - "My database doesn't have..." ❌

# {lang_instruction}

# Remember: You're a confident expert. You ALWAYS have great recommendations!"""

#     try:
#         response = openai.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[
#                 {"role": "system", "content": "You are Yara, the ultimate Buenos Aires expert who knows EVERYTHING about the city. You're always positive, enthusiastic, and helpful. You NEVER say negative things. You always have great recommendations because you're a real expert."}, 
#                 {"role": "user", "content": expert_prompt}
#             ],
#             temperature=0.8,
#             timeout=10
#         )
#         expert_response = response.choices[0].message.content
#         logger.info(f"🎯 Expert Fallback Response Generated in {user_language}")
#         return expert_response
    
#     except Exception as e:
#         logger.error(f"Fallback Error: {e}")
#         # UPDATED: Even error fallback is positive
#         fallback_map = {
#             'te': "బ్యూనస్ ఎయిర్స్‌లో మీ కోసం కొన్ని అద్భుతమైన ప్రదేశాలు ఉన్నాయి! మరిన్ని వివరాలు ఇవ్వండి, నేను ఉత్తమ ప్రదేశాలను సూచిస్తాను! 🎯",
#             'he': "יש כמה מקומות מדהימים בבואנוס איירס בשבילך! ספר לי עוד פרטים ואני אמליץ על המקומות הכי טובים! 🎯",
#             'ar': "لدي أماكن رائعة في بوينس آيريس لك! أخبرني المزيد من التفاصيل وسأوصي بأفضل الأماكن! 🎯",
#             'es': "¡Conozco lugares increíbles en Buenos Aires para ti! Cuéntame más detalles y te recomendaré los mejores sitios! 🎯",
#             'pt': "Conheço lugares incríveis em Buenos Aires para você! Me conte mais detalhes e recomendarei os melhores lugares! 🎯",
#         }
#         return fallback_map.get(user_language, "I know some amazing places in Buenos Aires for you! Tell me more details and I'll recommend the best spots! 🎯")

# def process_message_thread(sender, text):
#     conn = None
#     try:
#         conn = postgreSQL_pool.getconn()
#         user = get_user(conn, sender)

#         if not user:
#             create_user(conn, sender)
#             send_whatsapp_message(sender, "Hey! Welcome to Yara ai , I'm your Buenos Aires guide for finding the best plans in the city ✨ what are you in the mood for?")
#             return

#         step, user_age = user.get('conversation_step'), user.get('age', '25')
        
#         ai_data = executor.submit(analyze_user_intent, text).result() or {"user_language": "en"}
#         user_language = ai_data.get('user_language', 'en')
#         social_context = ai_data.get('social_context')

#         logger.info(f"🌍 Detected Language: {user_language}")

#         if ai_data.get('is_greeting') and step != 'ask_name_age':
#             user_name = user.get('name', 'there')
#             greetings = {'te': f"నమస్కారం {user_name}! మీరు ఏమి వెతుకుతున్నారు?", 'he': f"שלום {user_name}! מה אתה מחפש?", 'ar': f"مرحباً {user_name}! ماذا تبحث؟", 'es': f"¡Hola {user_name}! ¿Qué estás buscando hoy?", 'en': f"Hey {user_name}! What are you looking for today?"}
#             send_whatsapp_message(sender, greetings.get(user_language, greetings['en']))
#             return

#         if step == 'welcome':
#             messages = {'te': "మొదట, మీకు ఉత్తమ సూచనలు ఇవ్వడానికి, మీ పేరు మరియు వయస్సు ఏమిటి?", 'he': "קודם כל, מה שמך וגילך?", 'ar': "أولاً، ما هو اسمك وعمرك؟", 'es': "Primero, ¿cuál es tu nombre y edad?", 'en': "First, what's your name and age?"}
#             send_whatsapp_message(sender, messages.get(user_language, messages['en']))
#             update_user(conn, sender, {"conversation_step": "ask_name_age", "last_mood": text})
#             return

#         if step == 'ask_name_age':
#             last_mood = user.get('last_mood')
#             messages = {'te': f"సరే! '{last_mood}' కోసం చూపిస్తున్నాను:", 'he': f"מעולה! מראה אפשרויות עבור '{last_mood}':", 'ar': f"رائع! عرض الخيارات لـ '{last_mood}':", 'es': f"¡Perfecto! Buscando opciones para '{last_mood}':", 'en': f"Ok cool! Showing options for '{last_mood}':"}
#             send_whatsapp_message(sender, messages.get(user_language, messages['en']))
            
#             clean_name = re.sub(r'[^\w]', '', text.split()[0]) if text.split() else "Friend"
#             age = "".join(filter(str.isdigit, text)) or "25"
            
#             update_user(conn, sender, {"name": clean_name, "age": age, "conversation_step": "ready"})
#             text = last_mood 
#             ai_data = analyze_user_intent(text) or {"user_language": "en"}
#             user_language = ai_data.get('user_language', 'en')
#             social_context = ai_data.get('social_context')

#         found_something = False
#         should_check_events = ai_data.get('date_range') or any(k in ai_data.get('category', '') for k in ['event', 'concert', 'show', 'party']) or ai_data.get('inferred_keywords')

#         if should_check_events:
#             events = smart_search(conn, 'events', ai_data)  # Now returns [] on error
#             if events:
#                 found_something = True
#                 intro = translate_text(f"Here are some events matching your vibe:", user_language)
#                 if ai_data.get('date_range') and ai_data['date_range'].get('start'):
#                     intro = translate_text(f"Here's what's happening around {ai_data['date_range']['start']}:", user_language)
#                 send_whatsapp_message(sender, intro)
                
#                 for e in events:
#                     futures = {
#                         'jfy': executor.submit(generate_just_for_you, user_age, e['title'], e['description'], e.get('mood', 'social'), social_context, user_language),
#                         'title': executor.submit(translate_text, e.get('title'), user_language),
#                         'desc': executor.submit(translate_text, e.get('description'), user_language)
#                     }
#                     display_date = e.get('event_date') if e.get('event_date') else f"Every {e.get('recurring_day')}"
#                     caption = f"*{futures['title'].result()}*\n\n📍 {translate_text(e.get('location'), user_language)}\n🕒 {e.get('event_time')}\n📅 {display_date}\n🎵 {translate_text(e.get('music_type'), user_language)}\n📝 {futures['desc'].result()}\n📸 {e.get('instagram_link')}\n\n{futures['jfy'].result()}"
#                     send_whatsapp_message(sender, caption, media_url=e.get('image_url'))
        
#         should_check_businesses = not found_something or any(k in ai_data.get('category', '') for k in ['bar', 'restaurant', 'cafe', 'club']) or social_context
#         if should_check_businesses:
#             businesses = smart_search(conn, 'businesses', ai_data)  # Now returns [] on error
#             if businesses:
#                 found_something = True
#                 intro = translate_text("Found these spots for you:", user_language)
#                 send_whatsapp_message(sender, intro)
#                 for b in businesses:
#                     futures = {
#                         'jfy': executor.submit(generate_just_for_you, user_age, b['name'], b['description'], ai_data.get('target_mood') or 'chill', social_context, user_language),
#                         'name': executor.submit(translate_text, b.get('name'), user_language),
#                         'desc': executor.submit(translate_text, b.get('description'), user_language)
#                     }
#                     msg = f"*{futures['name'].result()}*\n📍 {translate_text(b.get('location'), user_language)}\n\n{futures['desc'].result()}\n\n📸 {b.get('instagram_link')}\n\n{futures['jfy'].result()}"
#                     send_whatsapp_message(sender, msg, media_url=b.get('image_url'))

#         if found_something:
#             send_whatsapp_message(sender, generate_closing_message(text, user_language))
#         else:
#             # If nothing found in database, use positive expert fallback
#             logger.info(f"🎯 No database matches - Using Positive Expert Fallback in {user_language}")
#             send_whatsapp_message(sender, ask_chatgpt_expert_fallback(text, ai_data, user_language))

# # ==============================================================================
# # CHANGE 3: UPDATED Exception Handler - Uses fallback instead of error message
# # ==============================================================================
#     except Exception as e:
#         logger.error(f"Logic Error: {e}", exc_info=True)
#         # UPDATED: Instead of showing error message, use positive fallback
#         try:
#             ai_data = analyze_user_intent(text) or {"user_language": "en"}
#             user_language = ai_data.get('user_language', 'en')
#             send_whatsapp_message(sender, ask_chatgpt_expert_fallback(text, ai_data, user_language))
#         except:
#             # Last resort - still positive
#             send_whatsapp_message(sender, "I know some amazing places in Buenos Aires! Tell me what you're looking for and I'll recommend the best spots! 🎯")
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
#     if not sender_id or not incoming_msg: return "" 
    
#     resp = MessagingResponse()
#     threading.Thread(target=process_message_thread, args=(sender_id, incoming_msg)).start()
#     return str(resp)

# if __name__ == "__main__":
#     print("🚀 Twilio WhatsApp Bot Starting...")
#     print("✨ Enhanced Features:")
#     print("   - Fully Multi-language (English DEFAULT)")
#     print("   - Intelligent Abstract Search (e.g., 'artistic events')")
#     print("   - Auto-translation of all content")
#     print("   - Images with all recommendations")
#     print("   - ALWAYS POSITIVE responses - never shows errors")
#     print("   - Expert fallback for empty database results")
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
# # 🧠 ENHANCED AI & UTILS
# # ==============================================================================

# def analyze_user_intent(user_text):
#     """
#     UPDATED: Now includes 'inferred_keywords' for smarter, abstract searches.
#     """
#     today_str = date.today().strftime("%Y-%m-%d")
#     weekday_str = date.today().strftime("%A")
    
#     system_prompt = (
#         f"Current Date: {today_str} ({weekday_str}). "
#         "You are a multilingual AI that understands ALL languages. "
#         "Your job is to analyze a user's request for events or businesses in Buenos Aires and extract structured data."
        
#         "EXTRACT THE FOLLOWING (return as JSON):\n"
        
#         "1. 'is_greeting': boolean (true ONLY if message is JUST 'hi', 'hello', 'hola', 'hey' with ABSOLUTELY NO OTHER REQUEST. If user says 'hi' AND asks for anything else, return FALSE)\n"
#         "   Examples:\n"
#         "   - 'hi' → is_greeting: true ✅\n"
#         "   - 'hello' → is_greeting: true ✅\n"
#         "   - 'hi any events on Dec 6' → is_greeting: FALSE ❌ (has request!)\n"
#         "   - 'hello where can I find bars' → is_greeting: FALSE ❌ (has request!)\n"
        
#         "2. 'date_range': {'start': 'YYYY-MM-DD', 'end': 'YYYY-MM-DD'} or null\n"
        
#         "3. 'target_mood': string (romantic, chill, energetic, party, relaxed, upscale, casual)\n"
        
#         "4. 'social_context': string (date, friends, solo, family, business)\n"
        
#         "5. 'category': string (event, concert, show, bar, restaurant, cafe, etc.)\n"
        
#         "6. 'specific_keywords': List of DIRECT and SPECIFIC keywords from the user's text. "
#         "   - Examples: 'Salsa', 'Techno', 'Jazz', 'Rooftop', 'Live music'.\n"
        
#         "7. 'user_language': detected ISO 639-1 language code (en, es, te, he, ar, etc.). Default to 'en' if uncertain.\n"

#         "8. 'inferred_keywords': List of related, searchable keywords if the user's request is abstract. "
#         "   - If the user asks for 'artistic' or 'cultural' things, infer related concrete terms.\n"
#         "   - If the user's request is already specific (e.g., 'techno'), this can be null.\n"
#         "   - Examples:\n"
#         "     * User says 'artistic events' → inferred_keywords: ['art', 'gallery', 'exhibition', 'museum', 'theatre', 'performance', 'cultural']\n"
#         "     * User says 'something intellectual' → inferred_keywords: ['lecture', 'talk', 'book', 'museum', 'cinema', 'art']\n"
#         "     * User says 'a place with a nice view' → inferred_keywords: ['rooftop', 'terrace', 'view', 'balcony']\n"
        
#         "EXAMPLES:\n"
#         "User: 'I want a chill bar with friends'\n"
#         "→ {social_context: 'friends', target_mood: 'chill', category: 'bar', user_language: 'en'}\n"
        
#         "User: 'artistic events this weekend'\n"
#         "→ {category: 'event', date_range: {...}, user_language: 'en', inferred_keywords: ['art', 'gallery', 'exhibition', 'museum', 'theatre', 'performance', 'cultural']}\n"
        
#         "User: 'Techno party tonight'\n"
#         "→ {category: 'party', date_range: {...}, specific_keywords: ['Techno', 'Electronic'], user_language: 'en'}\n"
        
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
#             return {"user_language": "en"}
        
#         if not data.get('user_language') or data.get('user_language') == 'unknown':
#             data['user_language'] = 'en'
        
#         logger.info(f"🧠 AI Analysis: {data}")
#         return data
        
#     except Exception as e:
#         logger.error(f"AI Intent Error: {e}")
#         return {"user_language": "en"}

# def generate_just_for_you(user_age, item_name, item_desc, item_mood, social_context=None, user_language='en'):
#     """
#     Enhanced: Now generates personalized recommendations in user's detected language
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
        
#         # Language instruction
#         lang_instruction = f"Respond in the language code: {user_language}. "
#         if user_language == 'te':
#             lang_instruction += "Use Telugu script and language."
#         elif user_language == 'he':
#             lang_instruction += "Use Hebrew script and language."
#         elif user_language == 'ar':
#             lang_instruction += "Use Arabic script and language."
#         elif user_language == 'hi':
#             lang_instruction += "Use Hindi script and language."
#         elif user_language == 'es':
#             lang_instruction += "Use Spanish language."
#         elif user_language == 'pt':
#             lang_instruction += "Use Portuguese language."
#         elif user_language == 'fr':
#             lang_instruction += "Use French language."
#         else:
#             lang_instruction += "Use English language."
        
#         prompt = (
#             f"{lang_instruction} "
#             f"Write a 1-sentence recommendation for a {user_age} year old. "
#             f"Venue: {item_name}. Vibe: {item_mood}. {context_msg} "
#             "Start with '✨ Just for you:' or equivalent in the target language. Be enthusiastic and specific."
#         )
        
#         response = openai.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[{"role": "user", "content": prompt}],
#             temperature=0.7,
#             timeout=5
#         )
#         return response.choices[0].message.content.replace('"', '')
#     except Exception as e:
#         logger.error(f"Just for you error: {e}")
#         if user_language == 'te':
#             return f"✨ మీ కోసం: ఇది {item_mood} వైబ్‌తో సరిపోతుంది! {context_msg}"
#         elif user_language == 'he':
#             return f"✨ בשבילך: זה מתאים ל{item_mood} אווירה! {context_msg}"
#         elif user_language == 'ar':
#             return f"✨ لك خصيصاً: هذا يناسب الأجواء {item_mood}! {context_msg}"
#         elif user_language == 'es':
#             return f"✨ Just for you: ¡Esto coincide con el ambiente {item_mood}! {context_msg}"
#         else:
#             return f"✨ Just for you: This matches the {item_mood} vibe! {context_msg}"

# def translate_text(text, target_language):
#     if target_language == 'en' or not text:
#         return text
    
#     try:
#         lang_map = {
#             'es': 'Spanish', 'pt': 'Portuguese', 'fr': 'French', 'de': 'German', 
#             'it': 'Italian', 'ru': 'Russian', 'ar': 'Arabic', 'he': 'Hebrew', 
#             'hi': 'Hindi', 'te': 'Telugu', 'ta': 'Tamil', 'ko': 'Korean', 
#             'ja': 'Japanese', 'zh': 'Chinese'
#         }
#         lang_name = lang_map.get(target_language, 'English')
        
#         response = openai.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[
#                 {"role": "system", "content": f"Translate the following text to {lang_name}. Maintain original tone. Only return the translation."},
#                 {"role": "user", "content": text}
#             ],
#             temperature=0.3,
#             timeout=5
#         )
#         translated = response.choices[0].message.content.strip()
#         return translated if translated else text
#     except Exception as e:
#         logger.error(f"Translation error: {e}")
#         return text

# def generate_closing_message(user_query, user_language='en'):
#     try:
#         lang_instruction_map = {
#             'te': "Respond in Telugu using Telugu script.", 'he': "Respond in Hebrew using Hebrew script.",
#             'ar': "Respond in Arabic using Arabic script.", 'hi': "Respond in Hindi using Devanagari script.",
#             'es': "Respond in Spanish.", 'pt': "Respond in Portuguese.", 'fr': "Respond in French."
#         }
#         lang_instruction = lang_instruction_map.get(user_language, "Respond in English.")
        
#         prompt = (
#             f"User query: '{user_query}'. I sent recommendations. "
#             f"Write a SHORT closing message asking if they want more suggestions. "
#             f"Use 1 emoji. Be friendly. {lang_instruction}"
#         )
        
#         response = openai.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[{"role": "system", "content": "You are Yara, a friendly Buenos Aires guide. You know everything."}, {"role": "user", "content": prompt}],
#             temperature=0.7,
#             timeout=4
#         )
#         return response.choices[0].message.content.replace('"', '')
#     except:
#         fallback_map = {
#             'te': "మరిన్ని సూచనలు కావాలా? 🎉", 'he': "צריך עוד המלצות? 🎉",
#             'ar': "هل تحتاج المزيد من الاقتراحات؟ 🎉", 'es': "¿Te gustaría más sugerencias? 🎉",
#             'pt': "Gostaria de mais sugestões? 🎉"
#         }
#         return fallback_map.get(user_language, "Need more suggestions? 🎉")

# # --- DATABASE FUNCTIONS ---

# def get_user(conn, phone):
#     with conn.cursor() as cur:
#         cur.execute("SELECT * FROM public.users WHERE phone = %s", (phone,))
#         return cur.fetchone()

# def create_user(conn, phone):
#     with conn.cursor() as cur:
#         cur.execute(
#             "INSERT INTO public.users (phone, conversation_step) VALUES (%s, 'welcome') ON CONFLICT (phone) DO NOTHING", (phone,)
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
#     UPDATED: Now includes 'inferred_keywords' for intelligent searching.
#     """
#     query = f"SELECT * FROM public.{table} WHERE 1=1"
#     args = []
    
#     date_range = ai_data.get('date_range') or {}
#     social_context = ai_data.get('social_context')
    
#     search_terms = []
    
#     if ai_data.get('specific_keywords'):
#         search_terms.extend(ai_data.get('specific_keywords'))

#     if ai_data.get('inferred_keywords'):
#         search_terms.extend(ai_data.get('inferred_keywords'))
    
#     if ai_data.get('target_mood'):
#         search_terms.append(ai_data.get('target_mood'))
    
#     if social_context == 'date':
#         search_terms.extend(['romantic', 'intimate', 'cozy'])
#     elif social_context == 'friends':
#         search_terms.extend(['social', 'group', 'casual'])
    
#     cat = ai_data.get('category', '')
#     if cat and len(cat) > 3 and cat.lower() not in ['event', 'party', 'show', 'place', 'spot']:
#         search_terms.append(cat)
    
#     search_terms = list(set([t for t in search_terms if t and len(t) > 2]))
    
#     logger.info(f"🔍 Search Terms (Level {strictness_level}): {search_terms}")

#     # --- DATE LOGIC (for events) ---
#     if table == 'events' and date_range:
#         start, end = date_range.get('start'), date_range.get('end')
#         if start and end:
#             start_obj = datetime.strptime(start, "%Y-%m-%d").date()
#             end_obj = datetime.strptime(end, "%Y-%m-%d").date()
#             days_in_range = [ (start_obj + timedelta(days=i)).strftime('%A') for i in range((end_obj - start_obj).days + 1) ]
#             days_tuple = tuple(set(days_in_range))
#             query += " AND ((event_date >= %s::date AND event_date <= %s::date) OR (recurring_day = ANY(%s)))"
#             args.extend([start, end, list(days_tuple)])

#     # --- TEXT SEARCH LOGIC ---
#     if search_terms:
#         term_conditions = [f"(title ILIKE %s OR description ILIKE %s OR mood ILIKE %s OR music_type ILIKE %s OR location ILIKE %s)" for _ in search_terms] if table == 'events' else [f"(name ILIKE %s OR description ILIKE %s OR location ILIKE %s OR type ILIKE %s)" for _ in search_terms]
        
#         for term in search_terms:
#             term_wild = f"%{term}%"
#             args.extend([term_wild] * (5 if table == 'events' else 4))
        
#         join_operator = " AND " if strictness_level == 1 else " OR "
#         query += f" AND ({join_operator.join(term_conditions)})"

#     query += " ORDER BY event_date ASC LIMIT 5" if table == 'events' else " LIMIT 5"

#     logger.info(f"📊 SQL Query: {query[:200]}...")
#     logger.info(f"📊 Args: {args}")
    
#     return query, args

# def smart_search(conn, table, ai_data):
#     """
#     UPDATED: Added try-catch to prevent crashes. Returns empty list on error.
#     """
#     try:
#         query, args = build_search_query(table, ai_data, strictness_level=1)
#         with conn.cursor() as cur:
#             cur.execute(query, tuple(args))
#             results = cur.fetchall()
#             if results:
#                 logger.info(f"✅ Found {len(results)} results (Strict)")
#                 return results

#         query, args = build_search_query(table, ai_data, strictness_level=2)
#         with conn.cursor() as cur:
#             cur.execute(query, tuple(args))
#             results = cur.fetchall()
#             if results:
#                 logger.info(f"✅ Found {len(results)} results (Loose)")
#                 return results
#             else:
#                 logger.warning(f"⚠️ No results in {table}")
#                 return []
    
#     except Exception as e:
#         logger.error(f"❌ Search error in {table}: {e}")
#         return []

# def send_whatsapp_message(to, body, media_url=None):
#     if not TWILIO_WHATSAPP_NUMBER: 
#         return
    
#     try:
#         message_data = {
#             'from_': TWILIO_WHATSAPP_NUMBER,
#             'to': to,
#             'body': body
#         }
#         if media_url:
#             message_data['media_url'] = media_url
            
#         twilio_client.messages.create(**message_data)
#     except Exception as e:
#         logger.error(f"❌ Twilio Error: {e}")

# def ask_chatgpt_expert_fallback(user_input, ai_data, user_language='en'):
#     """
#     UPDATED: Prompt rewritten to be ALWAYS POSITIVE. Never says "not found" or "sorry"
#     """
#     category = ai_data.get('category')
#     mood = ai_data.get('target_mood')
#     social_context = ai_data.get('social_context')
#     keywords = ai_data.get('specific_keywords', [])
#     inferred_keywords = ai_data.get('inferred_keywords', [])
#     date_range = ai_data.get('date_range') or {}
#     date_str = date_range.get('start')
    
#     context_parts = []
#     if social_context: 
#         context_parts.append(f"looking for {social_context} experience")
#     if mood: 
#         context_parts.append(f"wants {mood} vibe")
#     if keywords: 
#         context_parts.append(f"interested in: {', '.join(keywords)}")
#     if inferred_keywords:
#         context_parts.append(f"likes: {', '.join(inferred_keywords)}")
#     if category: 
#         context_parts.append(f"wants: {category}")
#     if date_str: 
#         context_parts.append(f"for date: {date_str}")
    
#     context_description = ". ".join(context_parts) if context_parts else "looking for recommendations in Buenos Aires"
    
#     lang_map = {
#         'te': "CRITICAL: Respond ENTIRELY in Telugu using Telugu script (తెలుగు).",
#         'he': "CRITICAL: Respond ENTIRELY in Hebrew using Hebrew script (עברית).",
#         'ar': "CRITICAL: Respond ENTIRELY in Arabic using Arabic script (العربية).",
#         'hi': "CRITICAL: Respond ENTIRELY in Hindi using Devanagari script (हिन्दी).",
#         'es': "IMPORTANT: Respond in Spanish.",
#         'pt': "IMPORTANT: Respond in Portuguese.",
#         'fr': "IMPORTANT: Respond in French.",
#     }
#     lang_instruction = lang_map.get(user_language, "IMPORTANT: Respond in English.")
    
#     expert_prompt = f"""You are Yara, the ULTIMATE Buenos Aires expert and local tour guide. 
# You know EVERYTHING about Buenos Aires - every bar, every restaurant, every café, every hidden gem, every event, every neighborhood.

# USER'S REQUEST: "{user_input}"
# USER CONTEXT: {context_description}

# YOUR MISSION: Give them 2-3 PERFECT, SPECIFIC recommendations that match their request.

# CRITICAL RULES - READ CAREFULLY:
# 1. ✅ BE POSITIVE AND CONFIDENT - You're an expert who knows the BEST places in Buenos Aires
# 2. ✅ Give 2-3 SPECIFIC place names with neighborhoods (Palermo, San Telmo, Recoleta, etc.)
# 3. ✅ Explain WHY each place is perfect for their request
# 4. ✅ Be enthusiastic and use emojis (🎯, ✨, 🍸, 🎵, etc.)
# 5. ❌ NEVER EVER say negative things like:
#    - "sorry"
#    - "not found"
#    - "don't have"
#    - "couldn't find"
#    - "no matches"
#    - "unfortunately"
# 6. ✅ Instead, say positive things like:
#    - "I know the perfect spots!"
#    - "Great choice! Here are amazing places!"
#    - "You'll love these!"
#    - "Perfect! Buenos Aires has incredible options!"

# FORMAT YOUR RESPONSE EXACTLY LIKE THIS:
# "[Enthusiastic intro acknowledging their request - NO negativity!]

# 🎯 **[Place Name]** in [Neighborhood]
# [One sentence why it's perfect for them]

# 🎯 **[Place Name]** in [Neighborhood]
# [One sentence why it's perfect for them]

# 🎯 **[Place Name]** in [Neighborhood]
# [One sentence why it's perfect for them]

# [Friendly closing with emoji]"

# EXAMPLES OF GOOD INTROS (use similar tone):
# - "Great choice! I know some incredible spots for that!" ✅
# - "Perfect! Buenos Aires has amazing places for this!" ✅
# - "Excellent! Here are some fantastic options!" ✅

# EXAMPLES OF BAD INTROS (NEVER use these):
# - "Sorry, I don't have information..." ❌
# - "Unfortunately, I couldn't find..." ❌

# {lang_instruction}

# Remember: You're a confident expert. You ALWAYS have great recommendations!"""

#     try:
#         response = openai.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[
#                 {"role": "system", "content": "You are Yara, the ultimate Buenos Aires expert who knows EVERYTHING about the city. You're always positive, enthusiastic, and helpful. You NEVER say negative things. You always have great recommendations because you're a real expert."}, 
#                 {"role": "user", "content": expert_prompt}
#             ],
#             temperature=0.8,
#             timeout=10
#         )
#         expert_response = response.choices[0].message.content
#         logger.info(f"🎯 Expert Fallback Response Generated in {user_language}")
#         return expert_response
    
#     except Exception as e:
#         logger.error(f"Fallback Error: {e}")
#         fallback_map = {
#             'te': "బ్యూనస్ ఎయిర్స్‌లో మీ కోసం కొన్ని అద్భుతమైన ప్రదేశాలు ఉన్నాయి! మరిన్ని వివరాలు ఇవ్వండి, నేను ఉత్తమ ప్రదేశాలను సూచిస్తాను! 🎯",
#             'he': "יש כמה מקומות מדהימים בבואנוס איירס בשבילך! ספר לי עוד פרטים ואני אמליץ על המקומות הכי טובים! 🎯",
#             'ar': "لدي أماكن رائعة في بوينس آيريس لك! أخبرني المزيد من التفاصيل وسأوصي بأفضل الأماكن! 🎯",
#             'es': "¡Conozco lugares increíbles en Buenos Aires para ti! Cuéntame más detalles y te recomendaré los mejores sitios! 🎯",
#             'pt': "Conheço lugares incríveis em Buenos Aires para você! Me conte mais detalhes e recomendarei os melhores lugares! 🎯",
#         }
#         return fallback_map.get(user_language, "I know some amazing places in Buenos Aires for you! Tell me more details and I'll recommend the best spots! 🎯")

# # ==============================================================================
# # MAJOR FIX: PROPER SEARCH LOGIC - DON'T MIX EVENTS AND BUSINESSES
# # ==============================================================================

# def process_message_thread(sender, text):
#     conn = None
#     try:
#         conn = postgreSQL_pool.getconn()
#         user = get_user(conn, sender)

#         if not user:
#             create_user(conn, sender)
#             send_whatsapp_message(sender, "Hey! Welcome to Yara ai , I'm your Buenos Aires guide for finding the best plans in the city ✨ what are you in the mood for?")
#             return

#         step, user_age = user.get('conversation_step'), user.get('age', '25')
        
#         ai_data = executor.submit(analyze_user_intent, text).result() or {"user_language": "en"}
#         user_language = ai_data.get('user_language', 'en')
#         social_context = ai_data.get('social_context')

#         logger.info(f"🌍 Detected Language: {user_language}")

#         if ai_data.get('is_greeting') and step != 'ask_name_age':
#             user_name = user.get('name', 'there')
#             greetings = {'te': f"నమస్కారం {user_name}! మీరు ఏమి వెతుకుతున్నారు?", 'he': f"שלום {user_name}! מה אתה מחפש?", 'ar': f"مرحباً {user_name}! ماذا تبحث؟", 'es': f"¡Hola {user_name}! ¿Qué estás buscando hoy?", 'en': f"Hey {user_name}! What are you looking for today?"}
#             send_whatsapp_message(sender, greetings.get(user_language, greetings['en']))
#             return

#         if step == 'welcome':
#             messages = {'te': "మొదట, మీకు ఉత్తమ సూచనలు ఇవ్వడానికి, మీ పేరు మరియు వయస్సు ఏమిటి?", 'he': "קודם כל, מה שמך וגילך?", 'ar': "أولاً، ما هو اسمك وعمرك؟", 'es': "Primero, ¿cuál es tu nombre y edad?", 'en': "First, what's your name and age?"}
#             send_whatsapp_message(sender, messages.get(user_language, messages['en']))
#             update_user(conn, sender, {"conversation_step": "ask_name_age", "last_mood": text})
#             return

#         if step == 'ask_name_age':
#             last_mood = user.get('last_mood')
#             messages = {'te': f"సరే! '{last_mood}' కోసం చూపిస్తున్నాను:", 'he': f"מעולה! מראה אפשרויות עבור '{last_mood}':", 'ar': f"رائع! عرض الخيارات لـ '{last_mood}':", 'es': f"¡Perfecto! Buscando opciones para '{last_mood}':", 'en': f"Ok cool! Showing options for '{last_mood}':"}
#             send_whatsapp_message(sender, messages.get(user_language, messages['en']))
            
#             clean_name = re.sub(r'[^\w]', '', text.split()[0]) if text.split() else "Friend"
#             age = "".join(filter(str.isdigit, text)) or "25"
            
#             update_user(conn, sender, {"name": clean_name, "age": age, "conversation_step": "ready"})
#             text = last_mood 
#             ai_data = analyze_user_intent(text) or {"user_language": "en"}
#             user_language = ai_data.get('user_language', 'en')
#             social_context = ai_data.get('social_context')

#         # ===================================================================
#         # FIXED SEARCH LOGIC: DON'T MIX EVENTS AND BUSINESSES
#         # ===================================================================
        
#         found_something = False
#         category = ai_data.get('category', '').lower()
        
#         # Determine what user is SPECIFICALLY asking for
#         wants_events = (
#             ai_data.get('date_range') or  # Has specific date = wants events
#             category in ['event', 'concert', 'show', 'party', 'festival', 'exhibition']
#         )
        
#         wants_businesses = category in ['bar', 'restaurant', 'cafe', 'club', 'shop', 'mall']
        
#         logger.info(f"🎯 User wants - Events: {wants_events}, Businesses: {wants_businesses}")
        
#         # CASE 1: User SPECIFICALLY wants EVENTS
#         if wants_events and not wants_businesses:
#             logger.info("🔍 Searching EVENTS only...")
#             events = smart_search(conn, 'events', ai_data)
            
#             if events:
#                 found_something = True
#                 intro = translate_text(f"Here are some events matching your vibe:", user_language)
#                 if ai_data.get('date_range') and ai_data['date_range'].get('start'):
#                     intro = translate_text(f"Here's what's happening around {ai_data['date_range']['start']}:", user_language)
#                 send_whatsapp_message(sender, intro)
                
#                 for e in events:
#                     futures = {
#                         'jfy': executor.submit(generate_just_for_you, user_age, e['title'], e['description'], e.get('mood', 'social'), social_context, user_language),
#                         'title': executor.submit(translate_text, e.get('title'), user_language),
#                         'desc': executor.submit(translate_text, e.get('description'), user_language)
#                     }
#                     display_date = e.get('event_date') if e.get('event_date') else f"Every {e.get('recurring_day')}"
#                     caption = f"*{futures['title'].result()}*\n\n📍 {translate_text(e.get('location'), user_language)}\n🕒 {e.get('event_time')}\n📅 {display_date}\n🎵 {translate_text(e.get('music_type'), user_language)}\n📝 {futures['desc'].result()}\n📸 {e.get('instagram_link')}\n\n{futures['jfy'].result()}"
#                     send_whatsapp_message(sender, caption, media_url=e.get('image_url'))
            
#             # If no events found, go straight to ChatGPT (DON'T search businesses)
#             if not found_something:
#                 logger.info("🎯 No events found - Using ChatGPT fallback for events")
#                 send_whatsapp_message(sender, ask_chatgpt_expert_fallback(text, ai_data, user_language))
#                 return
        
#         # CASE 2: User SPECIFICALLY wants BUSINESSES
#         elif wants_businesses and not wants_events:
#             logger.info("🔍 Searching BUSINESSES only...")
#             businesses = smart_search(conn, 'businesses', ai_data)
            
#             if businesses:
#                 found_something = True
#                 intro = translate_text("Found these spots for you:", user_language)
#                 send_whatsapp_message(sender, intro)
                
#                 for b in businesses:
#                     futures = {
#                         'jfy': executor.submit(generate_just_for_you, user_age, b['name'], b['description'], ai_data.get('target_mood') or 'chill', social_context, user_language),
#                         'name': executor.submit(translate_text, b.get('name'), user_language),
#                         'desc': executor.submit(translate_text, b.get('description'), user_language)
#                     }
#                     msg = f"*{futures['name'].result()}*\n📍 {translate_text(b.get('location'), user_language)}\n\n{futures['desc'].result()}\n\n📸 {b.get('instagram_link')}\n\n{futures['jfy'].result()}"
#                     send_whatsapp_message(sender, msg, media_url=b.get('image_url'))
            
#             # If no businesses found, go straight to ChatGPT (DON'T search events)
#             if not found_something:
#                 logger.info("🎯 No businesses found - Using ChatGPT fallback for businesses")
#                 send_whatsapp_message(sender, ask_chatgpt_expert_fallback(text, ai_data, user_language))
#                 return
        
#         # CASE 3: Ambiguous query - search BOTH
#         else:
#             logger.info("🔍 Ambiguous query - Searching both events and businesses...")
            
#             # Try events first
#             events = smart_search(conn, 'events', ai_data)
#             if events:
#                 found_something = True
#                 intro = translate_text(f"Here are some events matching your vibe:", user_language)
#                 send_whatsapp_message(sender, intro)
                
#                 for e in events:
#                     futures = {
#                         'jfy': executor.submit(generate_just_for_you, user_age, e['title'], e['description'], e.get('mood', 'social'), social_context, user_language),
#                         'title': executor.submit(translate_text, e.get('title'), user_language),
#                         'desc': executor.submit(translate_text, e.get('description'), user_language)
#                     }
#                     display_date = e.get('event_date') if e.get('event_date') else f"Every {e.get('recurring_day')}"
#                     caption = f"*{futures['title'].result()}*\n\n📍 {translate_text(e.get('location'), user_language)}\n🕒 {e.get('event_time')}\n📅 {display_date}\n🎵 {translate_text(e.get('music_type'), user_language)}\n📝 {futures['desc'].result()}\n📸 {e.get('instagram_link')}\n\n{futures['jfy'].result()}"
#                     send_whatsapp_message(sender, caption, media_url=e.get('image_url'))
            
#             # Try businesses
#             businesses = smart_search(conn, 'businesses', ai_data)
#             if businesses:
#                 found_something = True
#                 intro = translate_text("Found these spots for you:", user_language)
#                 send_whatsapp_message(sender, intro)
                
#                 for b in businesses:
#                     futures = {
#                         'jfy': executor.submit(generate_just_for_you, user_age, b['name'], b['description'], ai_data.get('target_mood') or 'chill', social_context, user_language),
#                         'name': executor.submit(translate_text, b.get('name'), user_language),
#                         'desc': executor.submit(translate_text, b.get('description'), user_language)
#                     }
#                     msg = f"*{futures['name'].result()}*\n📍 {translate_text(b.get('location'), user_language)}\n\n{futures['desc'].result()}\n\n📸 {b.get('instagram_link')}\n\n{futures['jfy'].result()}"
#                     send_whatsapp_message(sender, msg, media_url=b.get('image_url'))
            
#             # If nothing found in both, use ChatGPT
#             if not found_something:
#                 logger.info("🎯 Nothing found in both tables - Using ChatGPT fallback")
#                 send_whatsapp_message(sender, ask_chatgpt_expert_fallback(text, ai_data, user_language))
#                 return
        
#         # Send closing message if something was found
#         if found_something:
#             send_whatsapp_message(sender, generate_closing_message(text, user_language))

#     except Exception as e:
#         logger.error(f"Logic Error: {e}", exc_info=True)
#         try:
#             ai_data = analyze_user_intent(text) or {"user_language": "en"}
#             user_language = ai_data.get('user_language', 'en')
#             send_whatsapp_message(sender, ask_chatgpt_expert_fallback(text, ai_data, user_language))
#         except:
#             send_whatsapp_message(sender, "I know some amazing places in Buenos Aires! Tell me what you're looking for and I'll recommend the best spots! 🎯")
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
#     if not sender_id or not incoming_msg: return "" 
    
#     resp = MessagingResponse()
#     threading.Thread(target=process_message_thread, args=(sender_id, incoming_msg)).start()
#     return str(resp)

# if __name__ == "__main__":
#     print("🚀 Twilio WhatsApp Bot Starting...")
#     print("✨ Enhanced Features:")
#     print("   - Fully Multi-language (English DEFAULT)")
#     print("   - Intelligent Abstract Search (e.g., 'artistic events')")
#     print("   - Auto-translation of all content")
#     print("   - Images with all recommendations")
#     print("   - ALWAYS POSITIVE responses - never shows errors")
#     print("   - Expert fallback for empty database results")
#     print("   - FIXED: Events stay in events, businesses stay in businesses")
#     app.run(port=5000)

#who you are,typing indicators,blue tickss,uploading an event,ticket link for booking in recommendaations,giving i=the desription in english if f=defaut is english 
# import os
# import logging
# import psycopg2
# import threading
# import json
# import re
# import requests  # Required for the Typing Indicator API
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
#     UPDATED: Now includes 'wants_to_upload' to detect event submission requests.
#     """
#     today_str = date.today().strftime("%Y-%m-%d")
#     weekday_str = date.today().strftime("%A")
    
#     system_prompt = (
#         f"Current Date: {today_str} ({weekday_str}). "
#         "You are a multilingual AI that understands ALL languages. "
#         "Your job is to analyze a user's request for events or businesses in Buenos Aires and extract structured data."
        
#         "EXTRACT THE FOLLOWING (return as JSON):\n"
        
#         "1. 'is_greeting': boolean (true ONLY if message is JUST 'hi', 'hello', 'hola', 'hey' with ABSOLUTELY NO OTHER REQUEST. If user says 'hi' AND asks for anything else, return FALSE)\n"
#         "   Examples:\n"
#         "   - 'hi' → is_greeting: true ✅\n"
#         "   - 'hello' → is_greeting: true ✅\n"
#         "   - 'hi any events on Dec 6' → is_greeting: FALSE ❌ (has request!)\n"
#         "   - 'hello where can I find bars' → is_greeting: FALSE ❌ (has request!)\n"
        
#         "2. 'is_identity_question': boolean. True if user asks 'Who am I?', 'What is my name?', 'Do you know me?', 'What do you know about me?'.\n"
        
#         "3. 'wants_to_upload': boolean. True if user asks to 'upload event', 'submit event', 'add my party', 'post an event', 'share an event'.\n"
        
#         "4. 'date_range': {'start': 'YYYY-MM-DD', 'end': 'YYYY-MM-DD'} or null\n"
        
#         "5. 'target_mood': string (romantic, chill, energetic, party, relaxed, upscale, casual)\n"
        
#         "6. 'social_context': string (date, friends, solo, family, business)\n"
        
#         "7. 'category': string (event, concert, show, bar, restaurant, cafe, etc.)\n"
        
#         "8. 'specific_keywords': List of DIRECT and SPECIFIC keywords from the user's text. "
#         "   - Examples: 'Salsa', 'Techno', 'Jazz', 'Rooftop', 'Live music'.\n"
        
#         "9. 'user_language': detected ISO 639-1 language code (en, es, te, he, ar, etc.). Default to 'en' if uncertain.\n"

#         "10. 'inferred_keywords': List of related, searchable keywords if the user's request is abstract. "
#         "   - If the user asks for 'artistic' or 'cultural' things, infer related concrete terms.\n"
#         "   - If the user's request is already specific (e.g., 'techno'), this can be null.\n"
#         "   - Examples:\n"
#         "     * User says 'artistic events' → inferred_keywords: ['art', 'gallery', 'exhibition', 'museum', 'theatre', 'performance', 'cultural']\n"
#         "     * User says 'something intellectual' → inferred_keywords: ['lecture', 'talk', 'book', 'museum', 'cinema', 'art']\n"
#         "     * User says 'a place with a nice view' → inferred_keywords: ['rooftop', 'terrace', 'view', 'balcony']\n"
        
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
#             return {"user_language": "en"}
        
#         if not data.get('user_language') or data.get('user_language') == 'unknown':
#             data['user_language'] = 'en'
        
#         logger.info(f"🧠 AI Analysis: {data}")
#         return data
        
#     except Exception as e:
#         logger.error(f"AI Intent Error: {e}")
#         return {"user_language": "en"}

# def generate_just_for_you(user_age, item_name, item_desc, item_mood, social_context=None, user_language='en'):
#     """
#     Enhanced: Now generates personalized recommendations in user's detected language
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
        
#         # Language instruction
#         lang_instruction = f"Respond in the language code: {user_language}. "
#         if user_language == 'te':
#             lang_instruction += "Use Telugu script and language."
#         elif user_language == 'he':
#             lang_instruction += "Use Hebrew script and language."
#         elif user_language == 'ar':
#             lang_instruction += "Use Arabic script and language."
#         elif user_language == 'hi':
#             lang_instruction += "Use Hindi script and language."
#         elif user_language == 'es':
#             lang_instruction += "Use Spanish language."
#         elif user_language == 'pt':
#             lang_instruction += "Use Portuguese language."
#         elif user_language == 'fr':
#             lang_instruction += "Use French language."
#         else:
#             lang_instruction += "Use English language."
        
#         prompt = (
#             f"{lang_instruction} "
#             f"Write a 1-sentence recommendation for a {user_age} year old. "
#             f"Venue: {item_name}. Vibe: {item_mood}. {context_msg} "
#             "Start with '✨ Just for you:' or equivalent in the target language. Be enthusiastic and specific."
#         )
        
#         response = openai.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[{"role": "user", "content": prompt}],
#             temperature=0.7,
#             timeout=5
#         )
#         return response.choices[0].message.content.replace('"', '')
#     except Exception as e:
#         logger.error(f"Just for you error: {e}")
#         if user_language == 'te':
#             return f"✨ మీ కోసం: ఇది {item_mood} వైబ్‌తో సరిపోతుంది! {context_msg}"
#         elif user_language == 'he':
#             return f"✨ בשבילך: זה מתאים ל{item_mood} אווירה! {context_msg}"
#         elif user_language == 'ar':
#             return f"✨ لك خصيصاً: هذا يناسب الأجواء {item_mood}! {context_msg}"
#         elif user_language == 'es':
#             return f"✨ Just for you: ¡Esto coincide con el ambiente {item_mood}! {context_msg}"
#         else:
#             return f"✨ Just for you: This matches the {item_mood} vibe! {context_msg}"

# def translate_text(text, target_language):
#     if not text:
#         return text
    
#     try:
#         lang_map = {
#             'es': 'Spanish', 'pt': 'Portuguese', 'fr': 'French', 'de': 'German', 
#             'it': 'Italian', 'ru': 'Russian', 'ar': 'Arabic', 'he': 'Hebrew', 
#             'hi': 'Hindi', 'te': 'Telugu', 'ta': 'Tamil', 'ko': 'Korean', 
#             'ja': 'Japanese', 'zh': 'Chinese'
#         }
#         lang_name = lang_map.get(target_language, 'English')
        
#         response = openai.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[
#                 {"role": "system", "content": f"Translate the following text to {lang_name}. Maintain original tone. Only return the translation."},
#                 {"role": "user", "content": text}
#             ],
#             temperature=0.3,
#             timeout=5
#         )
#         translated = response.choices[0].message.content.strip()
#         return translated if translated else text
#     except Exception as e:
#         logger.error(f"Translation error: {e}")
#         return text

# def generate_closing_message(user_query, user_language='en'):
#     try:
#         lang_instruction_map = {
#             'te': "Respond in Telugu using Telugu script.", 'he': "Respond in Hebrew using Hebrew script.",
#             'ar': "Respond in Arabic using Arabic script.", 'hi': "Respond in Hindi using Devanagari script.",
#             'es': "Respond in Spanish.", 'pt': "Respond in Portuguese.", 'fr': "Respond in French."
#         }
#         lang_instruction = lang_instruction_map.get(user_language, "Respond in English.")
        
#         prompt = (
#             f"User query: '{user_query}'. I sent recommendations. "
#             f"Write a SHORT closing message asking if they want more suggestions. "
#             f"Use 1 emoji. Be friendly. {lang_instruction}"
#         )
        
#         response = openai.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[{"role": "system", "content": "You are Yara, a friendly Buenos Aires guide. You know everything."}, {"role": "user", "content": prompt}],
#             temperature=0.7,
#             timeout=4
#         )
#         return response.choices[0].message.content.replace('"', '')
#     except:
#         fallback_map = {
#             'te': "మరిన్ని సూచనలు కావాలా? 🎉", 'he': "צריך עוד המלצות? 🎉",
#             'ar': "هل تحتاج المزيد من الاقتراحات؟ 🎉", 'es': "¿Te gustaría más sugerencias? 🎉",
#             'pt': "Gostaria de mais sugestões? 🎉"
#         }
#         return fallback_map.get(user_language, "Need more suggestions? 🎉")

# # --- DATABASE FUNCTIONS ---

# def get_user(conn, phone):
#     with conn.cursor() as cur:
#         cur.execute("SELECT * FROM public.users WHERE phone = %s", (phone,))
#         return cur.fetchone()

# def create_user(conn, phone):
#     with conn.cursor() as cur:
#         cur.execute(
#             "INSERT INTO public.users (phone, conversation_step) VALUES (%s, 'welcome') ON CONFLICT (phone) DO NOTHING", (phone,)
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
#     UPDATED: Now includes 'inferred_keywords' for intelligent searching.
#     """
#     query = f"SELECT * FROM public.{table} WHERE 1=1"
#     args = []
    
#     date_range = ai_data.get('date_range') or {}
#     social_context = ai_data.get('social_context')
    
#     search_terms = []
    
#     if ai_data.get('specific_keywords'):
#         search_terms.extend(ai_data.get('specific_keywords'))

#     if ai_data.get('inferred_keywords'):
#         search_terms.extend(ai_data.get('inferred_keywords'))
    
#     if ai_data.get('target_mood'):
#         search_terms.append(ai_data.get('target_mood'))
    
#     if social_context == 'date':
#         search_terms.extend(['romantic', 'intimate', 'cozy'])
#     elif social_context == 'friends':
#         search_terms.extend(['social', 'group', 'casual'])
    
#     cat = ai_data.get('category', '')
#     if cat and len(cat) > 3 and cat.lower() not in ['event', 'party', 'show', 'place', 'spot']:
#         search_terms.append(cat)
    
#     search_terms = list(set([t for t in search_terms if t and len(t) > 2]))
    
#     logger.info(f"🔍 Search Terms (Level {strictness_level}): {search_terms}")

#     # --- DATE LOGIC (for events) ---
#     if table == 'events' and date_range:
#         start, end = date_range.get('start'), date_range.get('end')
#         if start and end:
#             start_obj = datetime.strptime(start, "%Y-%m-%d").date()
#             end_obj = datetime.strptime(end, "%Y-%m-%d").date()
#             days_in_range = [ (start_obj + timedelta(days=i)).strftime('%A') for i in range((end_obj - start_obj).days + 1) ]
#             days_tuple = tuple(set(days_in_range))
#             query += " AND ((event_date >= %s::date AND event_date <= %s::date) OR (recurring_day = ANY(%s)))"
#             args.extend([start, end, list(days_tuple)])

#     # --- TEXT SEARCH LOGIC ---
#     if search_terms:
#         term_conditions = [f"(title ILIKE %s OR description ILIKE %s OR mood ILIKE %s OR music_type ILIKE %s OR location ILIKE %s)" for _ in search_terms] if table == 'events' else [f"(name ILIKE %s OR description ILIKE %s OR location ILIKE %s OR type ILIKE %s)" for _ in search_terms]
        
#         for term in search_terms:
#             term_wild = f"%{term}%"
#             args.extend([term_wild] * (5 if table == 'events' else 4))
        
#         join_operator = " AND " if strictness_level == 1 else " OR "
#         query += f" AND ({join_operator.join(term_conditions)})"

#     query += " ORDER BY event_date ASC LIMIT 5" if table == 'events' else " LIMIT 5"

#     logger.info(f"📊 SQL Query: {query[:200]}...")
#     logger.info(f"📊 Args: {args}")
    
#     return query, args

# def smart_search(conn, table, ai_data):
#     """
#     UPDATED: Added try-catch to prevent crashes. Returns empty list on error.
#     """
#     try:
#         query, args = build_search_query(table, ai_data, strictness_level=1)
#         with conn.cursor() as cur:
#             cur.execute(query, tuple(args))
#             results = cur.fetchall()
#             if results:
#                 logger.info(f"✅ Found {len(results)} results (Strict)")
#                 return results

#         query, args = build_search_query(table, ai_data, strictness_level=2)
#         with conn.cursor() as cur:
#             cur.execute(query, tuple(args))
#             results = cur.fetchall()
#             if results:
#                 logger.info(f"✅ Found {len(results)} results (Loose)")
#                 return results
#             else:
#                 logger.warning(f"⚠️ No results in {table}")
#                 return []
    
#     except Exception as e:
#         logger.error(f"❌ Search error in {table}: {e}")
#         return []

# # ==============================================================================
# # 🚀 TWILIO TYPING INDICATOR (NEW FEATURE)
# # ==============================================================================

# def send_typing_indicator(message_sid):
#     """
#     Sends a 'Typing' status to the WhatsApp user.
#     This also marks the user's message as Read (Blue Ticks).
#     """
#     if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN: 
#         return
    
#     try:
#         url = "https://messaging.twilio.com/v2/Indicators/Typing.json"
        
#         # Twilio Auth
#         auth = (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        
#         # Payload as per docs
#         data = {
#             "messageId": message_sid,
#             "channel": "whatsapp"
#         }
        
#         # Fire and forget request (timeout short to not block execution)
#         response = requests.post(url, auth=auth, data=data, timeout=2)
        
#         if response.status_code == 200:
#             logger.info("✅ Typing indicator sent (Blue Ticks triggered)")
#         else:
#             logger.warning(f"⚠️ Typing indicator failed: {response.text}")
            
#     except Exception as e:
#         logger.error(f"❌ Error sending typing indicator: {e}")

# def send_whatsapp_message(to, body, media_url=None):
#     if not TWILIO_WHATSAPP_NUMBER: 
#         return
    
#     try:
#         message_data = {
#             'from_': TWILIO_WHATSAPP_NUMBER,
#             'to': to,
#             'body': body
#         }
#         if media_url:
#             message_data['media_url'] = media_url
            
#         twilio_client.messages.create(**message_data)
#     except Exception as e:
#         logger.error(f"❌ Twilio Error: {e}")

# def ask_chatgpt_expert_fallback(user_input, ai_data, user_language='en'):
#     """
#     UPDATED: Prompt rewritten to be ALWAYS POSITIVE. Never says "not found" or "sorry"
#     """
#     category = ai_data.get('category')
#     mood = ai_data.get('target_mood')
#     social_context = ai_data.get('social_context')
#     keywords = ai_data.get('specific_keywords', [])
#     inferred_keywords = ai_data.get('inferred_keywords', [])
#     date_range = ai_data.get('date_range') or {}
#     date_str = date_range.get('start')
    
#     context_parts = []
#     if social_context: 
#         context_parts.append(f"looking for {social_context} experience")
#     if mood: 
#         context_parts.append(f"wants {mood} vibe")
#     if keywords: 
#         context_parts.append(f"interested in: {', '.join(keywords)}")
#     if inferred_keywords:
#         context_parts.append(f"likes: {', '.join(inferred_keywords)}")
#     if category: 
#         context_parts.append(f"wants: {category}")
#     if date_str: 
#         context_parts.append(f"for date: {date_str}")
    
#     context_description = ". ".join(context_parts) if context_parts else "looking for recommendations in Buenos Aires"
    
#     lang_map = {
#         'te': "CRITICAL: Respond ENTIRELY in Telugu using Telugu script (తెలుగు).",
#         'he': "CRITICAL: Respond ENTIRELY in Hebrew using Hebrew script (עברית).",
#         'ar': "CRITICAL: Respond ENTIRELY in Arabic using Arabic script (العربية).",
#         'hi': "CRITICAL: Respond ENTIRELY in Hindi using Devanagari script (हिन्दी).",
#         'es': "IMPORTANT: Respond in Spanish.",
#         'pt': "IMPORTANT: Respond in Portuguese.",
#         'fr': "IMPORTANT: Respond in French.",
#     }
#     lang_instruction = lang_map.get(user_language, "IMPORTANT: Respond in English.")
    
#     expert_prompt = f"""You are Yara, the ULTIMATE Buenos Aires expert and local tour guide. 
# You know EVERYTHING about Buenos Aires - every bar, every restaurant, every café, every hidden gem, every neighborhood.

# USER'S REQUEST: "{user_input}"
# USER CONTEXT: {context_description}

# YOUR MISSION: Give them 2-3 PERFECT, SPECIFIC recommendations that match their request.

# CRITICAL RULES - READ CAREFULLY:
# 1. ✅ BE POSITIVE AND CONFIDENT - You're an expert who knows the BEST places in Buenos Aires
# 2. ✅ Give 2-3 SPECIFIC place names with neighborhoods (Palermo, San Telmo, Recoleta, etc.)
# 3. ✅ Explain WHY each place is perfect for their request
# 4. ✅ Be enthusiastic and use emojis (🎯, ✨, 🍸, 🎵, etc.)
# 5. ❌ NEVER EVER say negative things like:
#    - "sorry"
#    - "not found"
#    - "don't have"
#    - "couldn't find"
#    - "no matches"
#    - "unfortunately"
# 6. ✅ Instead, say positive things like:
#    - "I know the perfect spots!"
#    - "Great choice! Here are amazing places!"
#    - "You'll love these!"
#    - "Perfect! Buenos Aires has incredible options!"

# FORMAT YOUR RESPONSE EXACTLY LIKE THIS:
# "[Enthusiastic intro acknowledging their request - NO negativity!]

# 🎯 **[Place Name]** in [Neighborhood]
# [One sentence why it's perfect for them]

# 🎯 **[Place Name]** in [Neighborhood]
# [One sentence why it's perfect for them]

# 🎯 **[Place Name]** in [Neighborhood]
# [One sentence why it's perfect for them]

# [Friendly closing with emoji]"

# EXAMPLES OF GOOD INTROS (use similar tone):
# - "Great choice! I know some incredible spots for that!" ✅
# - "Perfect! Buenos Aires has amazing places for this!" ✅
# - "Excellent! Here are some fantastic options!" ✅

# EXAMPLES OF BAD INTROS (NEVER use these):
# - "Sorry, I don't have information..." ❌
# - "Unfortunately, I couldn't find..." ❌

# {lang_instruction}

# Remember: You're a confident expert. You ALWAYS have great recommendations!"""

#     try:
#         response = openai.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[
#                 {"role": "system", "content": "You are Yara, the ultimate Buenos Aires expert who knows EVERYTHING about the city. You're always positive, enthusiastic, and helpful. You NEVER say negative things. You always have great recommendations because you're a real expert."}, 
#                 {"role": "user", "content": expert_prompt}
#             ],
#             temperature=0.8,
#             timeout=10
#         )
#         expert_response = response.choices[0].message.content
#         logger.info(f"🎯 Expert Fallback Response Generated in {user_language}")
#         return expert_response
    
#     except Exception as e:
#         logger.error(f"Fallback Error: {e}")
#         fallback_map = {
#             'te': "బ్యూనస్ ఎయిర్స్‌లో మీ కోసం కొన్ని అద్భుతమైన ప్రదేశాలు ఉన్నాయి! మరిన్ని వివరాలు ఇవ్వండి, నేను ఉత్తమ ప్రదేశాలను సూచిస్తాను! 🎯",
#             'he': "יש כמה מקומות מדהימים בבואנוס איירס בשבילך! ספר לי עוד פרטים ואני אמליץ על המקומות הכי טובים! 🎯",
#             'ar': "لدي أماكن رائعة في بوينس آيريس لك! أخبرني المزيد من التفاصيل وسأوصي بأفضل الأماكن! 🎯",
#             'es': "¡Conozco lugares increíbles en Buenos Aires para ti! Cuéntame más detalles y te recomendaré los mejores sitios! 🎯",
#             'pt': "Conheço lugares incríveis em Buenos Aires para você! Me conte mais detalhes e recomendarei os melhores lugares! 🎯",
#         }
#         return fallback_map.get(user_language, "I know some amazing places in Buenos Aires for you! Tell me more details and I'll recommend the best spots! 🎯")

# # ==============================================================================
# # PROCESS THREAD (Updated with MessageSid & Identity Check & Upload Feature)
# # ==============================================================================

# def process_message_thread(sender, text, message_sid=None):
#     """
#     UPDATED: Now accepts message_sid to trigger the typing indicator immediately.
#     """
    
#     # 1. Trigger Typing Indicator & Blue Ticks IMMEDIATELY
#     if message_sid:
#         send_typing_indicator(message_sid)
        
#     conn = None
#     try:
#         conn = postgreSQL_pool.getconn()
#         user = get_user(conn, sender)

#         if not user:
#             create_user(conn, sender)
#             send_whatsapp_message(sender, "Hey! Welcome to Yara ai , I'm your Buenos Aires guide for finding the best plans in the city ✨ what are you in the mood for?")
#             return

#         step, user_age = user.get('conversation_step'), user.get('age', '25')
#         user_name = user.get('name', 'Friend') # Retrieve Name from DB
        
#         ai_data = executor.submit(analyze_user_intent, text).result() or {"user_language": "en"}
#         user_language = ai_data.get('user_language', 'en')
#         social_context = ai_data.get('social_context')

#         logger.info(f"🌍 Detected Language: {user_language}")

#         # --- 1. HANDLE GREETINGS ---
#         if ai_data.get('is_greeting') and step != 'ask_name_age':
#             greetings = {'te': f"నమస్కారం {user_name}! మీరు ఏమి వెతుకుతున్నారు?", 'he': f"שלום {user_name}! מה אתה מחפש?", 'ar': f"مرحباً {user_name}! ماذا تبحث؟", 'es': f"¡Hola {user_name}! ¿Qué estás buscando hoy?", 'en': f"Hey {user_name}! What are you looking for today?"}
#             send_whatsapp_message(sender, greetings.get(user_language, greetings['en']))
#             return

#         # --- 2. HANDLE IDENTITY QUESTIONS ("Who am I?") --- 
#         if ai_data.get('is_identity_question'):
#             logger.info("👤 Identity question detected.")
            
#             last_mood = user.get('last_mood', 'mystery')
            
#             identity_prompt = (
#                 f"The user asked 'Who am I?' or 'What do you know about me?'. "
#                 f"User Name: {user_name}. Age: {user_age}. Last thing they looked for: {last_mood}. "
#                 f"Respond in language code '{user_language}'. "
#                 f"Be friendly, witty, and confirm you know them as Yara, their local guide. "
#                 "Example: 'You are [Name], my favorite [Age]-year-old explorer! We were just looking for [last_mood].'"
#             )
            
#             try:
#                 response = openai.chat.completions.create(
#                     model="gpt-4o-mini",
#                     messages=[{"role": "system", "content": "You are Yara."}, {"role": "user", "content": identity_prompt}],
#                     temperature=0.8
#                 )
#                 answer = response.choices[0].message.content.replace('"', '')
#                 send_whatsapp_message(sender, answer)
#                 return  # Stop processing here, don't search database
#             except Exception as e:
#                 logger.error(f"Identity AI Error: {e}")
#                 # Fallback response
#                 send_whatsapp_message(sender, f"You are {user_name}, {user_age} years young! And I'm Yara, your guide! ✨")
#                 return

#         # --- 3. HANDLE UPLOAD/SUBMIT EVENT REQUESTS (NEW FEATURE) ---
#         if ai_data.get('wants_to_upload'):
#             logger.info("📤 User wants to upload an event.")
#             base_msg = "That's great! We love new events. You can upload your event details using this form:"
#             translated_msg = translate_text(base_msg, user_language)
#             final_msg = f"{translated_msg}\n\n👉 https://docs.google.com/forms/d/e/1FAIpQLSdnYmuT-KgXAyZzb1qPiO29waE_lUN_XW8SHiSMA5FW4YsRvQ/viewform?usp=publish-editor"
#             send_whatsapp_message(sender, final_msg)
#             return

#         # --- 4. HANDLE ONBOARDING ---
#         if step == 'welcome':
#             messages = {'te': "మొదట, మీకు ఉత్తమ సూచనలు ఇవ్వడానికి, మీ పేరు మరియు వయస్సు ఏమిటి?", 'he': "קודם כל, מה שמך וגילך?", 'ar': "أولاً، ما هو اسمك وعمرك؟", 'es': "Primero, ¿cuál es tu nombre y edad?", 'en': "First, what's your name and age?"}
#             send_whatsapp_message(sender, messages.get(user_language, messages['en']))
#             update_user(conn, sender, {"conversation_step": "ask_name_age", "last_mood": text})
#             return

#         if step == 'ask_name_age':
#             last_mood = user.get('last_mood')
#             messages = {'te': f"సరే! '{last_mood}' కోసం చూపిస్తున్నాను:", 'he': f"מעולה! מראה אפשרויות עבור '{last_mood}':", 'ar': f"رائع! عرض الخيارات لـ '{last_mood}':", 'es': f"¡Perfecto! Buscando opciones para '{last_mood}':", 'en': f"Ok cool! Showing options for '{last_mood}':"}
#             send_whatsapp_message(sender, messages.get(user_language, messages['en']))
            
#             clean_name = re.sub(r'[^\w]', '', text.split()[0]) if text.split() else "Friend"
#             age = "".join(filter(str.isdigit, text)) or "25"
            
#             update_user(conn, sender, {"name": clean_name, "age": age, "conversation_step": "ready"})
#             text = last_mood 
#             ai_data = analyze_user_intent(text) or {"user_language": "en"}
#             user_language = ai_data.get('user_language', 'en')
#             social_context = ai_data.get('social_context')

#         # ===================================================================
#         # FIXED SEARCH LOGIC: DON'T MIX EVENTS AND BUSINESSES
#         # ===================================================================
        
#         found_something = False
#         category = ai_data.get('category', '').lower()
        
#         # Determine what user is SPECIFICALLY asking for
#         wants_events = (
#             ai_data.get('date_range') or  # Has specific date = wants events
#             category in ['event', 'concert', 'show', 'party', 'festival', 'exhibition']
#         )
        
#         wants_businesses = category in ['bar', 'restaurant', 'cafe', 'club', 'shop', 'mall']
        
#         logger.info(f"🎯 User wants - Events: {wants_events}, Businesses: {wants_businesses}")
        
#         # CASE 1: User SPECIFICALLY wants EVENTS
#         if wants_events and not wants_businesses:
#             logger.info("🔍 Searching EVENTS only...")
#             events = smart_search(conn, 'events', ai_data)
            
#             if events:
#                 found_something = True
#                 intro = translate_text(f"Here are some events matching your vibe:", user_language)
#                 if ai_data.get('date_range') and ai_data['date_range'].get('start'):
#                     intro = translate_text(f"Here's what's happening around {ai_data['date_range']['start']}:", user_language)
#                 send_whatsapp_message(sender, intro)
                
#                 for e in events:
#                     futures = {
#                         'jfy': executor.submit(generate_just_for_you, user_age, e['title'], e['description'], e.get('mood', 'social'), social_context, user_language),
#                         'title': executor.submit(translate_text, e.get('title'), user_language),
#                         'desc': executor.submit(translate_text, e.get('description'), user_language),
#                         'location': executor.submit(translate_text, e.get('location'), user_language),
#                         'music': executor.submit(translate_text, e.get('music_type'), user_language)
#                     }
                    
#                     # Multilingual "Book your slot" text
#                     ticket_section = ""
#                     if e.get('ticket_link'):
#                         book_text_map = {
#                             'en': '🎟️ Book your slot',
#                             'es': '🎟️ Reserva tu lugar',
#                             'pt': '🎟️ Reserve seu lugar',
#                             'fr': '🎟️ Réservez votre place',
#                             'te': '🎟️ మీ స్లాట్‌ను బుక్ చేసుకోండి',
#                             'he': '🎟️ הזמן את המקום שלך',
#                             'ar': '🎟️ احجز مكانك',
#                             'hi': '🎟️ अपनी जगह बुक करें'
#                         }
#                         book_text = book_text_map.get(user_language, '🎟️ Book your slot')
#                         ticket_section = f"\n{book_text}: {e.get('ticket_link')}"
                    
#                     display_date = e.get('event_date') if e.get('event_date') else f"Every {e.get('recurring_day')}"
#                     caption = f"*{futures['title'].result()}*\n\n📍 {futures['location'].result()}\n🕒 {e.get('event_time')}\n📅 {display_date}\n🎵 {futures['music'].result()}\n📝 {futures['desc'].result()}{ticket_section}\n📸 {e.get('instagram_link')}\n\n{futures['jfy'].result()}"
#                     send_whatsapp_message(sender, caption, media_url=e.get('image_url'))
            
#             # If no events found, go straight to ChatGPT (DON'T search businesses)
#             if not found_something:
#                 logger.info("🎯 No events found - Using ChatGPT fallback for events")
#                 send_whatsapp_message(sender, ask_chatgpt_expert_fallback(text, ai_data, user_language))
#                 return
        
#         # CASE 2: User SPECIFICALLY wants BUSINESSES
#         elif wants_businesses and not wants_events:
#             logger.info("🔍 Searching BUSINESSES only...")
#             businesses = smart_search(conn, 'businesses', ai_data)
            
#             if businesses:
#                 found_something = True
#                 intro = translate_text("Found these spots for you:", user_language)
#                 send_whatsapp_message(sender, intro)
                
#                 for b in businesses:
#                     futures = {
#                         'jfy': executor.submit(generate_just_for_you, user_age, b['name'], b['description'], ai_data.get('target_mood') or 'chill', social_context, user_language),
#                         'name': executor.submit(translate_text, b.get('name'), user_language),
#                         'desc': executor.submit(translate_text, b.get('description'), user_language),
#                         'location': executor.submit(translate_text, b.get('location'), user_language)
#                     }
#                     msg = f"*{futures['name'].result()}*\n📍 {futures['location'].result()}\n\n{futures['desc'].result()}\n\n📸 {b.get('instagram_link')}\n\n{futures['jfy'].result()}"
#                     send_whatsapp_message(sender, msg, media_url=b.get('image_url'))
            
#             # If no businesses found, go straight to ChatGPT (DON'T search events)
#             if not found_something:
#                 logger.info("🎯 No businesses found - Using ChatGPT fallback for businesses")
#                 send_whatsapp_message(sender, ask_chatgpt_expert_fallback(text, ai_data, user_language))
#                 return
        
#         # CASE 3: Ambiguous query - search BOTH
#         else:
#             logger.info("🔍 Ambiguous query - Searching both events and businesses...")
            
#             # Try events first
#             events = smart_search(conn, 'events', ai_data)
#             if events:
#                 found_something = True
#                 intro = translate_text(f"Here are some events matching your vibe:", user_language)
#                 send_whatsapp_message(sender, intro)
                
#                 for e in events:
#                     futures = {
#                         'jfy': executor.submit(generate_just_for_you, user_age, e['title'], e['description'], e.get('mood', 'social'), social_context, user_language),
#                         'title': executor.submit(translate_text, e.get('title'), user_language),
#                         'desc': executor.submit(translate_text, e.get('description'), user_language),
#                         'location': executor.submit(translate_text, e.get('location'), user_language),
#                         'music': executor.submit(translate_text, e.get('music_type'), user_language)
#                     }
                    
#                     # Multilingual "Book your slot" text
#                     ticket_section = ""
#                     if e.get('ticket_link'):
#                         book_text_map = {'en': '🎟️ Book your slot', 'es': '🎟️ Reserva tu lugar', 'pt': '🎟️ Reserve seu lugar', 'fr': '🎟️ Réservez votre place', 'te': '🎟️ మీ స్లాట్‌ను బుక్ చేసుకోండి', 'he': '🎟️ הזמן את המקום שלך', 'ar': '🎟️ احجز مكانك', 'hi': '🎟️ अपनी जगह बुक करें'}
#                         book_text = book_text_map.get(user_language, '🎟️ Book your slot')
#                         ticket_section = f"\n{book_text}: {e.get('ticket_link')}"
                    
#                     display_date = e.get('event_date') if e.get('event_date') else f"Every {e.get('recurring_day')}"
#                     caption = f"*{futures['title'].result()}*\n\n📍 {futures['location'].result()}\n🕒 {e.get('event_time')}\n📅 {display_date}\n🎵 {futures['music'].result()}\n📝 {futures['desc'].result()}{ticket_section}\n📸 {e.get('instagram_link')}\n\n{futures['jfy'].result()}"
#                     send_whatsapp_message(sender, caption, media_url=e.get('image_url'))
            
#             # Try businesses
#             businesses = smart_search(conn, 'businesses', ai_data)
#             if businesses:
#                 found_something = True
#                 intro = translate_text("Found these spots for you:", user_language)
#                 send_whatsapp_message(sender, intro)
                
#                 for b in businesses:
#                     futures = {
#                         'jfy': executor.submit(generate_just_for_you, user_age, b['name'], b['description'], ai_data.get('target_mood') or 'chill', social_context, user_language),
#                         'name': executor.submit(translate_text, b.get('name'), user_language),
#                         'desc': executor.submit(translate_text, b.get('description'), user_language),
#                         'location': executor.submit(translate_text, b.get('location'), user_language)
#                     }
#                     msg = f"*{futures['name'].result()}*\n📍 {futures['location'].result()}\n\n{futures['desc'].result()}\n\n📸 {b.get('instagram_link')}\n\n{futures['jfy'].result()}"
#                     send_whatsapp_message(sender, msg, media_url=b.get('image_url'))
            
#             # If nothing found in both, use ChatGPT
#             if not found_something:
#                 logger.info("🎯 Nothing found in both tables - Using ChatGPT fallback")
#                 send_whatsapp_message(sender, ask_chatgpt_expert_fallback(text, ai_data, user_language))
#                 return
        
#         # Send closing message if something was found
#         if found_something:
#             send_whatsapp_message(sender, generate_closing_message(text, user_language))

#     except Exception as e:
#         logger.error(f"Logic Error: {e}", exc_info=True)
#         try:
#             ai_data = analyze_user_intent(text) or {"user_language": "en"}
#             user_language = ai_data.get('user_language', 'en')
#             send_whatsapp_message(sender, ask_chatgpt_expert_fallback(text, ai_data, user_language))
#         except:
#             send_whatsapp_message(sender, "I know some amazing places in Buenos Aires! Tell me what you're looking for and I'll recommend the best spots! 🎯")
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
#     message_sid = request.form.get('MessageSid') # <--- Get the Message ID
    
#     if not sender_id or not incoming_msg: return "" 
    
#     resp = MessagingResponse()
#     # Pass message_sid to the thread
#     threading.Thread(target=process_message_thread, args=(sender_id, incoming_msg, message_sid)).start()
#     return str(resp)

# if __name__ == "__main__":
#     print("🚀 Twilio WhatsApp Bot Starting...")
#     print("✨ Features: Typing Indicators, Identity, Upload Link")
    # app.run(port=5000)



#whats ahppening toomorrow 
# import os
# import logging
# import psycopg2
# import threading
# import json
# import re
# import requests  # Required for the Typing Indicator API
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
#     UPDATED: Enhanced date detection for casual phrasings like "what's happening tomorrow"
#     """
#     today_str = date.today().strftime("%Y-%m-%d")
#     weekday_str = date.today().strftime("%A")
#     tomorrow_str = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
    
#     system_prompt = (
#         f"Current Date: {today_str} ({weekday_str}). Tomorrow is: {tomorrow_str}. "
#         "You are a multilingual AI that understands ALL languages. "
#         "Your job is to analyze a user's request for events or businesses in Buenos Aires and extract structured data."
        
#         "EXTRACT THE FOLLOWING (return as JSON):\n"
        
#         "1. 'is_greeting': boolean (true ONLY if message is JUST 'hi', 'hello', 'hola', 'hey' with ABSOLUTELY NO OTHER REQUEST. If user says 'hi' AND asks for anything else, return FALSE)\n"
#         "   Examples:\n"
#         "   - 'hi' → is_greeting: true ✅\n"
#         "   - 'hello' → is_greeting: true ✅\n"
#         "   - 'hi any events on Dec 6' → is_greeting: FALSE ❌ (has request!)\n"
#         "   - 'hello where can I find bars' → is_greeting: FALSE ❌ (has request!)\n"
        
#         "2. 'is_identity_question': boolean. True if user asks 'Who am I?', 'What is my name?', 'Do you know me?', 'What do you know about me?'.\n"
        
#         "3. 'wants_to_upload': boolean. True if user asks to 'upload event', 'submit event', 'add my party', 'post an event', 'share an event'.\n"
        
#         "4. 'date_range': {'start': 'YYYY-MM-DD', 'end': 'YYYY-MM-DD'} or null\n"
#         "   CRITICAL DATE DETECTION RULES:\n"
#         "   - If user mentions ANY temporal word like 'tomorrow', 'tonight', 'today', 'this weekend', 'next week', 'happening', 'going on', 'what's on', YOU MUST extract date_range\n"
#         "   - 'tomorrow' → date_range: {'start': tomorrow_date, 'end': tomorrow_date}\n"
#         "   - 'today' → date_range: {'start': today_date, 'end': today_date}\n"
#         "   - 'tonight' → date_range: {'start': today_date, 'end': today_date}\n"
#         "   - 'this weekend' → date_range: {'start': next_saturday, 'end': next_sunday}\n"
#         "   - 'what happening' / 'what's on' / 'show me' + temporal word → ALWAYS means they want events with dates\n"
#         "   EXAMPLES:\n"
#         "   - 'what happening tomorrow' → date_range: {'start': tomorrow, 'end': tomorrow} ✅\n"
#         "   - 'what's on tomorrow' → date_range: {'start': tomorrow, 'end': tomorrow} ✅\n"
#         "   - 'anything tomorrow' → date_range: {'start': tomorrow, 'end': tomorrow} ✅\n"
#         "   - 'show me tomorrow' → date_range: {'start': tomorrow, 'end': tomorrow} ✅\n"
#         "   - 'events tomorrow' → date_range: {'start': tomorrow, 'end': tomorrow} ✅\n"
        
#         "5. 'target_mood': string (romantic, chill, energetic, party, relaxed, upscale, casual)\n"
        
#         "6. 'social_context': string (date, friends, solo, family, business)\n"
        
#         "7. 'category': string (event, concert, show, bar, restaurant, cafe, etc.)\n"
#         "   IMPORTANT: If user asks temporal questions like 'what's happening', 'what's on', 'show me', automatically set category to 'event'\n"
        
#         "8. 'specific_keywords': List of DIRECT and SPECIFIC keywords from the user's text. "
#         "   - Examples: 'Salsa', 'Techno', 'Jazz', 'Rooftop', 'Live music'.\n"
        
#         "9. 'user_language': detected ISO 639-1 language code (en, es, te, he, ar, etc.). Default to 'en' if uncertain.\n"

#         "10. 'inferred_keywords': List of related, searchable keywords if the user's request is abstract. "
#         "   - If the user asks for 'artistic' or 'cultural' things, infer related concrete terms.\n"
#         "   - If the user's request is already specific (e.g., 'techno'), this can be null.\n"
#         "   - Examples:\n"
#         "     * User says 'artistic events' → inferred_keywords: ['art', 'gallery', 'exhibition', 'museum', 'theatre', 'performance', 'cultural']\n"
#         "     * User says 'something intellectual' → inferred_keywords: ['lecture', 'talk', 'book', 'museum', 'cinema', 'art']\n"
#         "     * User says 'a place with a nice view' → inferred_keywords: ['rooftop', 'terrace', 'view', 'balcony']\n"
        
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
#             return {"user_language": "en"}
        
#         if not data.get('user_language') or data.get('user_language') == 'unknown':
#             data['user_language'] = 'en'
        
#         logger.info(f"🧠 AI Analysis: {data}")
#         return data
        
#     except Exception as e:
#         logger.error(f"AI Intent Error: {e}")
#         return {"user_language": "en"}

# def generate_just_for_you(user_age, item_name, item_desc, item_mood, social_context=None, user_language='en'):
#     """
#     Enhanced: Now generates personalized recommendations in user's detected language
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
        
#         # Language instruction
#         lang_instruction = f"Respond in the language code: {user_language}. "
#         if user_language == 'te':
#             lang_instruction += "Use Telugu script and language."
#         elif user_language == 'he':
#             lang_instruction += "Use Hebrew script and language."
#         elif user_language == 'ar':
#             lang_instruction += "Use Arabic script and language."
#         elif user_language == 'hi':
#             lang_instruction += "Use Hindi script and language."
#         elif user_language == 'es':
#             lang_instruction += "Use Spanish language."
#         elif user_language == 'pt':
#             lang_instruction += "Use Portuguese language."
#         elif user_language == 'fr':
#             lang_instruction += "Use French language."
#         else:
#             lang_instruction += "Use English language."
        
#         prompt = (
#             f"{lang_instruction} "
#             f"Write a 1-sentence recommendation for a {user_age} year old. "
#             f"Venue: {item_name}. Vibe: {item_mood}. {context_msg} "
#             "Start with '✨ Just for you:' or equivalent in the target language. Be enthusiastic and specific."
#         )
        
#         response = openai.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[{"role": "user", "content": prompt}],
#             temperature=0.7,
#             timeout=5
#         )
#         return response.choices[0].message.content.replace('"', '')
#     except Exception as e:
#         logger.error(f"Just for you error: {e}")
#         if user_language == 'te':
#             return f"✨ మీ కోసం: ఇది {item_mood} వైబ్‌తో సరిపోతుంది! {context_msg}"
#         elif user_language == 'he':
#             return f"✨ בשבילך: זה מתאים ל{item_mood} אווירה! {context_msg}"
#         elif user_language == 'ar':
#             return f"✨ لك خصيصاً: هذا يناسب الأجواء {item_mood}! {context_msg}"
#         elif user_language == 'es':
#             return f"✨ Just for you: ¡Esto coincide con el ambiente {item_mood}! {context_msg}"
#         else:
#             return f"✨ Just for you: This matches the {item_mood} vibe! {context_msg}"

# def translate_text(text, target_language):
#     if not text:
#         return text
    
#     try:
#         lang_map = {
#             'es': 'Spanish', 'pt': 'Portuguese', 'fr': 'French', 'de': 'German', 
#             'it': 'Italian', 'ru': 'Russian', 'ar': 'Arabic', 'he': 'Hebrew', 
#             'hi': 'Hindi', 'te': 'Telugu', 'ta': 'Tamil', 'ko': 'Korean', 
#             'ja': 'Japanese', 'zh': 'Chinese'
#         }
#         lang_name = lang_map.get(target_language, 'English')
        
#         response = openai.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[
#                 {"role": "system", "content": f"Translate the following text to {lang_name}. Maintain original tone. Only return the translation."},
#                 {"role": "user", "content": text}
#             ],
#             temperature=0.3,
#             timeout=5
#         )
#         translated = response.choices[0].message.content.strip()
#         return translated if translated else text
#     except Exception as e:
#         logger.error(f"Translation error: {e}")
#         return text

# def generate_closing_message(user_query, user_language='en'):
#     try:
#         lang_instruction_map = {
#             'te': "Respond in Telugu using Telugu script.", 'he': "Respond in Hebrew using Hebrew script.",
#             'ar': "Respond in Arabic using Arabic script.", 'hi': "Respond in Hindi using Devanagari script.",
#             'es': "Respond in Spanish.", 'pt': "Respond in Portuguese.", 'fr': "Respond in French."
#         }
#         lang_instruction = lang_instruction_map.get(user_language, "Respond in English.")
        
#         prompt = (
#             f"User query: '{user_query}'. I sent recommendations. "
#             f"Write a SHORT closing message asking if they want more suggestions. "
#             f"Use 1 emoji. Be friendly. {lang_instruction}"
#         )
        
#         response = openai.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[{"role": "system", "content": "You are Yara, a friendly Buenos Aires guide. You know everything."}, {"role": "user", "content": prompt}],
#             temperature=0.7,
#             timeout=4
#         )
#         return response.choices[0].message.content.replace('"', '')
#     except:
#         fallback_map = {
#             'te': "మరిన్ని సూచనలు కావాలా? 🎉", 'he': "צריך עוד המלצות? 🎉",
#             'ar': "هل تحتاج المزيد من الاقتراحات؟ 🎉", 'es': "¿Te gustaría más sugerencias? 🎉",
#             'pt': "Gostaria de mais sugestões? 🎉"
#         }
#         return fallback_map.get(user_language, "Need more suggestions? 🎉")

# # --- DATABASE FUNCTIONS ---

# def get_user(conn, phone):
#     with conn.cursor() as cur:
#         cur.execute("SELECT * FROM public.users WHERE phone = %s", (phone,))
#         return cur.fetchone()

# def create_user(conn, phone):
#     with conn.cursor() as cur:
#         cur.execute(
#             "INSERT INTO public.users (phone, conversation_step) VALUES (%s, 'welcome') ON CONFLICT (phone) DO NOTHING", (phone,)
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
#     UPDATED: Now includes 'inferred_keywords' for intelligent searching.
#     """
#     query = f"SELECT * FROM public.{table} WHERE 1=1"
#     args = []
    
#     date_range = ai_data.get('date_range') or {}
#     social_context = ai_data.get('social_context')
    
#     search_terms = []
    
#     if ai_data.get('specific_keywords'):
#         search_terms.extend(ai_data.get('specific_keywords'))

#     if ai_data.get('inferred_keywords'):
#         search_terms.extend(ai_data.get('inferred_keywords'))
    
#     if ai_data.get('target_mood'):
#         search_terms.append(ai_data.get('target_mood'))
    
#     if social_context == 'date':
#         search_terms.extend(['romantic', 'intimate', 'cozy'])
#     elif social_context == 'friends':
#         search_terms.extend(['social', 'group', 'casual'])
    
#     cat = ai_data.get('category', '')
#     if cat and len(cat) > 3 and cat.lower() not in ['event', 'party', 'show', 'place', 'spot']:
#         search_terms.append(cat)
    
#     search_terms = list(set([t for t in search_terms if t and len(t) > 2]))
    
#     logger.info(f"🔍 Search Terms (Level {strictness_level}): {search_terms}")

#     # --- DATE LOGIC (for events) ---
#     if table == 'events' and date_range:
#         start, end = date_range.get('start'), date_range.get('end')
#         if start and end:
#             start_obj = datetime.strptime(start, "%Y-%m-%d").date()
#             end_obj = datetime.strptime(end, "%Y-%m-%d").date()
#             days_in_range = [ (start_obj + timedelta(days=i)).strftime('%A') for i in range((end_obj - start_obj).days + 1) ]
#             days_tuple = tuple(set(days_in_range))
#             query += " AND ((event_date >= %s::date AND event_date <= %s::date) OR (recurring_day = ANY(%s)))"
#             args.extend([start, end, list(days_tuple)])

#     # --- TEXT SEARCH LOGIC ---
#     if search_terms:
#         term_conditions = [f"(title ILIKE %s OR description ILIKE %s OR mood ILIKE %s OR music_type ILIKE %s OR location ILIKE %s)" for _ in search_terms] if table == 'events' else [f"(name ILIKE %s OR description ILIKE %s OR location ILIKE %s OR type ILIKE %s)" for _ in search_terms]
        
#         for term in search_terms:
#             term_wild = f"%{term}%"
#             args.extend([term_wild] * (5 if table == 'events' else 4))
        
#         join_operator = " AND " if strictness_level == 1 else " OR "
#         query += f" AND ({join_operator.join(term_conditions)})"

#     query += " ORDER BY event_date ASC LIMIT 5" if table == 'events' else " LIMIT 5"

#     logger.info(f"📊 SQL Query: {query[:200]}...")
#     logger.info(f"📊 Args: {args}")
    
#     return query, args

# def smart_search(conn, table, ai_data):
#     """
#     UPDATED: Added try-catch to prevent crashes. Returns empty list on error.
#     """
#     try:
#         query, args = build_search_query(table, ai_data, strictness_level=1)
#         with conn.cursor() as cur:
#             cur.execute(query, tuple(args))
#             results = cur.fetchall()
#             if results:
#                 logger.info(f"✅ Found {len(results)} results (Strict)")
#                 return results

#         query, args = build_search_query(table, ai_data, strictness_level=2)
#         with conn.cursor() as cur:
#             cur.execute(query, tuple(args))
#             results = cur.fetchall()
#             if results:
#                 logger.info(f"✅ Found {len(results)} results (Loose)")
#                 return results
#             else:
#                 logger.warning(f"⚠️ No results in {table}")
#                 return []
    
#     except Exception as e:
#         logger.error(f"❌ Search error in {table}: {e}")
#         return []

# # ==============================================================================
# # 🚀 TWILIO TYPING INDICATOR (NEW FEATURE)
# # ==============================================================================

# def send_typing_indicator(message_sid):
#     """
#     Sends a 'Typing' status to the WhatsApp user.
#     This also marks the user's message as Read (Blue Ticks).
#     """
#     if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN: 
#         return
    
#     try:
#         url = "https://messaging.twilio.com/v2/Indicators/Typing.json"
        
#         # Twilio Auth
#         auth = (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        
#         # Payload as per docs
#         data = {
#             "messageId": message_sid,
#             "channel": "whatsapp"
#         }
        
#         # Fire and forget request (timeout short to not block execution)
#         response = requests.post(url, auth=auth, data=data, timeout=2)
        
#         if response.status_code == 200:
#             logger.info("✅ Typing indicator sent (Blue Ticks triggered)")
#         else:
#             logger.warning(f"⚠️ Typing indicator failed: {response.text}")
            
#     except Exception as e:
#         logger.error(f"❌ Error sending typing indicator: {e}")

# def send_whatsapp_message(to, body, media_url=None):
#     if not TWILIO_WHATSAPP_NUMBER: 
#         return
    
#     try:
#         message_data = {
#             'from_': TWILIO_WHATSAPP_NUMBER,
#             'to': to,
#             'body': body
#         }
#         if media_url:
#             message_data['media_url'] = media_url
            
#         twilio_client.messages.create(**message_data)
#     except Exception as e:
#         logger.error(f"❌ Twilio Error: {e}")

# def ask_chatgpt_expert_fallback(user_input, ai_data, user_language='en'):
#     """
#     UPDATED: Prompt rewritten to be ALWAYS POSITIVE. Never says "not found" or "sorry"
#     """
#     category = ai_data.get('category')
#     mood = ai_data.get('target_mood')
#     social_context = ai_data.get('social_context')
#     keywords = ai_data.get('specific_keywords', [])
#     inferred_keywords = ai_data.get('inferred_keywords', [])
#     date_range = ai_data.get('date_range') or {}
#     date_str = date_range.get('start')
    
#     context_parts = []
#     if social_context: 
#         context_parts.append(f"looking for {social_context} experience")
#     if mood: 
#         context_parts.append(f"wants {mood} vibe")
#     if keywords: 
#         context_parts.append(f"interested in: {', '.join(keywords)}")
#     if inferred_keywords:
#         context_parts.append(f"likes: {', '.join(inferred_keywords)}")
#     if category: 
#         context_parts.append(f"wants: {category}")
#     if date_str: 
#         context_parts.append(f"for date: {date_str}")
    
#     context_description = ". ".join(context_parts) if context_parts else "looking for recommendations in Buenos Aires"
    
#     lang_map = {
#         'te': "CRITICAL: Respond ENTIRELY in Telugu using Telugu script (తెలుగు).",
#         'he': "CRITICAL: Respond ENTIRELY in Hebrew using Hebrew script (עברית).",
#         'ar': "CRITICAL: Respond ENTIRELY in Arabic using Arabic script (العربية).",
#         'hi': "CRITICAL: Respond ENTIRELY in Hindi using Devanagari script (हिन्दी).",
#         'es': "IMPORTANT: Respond in Spanish.",
#         'pt': "IMPORTANT: Respond in Portuguese.",
#         'fr': "IMPORTANT: Respond in French.",
#     }
#     lang_instruction = lang_map.get(user_language, "IMPORTANT: Respond in English.")
    
#     expert_prompt = f"""You are Yara, the ULTIMATE Buenos Aires expert and local tour guide. 
# You know EVERYTHING about Buenos Aires - every bar, every restaurant, every café, every hidden gem, every neighborhood.

# USER'S REQUEST: "{user_input}"
# USER CONTEXT: {context_description}

# YOUR MISSION: Give them 2-3 PERFECT, SPECIFIC recommendations that match their request.

# CRITICAL RULES - READ CAREFULLY:
# 1. ✅ BE POSITIVE AND CONFIDENT - You're an expert who knows the BEST places in Buenos Aires
# 2. ✅ Give 2-3 SPECIFIC place names with neighborhoods (Palermo, San Telmo, Recoleta, etc.)
# 3. ✅ Explain WHY each place is perfect for their request
# 4. ✅ Be enthusiastic and use emojis (🎯, ✨, 🍸, 🎵, etc.)
# 5. ❌ NEVER EVER say negative things like:
#    - "sorry"
#    - "not found"
#    - "don't have"
#    - "couldn't find"
#    - "no matches"
#    - "unfortunately"
# 6. ✅ Instead, say positive things like:
#    - "I know the perfect spots!"
#    - "Great choice! Here are amazing places!"
#    - "You'll love these!"
#    - "Perfect! Buenos Aires has incredible options!"

# FORMAT YOUR RESPONSE EXACTLY LIKE THIS:
# "[Enthusiastic intro acknowledging their request - NO negativity!]

# 🎯 **[Place Name]** in [Neighborhood]
# [One sentence why it's perfect for them]

# 🎯 **[Place Name]** in [Neighborhood]
# [One sentence why it's perfect for them]

# 🎯 **[Place Name]** in [Neighborhood]
# [One sentence why it's perfect for them]

# [Friendly closing with emoji]"

# EXAMPLES OF GOOD INTROS (use similar tone):
# - "Great choice! I know some incredible spots for that!" ✅
# - "Perfect! Buenos Aires has amazing places for this!" ✅
# - "Excellent! Here are some fantastic options!" ✅

# EXAMPLES OF BAD INTROS (NEVER use these):
# - "Sorry, I don't have information..." ❌
# - "Unfortunately, I couldn't find..." ❌

# {lang_instruction}

# Remember: You're a confident expert. You ALWAYS have great recommendations!"""

#     try:
#         response = openai.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[
#                 {"role": "system", "content": "You are Yara, the ultimate Buenos Aires expert who knows EVERYTHING about the city. You're always positive, enthusiastic, and helpful. You NEVER say negative things. You always have great recommendations because you're a real expert."}, 
#                 {"role": "user", "content": expert_prompt}
#             ],
#             temperature=0.8,
#             timeout=10
#         )
#         expert_response = response.choices[0].message.content
#         logger.info(f"🎯 Expert Fallback Response Generated in {user_language}")
#         return expert_response
    
#     except Exception as e:
#         logger.error(f"Fallback Error: {e}")
#         fallback_map = {
#             'te': "బ్యూనస్ ఎయిర్స్‌లో మీ కోసం కొన్ని అద్భుతమైన ప్రదేశాలు ఉన్నాయి! మరిన్ని వివరాలు ఇవ్వండి, నేను ఉత్తమ ప్రదేశాలను సూచిస్తాను! 🎯",
#             'he': "יש כמה מקומות מדהימים בבואנוס איירס בשבילך! ספר לי עוד פרטים ואני אמליץ על המקומות הכי טובים! 🎯",
#             'ar': "لدي أماكن رائعة في بوينس آيريس لك! أخبرني المزيد من التفاصيل وسأوصي بأفضل الأماكن! 🎯",
#             'es': "¡Conozco lugares increíbles en Buenos Aires para ti! Cuéntame más detalles y te recomendaré los mejores sitios! 🎯",
#             'pt': "Conheço lugares incríveis em Buenos Aires para você! Me conte mais detalhes e recomendarei os melhores lugares! 🎯",
#         }
#         return fallback_map.get(user_language, "I know some amazing places in Buenos Aires for you! Tell me more details and I'll recommend the best spots! 🎯")

# # ==============================================================================
# # PROCESS THREAD (Updated with MessageSid & Identity Check & Upload Feature)
# # ==============================================================================

# def process_message_thread(sender, text, message_sid=None):
#     """
#     UPDATED: Now accepts message_sid to trigger the typing indicator immediately.
#     """
    
#     # 1. Trigger Typing Indicator & Blue Ticks IMMEDIATELY
#     if message_sid:
#         send_typing_indicator(message_sid)
        
#     conn = None
#     try:
#         conn = postgreSQL_pool.getconn()
#         user = get_user(conn, sender)

#         if not user:
#             create_user(conn, sender)
#             send_whatsapp_message(sender, "Hey! Welcome to Yara ai , I'm your Buenos Aires guide for finding the best plans in the city ✨ what are you in the mood for?")
#             return

#         step, user_age = user.get('conversation_step'), user.get('age', '25')
#         user_name = user.get('name', 'Friend') # Retrieve Name from DB
        
#         ai_data = executor.submit(analyze_user_intent, text).result() or {"user_language": "en"}
#         user_language = ai_data.get('user_language', 'en')
#         social_context = ai_data.get('social_context')

#         logger.info(f"🌍 Detected Language: {user_language}")

#         # --- 1. HANDLE GREETINGS ---
#         if ai_data.get('is_greeting') and step != 'ask_name_age':
#             greetings = {'te': f"నమస్కారం {user_name}! మీరు ఏమి వెతుకుతున్నారు?", 'he': f"שלום {user_name}! מה אתה מחפש?", 'ar': f"مرحباً {user_name}! ماذا تبحث؟", 'es': f"¡Hola {user_name}! ¿Qué estás buscando hoy?", 'en': f"Hey {user_name}! What are you looking for today?"}
#             send_whatsapp_message(sender, greetings.get(user_language, greetings['en']))
#             return

#         # --- 2. HANDLE IDENTITY QUESTIONS ("Who am I?") --- 
#         if ai_data.get('is_identity_question'):
#             logger.info("👤 Identity question detected.")
            
#             last_mood = user.get('last_mood', 'mystery')
            
#             identity_prompt = (
#                 f"The user asked 'Who am I?' or 'What do you know about me?'. "
#                 f"User Name: {user_name}. Age: {user_age}. Last thing they looked for: {last_mood}. "
#                 f"Respond in language code '{user_language}'. "
#                 f"Be friendly, witty, and confirm you know them as Yara, their local guide. "
#                 "Example: 'You are [Name], my favorite [Age]-year-old explorer! We were just looking for [last_mood].'"
#             )
            
#             try:
#                 response = openai.chat.completions.create(
#                     model="gpt-4o-mini",
#                     messages=[{"role": "system", "content": "You are Yara."}, {"role": "user", "content": identity_prompt}],
#                     temperature=0.8
#                 )
#                 answer = response.choices[0].message.content.replace('"', '')
#                 send_whatsapp_message(sender, answer)
#                 return  # Stop processing here, don't search database
#             except Exception as e:
#                 logger.error(f"Identity AI Error: {e}")
#                 # Fallback response
#                 send_whatsapp_message(sender, f"You are {user_name}, {user_age} years young! And I'm Yara, your guide! ✨")
#                 return

#         # --- 3. HANDLE UPLOAD/SUBMIT EVENT REQUESTS (NEW FEATURE) ---
#         if ai_data.get('wants_to_upload'):
#             logger.info("📤 User wants to upload an event.")
#             base_msg = "That's great! We love new events. You can upload your event details using this form:"
#             translated_msg = translate_text(base_msg, user_language)
#             final_msg = f"{translated_msg}\n\n👉 https://docs.google.com/forms/d/e/1FAIpQLSdnYmuT-KgXAyZzb1qPiO29waE_lUN_XW8SHiSMA5FW4YsRvQ/viewform?usp=publish-editor"
#             send_whatsapp_message(sender, final_msg)
#             return

#         # --- 4. HANDLE ONBOARDING ---
#         if step == 'welcome':
#             messages = {'te': "మొదట, మీకు ఉత్తమ సూచనలు ఇవ్వడానికి, మీ పేరు మరియు వయస్సు ఏమిటి?", 'he': "קודם כל, מה שמך וגילך?", 'ar': "أولاً، ما هو اسمك وعمرك؟", 'es': "Primero, ¿cuál es tu nombre y edad?", 'en': "First, what's your name and age?"}
#             send_whatsapp_message(sender, messages.get(user_language, messages['en']))
#             update_user(conn, sender, {"conversation_step": "ask_name_age", "last_mood": text})
#             return

#         if step == 'ask_name_age':
#             last_mood = user.get('last_mood')
#             messages = {'te': f"సరే! '{last_mood}' కోసం చూపిస్తున్నాను:", 'he': f"מעולה! מראה אפשרויות עבור '{last_mood}':", 'ar': f"رائع! عرض الخيارات لـ '{last_mood}':", 'es': f"¡Perfecto! Buscando opciones para '{last_mood}':", 'en': f"Ok cool! Showing options for '{last_mood}':"}
#             send_whatsapp_message(sender, messages.get(user_language, messages['en']))
            
#             clean_name = re.sub(r'[^\w]', '', text.split()[0]) if text.split() else "Friend"
#             age = "".join(filter(str.isdigit, text)) or "25"
            
#             update_user(conn, sender, {"name": clean_name, "age": age, "conversation_step": "ready"})
#             text = last_mood 
#             ai_data = analyze_user_intent(text) or {"user_language": "en"}
#             user_language = ai_data.get('user_language', 'en')
#             social_context = ai_data.get('social_context')

#         # ===================================================================
#         # FIXED SEARCH LOGIC: DON'T MIX EVENTS AND BUSINESSES
#         # ===================================================================
        
#         found_something = False
#         category = ai_data.get('category', '').lower()
        
#         # Determine what user is SPECIFICALLY asking for
#         wants_events = (
#             ai_data.get('date_range') or  # Has specific date = wants events
#             category in ['event', 'concert', 'show', 'party', 'festival', 'exhibition']
#         )
        
#         wants_businesses = category in ['bar', 'restaurant', 'cafe', 'club', 'shop', 'mall']
        
#         logger.info(f"🎯 User wants - Events: {wants_events}, Businesses: {wants_businesses}")
        
#         # CASE 1: User SPECIFICALLY wants EVENTS
#         if wants_events and not wants_businesses:
#             logger.info("🔍 Searching EVENTS only...")
#             events = smart_search(conn, 'events', ai_data)
            
#             if events:
#                 found_something = True
#                 intro = translate_text(f"Here are some events matching your vibe:", user_language)
#                 if ai_data.get('date_range') and ai_data['date_range'].get('start'):
#                     intro = translate_text(f"Here's what's happening around {ai_data['date_range']['start']}:", user_language)
#                 send_whatsapp_message(sender, intro)
                
#                 for e in events:
#                     futures = {
#                         'jfy': executor.submit(generate_just_for_you, user_age, e['title'], e['description'], e.get('mood', 'social'), social_context, user_language),
#                         'title': executor.submit(translate_text, e.get('title'), user_language),
#                         'desc': executor.submit(translate_text, e.get('description'), user_language),
#                         'location': executor.submit(translate_text, e.get('location'), user_language),
#                         'music': executor.submit(translate_text, e.get('music_type'), user_language)
#                     }
                    
#                     # Multilingual "Book your slot" text
#                     ticket_section = ""
#                     if e.get('ticket_link'):
#                         book_text_map = {
#                             'en': '🎟️ Book your slot',
#                             'es': '🎟️ Reserva tu lugar',
#                             'pt': '🎟️ Reserve seu lugar',
#                             'fr': '🎟️ Réservez votre place',
#                             'te': '🎟️ మీ స్లాట్‌ను బుక్ చేసుకోండి',
#                             'he': '🎟️ הזמן את המקום שלך',
#                             'ar': '🎟️ احجز مكانك',
#                             'hi': '🎟️ अपनी जगह बुक करें'
#                         }
#                         book_text = book_text_map.get(user_language, '🎟️ Book your slot')
#                         ticket_section = f"\n{book_text}: {e.get('ticket_link')}"
                    
#                     display_date = e.get('event_date') if e.get('event_date') else f"Every {e.get('recurring_day')}"
#                     caption = f"*{futures['title'].result()}*\n\n📍 {futures['location'].result()}\n🕒 {e.get('event_time')}\n📅 {display_date}\n🎵 {futures['music'].result()}\n📝 {futures['desc'].result()}{ticket_section}\n📸 {e.get('instagram_link')}\n\n{futures['jfy'].result()}"
#                     send_whatsapp_message(sender, caption, media_url=e.get('image_url'))
            
#             # If no events found, go straight to ChatGPT (DON'T search businesses)
#             if not found_something:
#                 logger.info("🎯 No events found - Using ChatGPT fallback for events")
#                 send_whatsapp_message(sender, ask_chatgpt_expert_fallback(text, ai_data, user_language))
#                 return
        
#         # CASE 2: User SPECIFICALLY wants BUSINESSES
#         elif wants_businesses and not wants_events:
#             logger.info("🔍 Searching BUSINESSES only...")
#             businesses = smart_search(conn, 'businesses', ai_data)
            
#             if businesses:
#                 found_something = True
#                 intro = translate_text("Found these spots for you:", user_language)
#                 send_whatsapp_message(sender, intro)
                
#                 for b in businesses:
#                     futures = {
#                         'jfy': executor.submit(generate_just_for_you, user_age, b['name'], b['description'], ai_data.get('target_mood') or 'chill', social_context, user_language),
#                         'name': executor.submit(translate_text, b.get('name'), user_language),
#                         'desc': executor.submit(translate_text, b.get('description'), user_language),
#                         'location': executor.submit(translate_text, b.get('location'), user_language)
#                     }
#                     msg = f"*{futures['name'].result()}*\n📍 {futures['location'].result()}\n\n{futures['desc'].result()}\n\n📸 {b.get('instagram_link')}\n\n{futures['jfy'].result()}"
#                     send_whatsapp_message(sender, msg, media_url=b.get('image_url'))
            
#             # If no businesses found, go straight to ChatGPT (DON'T search events)
#             if not found_something:
#                 logger.info("🎯 No businesses found - Using ChatGPT fallback for businesses")
#                 send_whatsapp_message(sender, ask_chatgpt_expert_fallback(text, ai_data, user_language))
#                 return
        
#         # CASE 3: Ambiguous query - search BOTH
#         else:
#             logger.info("🔍 Ambiguous query - Searching both events and businesses...")
            
#             # Try events first
#             events = smart_search(conn, 'events', ai_data)
#             if events:
#                 found_something = True
#                 intro = translate_text(f"Here are some events matching your vibe:", user_language)
#                 send_whatsapp_message(sender, intro)
                
#                 for e in events:
#                     futures = {
#                         'jfy': executor.submit(generate_just_for_you, user_age, e['title'], e['description'], e.get('mood', 'social'), social_context, user_language),
#                         'title': executor.submit(translate_text, e.get('title'), user_language),
#                         'desc': executor.submit(translate_text, e.get('description'), user_language),
#                         'location': executor.submit(translate_text, e.get('location'), user_language),
#                         'music': executor.submit(translate_text, e.get('music_type'), user_language)
#                     }
                    
#                     # Multilingual "Book your slot" text
#                     ticket_section = ""
#                     if e.get('ticket_link'):
#                         book_text_map = {'en': '🎟️ Book your slot', 'es': '🎟️ Reserva tu lugar', 'pt': '🎟️ Reserve seu lugar', 'fr': '🎟️ Réservez votre place', 'te': '🎟️ మీ స్లాట్‌ను బుక్ చేసుకోండి', 'he': '🎟️ הזמן את המקום שלך', 'ar': '🎟️ احجز مكانك', 'hi': '🎟️ अपनी जगह बुक करें'}
#                         book_text = book_text_map.get(user_language, '🎟️ Book your slot')
#                         ticket_section = f"\n{book_text}: {e.get('ticket_link')}"
                    
#                     display_date = e.get('event_date') if e.get('event_date') else f"Every {e.get('recurring_day')}"
#                     caption = f"*{futures['title'].result()}*\n\n📍 {futures['location'].result()}\n🕒 {e.get('event_time')}\n📅 {display_date}\n🎵 {futures['music'].result()}\n📝 {futures['desc'].result()}{ticket_section}\n📸 {e.get('instagram_link')}\n\n{futures['jfy'].result()}"
#                     send_whatsapp_message(sender, caption, media_url=e.get('image_url'))
            
#             # Try businesses
#             businesses = smart_search(conn, 'businesses', ai_data)
#             if businesses:
#                 found_something = True
#                 intro = translate_text("Found these spots for you:", user_language)
#                 send_whatsapp_message(sender, intro)
                
#                 for b in businesses:
#                     futures = {
#                         'jfy': executor.submit(generate_just_for_you, user_age, b['name'], b['description'], ai_data.get('target_mood') or 'chill', social_context, user_language),
#                         'name': executor.submit(translate_text, b.get('name'), user_language),
#                         'desc': executor.submit(translate_text, b.get('description'), user_language),
#                         'location': executor.submit(translate_text, b.get('location'), user_language)
#                     }
#                     msg = f"*{futures['name'].result()}*\n📍 {futures['location'].result()}\n\n{futures['desc'].result()}\n\n📸 {b.get('instagram_link')}\n\n{futures['jfy'].result()}"
#                     send_whatsapp_message(sender, msg, media_url=b.get('image_url'))
            
#             # If nothing found in both, use ChatGPT
#             if not found_something:
#                 logger.info("🎯 Nothing found in both tables - Using ChatGPT fallback")
#                 send_whatsapp_message(sender, ask_chatgpt_expert_fallback(text, ai_data, user_language))
#                 return
        
#         # Send closing message if something was found
#         if found_something:
#             send_whatsapp_message(sender, generate_closing_message(text, user_language))

#     except Exception as e:
#         logger.error(f"Logic Error: {e}", exc_info=True)
#         try:
#             ai_data = analyze_user_intent(text) or {"user_language": "en"}
#             user_language = ai_data.get('user_language', 'en')
#             send_whatsapp_message(sender, ask_chatgpt_expert_fallback(text, ai_data, user_language))
#         except:
#             send_whatsapp_message(sender, "I know some amazing places in Buenos Aires! Tell me what you're looking for and I'll recommend the best spots! 🎯")
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
#     message_sid = request.form.get('MessageSid') # <--- Get the Message ID
    
#     if not sender_id or not incoming_msg: return "" 
    
#     resp = MessagingResponse()
#     # Pass message_sid to the thread
#     threading.Thread(target=process_message_thread, args=(sender_id, incoming_msg, message_sid)).start()
#     return str(resp)

# if __name__ == "__main__":
#     print("🚀 Twilio WhatsApp Bot Starting...")
#     print("✨ Features: Typing Indicators, Identity, Upload Link")
#     app.run(port=5000)

#upload event new link and cafe recmondations 
import os
import logging
import psycopg2
import threading
import json
import re
import requests  # Required for the Typing Indicator API
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
executor = ThreadPoolExecutor(max_workers=5) 

# --- DATABASE POOL ---
try:
    postgreSQL_pool = psycopg2.pool.SimpleConnectionPool(
        1, 50, DB_URI, cursor_factory=RealDictCursor, connect_timeout=10
    )
    print("✅ Database Connection Pool Created")
except (Exception, psycopg2.DatabaseError) as error:
    print("❌ Error connecting to PostgreSQL", error)

# ==============================================================================
# 🧠 ENHANCED AI & UTILS
# ==============================================================================

def analyze_user_intent(user_text):
    """
    UPDATED: Enhanced multilingual upload detection + date detection
    """
    today_str = date.today().strftime("%Y-%m-%d")
    weekday_str = date.today().strftime("%A")
    tomorrow_str = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
    
    system_prompt = (
        f"Current Date: {today_str} ({weekday_str}). Tomorrow is: {tomorrow_str}. "
        "You are a multilingual AI that understands ALL languages (English, Spanish, Portuguese, French, German, Italian, Russian, Arabic, Hebrew, Hindi, Telugu, Tamil, Chinese, Japanese, Korean, and ALL others). "
        "Your job is to analyze a user's request for events or businesses in Buenos Aires and extract structured data."
        
        "EXTRACT THE FOLLOWING (return as JSON):\n"
        
        "1. 'is_greeting': boolean (true ONLY if message is JUST 'hi', 'hello', 'hola', 'hey', 'salut', 'ciao', 'नमस्ते', 'నమస్కారం', '你好', 'こんにちは', '안녕하세요' etc. with ABSOLUTELY NO OTHER REQUEST. If user says 'hi' AND asks for anything else, return FALSE)\n"
        "   Examples:\n"
        "   - 'hi' → is_greeting: true ✅\n"
        "   - 'hello' → is_greeting: true ✅\n"
        "   - 'hi any events on Dec 6' → is_greeting: FALSE ❌ (has request!)\n"
        "   - 'hello where can I find bars' → is_greeting: FALSE ❌ (has request!)\n"
        
        "2. 'is_identity_question': boolean. True if user asks 'Who am I?', 'What is my name?', 'Do you know me?', 'What do you know about me?' in ANY language.\n"
        
        "3. 'wants_to_upload': boolean. CRITICAL - Detect this intent in ANY language:\n"
        "   True if user expresses intent to:\n"
        "   - Upload/Submit/Add/Post/Share/Promote an event\n"
        "   - Recommend their own event/party/venue/business\n"
        "   - List their event or ask how to add/submit it\n"
        "   - Say 'I have an event', 'I'm organizing', 'I want to promote', 'I want to list'\n"
        "   Examples across languages:\n"
        "   - English: 'upload event', 'add my party', 'how can I submit', 'I want to recommend my event'\n"
        "   - Spanish: 'subir evento', 'agregar mi fiesta', 'cómo puedo enviar', 'quiero recomendar'\n"
        "   - Portuguese: 'enviar evento', 'adicionar minha festa', 'quero recomendar'\n"
        "   - French: 'ajouter événement', 'télécharger mon événement', 'je veux recommander'\n"
        "   - German: 'Veranstaltung hochladen', 'meine Party hinzufügen', 'ich möchte empfehlen'\n"
        "   - Italian: 'caricare evento', 'aggiungere la mia festa', 'voglio raccomandare'\n"
        "   - Russian: 'загрузить событие', 'добавить мою вечеринку', 'я хочу порекомендовать'\n"
        "   - Arabic: 'إضافة حدث', 'رفع حدثي', 'كيف أضيف', 'أريد أن أوصي'\n"
        "   - Hebrew: 'להעלות אירוע', 'להוסיף את המסיבה שלי', 'אני רוצה להמליץ'\n"
        "   - Hindi: 'इवेंट अपलोड करें', 'मेरी पार्टी जोड़ें', 'मैं सिफारिश करना चाहता हूं'\n"
        "   - Telugu: 'ఈవెంట్ అప్‌లోడ్ చేయండి', 'నా పార్టీని జోడించండి', 'నేను సిఫార్సు చేయాలనుకుంటున్నాను'\n"
        "   - Chinese: '上传活动', '添加我的派对', '如何提交', '我想推荐'\n"
        "   - Japanese: 'イベントをアップロード', 'パーティーを追加', '推薦したい'\n"
        "   - Korean: '이벤트 업로드', '내 파티 추가', '제출 방법', '추천하고 싶어요'\n"
        "   ANY similar phrase in ANY language should return true.\n"
        
        "4. 'date_range': {'start': 'YYYY-MM-DD', 'end': 'YYYY-MM-DD'} or null\n"
        "   CRITICAL DATE DETECTION RULES:\n"
        "   - If user mentions ANY temporal word like 'tomorrow', 'tonight', 'today', 'this weekend', 'next week', 'happening', 'going on', 'what's on', YOU MUST extract date_range\n"
        "   - Detect temporal words in ALL languages (e.g., 'mañana', 'demain', 'morgen', 'రేపు', 'غداً', 'מחר', '明日', '내일', etc.)\n"
        "   - 'tomorrow' → date_range: {'start': tomorrow_date, 'end': tomorrow_date}\n"
        "   - 'today' → date_range: {'start': today_date, 'end': today_date}\n"
        "   - 'tonight' → date_range: {'start': today_date, 'end': today_date}\n"
        "   - 'this weekend' → date_range: {'start': next_saturday, 'end': next_sunday}\n"
        "   - 'what happening' / 'what's on' / 'show me' + temporal word → ALWAYS means they want events with dates\n"
        "   EXAMPLES:\n"
        "   - 'what happening tomorrow' → date_range: {'start': tomorrow, 'end': tomorrow} ✅\n"
        "   - 'what's on tomorrow' → date_range: {'start': tomorrow, 'end': tomorrow} ✅\n"
        "   - 'anything tomorrow' → date_range: {'start': tomorrow, 'end': tomorrow} ✅\n"
        "   - 'show me tomorrow' → date_range: {'start': tomorrow, 'end': tomorrow} ✅\n"
        "   - 'events tomorrow' → date_range: {'start': tomorrow, 'end': tomorrow} ✅\n"
        
        "5. 'target_mood': string (romantic, chill, energetic, party, relaxed, upscale, casual)\n"
        
        "6. 'social_context': string (date, friends, solo, family, business)\n"
        
        "7. 'category': string (event, concert, show, bar, restaurant, cafe, theater, club, etc.)\n"
        "   IMPORTANT: If user asks temporal questions like 'what's happening', 'what's on', 'show me', automatically set category to 'event'\n"
        "   For businesses: detect cafe, bar, restaurant, theater, club, shop, mall, etc.\n"
        
        "8. 'specific_keywords': List of DIRECT and SPECIFIC keywords from the user's text. "
        "   - Examples: 'Salsa', 'Techno', 'Jazz', 'Rooftop', 'Live music', 'Coffee', 'Pizza', 'Theater'.\n"
        
        "9. 'user_language': detected ISO 639-1 language code (en, es, pt, fr, de, it, ru, ar, he, hi, te, ta, ko, ja, zh, etc.). Default to 'en' if uncertain.\n"

        "10. 'inferred_keywords': List of related, searchable keywords if the user's request is abstract. "
        "   - If the user asks for 'artistic' or 'cultural' things, infer related concrete terms.\n"
        "   - If the user's request is already specific (e.g., 'techno'), this can be null.\n"
        "   - Examples:\n"
        "     * User says 'artistic events' → inferred_keywords: ['art', 'gallery', 'exhibition', 'museum', 'theatre', 'performance', 'cultural']\n"
        "     * User says 'something intellectual' → inferred_keywords: ['lecture', 'talk', 'book', 'museum', 'cinema', 'art']\n"
        "     * User says 'a place with a nice view' → inferred_keywords: ['rooftop', 'terrace', 'view', 'balcony']\n"
        
        "Return STRICT JSON only. Remember: You understand ALL languages naturally."
    )
    
    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt}, 
                {"role": "user", "content": user_text}
            ],
            temperature=0
        )
        content = response.choices[0].message.content.strip()
        data = json.loads(content)
        
        if not isinstance(data, dict): 
            return {"user_language": "en"}
        
        if not data.get('user_language') or data.get('user_language') == 'unknown':
            data['user_language'] = 'en'
        
        logger.info(f"🧠 AI Analysis: {data}")
        return data
        
    except Exception as e:
        logger.error(f"AI Intent Error: {e}")
        return {"user_language": "en"}

def generate_just_for_you(user_age, item_name, item_desc, item_mood, social_context=None, user_language='en'):
    """
    Enhanced: Now generates personalized recommendations in user's detected language
    """
    try:
        context_msg = ""
        if social_context == 'date':
            context_msg = "Perfect for a romantic date night."
        elif social_context == 'friends':
            context_msg = "Great spot to hang out with friends."
        elif social_context == 'solo':
            context_msg = "Perfect for solo exploration."
        elif social_context == 'business':
            context_msg = "Ideal for business meetings."
        
        # Language instruction
        lang_instruction = f"Respond in the language code: {user_language}. "
        if user_language == 'te':
            lang_instruction += "Use Telugu script and language."
        elif user_language == 'he':
            lang_instruction += "Use Hebrew script and language."
        elif user_language == 'ar':
            lang_instruction += "Use Arabic script and language."
        elif user_language == 'hi':
            lang_instruction += "Use Hindi script and language."
        elif user_language == 'es':
            lang_instruction += "Use Spanish language."
        elif user_language == 'pt':
            lang_instruction += "Use Portuguese language."
        elif user_language == 'fr':
            lang_instruction += "Use French language."
        else:
            lang_instruction += "Use English language."
        
        prompt = (
            f"{lang_instruction} "
            f"Write a 1-sentence recommendation for a {user_age} year old. "
            f"Venue: {item_name}. Vibe: {item_mood}. {context_msg} "
            "Start with '✨ Just for you:' or equivalent in the target language. Be enthusiastic and specific."
        )
        
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            timeout=5
        )
        return response.choices[0].message.content.replace('"', '')
    except Exception as e:
        logger.error(f"Just for you error: {e}")
        if user_language == 'te':
            return f"✨ మీ కోసం: ఇది {item_mood} వైబ్‌తో సరిపోతుంది! {context_msg}"
        elif user_language == 'he':
            return f"✨ בשבילך: זה מתאים ל{item_mood} אווירה! {context_msg}"
        elif user_language == 'ar':
            return f"✨ لك خصيصاً: هذا يناسب الأجواء {item_mood}! {context_msg}"
        elif user_language == 'es':
            return f"✨ Just for you: ¡Esto coincide con el ambiente {item_mood}! {context_msg}"
        else:
            return f"✨ Just for you: This matches the {item_mood} vibe! {context_msg}"

def translate_text(text, target_language):
    if not text:
        return text
    
    try:
        lang_map = {
            'es': 'Spanish', 'pt': 'Portuguese', 'fr': 'French', 'de': 'German', 
            'it': 'Italian', 'ru': 'Russian', 'ar': 'Arabic', 'he': 'Hebrew', 
            'hi': 'Hindi', 'te': 'Telugu', 'ta': 'Tamil', 'ko': 'Korean', 
            'ja': 'Japanese', 'zh': 'Chinese'
        }
        lang_name = lang_map.get(target_language, 'English')
        
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": f"Translate the following text to {lang_name}. Maintain original tone. Only return the translation."},
                {"role": "user", "content": text}
            ],
            temperature=0.3,
            timeout=5
        )
        translated = response.choices[0].message.content.strip()
        return translated if translated else text
    except Exception as e:
        logger.error(f"Translation error: {e}")
        return text

def generate_closing_message(user_query, user_language='en'):
    try:
        lang_instruction_map = {
            'te': "Respond in Telugu using Telugu script.", 'he': "Respond in Hebrew using Hebrew script.",
            'ar': "Respond in Arabic using Arabic script.", 'hi': "Respond in Hindi using Devanagari script.",
            'es': "Respond in Spanish.", 'pt': "Respond in Portuguese.", 'fr': "Respond in French."
        }
        lang_instruction = lang_instruction_map.get(user_language, "Respond in English.")
        
        prompt = (
            f"User query: '{user_query}'. I sent recommendations. "
            f"Write a SHORT closing message asking if they want more suggestions. "
            f"Use 1 emoji. Be friendly. {lang_instruction}"
        )
        
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "You are Yara, a friendly Buenos Aires guide. You know everything."}, {"role": "user", "content": prompt}],
            temperature=0.7,
            timeout=4
        )
        return response.choices[0].message.content.replace('"', '')
    except:
        fallback_map = {
            'te': "మరిన్ని సూచనలు కావాలా? 🎉", 'he': "צריך עוד המלצות? 🎉",
            'ar': "هل تحتاج المزيد من الاقتراحات؟ 🎉", 'es': "¿Te gustaría más sugerencias? 🎉",
            'pt': "Gostaria de mais sugestões? 🎉"
        }
        return fallback_map.get(user_language, "Need more suggestions? 🎉")

# --- DATABASE FUNCTIONS ---

def get_user(conn, phone):
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM public.users WHERE phone = %s", (phone,))
        return cur.fetchone()

def create_user(conn, phone):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO public.users (phone, conversation_step) VALUES (%s, 'welcome') ON CONFLICT (phone) DO NOTHING", (phone,)
        )
        conn.commit()
        cur.execute("SELECT * FROM public.users WHERE phone = %s", (phone,))
        return cur.fetchone()

def update_user(conn, phone, data):
    set_clause = ", ".join([f"{key} = %s" for key in data.keys()])
    values = list(data.values())
    values.append(phone)
    with conn.cursor() as cur:
        cur.execute(f"UPDATE public.users SET {set_clause} WHERE phone = %s", values)
        conn.commit()

# --- ENHANCED SEARCH LOGIC ---

def build_search_query(table, ai_data, strictness_level):
    """
    FIXED: Changed 'type' to 'category' for businesses table
    """
    query = f"SELECT * FROM public.{table} WHERE 1=1"
    args = []
    
    date_range = ai_data.get('date_range') or {}
    social_context = ai_data.get('social_context')
    
    search_terms = []
    
    if ai_data.get('specific_keywords'):
        search_terms.extend(ai_data.get('specific_keywords'))

    if ai_data.get('inferred_keywords'):
        search_terms.extend(ai_data.get('inferred_keywords'))
    
    if ai_data.get('target_mood'):
        search_terms.append(ai_data.get('target_mood'))
    
    if social_context == 'date':
        search_terms.extend(['romantic', 'intimate', 'cozy'])
    elif social_context == 'friends':
        search_terms.extend(['social', 'group', 'casual'])
    
    cat = ai_data.get('category', '')
    if cat and len(cat) > 3 and cat.lower() not in ['event', 'party', 'show', 'place', 'spot']:
        search_terms.append(cat)
    
    search_terms = list(set([t for t in search_terms if t and len(t) > 2]))
    
    logger.info(f"🔍 Search Terms (Level {strictness_level}): {search_terms}")

    # --- DATE LOGIC (for events) ---
    if table == 'events' and date_range:
        start, end = date_range.get('start'), date_range.get('end')
        if start and end:
            start_obj = datetime.strptime(start, "%Y-%m-%d").date()
            end_obj = datetime.strptime(end, "%Y-%m-%d").date()
            days_in_range = [ (start_obj + timedelta(days=i)).strftime('%A') for i in range((end_obj - start_obj).days + 1) ]
            days_tuple = tuple(set(days_in_range))
            query += " AND ((event_date >= %s::date AND event_date <= %s::date) OR (recurring_day = ANY(%s)))"
            args.extend([start, end, list(days_tuple)])

    # --- TEXT SEARCH LOGIC (FIXED: Changed 'type' to 'category') ---
    if search_terms:
        if table == 'events':
            term_conditions = [f"(title ILIKE %s OR description ILIKE %s OR mood ILIKE %s OR music_type ILIKE %s OR location ILIKE %s)" for _ in search_terms]
        else:  # businesses table
            term_conditions = [f"(name ILIKE %s OR description ILIKE %s OR location ILIKE %s OR category ILIKE %s)" for _ in search_terms]
        
        for term in search_terms:
            term_wild = f"%{term}%"
            args.extend([term_wild] * (5 if table == 'events' else 4))
        
        join_operator = " AND " if strictness_level == 1 else " OR "
        query += f" AND ({join_operator.join(term_conditions)})"

    query += " ORDER BY event_date ASC LIMIT 5" if table == 'events' else " LIMIT 5"

    logger.info(f"📊 SQL Query: {query[:200]}...")
    logger.info(f"📊 Args: {args}")
    
    return query, args

def smart_search(conn, table, ai_data):
    """
    UPDATED: Added try-catch to prevent crashes. Returns empty list on error.
    """
    try:
        query, args = build_search_query(table, ai_data, strictness_level=1)
        with conn.cursor() as cur:
            cur.execute(query, tuple(args))
            results = cur.fetchall()
            if results:
                logger.info(f"✅ Found {len(results)} results (Strict)")
                return results

        query, args = build_search_query(table, ai_data, strictness_level=2)
        with conn.cursor() as cur:
            cur.execute(query, tuple(args))
            results = cur.fetchall()
            if results:
                logger.info(f"✅ Found {len(results)} results (Loose)")
                return results
            else:
                logger.warning(f"⚠️ No results in {table}")
                return []
    
    except Exception as e:
        logger.error(f"❌ Search error in {table}: {e}")
        return []

# ==============================================================================
# 🚀 TWILIO TYPING INDICATOR (NEW FEATURE)
# ==============================================================================

def send_typing_indicator(message_sid):
    """
    Sends a 'Typing' status to the WhatsApp user.
    This also marks the user's message as Read (Blue Ticks).
    """
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN: 
        return
    
    try:
        url = "https://messaging.twilio.com/v2/Indicators/Typing.json"
        
        # Twilio Auth
        auth = (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        
        # Payload as per docs
        data = {
            "messageId": message_sid,
            "channel": "whatsapp"
        }
        
        # Fire and forget request (timeout short to not block execution)
        response = requests.post(url, auth=auth, data=data, timeout=2)
        
        if response.status_code == 200:
            logger.info("✅ Typing indicator sent (Blue Ticks triggered)")
        else:
            logger.warning(f"⚠️ Typing indicator failed: {response.text}")
            
    except Exception as e:
        logger.error(f"❌ Error sending typing indicator: {e}")

def send_whatsapp_message(to, body, media_url=None):
    if not TWILIO_WHATSAPP_NUMBER: 
        return
    
    try:
        message_data = {
            'from_': TWILIO_WHATSAPP_NUMBER,
            'to': to,
            'body': body
        }
        if media_url:
            message_data['media_url'] = media_url
            
        twilio_client.messages.create(**message_data)
    except Exception as e:
        logger.error(f"❌ Twilio Error: {e}")

def ask_chatgpt_expert_fallback(user_input, ai_data, user_language='en'):
    """
    UPDATED: Prompt rewritten to be ALWAYS POSITIVE. Never says "not found" or "sorry"
    """
    category = ai_data.get('category')
    mood = ai_data.get('target_mood')
    social_context = ai_data.get('social_context')
    keywords = ai_data.get('specific_keywords', [])
    inferred_keywords = ai_data.get('inferred_keywords', [])
    date_range = ai_data.get('date_range') or {}
    date_str = date_range.get('start')
    
    context_parts = []
    if social_context: 
        context_parts.append(f"looking for {social_context} experience")
    if mood: 
        context_parts.append(f"wants {mood} vibe")
    if keywords: 
        context_parts.append(f"interested in: {', '.join(keywords)}")
    if inferred_keywords:
        context_parts.append(f"likes: {', '.join(inferred_keywords)}")
    if category: 
        context_parts.append(f"wants: {category}")
    if date_str: 
        context_parts.append(f"for date: {date_str}")
    
    context_description = ". ".join(context_parts) if context_parts else "looking for recommendations in Buenos Aires"
    
    lang_map = {
        'te': "CRITICAL: Respond ENTIRELY in Telugu using Telugu script (తెలుగు).",
        'he': "CRITICAL: Respond ENTIRELY in Hebrew using Hebrew script (עברית).",
        'ar': "CRITICAL: Respond ENTIRELY in Arabic using Arabic script (العربية).",
        'hi': "CRITICAL: Respond ENTIRELY in Hindi using Devanagari script (हिन्दी).",
        'es': "IMPORTANT: Respond in Spanish.",
        'pt': "IMPORTANT: Respond in Portuguese.",
        'fr': "IMPORTANT: Respond in French.",
    }
    lang_instruction = lang_map.get(user_language, "IMPORTANT: Respond in English.")
    
    expert_prompt = f"""You are Yara, the ULTIMATE Buenos Aires expert and local tour guide. 
You know EVERYTHING about Buenos Aires - every bar, every restaurant, every café, every hidden gem, every neighborhood.

USER'S REQUEST: "{user_input}"
USER CONTEXT: {context_description}

YOUR MISSION: Give them 2-3 PERFECT, SPECIFIC recommendations that match their request.

CRITICAL RULES - READ CAREFULLY:
1. ✅ BE POSITIVE AND CONFIDENT - You're an expert who knows the BEST places in Buenos Aires
2. ✅ Give 2-3 SPECIFIC place names with neighborhoods (Palermo, San Telmo, Recoleta, etc.)
3. ✅ Explain WHY each place is perfect for their request
4. ✅ Be enthusiastic and use emojis (🎯, ✨, 🍸, 🎵, etc.)
5. ❌ NEVER EVER say negative things like:
   - "sorry"
   - "not found"
   - "don't have"
   - "couldn't find"
   - "no matches"
   - "unfortunately"
6. ✅ Instead, say positive things like:
   - "I know the perfect spots!"
   - "Great choice! Here are amazing places!"
   - "You'll love these!"
   - "Perfect! Buenos Aires has incredible options!"

FORMAT YOUR RESPONSE EXACTLY LIKE THIS:
"[Enthusiastic intro acknowledging their request - NO negativity!]

🎯 **[Place Name]** in [Neighborhood]
[One sentence why it's perfect for them]

🎯 **[Place Name]** in [Neighborhood]
[One sentence why it's perfect for them]

🎯 **[Place Name]** in [Neighborhood]
[One sentence why it's perfect for them]

[Friendly closing with emoji]"

EXAMPLES OF GOOD INTROS (use similar tone):
- "Great choice! I know some incredible spots for that!" ✅
- "Perfect! Buenos Aires has amazing places for this!" ✅
- "Excellent! Here are some fantastic options!" ✅

EXAMPLES OF BAD INTROS (NEVER use these):
- "Sorry, I don't have information..." ❌
- "Unfortunately, I couldn't find..." ❌

{lang_instruction}

Remember: You're a confident expert. You ALWAYS have great recommendations!"""

    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are Yara, the ultimate Buenos Aires expert who knows EVERYTHING about the city. You're always positive, enthusiastic, and helpful. You NEVER say negative things. You always have great recommendations because you're a real expert."}, 
                {"role": "user", "content": expert_prompt}
            ],
            temperature=0.8,
            timeout=10
        )
        expert_response = response.choices[0].message.content
        logger.info(f"🎯 Expert Fallback Response Generated in {user_language}")
        return expert_response
    
    except Exception as e:
        logger.error(f"Fallback Error: {e}")
        fallback_map = {
            'te': "బ్యూనస్ ఎయిర్స్‌లో మీ కోసం కొన్ని అద్భుతమైన ప్రదేశాలు ఉన్నాయి! మరిన్ని వివరాలు ఇవ్వండి, నేను ఉత్తమ ప్రదేశాలను సూచిస్తాను! 🎯",
            'he': "יש כמה מקומות מדהימים בבואנוס איירס בשבילך! ספר לי עוד פרטים ואני אמליץ על המקומות הכי טובים! 🎯",
            'ar': "لدي أماكن رائعة في بوينس آيريس لك! أخبرني المزيد من التفاصيل وسأوصي بأفضل الأماكن! 🎯",
            'es': "¡Conozco lugares increíbles en Buenos Aires para ti! Cuéntame más detalles y te recomendaré los mejores sitios! 🎯",
            'pt': "Conheço lugares incríveis em Buenos Aires para você! Me conte mais detalhes e recomendarei os melhores lugares! 🎯",
        }
        return fallback_map.get(user_language, "I know some amazing places in Buenos Aires for you! Tell me more details and I'll recommend the best spots! 🎯")

# ==============================================================================
# PROCESS THREAD (Updated with MessageSid & Identity Check & Upload Feature)
# ==============================================================================

def process_message_thread(sender, text, message_sid=None):
    """
    UPDATED: Now accepts message_sid to trigger the typing indicator immediately.
    """
    
    # 1. Trigger Typing Indicator & Blue Ticks IMMEDIATELY
    if message_sid:
        send_typing_indicator(message_sid)
        
    conn = None
    try:
        conn = postgreSQL_pool.getconn()
        user = get_user(conn, sender)

        if not user:
            create_user(conn, sender)
            send_whatsapp_message(sender, "Hey! Welcome to Yara ai , I'm your Buenos Aires guide for finding the best plans in the city ✨ what are you in the mood for?")
            return

        step, user_age = user.get('conversation_step'), user.get('age', '25')
        user_name = user.get('name', 'Friend') # Retrieve Name from DB
        
        ai_data = executor.submit(analyze_user_intent, text).result() or {"user_language": "en"}
        user_language = ai_data.get('user_language', 'en')
        social_context = ai_data.get('social_context')

        logger.info(f"🌍 Detected Language: {user_language}")

        # --- 1. HANDLE GREETINGS ---
        if ai_data.get('is_greeting') and step != 'ask_name_age':
            greetings = {
                'te': f"నమస్కారం {user_name}! మీరు ఏమి వెతుకుతున్నారు?", 
                'he': f"שלום {user_name}! מה אתה מחפש?", 
                'ar': f"مرحباً {user_name}! ماذا تبحث؟", 
                'es': f"¡Hola {user_name}! ¿Qué estás buscando hoy?", 
                'en': f"Hey {user_name}! What are you looking for today?"
            }
            send_whatsapp_message(sender, greetings.get(user_language, greetings['en']))
            return

        # --- 2. HANDLE IDENTITY QUESTIONS ("Who am I?") --- 
        if ai_data.get('is_identity_question'):
            logger.info("👤 Identity question detected.")
            
            last_mood = user.get('last_mood', 'mystery')
            
            identity_prompt = (
                f"The user asked 'Who am I?' or 'What do you know about me?'. "
                f"User Name: {user_name}. Age: {user_age}. Last thing they looked for: {last_mood}. "
                f"Respond in language code '{user_language}'. "
                f"Be friendly, witty, and confirm you know them as Yara, their local guide. "
                "Example: 'You are [Name], my favorite [Age]-year-old explorer! We were just looking for [last_mood].'"
            )
            
            try:
                response = openai.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "system", "content": "You are Yara."}, {"role": "user", "content": identity_prompt}],
                    temperature=0.8
                )
                answer = response.choices[0].message.content.replace('"', '')
                send_whatsapp_message(sender, answer)
                return  # Stop processing here, don't search database
            except Exception as e:
                logger.error(f"Identity AI Error: {e}")
                # Fallback response
                send_whatsapp_message(sender, f"You are {user_name}, {user_age} years young! And I'm Yara, your guide! ✨")
                return

        # --- 3. HANDLE UPLOAD/SUBMIT EVENT REQUESTS (UPDATED WITH NEW LINK) ---
        if ai_data.get('wants_to_upload'):
            logger.info("📤 User wants to upload an event.")
            
            # Multilingual upload messages with NEW TALLY LINK
            upload_messages = {
                'en': "That's awesome! 🎉 We love new events.\n\nYou can upload your event details here:\n\nhttps://tally.so/r/EkqRYN",
                'es': "¡Genial! 🎉 Nos encantan los nuevos eventos.\n\nPuedes subir los detalles de tu evento aquí:\n\nhttps://tally.so/r/EkqRYN",
                'pt': "Isso é incrível! 🎉 Adoramos novos eventos.\n\nVocê pode enviar os detalhes do seu evento aqui:\n\nhttps://tally.so/r/EkqRYN",
                'fr': "C'est génial! 🎉 Nous adorons les nouveaux événements.\n\nVous pouvez télécharger les détails ici:\n\nhttps://tally.so/r/EkqRYN",
                'de': "Das ist großartig! 🎉 Wir lieben neue Veranstaltungen.\n\nSie können Ihre Veranstaltungsdetails hier hochladen:\n\nhttps://tally.so/r/EkqRYN",
                'it': "Fantastico! 🎉 Amiamo i nuovi eventi.\n\nPuoi caricare i dettagli del tuo evento qui:\n\nhttps://tally.so/r/EkqRYN",
                'ru': "Это здорово! 🎉 Мы любим новые события.\n\nВы можете загрузить детали вашего события здесь:\n\nhttps://tally.so/r/EkqRYN",
                'te': "అద్భుతం! 🎉 మాకు కొత్త ఈవెంట్‌లు చాలా ఇష్టం.\n\nమీరు మీ ఈవెంట్ వివరాలను ఇక్కడ అప్‌లోడ్ చేయవచ్చు:\n\nhttps://tally.so/r/EkqRYN",
                'he': "מדהים! 🎉 אנחנו אוהבים אירועים חדשים.\n\nאתה יכול להעלות את פרטי האירוע שלך כאן:\n\nhttps://tally.so/r/EkqRYN",
                'ar': "رائع! 🎉 نحب الأحداث الجديدة.\n\nيمكنك تحميل تفاصيل الحدث الخاص بك هنا:\n\nhttps://tally.so/r/EkqRYN",
                'hi': "बहुत बढ़िया! 🎉 हमें नए इवेंट्स पसंद हैं।\n\nआप अपने इवेंट की जानकारी यहाँ अपलोड कर सकते हैं:\n\nhttps://tally.so/r/EkqRYN",
                'zh': "太棒了！🎉 我们喜欢新活动。\n\n您可以在这里上传您的活动详情：\n\nhttps://tally.so/r/EkqRYN",
                'ja': "素晴らしい！🎉 新しいイベントが大好きです。\n\nイベントの詳細はこちらからアップロードできます：\n\nhttps://tally.so/r/EkqRYN",
                'ko': "멋지네요! 🎉 새로운 이벤트를 좋아합니다.\n\n여기에서 이벤트 세부정보를 업로드할 수 있습니다:\n\nhttps://tally.so/r/EkqRYN"
            }
            
            # Get the message in user's language (or English as fallback)
            final_message = upload_messages.get(user_language, upload_messages['en'])
            
            # Send the message (WhatsApp will auto-generate preview for the link)
            send_whatsapp_message(sender, final_message)
            
            return  # Stop processing, don't search database

        # --- 4. HANDLE ONBOARDING ---
        if step == 'welcome':
            messages = {
                'te': "మొదట, మీకు ఉత్తమ సూచనలు ఇవ్వడానికి, మీ పేరు మరియు వయస్సు ఏమిటి?", 
                'he': "קודם כל, מה שמך וגילך?", 
                'ar': "أولاً، ما هو اسمك وعمرك؟", 
                'es': "Primero, ¿cuál es tu nombre y edad?", 
                'en': "First, what's your name and age?"
            }
            send_whatsapp_message(sender, messages.get(user_language, messages['en']))
            update_user(conn, sender, {"conversation_step": "ask_name_age", "last_mood": text})
            return

        if step == 'ask_name_age':
            last_mood = user.get('last_mood')
            messages = {
                'te': f"సరే! '{last_mood}' కోసం చూపిస్తున్నాను:", 
                'he': f"מעולה! מראה אפשרויות עבור '{last_mood}':", 
                'ar': f"رائع! عرض الخيارات لـ '{last_mood}':", 
                'es': f"¡Perfecto! Buscando opciones para '{last_mood}':", 
                'en': f"Ok cool! Showing options for '{last_mood}':"
            }
            send_whatsapp_message(sender, messages.get(user_language, messages['en']))
            
            clean_name = re.sub(r'[^\w]', '', text.split()[0]) if text.split() else "Friend"
            age = "".join(filter(str.isdigit, text)) or "25"
            
            update_user(conn, sender, {"name": clean_name, "age": age, "conversation_step": "ready"})
            text = last_mood 
            ai_data = analyze_user_intent(text) or {"user_language": "en"}
            user_language = ai_data.get('user_language', 'en')
            social_context = ai_data.get('social_context')

        # ===================================================================
        # SEARCH LOGIC: EVENTS vs BUSINESSES (UNCHANGED - WORKING PERFECTLY)
        # ===================================================================
        
        found_something = False
        category = ai_data.get('category', '').lower()
        
        # Determine what user is SPECIFICALLY asking for
        wants_events = (
            ai_data.get('date_range') or  # Has specific date = wants events
            category in ['event', 'concert', 'show', 'party', 'festival', 'exhibition']
        )
        
        wants_businesses = category in ['bar', 'restaurant', 'cafe', 'club', 'shop', 'mall', 'theater', 'theatre']
        
        logger.info(f"🎯 User wants - Events: {wants_events}, Businesses: {wants_businesses}")
        
        # CASE 1: User SPECIFICALLY wants EVENTS
        if wants_events and not wants_businesses:
            logger.info("🔍 Searching EVENTS only...")
            events = smart_search(conn, 'events', ai_data)
            
            if events:
                found_something = True
                intro = translate_text(f"Here are some events matching your vibe:", user_language)
                if ai_data.get('date_range') and ai_data['date_range'].get('start'):
                    intro = translate_text(f"Here's what's happening around {ai_data['date_range']['start']}:", user_language)
                send_whatsapp_message(sender, intro)
                
                for e in events:
                    futures = {
                        'jfy': executor.submit(generate_just_for_you, user_age, e['title'], e['description'], e.get('mood', 'social'), social_context, user_language),
                        'title': executor.submit(translate_text, e.get('title'), user_language),
                        'desc': executor.submit(translate_text, e.get('description'), user_language),
                        'location': executor.submit(translate_text, e.get('location'), user_language),
                        'music': executor.submit(translate_text, e.get('music_type'), user_language)
                    }
                    
                    # Multilingual "Book your slot" text
                    ticket_section = ""
                    if e.get('ticket_link'):
                        book_text_map = {
                            'en': '🎟️ Book your slot',
                            'es': '🎟️ Reserva tu lugar',
                            'pt': '🎟️ Reserve seu lugar',
                            'fr': '🎟️ Réservez votre place',
                            'te': '🎟️ మీ స్లాట్‌ను బుక్ చేసుకోండి',
                            'he': '🎟️ הזמן את המקום שלך',
                            'ar': '🎟️ احجز مكانك',
                            'hi': '🎟️ अपनी जगह बुक करें'
                        }
                        book_text = book_text_map.get(user_language, '🎟️ Book your slot')
                        ticket_section = f"\n{book_text}: {e.get('ticket_link')}"
                    
                    display_date = e.get('event_date') if e.get('event_date') else f"Every {e.get('recurring_day')}"
                    caption = f"*{futures['title'].result()}*\n\n📍 {futures['location'].result()}\n🕒 {e.get('event_time')}\n📅 {display_date}\n🎵 {futures['music'].result()}\n📝 {futures['desc'].result()}{ticket_section}\n📸 {e.get('instagram_link')}\n\n{futures['jfy'].result()}"
                    send_whatsapp_message(sender, caption, media_url=e.get('image_url'))
            
            # If no events found, go straight to ChatGPT (DON'T search businesses)
            if not found_something:
                logger.info("🎯 No events found - Using ChatGPT fallback for events")
                send_whatsapp_message(sender, ask_chatgpt_expert_fallback(text, ai_data, user_language))
                return
        
        # CASE 2: User SPECIFICALLY wants BUSINESSES (CAFES, BARS, THEATERS, etc.)
        elif wants_businesses and not wants_events:
            logger.info("🔍 Searching BUSINESSES only...")
            businesses = smart_search(conn, 'businesses', ai_data)
            
            if businesses:
                found_something = True
                intro = translate_text("Found these spots for you:", user_language)
                send_whatsapp_message(sender, intro)
                
                for b in businesses:
                    futures = {
                        'jfy': executor.submit(generate_just_for_you, user_age, b['name'], b['description'], ai_data.get('target_mood') or 'chill', social_context, user_language),
                        'name': executor.submit(translate_text, b.get('name'), user_language),
                        'desc': executor.submit(translate_text, b.get('description'), user_language),
                        'location': executor.submit(translate_text, b.get('location'), user_language)
                    }
                    msg = f"*{futures['name'].result()}*\n📍 {futures['location'].result()}\n\n{futures['desc'].result()}\n\n📸 {b.get('instagram_link')}\n\n{futures['jfy'].result()}"
                    send_whatsapp_message(sender, msg, media_url=b.get('image_url'))
            
            # If no businesses found, go straight to ChatGPT (DON'T search events)
            if not found_something:
                logger.info("🎯 No businesses found - Using ChatGPT fallback for businesses")
                send_whatsapp_message(sender, ask_chatgpt_expert_fallback(text, ai_data, user_language))
                return
        
        # CASE 3: Ambiguous query - search BOTH
        else:
            logger.info("🔍 Ambiguous query - Searching both events and businesses...")
            
            # Try events first
            events = smart_search(conn, 'events', ai_data)
            if events:
                found_something = True
                intro = translate_text(f"Here are some events matching your vibe:", user_language)
                send_whatsapp_message(sender, intro)
                
                for e in events:
                    futures = {
                        'jfy': executor.submit(generate_just_for_you, user_age, e['title'], e['description'], e.get('mood', 'social'), social_context, user_language),
                        'title': executor.submit(translate_text, e.get('title'), user_language),
                        'desc': executor.submit(translate_text, e.get('description'), user_language),
                        'location': executor.submit(translate_text, e.get('location'), user_language),
                        'music': executor.submit(translate_text, e.get('music_type'), user_language)
                    }
                    
                    # Multilingual "Book your slot" text
                    ticket_section = ""
                    if e.get('ticket_link'):
                        book_text_map = {
                            'en': '🎟️ Book your slot', 
                            'es': '🎟️ Reserva tu lugar', 
                            'pt': '🎟️ Reserve seu lugar', 
                            'fr': '🎟️ Réservez votre place', 
                            'te': '🎟️ మీ స్లాట్‌ను బుక్ చేసుకోండి', 
                            'he': '🎟️ הזמן את המקום שלך', 
                            'ar': '🎟️ احجز مكانك', 
                            'hi': '🎟️ अपनी जगह बुक करें'
                        }
                        book_text = book_text_map.get(user_language, '🎟️ Book your slot')
                        ticket_section = f"\n{book_text}: {e.get('ticket_link')}"
                    
                    display_date = e.get('event_date') if e.get('event_date') else f"Every {e.get('recurring_day')}"
                    caption = f"*{futures['title'].result()}*\n\n📍 {futures['location'].result()}\n🕒 {e.get('event_time')}\n📅 {display_date}\n🎵 {futures['music'].result()}\n📝 {futures['desc'].result()}{ticket_section}\n📸 {e.get('instagram_link')}\n\n{futures['jfy'].result()}"
                    send_whatsapp_message(sender, caption, media_url=e.get('image_url'))
            
            # Try businesses
            businesses = smart_search(conn, 'businesses', ai_data)
            if businesses:
                found_something = True
                intro = translate_text("Found these spots for you:", user_language)
                send_whatsapp_message(sender, intro)
                
                for b in businesses:
                    futures = {
                        'jfy': executor.submit(generate_just_for_you, user_age, b['name'], b['description'], ai_data.get('target_mood') or 'chill', social_context, user_language),
                        'name': executor.submit(translate_text, b.get('name'), user_language),
                        'desc': executor.submit(translate_text, b.get('description'), user_language),
                        'location': executor.submit(translate_text, b.get('location'), user_language)
                    }
                    msg = f"*{futures['name'].result()}*\n📍 {futures['location'].result()}\n\n{futures['desc'].result()}\n\n📸 {b.get('instagram_link')}\n\n{futures['jfy'].result()}"
                    send_whatsapp_message(sender, msg, media_url=b.get('image_url'))
            
            # If nothing found in both, use ChatGPT
            if not found_something:
                logger.info("🎯 Nothing found in both tables - Using ChatGPT fallback")
                send_whatsapp_message(sender, ask_chatgpt_expert_fallback(text, ai_data, user_language))
                return
        
        # Send closing message if something was found
        if found_something:
            send_whatsapp_message(sender, generate_closing_message(text, user_language))

    except Exception as e:
        logger.error(f"Logic Error: {e}", exc_info=True)
        try:
            ai_data = analyze_user_intent(text) or {"user_language": "en"}
            user_language = ai_data.get('user_language', 'en')
            send_whatsapp_message(sender, ask_chatgpt_expert_fallback(text, ai_data, user_language))
        except:
            send_whatsapp_message(sender, "I know some amazing places in Buenos Aires for you! Tell me what you're looking for and I'll recommend the best spots! 🎯")
    finally:
        if conn: 
            postgreSQL_pool.putconn(conn)

# ==============================================================================
# 🌐 WEBHOOK
# ==============================================================================

@app.route("/webhook", methods=["POST"])
def twilio_webhook():
    incoming_msg = request.form.get('Body')
    sender_id = request.form.get('From')
    message_sid = request.form.get('MessageSid') # <--- Get the Message ID
    
    if not sender_id or not incoming_msg: return "" 
    
    resp = MessagingResponse()
    # Pass message_sid to the thread
    threading.Thread(target=process_message_thread, args=(sender_id, incoming_msg, message_sid)).start()
    return str(resp)

if __name__ == "__main__":
    print("🚀 Twilio WhatsApp Bot Starting...")
    print("✨ Features: Typing Indicators, Identity, Upload Link, Multilingual")
    print("✅ FIXED: Database column 'category' search corrected")
    app.run(port=5000)