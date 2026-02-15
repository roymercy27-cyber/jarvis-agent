import logging
from livekit.agents import function_tool, RunContext
import httpx 
import os
import smtplib
from email.mime.multipart import MIMEMultipart  
from email.mime.text import MIMEText
from typing import Optional
from datetime import datetime
import pytz
import asyncio 
from tavily import TavilyClient

@function_tool()
async def get_weather(
    context: RunContext,
    city: str
) -> str:
    """Get the current weather for a given city quickly and accurately."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"https://wttr.in/{city}?format=%l:+%C+%t+%w+%h")
            if response.status_code == 200:
                return response.text.strip()
            return f"Could not retrieve weather for {city}."
    except Exception as e:
        return f"Error: {e}"

@function_tool()
async def search_web(
    context: RunContext,
    query: str
) -> str:
    """Search the web for real-time info. Use this for stocks and news."""
    try:
        tavily_key = os.getenv("TAVILY_API_KEY")
        client = TavilyClient(api_key=tavily_key)
        
        # FIX: We use 'basic' depth and max_results=2 for maximum speed
        response = client.search(query=query, search_depth="basic", max_results=2)
        
        results = []
        for res in response['results']:
            results.append(f"Data: {res['content']}")
            
        search_summary = "\n".join(results)
        
        # FIX: Explicitly tell the LLM to respond now so the user doesn't have to nudge
        return f"SEARCH_COMPLETE: {search_summary}. Please provide the answer to the user immediately."
    except Exception as e:
        logging.error(f"Search error: {e}")
        return "I'm having trouble connecting to my search tools right now."

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
        gmail_password = os.getenv("GMAIL_APP_PASSWORD")
        msg = MIMEMultipart()
        msg['From'], msg['To'], msg['Subject'] = gmail_user, to_email, subject
        msg.attach(MIMEText(message, 'plain'))
        
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(gmail_user, gmail_password)
        server.sendmail(gmail_user, [to_email], msg.as_string())
        server.quit()
        return f"Email successfully sent to {to_email}"
    except Exception as e:
        return f"Email failed: {e}"

@function_tool()
async def get_time(
    context: RunContext
) -> str:
    """Get the current local time in Kenya (UTC+3)."""
    tz = pytz.timezone("Africa/Nairobi")
    current_time = datetime.now(tz).strftime("%I:%M %p")
    return f"The current time is {current_time}"