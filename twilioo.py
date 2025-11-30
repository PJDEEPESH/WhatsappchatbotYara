import os
import logging
import psycopg2
import threading
import json
from concurrent.futures import ThreadPoolExecutor
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta, date
from flask import Flask, request, jsonify
import requests
import openai
from twilio.rest import Client as TwilioClient 
from twilio.twiml.messaging_response import MessagingResponse 
from dotenv import load_dotenv

# 1. Load Environment Variables
load_dotenv()

app = Flask(__name__)

# --- CONFIGURATION (TWILIO ADDITIONS) ---
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

# --- GLOBAL THREAD POOL & TIMERS ---
executor = ThreadPoolExecutor(max_workers=5) 
user_timers = {}

# --- DATABASE POOL ---
try:
    postgreSQL_pool = psycopg2.pool.SimpleConnectionPool(
        1, 50, DB_URI, cursor_factory=RealDictCursor, connect_timeout=10
    )
    print("✅ Database Connection Pool Created (Supports concurrent users)")
except (Exception, psycopg2.DatabaseError) as error:
    print("❌ Error connecting to PostgreSQL", error)

# ==============================================================================
# 🧠 AI & UTILS (CRASH FIXES IMPLEMENTED)
# ==============================================================================

def analyze_user_intent(user_text):
    # ... (Logic remains mostly the same, strict JSON required)
    today_str = date.today().strftime("%Y-%m-%d")
    weekday_str = date.today().strftime("%A")
    
    system_prompt = (
        f"Current Date: {today_str} ({weekday_str}). "
        "Analyze the user's intent perfectly. "
        "1. 'is_greeting': boolean (true only if user JUST says 'hi', 'hello' with NO request). "
        "2. 'date_range': {'start': 'YYYY-MM-DD', 'end': 'YYYY-MM-DD'} or null. "
        "3. 'target_mood': string (e.g. romantic, chill, party). "
        "4. 'category': string (e.g. bar, club, museum). "
        "5. 'specific_keywords': List of strings. Specific things like 'salsa', 'techno', 'jazz', 'burger'. "
        "Return STRICT JSON."
    )
    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_text}],
            temperature=0
        )
        content = response.choices[0].message.content.strip()
        data = json.loads(content)
        return data
    except: return {}

def generate_just_for_you(user_age, item_name, item_desc, item_mood):
    try:
        # ... (Same logic)
        prompt = (
            f"Write a 1-sentence recommendation for a {user_age} year old. "
            f"Venue: {item_name}. Vibe: {item_mood}. "
            "Start with '✨ Just for you:'."
        )
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            timeout=3
        )
        return response.choices[0].message.content.replace('"', '')
    except:
        return f"✨ Just for you: This matches the {item_mood} vibe!"

def generate_closing_message(user_query):
    try:
        # ... (Same logic)
        prompt = (
            f"User query: '{user_query}'. I sent recommendations. "
            "Write a short closing message asking if they are satisfied. Use an emoji."
        )
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "You are Yara."}, 
                      {"role": "user", "content": prompt}],
            temperature=0.7,
            timeout=3
        )
        return response.choices[0].message.content.replace('"', '')
    except:
        return "Are you satisfied with these options? 🎉"

# --- DATABASE FUNCTIONS (UNTOUCHED) ---
# ... (All DB functions are identical) ...
def get_user(conn, phone):
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM public.users WHERE phone = %s", (phone,))
        return cur.fetchone()

def create_user(conn, phone):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO public.users (phone, conversation_step) VALUES (%s, 'welcome') ON CONFLICT (phone) DO NOTHING", (phone,))
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

def build_search_query(table, ai_data, strictness_level):
    query = f"SELECT * FROM public.{table} WHERE 1=1"
    args = []
    
    date_range = ai_data.get('date_range')
    mood = ai_data.get('target_mood')
    category = ai_data.get('category')
    keywords = ai_data.get('specific_keywords', [])

    # --- DATE LOGIC ---
    if table == 'events' and date_range:
        start = date_range['start']
        end = date_range['end']
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

    # --- FILTER LOGIC ---
    conditions = []

    # LEVEL 1: Keywords + Mood
    if strictness_level == 1:
        if keywords:
            for kw in keywords:
                kw_wild = f"%{kw}%"
                if table == 'events':
                    conditions.append(f"(title ILIKE %s OR description ILIKE %s OR music_type ILIKE %s)")
                    args.extend([kw_wild, kw_wild, kw_wild])
                else:
                    conditions.append(f"(name ILIKE %s OR description ILIKE %s)")
                    args.extend([kw_wild, kw_wild])
        if mood:
            args.append(f"%{mood}%")
            if table == 'events': conditions.append("mood ILIKE %s")
            else: conditions.append("description ILIKE %s")

    # LEVEL 2: Category OR Mood
    elif strictness_level == 2:
        if category:
            args.extend([f"%{category}%", f"%{category}%"])
            if table == 'events': conditions.append("(title ILIKE %s OR description ILIKE %s)")
            else: conditions.append("(name ILIKE %s OR description ILIKE %s)")
        if mood and not category:
            args.append(f"%{mood}%")
            if table == 'events': conditions.append("mood ILIKE %s")
            else: conditions.append("description ILIKE %s")

    # LEVEL 3: NO FILTERS (Just Date/All)
    elif strictness_level == 3:
        pass 

    if conditions:
        query += " AND (" + " OR ".join(conditions) + ")"

    if table == 'events': query += " ORDER BY event_date ASC LIMIT 5"
    else: query += " LIMIT 5"

    return query, args

