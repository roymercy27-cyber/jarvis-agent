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
    """Get the current weather for a city quickly."""
    try:
        # Reduced timeout to 3.0s for faster failure recovery
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"https://wttr.in/{city}?format=%l:+%C+%t+%w+%h")
            return response.text.strip() if response.status_code == 200 else f"Weather unavailable for {city}."
    except Exception:
        return "Weather sensors offline."

@function_tool()
async def search_web(context: RunContext, query: str) -> str:
    """Search the web for real-time info (stocks, news)."""
    try:
        client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
        # Using 'basic' depth for 2x faster results than 'advanced'
        response = client.search(query=query, search_depth="basic", max_results=2)
        
        results = "\n".join([f"Data: {res['content']}" for res in response['results']])
        # Return a trigger phrase to ensure Jarvis speaks immediately
        return f"SEARCH_RESULTS: {results}. Assistant, summarize this for the user now."
    except Exception:
        return "Search archives unreachable."

@function_tool()
async def send_email(context: RunContext, to_email: str, subject: str, message: str) -> str:
    """Send an email through Gmail."""
    try:
        gmail_user = os.getenv("GMAIL_USER")
        gmail_password = os.getenv("GMAIL_APP_PASSWORD")
        msg = MIMEMultipart()
        msg['From'], msg['To'], msg['Subject'] = gmail_user, to_email, subject
        msg.attach(MIMEText(message, 'plain'))
        
        # Use simple SMTP for faster connection than SSL on some networks
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(gmail_user, gmail_password)
        server.sendmail(gmail_user, [to_email], msg.as_string())
        server.quit()
        return f"Email sent to {to_email}."
    except Exception as e:
        return f"Email failed: {e}"

@function_tool()
async def get_time(context: RunContext) -> str:
    """Get current local time in Kenya (UTC+3)."""
    tz = pytz.timezone("Africa/Nairobi")
    return f"The current time is {datetime.now(tz).strftime('%I:%M %p')}."
