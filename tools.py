import logging
import os
import requests
import smtplib
from livekit.agents import function_tool, RunContext
from tavily import TavilyClient
from email.mime.multipart import MIMEMultipart  
from email.mime.text import MIMEText
from typing import Optional

# Initialize Tavily Client (ensure TAVILY_API_KEY is in your .env)
tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

@function_tool()
async def search_web(
    context: RunContext, 
    query: str) -> str:
    """
    Search the web for real-time information, news, or specific facts.
    Use this for any questions about current events or data not in your training set.
    """
    try:
        # Using 'advanced' depth for higher accuracy and better reasoning
        response = tavily.search(query=query, search_depth="advanced", max_results=5)
        
        results = []
        for res in response.get("results", []):
            results.append(f"Title: {res['title']}\nContent: {res['content']}\nURL: {res['url']}\n")
        
        output = "\n".join(results)
        logging.info(f"Tavily search for '{query}' completed.")
        return output if output else "No relevant results found."
    except Exception as e:
        logging.error(f"Tavily search error: {e}")
        return f"Error searching the web: {str(e)}"

@function_tool()
async def get_weather(context: RunContext, city: str) -> str:
    """Get the current weather for a specific city."""
    try:
        response = requests.get(f"https://wttr.in/{city}?format=%C+%t+%w")
        if response.status_code == 200:
            return f"Current weather in {city}: {response.text.strip()}"
        return f"Could not retrieve weather for {city}."
    except Exception as e:
        return f"Weather error: {str(e)}"

@function_tool()    
async def send_email(
    context: RunContext,
    to_email: str,
    subject: str,
    message: str,
    cc_email: Optional[str] = None
) -> str:
    """Send an email. Requires 'to_email', 'subject', and 'message'."""
    try:
        gmail_user = os.getenv("GMAIL_USER")
        gmail_password = os.getenv("GMAIL_APP_PASSWORD")
        
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
        
        return f"Email successfully sent to {to_email}"
    except Exception as e:
        return f"Failed to send email: {str(e)}"