def smart_search(conn, table, ai_data):
    # Attempt 1: Strict
    query, args = build_search_query(table, ai_data, 1)
    with conn.cursor() as cur:
        cur.execute(query, tuple(args))
        results = cur.fetchall()
        if results: return results

    # Attempt 2: Medium
    if ai_data.get('mood') or ai_data.get('category'):
        query, args = build_search_query(table, ai_data, 2)
        with conn.cursor() as cur:
            cur.execute(query, tuple(args))
            results = cur.fetchall()
            if results: return results

    # Attempt 3: Loose (Date only or All)
    query, args = build_search_query(table, ai_data, 3)
    with conn.cursor() as cur:
        cur.execute(query, tuple(args))
        results = cur.fetchall()
        return results

    return []

# --- TWILIO UTILS (REPLACED META LOGIC) ---

def send_whatsapp_message(to, body, media_url=None):
    if not TWILIO_WHATSAPP_NUMBER: return
    to_number_format = to 

    try:
        if media_url:
            message = twilio_client.messages.create(
                from_=TWILIO_WHATSAPP_NUMBER,
                to=to_number_format,
                body=body,
                media_url=media_url
            )
        else:
            message = twilio_client.messages.create(
                from_=TWILIO_WHATSAPP_NUMBER,
                to=to_number_format,
                body=body
            )
    except Exception as e:
        print(f"❌ Twilio Send Error: {e}")

# ==============================================================================
# 📡 FINAL FALLBACK (SMART CONTEXTUAL RESPONSE)
# ==============================================================================

def ask_chatgpt_fallback(user_input, ai_data):
    """
    Asks ChatGPT to generate a contextual, helpful suggestion when DB is empty.
    """
    category = ai_data.get('category')
    mood = ai_data.get('target_mood')
    date_str = ai_data.get('date_range', {}).get('start')
    
    # Construct a detailed prompt for the AI
    if date_str:
        context = f"The user asked about {date_str}. My database is empty for this date/topic. Suggest something appropriate for a tourist on this date."
    elif category:
        context = f"The user asked for '{category}' and my database is empty. Suggest a great general place in Buenos Aires that fits this category."
    elif mood:
        context = f"The user asked for a '{mood}' vibe, but my database is empty. Give a general, highly-rated suggestion that fits this mood."
    else:
        context = "The user made a request but my database has no matches. Suggest something fun and general for a tourist in Buenos Aires."

    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": f"You are Yara, an expert, non-stop helpful Buenos Aires local guide. {context}"}, 
                      {"role": "user", "content": user_input}],
            timeout=5
        )
        return response.choices[0].message.content
    except: 
        return "I couldn't find specific matches, but I'm looking for general ideas now! Try asking me again in a moment."


# --- TIMEOUT LOGIC (UNCHANGED) ---
def send_followup_message(user_id):
    try:
        print(f"⏰ Sending follow-up to {user_id}")
        msg = "Hey! Just checking in. Let me know if you need anything else! 👋"
        send_whatsapp_message(user_id, msg)
        if user_id in user_timers: del user_timers[user_id]
    except: pass

def reset_user_timer(user_id):
    if user_id in user_timers: user_timers[user_id].cancel()
    timer = threading.Timer(60.0, send_followup_message, args=[user_id])
    user_timers[user_id] = timer
    timer.start()


# ==============================================================================
# ⚙️ MAIN PROCESS
# ==============================================================================

