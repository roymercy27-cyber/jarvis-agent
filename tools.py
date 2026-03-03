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

tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

@function_tool()
async def search_web(context: RunContext, query: str) -> str:
    """CRITICAL: Use for factual queries or recent events."""
    try:
        response = tavily.search(query=query, search_depth="advanced", max_results=3, include_answer=True)
        if response.get("answer"): return f"DIRECT SEARCH ANSWER: {response['answer']}"
        results = [f"- {res['title']}: {res['content']} ({res['url']})" for res in response.get("results", [])]
        return "\n".join(results) if results else "No relevant info found."
    except Exception as e:
        return f"Search error: {str(e)}"

@function_tool()
async def get_weather(context: RunContext, city: str) -> str:
    """Get the current weather."""
    try:
        response = requests.get(f"https://wttr.in/{city}?format=%C+%t+with+wind+at+%w")
        return f"Weather in {city}: {response.text.strip()}" if response.status_code == 200 else "Weather data unavailable."
    except Exception as e:
        return f"Weather error: {str(e)}"

@function_tool()    
async def send_email(context: RunContext, to_email: str, subject: str, message: str, cc_email: Optional[str] = None) -> str:
    """Send an email."""
    def _blocking_send():
        gmail_user, gmail_password = os.getenv("GMAIL_USER"), os.getenv("GMAIL_APP_PASSWORD")
        if not gmail_user or not gmail_password: return "Email error: Credentials missing."
        msg = MIMEMultipart(); msg['From'] = gmail_user; msg['To'] = to_email; msg['Subject'] = subject
        msg.attach(MIMEText(message, 'plain'))
        recipients = [to_email] + ([cc_email] if cc_email else [])
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls(); server.login(gmail_user, gmail_password); server.sendmail(gmail_user, recipients, msg.as_string())
        return f"Success: Email sent to {to_email}."
    try: return await asyncio.to_thread(_blocking_send)
    except Exception as e: return f"Failed to send email: {str(e)}"

@function_tool()
async def mobile_whatsapp(context: RunContext, phone_number: str, message: str) -> str:
    """Triggers mobile to open WhatsApp. phone_number must include country code."""
    try:
        clean_number = phone_number.replace("+", "").replace(" ", "").replace("-", "")
        payload_str = f"whatsapp|{clean_number}|{message}"
        await context.room.local_participant.publish_data(payload_str.encode('utf-8'), reliable=True)
        return f"Initiating WhatsApp link for {clean_number}."
    except Exception as e:
        return f"WhatsApp Handshake failed: {e}"

@function_tool()
async def mobile_discord(context: RunContext, message: str) -> str:
    """Triggers mobile to open Discord."""
    try:
        payload_str = f"discord|none|{message}"
        await context.room.local_participant.publish_data(payload_str.encode('utf-8'), reliable=True)
        return "Initiating Discord uplink, sir."
    except Exception as e:
        return f"Discord Handshake failed: {e}"







