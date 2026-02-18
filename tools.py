import os
import smtplib
import httpx
import pytz
from email.mime.multipart import MIMEMultipart  
from email.mime.text import MIMEText
from datetime import datetime
from livekit.agents import function_tool, RunContext
from tavily import AsyncTavilyClient

@function_tool()
async def get_weather(context: RunContext, city: str) -> str:
    """Get the current weather for a city."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"https://wttr.in/{city}?format=%l:+%C+%t")
            return response.text.strip() if response.status_code == 200 else "Weather unavailable."
    except Exception:
        return "Weather service timeout."

@function_tool()
async def search_web(context: RunContext, query: str) -> str:
    """Search the web for real-time info using Tavily."""
    try:
        # Using Async client to prevent blocking the agent
        tavily = AsyncTavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
        response = await tavily.search(query=query, search_depth="basic", max_results=2)
        
        results = "\n".join([res['content'] for res in response['results']])
        return f"Found info: {results}"
    except Exception as e:
        return f"Search failed: {str(e)}"

@function_tool()
async def send_email(context: RunContext, to_email: str, subject: str, message: str) -> str:
    """Send an email via Gmail SMTP."""
    try:
        gmail_user = os.getenv("GMAIL_USER")
        gmail_password = os.getenv("GMAIL_APP_PASSWORD")
        
        msg = MIMEMultipart()
        msg['From'], msg['To'], msg['Subject'] = gmail_user, to_email, subject
        msg.attach(MIMEText(message, 'plain'))
        
        # SMTP should be wrapped in a thread if it takes too long, 
        # but for simple text, this is usually fine.
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(gmail_user, gmail_password)
            server.sendmail(gmail_user, [to_email], msg.as_string())
        return f"Successfully sent email to {to_email}."
    except Exception as e:
        return f"Email error: {e}"

@function_tool()
async def get_time(context: RunContext) -> str:
    """Get current time in Kenya."""
    tz = pytz.timezone("Africa/Nairobi")
    return f"It is currently {datetime.now(tz).strftime('%I:%M %p')} in Kenya."
