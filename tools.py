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
    """Get the current weather for a given city with precise metrics."""
    try:
        # 'm' for metric, 'M' for wind speed in m/s, 1 for current condition only
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"https://wttr.in/{city}?format=%l:+%C+%t+(FeelsLike:%f)+Wind:%w+Humidity:%h&m")
            if response.status_code == 200:
                return f"Current weather in {response.text.strip()}"
            return f"I'm unable to reach the weather service for {city} right now, Sir."
    except Exception as e:
        logging.error(f"Weather error: {e}")
        return "The weather satellites are unresponsive at the moment."

@function_tool()
async def search_web(context: RunContext, query: str) -> str:
    """Search the web for real-time info. Optimized for accuracy and freshness."""
    try:
        tavily_key = os.getenv("TAVILY_API_KEY")
        client = TavilyClient(api_key=tavily_key)
        
        # Injecting current year into query to ensure the most recent data
        current_year = datetime.now().year
        refined_query = f"{query} {current_year}"
        
        # Use 'advanced' for accuracy, but max_results=3 for speed
        response = client.search(query=refined_query, search_depth="advanced", max_results=3)
        
        results = []
        for res in response['results']:
            results.append(f"Source [{res['url']}]: {res['content']}")
        
        search_summary = "\n".join(results)
        return f"CRITICAL_DATA_FOUND:\n{search_summary}\nAnalyze this and brief the user immediately."
    except Exception as e:
        logging.error(f"Search error: {e}")
        return "My connection to the global archives has been interrupted, Sir."

@function_tool()
async def send_email(context: RunContext, to_email: str, subject: str, message: str) -> str:
    """Send an encrypted email via Gmail secure protocols."""
    try:
        gmail_user = os.getenv("GMAIL_USER")
        gmail_password = os.getenv("GMAIL_APP_PASSWORD")
        
        msg = MIMEMultipart()
        msg['From'], msg['To'], msg['Subject'] = gmail_user, to_email, subject
        msg.attach(MIMEText(message, 'plain'))
        
        # Using SMTP_SSL for a more stable and secure connection
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_user, gmail_password)
            server.send_message(msg)
            
        return f"Protocol complete. Email sent to {to_email}."
    except Exception as e:
        logging.error(f"Email failure: {e}")
        return f"The email transmission failed: {str(e)}"

@function_tool()
async def get_time(context: RunContext) -> str:
    """Get the precise current time and date for Nairobi (UTC+3)."""
    tz = pytz.timezone("Africa/Nairobi")
    now = datetime.now(tz)
    # Added day and date for better context
    return f"It is {now.strftime('%A, %B %d')}. The time is {now.strftime('%I:%M %p')}."
