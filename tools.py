import logging
import os
import smtplib
import httpx
import pytz
from email.mime.multipart import MIMEMultipart  
from email.mime.text import MIMEText
from typing import Optional
from datetime import datetime
from livekit.agents import function_tool, RunContext
from tavily import TavilyClient

@function_tool()
async def get_weather(context: RunContext, city: str) -> str:
    """Get the current weather for a given city."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"https://wttr.in/{city}?format=%l:+%C+%t+%w+%h")
            if response.status_code == 200:
                return response.text.strip()
            return f"Could not retrieve weather for {city}."
    except Exception as e:
        return f"Weather Error: {e}"

@function_tool()
async def search_web(context: RunContext, query: str) -> str:
    """Search the web for real-time info, stocks, and news."""
    try:
        tavily_key = os.getenv("TAVILY_API_KEY")
        client = TavilyClient(api_key=tavily_key)
        
        # Optimized for speed: 'basic' depth and limited results
        response = client.search(query=query, search_depth="basic", max_results=2)
        
        results = [f"Source: {res['content']}" for res in response['results']]
        search_summary = "\n".join(results)
        
        return f"DATA_ACQUIRED: {search_summary}. Answer the user immediately."
    except Exception as e:
        logging.error(f"Search error: {e}")
        return "Search systems are currently offline, Sir."

@function_tool()
async def send_email(context: RunContext, to_email: str, subject: str, message: str) -> str:
    """Send an email through Gmail."""
    try:
        gmail_user = os.getenv("GMAIL_USER")
        gmail_password = os.getenv("GMAIL_APP_PASSWORD")
        msg = MIMEMultipart()
        msg['From'], msg['To'], msg['Subject'] = gmail_user, to_email, subject
        msg.attach(MIMEText(message, 'plain'))
        
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(gmail_user, gmail_password)
            server.sendmail(gmail_user, [to_email], msg.as_string())
        return f"Email sent to {to_email}."
    except Exception as e:
        return f"Email failed: {e}"

@function_tool()
async def get_time(context: RunContext) -> str:
    """Get the current local time in Kenya (UTC+3)."""
    tz = pytz.timezone("Africa/Nairobi")
    return f"The current time is {datetime.now(tz).strftime('%I:%M %p')}."
