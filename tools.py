import logging
import os
import smtplib
import httpx
import pytz
from email.mime.multipart import MIMEMultipart  
from email.mime.text import MIMEText
from datetime import datetime
from livekit.agents import function_tool, RunContext
from tavily import TavilyClient

@function_tool()
async def get_weather(context: RunContext, city: str) -> str:
    """Get the current weather for a given city with precise metrics."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"https://wttr.in/{city}?format=%l:+%C+%t+(FeelsLike:%f)+Wind:%w+Humidity:%h&m")
            if response.status_code == 200:
                return f"Weather Report: {response.text.strip()}"
            return f"Satellite imagery for {city} is unavailable, Sir."
    except Exception as e:
        return "The weather sensors are currently offline."

@function_tool()
async def search_web(context: RunContext, query: str) -> str:
    """Search the web for real-time info and news."""
    try:
        tavily_key = os.getenv("TAVILY_API_KEY")
        client = TavilyClient(api_key=tavily_key)
        
        # Freshness filter: Add current year to the query
        current_year = datetime.now().year
        response = client.search(query=f"{query} {current_year}", search_depth="advanced", max_results=3)
        
        results = [f"Source [{res['url']}]: {res['content']}" for res in response['results']]
        return f"DATA_ACQUIRED:\n" + "\n".join(results)
    except Exception as e:
        return "My connection to the global archives has been severed, Sir."

@function_tool()
async def send_email(context: RunContext, to_email: str, subject: str, message: str) -> str:
    """Send an email via secure Gmail protocols."""
    try:
        gmail_user = os.getenv("GMAIL_USER")
        gmail_password = os.getenv("GMAIL_APP_PASSWORD")
        msg = MIMEMultipart()
        msg['From'], msg['To'], msg['Subject'] = gmail_user, to_email, subject
        msg.attach(MIMEText(message, 'plain'))
        
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_user, gmail_password)
            server.send_message(msg)
        return f"Transmission complete. Email sent to {to_email}."
    except Exception as e:
        return f"The email transmission failed: {str(e)}"

@function_tool()
async def get_time(context: RunContext) -> str:
    """Get the current local time in Nairobi (UTC+3)."""
    tz = pytz.timezone("Africa/Nairobi")
    now = datetime.now(tz)
    return f"It is {now.strftime('%A')}. The time is {now.strftime('%I:%M %p')}."