def process_message_thread(sender, text):
    reset_user_timer(sender)

    conn = None
    try:
        conn = postgreSQL_pool.getconn()
        user = get_user(conn, sender)

        # NEW USER
        if not user:
            create_user(conn, sender)
            send_whatsapp_message(sender, "Hey! 🇦🇷 Welcome to Buenos Aires.\nI'm Yara, your local guide to events, bars, restaurants, and hidden gems.\nWhat are you in the mood for today?")
            return

        step = user.get('conversation_step')
        user_age = user.get('age', '25')

        # AI ANALYZE INTENT
        future_ai = executor.submit(analyze_user_intent, text)
        ai_data = future_ai.result()
        if not ai_data: ai_data = {}

        # GREETING
        if ai_data.get('is_greeting'):
            user_name = user.get('name')
            greeting = f"Hey {user_name}! What are you looking for today?" if user_name else "Hey! What are you looking for today?"
            send_whatsapp_message(sender, greeting)
            return

        # ONBOARDING
        if step == 'first_mood':
            send_whatsapp_message(sender, "First, to give you the best personalized recommendations, what’s your name and age?")
            update_user(conn, sender, {"conversation_step": "ask_name_age", "last_mood": text})
            return

        if step == 'ask_name_age':
            send_whatsapp_message(sender, f"Ok cool! Showing options for '{user.get('last_mood')}':")
            parts = text.split()
            name = parts[0] if parts else "Friend"
            age = "".join(filter(str.isdigit, text)) or "25"
            update_user(conn, sender, {"name": name, "age": age, "conversation_step": "ready"})
            text = user.get('last_mood') 
            ai_data = analyze_user_intent(text)

        # --- SEARCH LOGIC ---
        found_something = False

        # A. SEARCH EVENTS
        if ai_data.get('date_range') or ai_data.get('category') in ['event', 'party', 'show', 'concert']:
            events = smart_search(conn, 'events', ai_data)
            
            if events:
                found_something = True
                start_date = ai_data.get('date_range', {}).get('start')
                intro = f"Here is what's happening around {start_date}:" if start_date else "Here are some events matching your vibe:"
                send_whatsapp_message(sender, intro)

                for e in events:
                    future_jfy = executor.submit(generate_just_for_you, user_age, e['title'], e['description'], e.get('mood', 'social'))
                    just_for_you = future_jfy.result() # Parallel AI call
                    
                    display_date = e.get('event_date') if e.get('event_date') else f"Every {e.get('recurring_day')}"
                    caption = (
                        f"*{e.get('title')}*\n\n"
                        f"📍 Location: {e.get('location')}\n"
                        f"🕒 Time: {e.get('event_time')}\n"
                        f"📅 Date: {display_date}\n"
                        f"🎵 Music: {e.get('music_type')}\n"
                        f"📝 {e.get('description')}\n"
                        f"📸 {e.get('instagram_link')}\n\n"
                        f"{just_for_you}"
                    )
                    # TWILIO REQUIRES SEPARATE CALLS FOR MEDIA/TEXT
                    if e.get('image_url'): 
                        send_whatsapp_message(sender, caption, media_url=e.get('image_url'))
                    else: 
                        send_whatsapp_message(sender, caption)

        # B. SEARCH BUSINESSES (Fallback or Explicit Interest)
        if not found_something or ai_data.get('category') in ['bar', 'restaurant', 'cafe', 'shop', 'museum']:
            businesses = smart_search(conn, 'businesses', ai_data)
            
            if businesses:
                found_something = True
                send_whatsapp_message(sender, "Found these spots for you:")
                for b in businesses:
                    future_jfy = executor.submit(generate_just_for_you, user_age, b['name'], b['description'], 'chill')
                    just_for_you = future_jfy.result() # Parallel AI call
                    
                    msg = (
                        f"*{b.get('name')}*\n"
                        f"📍 {b.get('location')}\n\n"
                        f"{b.get('description')}\n\n"
                        f"📸 {b.get('instagram_link')}\n\n"
                        f"{just_for_you}"
                    )
                    send_whatsapp_message(sender, msg)

        # C. RESULT HANDLING
        if found_something:
            closing = generate_closing_message(text)
            send_whatsapp_message(sender, closing)
        else:
            # D. INTELLIGENT FALLBACK (The Final Solution)
            fallback_text = ask_chatgpt_fallback(text, ai_data)
            send_whatsapp_message(sender, fallback_text)

    except Exception as e:
        logger.error(f"Logic Error: {e}")
    finally:
        if conn: postgreSQL_pool.putconn(conn)

# ==============================================================================
# 🌐 TWILIO WEBHOOK (MAIN ENTRY POINT)
# ==============================================================================

@app.route("/webhook", methods=["POST"])
def twilio_webhook():
    incoming_msg = request.form.get('Body')
    sender_id = request.form.get('From') 

    # --- CRASH FIX IMPLEMENTATION ---
    if not sender_id or not incoming_msg:
        logger.warning("Received invalid Twilio request (Missing 'From' or 'Body'). Ignoring.")
        return "" 
    # --- END CRASH FIX ---
    
    resp = MessagingResponse()
    
    # 1. Start processing in a background thread to prevent Twilio timeout
    thread = threading.Thread(target=process_message_thread, args=(sender_id, incoming_msg))
    thread.start()
    
    # 2. Return empty TwiML response immediately
    return str(resp)

if __name__ == "__main__":
    print("🚀 Twilio Bot is starting...")
    print("\n⚠️ ACTION REQUIRED: Set your Twilio Webhook URL to point to /webhook.")
    print("   - Use Ngrok: Run 'ngrok http 5000' and paste the HTTPS URL into the Twilio Console.\n")
    app.run(port=5000)