import logging
import os
import requests
import smtplib
import asyncio
from livekit import agents 
from tavily import TavilyClient
from email.mime.multipart import MIMEMultipart  
from email.mime.text import MIMEText
from typing import Optional

# Initialize Tavily
tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

@agents.function_tool(description="CRITICAL: Use for factual queries or recent events.")
async def search_web(query: str) -> str:
    """Search the internet for real-time information."""
    try:
        response = tavily.search(query=query, search_depth="advanced", max_results=3, include_answer=True)
        if response.get("answer"): return f"DIRECT SEARCH ANSWER: {response['answer']}"
        results = [f"- {res['title']}: {res['content']} ({res['url']})" for res in response.get("results", [])]
        return "\n".join(results) if results else "No relevant info found."
    except Exception as e:
        return f"Search error: {str(e)}"

@agents.function_tool(description="Get the current weather for a specific city.")
async def get_weather(city: str) -> str:
    """Fetch current weather using wttr.in."""
    try:
        response = requests.get(f"https://wttr.in/{city}?format=%C+%t+with+wind+at+%w")
        return f"Weather in {city}: {response.text.strip()}" if response.status_code == 200 else "Weather data unavailable."
    except Exception as e:
        return f"Weather error: {str(e)}"

@agents.function_tool(description="Send an email directly from Jarvis using Gmail SMTP.")
async def send_email(to_email: str, subject: str, message: str, cc_email: Optional[str] = None) -> str:
    """Sends a professional email via Gmail Port 465 (SSL)."""
    def _blocking_send():
        # Using standardized variable names
        gmail_user = os.getenv("GMAIL_USER")
        gmail_password = os.getenv("GMAIL_APP_PASSWORD")
        
        if not gmail_user or not gmail_password: 
            return "Email error: GMAIL_USER or GMAIL_APP_PASSWORD missing in Railway Variables."
            
        msg = MIMEMultipart()
        msg['From'] = gmail_user
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(message, 'plain'))
        
        if cc_email:
            msg['Cc'] = cc_email
        
        recipients = [to_email] + ([cc_email] if cc_email else [])
        
        try:
            # Port 465 is mandatory for SSL in many cloud environments
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(gmail_user, gmail_password)
                server.sendmail(gmail_user, recipients, msg.as_string())
            return f"Success: Email sent to {to_email} via SSL."
        except Exception as smtp_err:
            return f"SMTP Connection Error: {str(smtp_err)}"

    try: 
        logging.info(f"Jarvis attempting to send email to {to_email}...")
        result = await asyncio.to_thread(_blocking_send)
        return result
    except Exception as e: 
        return f"System Failure: {str(e)}"

@agents.function_tool(description="Triggers mobile to open WhatsApp.")
async def mobile_whatsapp(phone_number: str, message: str) -> str:
    """Handshake tool for mobile WhatsApp automation."""
    return f"WhatsApp request for {phone_number} initiated. Message: {message}"

@agents.function_tool(description="Triggers mobile to open Discord.")
async def mobile_discord(message: str) -> str:
    """Handshake tool for mobile Discord automation."""
    return "Discord uplink initiated."
