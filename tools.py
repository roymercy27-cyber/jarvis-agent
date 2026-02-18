import logging
import os
import smtplib
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from email.mime.multipart import MIMEMultipart  
from email.mime.text import MIMEText
from typing import Optional
import requests
from livekit.agents import function_tool, RunContext
from duckduckgo_search import DDGS 

@function_tool()
async def get_current_time(context: RunContext, timezone: str = "Africa/Nairobi") -> str:
    """Get the current local time. Call this whenever the user asks for the time."""
    try:
        # ZoneInfo looks for the 'tzdata' package in your requirements.txt
        now = datetime.now(ZoneInfo(timezone))
        return f"It is currently {now.strftime('%I:%M %p')} in {timezone} on {now.strftime('%A, %b %d')}."
    except Exception as e:
        # Fallback to UTC if timezone lookup fails (common in slim cloud containers)
        logging.error(f"Timezone error for {timezone}: {e}")
        now_utc = datetime.now(ZoneInfo("UTC"))
        return f"I had trouble accessing the {timezone} clock, but the current UTC time is {now_utc.strftime('%I:%M %p')}."

@function_tool()
async def get_weather(context: RunContext, city: str) -> str:
    """Get the current weather for a city."""
    try:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1"
        res = requests.get(geo_url).json()
        if not res.get("results"): return f"I couldn't find {city}."
        loc = res["results"][0]
        w_url = f"https://api.open-meteo.com/v1/forecast?latitude={loc['latitude']}&longitude={loc['longitude']}&current_weather=true"
        w_data = requests.get(w_url).json()
        temp = w_data["current_weather"]["temperature"]
        return f"The current weather in {city} is {temp}°C."
    except Exception as e:
        logging.error(f"Weather error: {e}")
        return "Weather service unavailable."

@function_tool()
async def search_web(context: RunContext, query: str) -> str:
    """Search the web for up-to-date information."""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
            if not results: return "No search results found."
            blob = "\n".join([f"- {r['title']}: {r['body']}" for r in results])
            return f"Results for '{query}':\n{blob}"
    except Exception as e:
        logging.error(f"Search error: {e}")
        return "Search failed."

@function_tool()    
async def send_email(
    context: RunContext, 
    to_email: str,
    subject: str,
    message: str,
    cc_email: Optional[str] = None
) -> str:
    """Send an email through Gmail."""
    try:
        gmail_user = os.getenv("GMAIL_USER")
        gmail_pass = os.getenv("GMAIL_APP_PASSWORD") 
        if not gmail_user or not gmail_pass: return "Email failed: Missing credentials."
        
        msg = MIMEMultipart()
        msg['From'], msg['To'], msg['Subject'] = gmail_user, to_email, subject
        if cc_email: msg['Cc'] = cc_email
        msg.attach(MIMEText(message, 'plain'))
        
        def _send():
            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.starttls()
                server.login(gmail_user, gmail_pass)
                server.sendmail(gmail_user, [to_email] + ([cc_email] if cc_email else []), msg.as_string())
        
        await asyncio.to_thread(_send)
        return f"Email sent to {to_email}."
    except Exception as e:
        return f"Email error: {str(e)}"
