import logging
import os
import requests
import smtplib
from email.mime.multipart import MIMEMultipart  
from email.mime.text import MIMEText
from typing import Optional
from livekit.agents import function_tool, RunContext
from langchain_community.tools import DuckDuckGoSearchRun

# Initialize search globally to save memory
ddg_search = DuckDuckGoSearchRun()

@function_tool()
async def search_web(
    context: RunContext, 
    query: str) -> str:
    """
    Search the web for real-time information, stock prices, or news.
    """
    try:
        logging.info(f"Executing web search for: {query}")
        # Explicitly mention stock price if query looks like a ticker
        results = ddg_search.run(query)
        if not results:
            return "I couldn't find any specific data on that topic at the moment."
        return results
    except Exception as e:
        logging.error(f"Search error: {e}")
        return f"I encountered an error while searching for {query}."

@function_tool()
async def get_weather(context: RunContext, city: str) -> str:
    """Get the current weather."""
    try:
        response = requests.get(f"https://wttr.in/{city}?format=3", timeout=5)
        return response.text.strip() if response.status_code == 200 else "Weather unavailable."
    except:
        return "I can't reach the weather service right now."

@function_tool()     
async def send_email(
    context: RunContext, 
    to_email: str,
    subject: str,
    message: str
) -> str:
    """Send an email via Gmail."""
    try:
        gmail_user = os.getenv("GMAIL_USER")
        gmail_pw = os.getenv("GMAIL_APP_PASSWORD")
        if not gmail_user or not gmail_pw: return "Credentials missing."
        
        msg = MIMEMultipart()
        msg['From'], msg['To'], msg['Subject'] = gmail_user, to_email, subject
        msg.attach(MIMEText(message, 'plain'))
        
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(gmail_user, gmail_pw)
            server.send_message(msg)
        return f"Email sent to {to_email}."
    except Exception as e:
        return f"Email failed: {str(e)}"
