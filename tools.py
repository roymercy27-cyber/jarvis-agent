import logging
import os
import requests
import smtplib
import asyncio
from livekit.agents import function_tool, RunContext
from tavily import TavilyClient
from email.mime.multipart import MIMEMultipart  
from email.mime.text import MIMEText
from typing import Optional

# Initialize Tavily Client
tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

@function_tool()
async def search_web(context: RunContext, query: str) -> str:
    """CRITICAL: Use for factual queries, news, or recent events. DO NOT guess."""
    try:
        response = tavily.search(query=query, search_depth="advanced", max_results=3, include_answer=True)
        if response.get("answer"):
            return f"DIRECT SEARCH ANSWER: {response['answer']}"
        results = [f"- {res['title']}: {res['content']} ({res['url']})" for res in response.get("results", [])]
        return "\n".join(results) if results else "No relevant information found."
    except Exception as e:
        logging.error(f"Tavily error: {e}")
        return f"Search error: {str(e)}"

@function_tool()
async def get_weather(context: RunContext, city: str) -> str:
    """Get the current weather for a specific city."""
    try:
        response = requests.get(f"https://wttr.in/{city}?format=%C+%t+with+wind+at+%w")
        return f"Weather in {city}: {response.text.strip()}" if response.status_code == 200 else "Data unavailable."
    except Exception as e:
        return f"Weather service error: {str(e)}"

@function_tool()    
async def send_email(context: RunContext, to_email: str, subject: str, message: str, cc_email: Optional[str] = None) -> str:
    """Send an email using Gmail SMTP via background thread."""
    def _blocking_send():
        gmail_user = os.getenv("GMAIL_USER")
        gmail_password = os.getenv("GMAIL_APP_PASSWORD")
        if not gmail_user or not gmail_password: return "Credentials not configured."
        msg = MIMEMultipart(); msg['From'] = gmail_user; msg['To'] = to_email; msg['Subject'] = subject
        msg.attach(MIMEText(message, 'plain'))
        recipients = [to_email] + ([cc_email] if cc_email else [])
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls(); server.login(gmail_user, gmail_password)
            server.sendmail(gmail_user, recipients, msg.as_string())
        return f"Success: Email sent to {to_email}."
    try:
        return await asyncio.to_thread(_blocking_send)
    except Exception as e:
        return f"Failed to send email: {str(e)}"

# --- NEW DISCORD & MOBILE PROTOCOLS ---

@function_tool()
async def send_discord_message(context: RunContext, message: str) -> str:
    """Sends a priority message to the Discord command center."""
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url: return "Discord uplink not configured, sir."
    
    def _post():
        return requests.post(webhook_url, json={"content": message, "username": "JARVIS"})
    
    try:
        response = await asyncio.to_thread(_post)
        return "Message transmitted to Discord channel." if response.status_code == 204 else "Discord relay failed."
    except Exception as e:
        return f"Discord error: {e}"

@function_tool()
async def mobile_whatsapp(context: RunContext, phone_number: str, message: str) -> str:
    """Triggers a WhatsApp message protocol on your Android device."""
    try:
        payload = f"whatsapp|{phone_number}|{message}".encode('utf-8')
        await context.room.local_participant.publish_data(payload)
        return f"Signal sent to mobile device for {phone_number}."
    except Exception as e:
        return f"Mobile uplink failure: {e}"

@function_tool()
async def check_calendar(context: RunContext) -> str:
    """Accesses your schedule via the n8n nexus flow."""
    url = os.getenv("N8N_CALENDAR_WEBHOOK_URL")
    if not url: return "n8n link missing."
    try:
        response = await asyncio.to_thread(lambda: requests.get(url))
        return f"Your schedule: {response.text}" if response.status_code == 200 else "Schedule sync failed."
    except Exception as e:
        return f"n8n error: {e}"
