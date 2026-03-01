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
    """
    CRITICAL: Use this tool for ANY factual query, news, stock prices, or recent events. 
    DO NOT guess. If the user asks for information from the internet, you MUST call this.
    """
    try:
        response = tavily.search(
            query=query, 
            search_depth="advanced", 
            max_results=3, 
            include_answer=True
        )
        
        if response.get("answer"):
            return f"DIRECT SEARCH ANSWER: {response['answer']}"
        
        results = []
        for res in response.get("results", []):
            results.append(f"- {res['title']}: {res['content']} ({res['url']})")
        
        output = "\n".join(results)
        return output if output else "No relevant real-time information found."
        
    except Exception as e:
        logging.error(f"Tavily error: {e}")
        return f"Search error: {str(e)}"

@function_tool()
async def get_weather(context: RunContext, city: str) -> str:
    """Get the current weather for a specific city."""
    try:
        response = requests.get(f"https://wttr.in/{city}?format=%C+%t+with+wind+at+%w")
        if response.status_code == 200:
            return f"Weather in {city}: {response.text.strip()}"
        return f"I couldn't find weather data for {city} right now."
    except Exception as e:
        return f"Weather service error: {str(e)}"

@function_tool()    
async def send_email(
    context: RunContext,
    to_email: str,
    subject: str,
    message: str,
    cc_email: Optional[str] = None
) -> str:
    """Send an email. Mandatory parameters: to_email, subject, message."""
    def _blocking_send():
        gmail_user = os.getenv("GMAIL_USER")
        gmail_password = os.getenv("GMAIL_APP_PASSWORD")
        if not gmail_user or not gmail_password:
            return "Email error: Credentials not configured."

        msg = MIMEMultipart()
        msg['From'] = gmail_user
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(message, 'plain'))
        
        recipients = [to_email]
        if cc_email:
            msg['Cc'] = cc_email
            recipients.append(cc_email)

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(gmail_user, gmail_password)
            server.sendmail(gmail_user, recipients, msg.as_string())
        
        return f"Success: Email sent to {to_email}."

    try:
        result = await asyncio.to_thread(_blocking_send)
        return result
    except Exception as e:
        logging.error(f"Email failed: {e}")
        return f"Failed to send email: {str(e)}"

@function_tool()
async def mobile_whatsapp(
    context: RunContext, 
    phone_number: str, 
    message: str
) -> str:
    """
    Triggers your mobile device to open WhatsApp with a specific message.
    The phone number should include the country code (e.g., +1234567890).
    """
    try:
        # Construct the payload for the Android listener
        payload_str = f"whatsapp|{phone_number}|{message}"
        payload = payload_str.encode('utf-8')
        
        # Publish to the room so the Android app catches it
        await context.room.local_participant.publish_data(payload)
        
        logging.info(f"WhatsApp handshake sent for {phone_number}")
        return f"Protocol initiated. Transmitting the WhatsApp data to your device for {phone_number}."
    except Exception as e:
        logging.error(f"WhatsApp Handshake failed: {e}")
        return "I encountered a disturbance in the mobile uplink, sir."
