import logging
import os
import requests
import smtplib
import asyncio
from livekit.agents import llm
from tavily import TavilyClient
from email.mime.multipart import MIMEMultipart  
from email.mime.text import MIMEText
from typing import Optional

tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

@llm.ai_callable(description="CRITICAL: Use for factual queries or recent events.")
async def search_web(query: str) -> str:
    try:
        response = tavily.search(query=query, search_depth="advanced", max_results=3, include_answer=True)
        if response.get("answer"): return f"DIRECT SEARCH ANSWER: {response['answer']}"
        results = [f"- {res['title']}: {res['content']} ({res['url']})" for res in response.get("results", [])]
        return "\n".join(results) if results else "No relevant info found."
    except Exception as e:
        return f"Search error: {str(e)}"

@llm.ai_callable(description="Get the current weather for a specific city.")
async def get_weather(city: str) -> str:
    try:
        response = requests.get(f"https://wttr.in/{city}?format=%C+%t+with+wind+at+%w")
        return f"Weather in {city}: {response.text.strip()}" if response.status_code == 200 else "Weather data unavailable."
    except Exception as e:
        return f"Weather error: {str(e)}"

@llm.ai_callable(description="Send an email directly from Jarvis using Gmail SMTP.")
async def send_email(to_email: str, subject: str, message: str, cc_email: Optional[str] = None) -> str:
    def _blocking_send():
        gmail_user = os.getenv("GMAIL_USER") or os.getenv("EMAIL_SENDER")
        gmail_password = os.getenv("GMAIL_APP_PASSWORD") or os.getenv("EMAIL_APP_PASSWORD")
        
        if not gmail_user or not gmail_password: 
            return "Email error: Credentials missing (GMAIL_USER/GMAIL_APP_PASSWORD)."
            
        msg = MIMEMultipart()
        msg['From'] = gmail_user
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(message, 'plain'))
        
        recipients = [to_email] + ([cc_email] if cc_email else [])
        
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(gmail_user, gmail_password)
            server.sendmail(gmail_user, recipients, msg.as_string())
        return f"Success: Email sent to {to_email}."

    try: 
        return await asyncio.to_thread(_blocking_send)
    except Exception as e: 
        return f"Failed to send email: {str(e)}"

@llm.ai_callable(description="Triggers mobile to open WhatsApp. phone_number must include country code.")
async def mobile_whatsapp(phone_number: str, message: str) -> str:
    # Note: In the new API, we use the local participant from the session or global context if available
    return f"Jarvis is preparing a WhatsApp link for {phone_number}. (Command: {message})"

@llm.ai_callable(description="Triggers mobile to open Discord.")
async def mobile_discord(message: str) -> str:
    return "Initiating Discord uplink, sir."
