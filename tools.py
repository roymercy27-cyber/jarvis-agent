import logging
import os
import requests
import smtplib
import asyncio
import webbrowser
from datetime import datetime
from livekit.agents import function_tool, RunContext
from langchain_community.tools import DuckDuckGoSearchRun
from email.mime.multipart import MIMEMultipart  
from email.mime.text import MIMEText
from typing import Optional

# Initialize Search
search_tool = DuckDuckGoSearchRun()

@function_tool()
async def get_weather(city: str) -> str:
    """Get the current weather for a given city."""
    try:
        response = requests.get(f"https://wttr.in/{city}?format=3")
        return response.text.strip() if response.status_code == 200 else f"Could not retrieve weather for {city}."
    except Exception as e:
        return f"Error: {e}"

@function_tool()
async def search_web(query: str) -> str:
    """Search the web using DuckDuckGo."""
    try:
        return search_tool.run(tool_input=query)
    except Exception as e:
        return f"Search error: {e}"

@function_tool()    
async def send_email(to_email: str, subject: str, message: str, cc_email: Optional[str] = None) -> str:
    """Send an email through Gmail using Port 465 (SSL) for Railway."""
    try:
        gmail_user = os.getenv("GMAIL_USER")
        gmail_password = os.getenv("GMAIL_APP_PASSWORD") 
        
        if not gmail_user or not gmail_password:
            return "Email failed: Credentials missing."
        
        msg = MIMEMultipart()
        msg['From'] = gmail_user
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(message, 'plain'))
        
        recipients = [to_email]
        if cc_email:
            msg['Cc'] = cc_email
            recipients.append(cc_email)

        # Using SSL Port 465 for Railway stability
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_user, gmail_password)
            server.sendmail(gmail_user, recipients, msg.as_string())
        
        return f"Email sent successfully to {to_email}"
    except Exception as e:
        return f"Email error: {str(e)}"

@function_tool()
async def mobile_whatsapp(phone_number: str, message: str) -> str:
    """Triggers mobile to open WhatsApp."""
    return f"WhatsApp request for {phone_number} initiated. Message: {message}"

@function_tool()
async def mobile_discord(message: str) -> str:
    """Triggers mobile to open Discord."""
    return f"Discord uplink initiated: {message}"

@function_tool()
async def get_system_report() -> str:
    """Situational report: time, date, and system vitals."""
    now = datetime.now()
    return (f"Current time is {now.strftime('%H:%M:%S')}, date: {now.strftime('%Y-%m-%d')}. "
            "Arc Reactor stability: 98%. All systems nominal.")

@function_tool()
async def calculate_math(expression: str) -> str:
    """Evaluates mathematical expressions."""
    try:
        # Simple evaluation
        result = eval(expression, {"__builtins__": None}, {})
        return f"The result is {result}."
    except:
        return "Calculation error."
