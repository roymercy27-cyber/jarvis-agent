import logging
import os
import requests
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional
from livekit.agents import function_tool, RunContext
# NEW: Import Tavily
from tavily import AsyncTavilyClient

# Initialize Tavily Client
tavily_client = AsyncTavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

@function_tool()
async def get_weather(
    context: RunContext, 
    city: str) -> str:
    """Get the current weather for a given city."""
    try:
        response = requests.get(f"https://wttr.in/{city}?format=3")
        if response.status_code == 200:
            return response.text.strip()
        return f"Could not retrieve weather for {city}."
    except Exception as e:
        return f"Error retrieving weather: {e}"

@function_tool()
async def search_web(
    context: RunContext, 
    query: str) -> str:
    """
    Search the web for real-time information, news, and stock prices using Tavily.
    """
    try:
        # Using Tavily for high-quality AI-ready results
        # We use 'advanced' depth to ensure we get live data like stock prices
        response = await tavily_client.search(query, search_depth="advanced", max_results=5)
        results = response.get("results", [])
        
        if not results:
            return f"I couldn't find any recent information for '{query}'."
            
        formatted_results = "\n".join([f"- {r['content']} (Source: {r['url']})" for r in results])
        logging.info(f"Tavily search successful for: {query}")
        return f"Here is the latest information I found:\n{formatted_results}"
    except Exception as e:
        logging.error(f"Tavily search error: {e}")
        return f"An error occurred while searching the web: {str(e)}"

@function_tool()
async def send_email(
    context: RunContext,
    to_email: str,
    subject: str,
    message: str,
    cc_email: Optional[str] = None
) -> str:
    """Send an email through Gmail."""
    try:
        smtp_server = "smtp.gmail.com"
        smtp_port = 587
        gmail_user = os.getenv("GMAIL_USER")
        gmail_password = os.getenv("GMAIL_APP_PASSWORD")
        
        if not gmail_user or not gmail_password:
            return "Email failed: Credentials not configured."
        
        msg = MIMEMultipart()
        msg['From'] = gmail_user
        msg['To'] = to_email
        msg['Subject'] = subject
        if cc_email: msg['Cc'] = cc_email
        msg.attach(MIMEText(message, 'plain'))
        
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(gmail_user, gmail_password)
        server.sendmail(gmail_user, [to_email] + ([cc_email] if cc_email else []), msg.as_string())
        server.quit()
        return f"Email sent successfully to {to_email}"
    except Exception as e:
        return f"Error sending email: {e}"
