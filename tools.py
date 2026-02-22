import logging
import os
import requests
import smtplib
from email.mime.multipart import MIMEMultipart  
from email.mime.text import MIMEText
from typing import Optional
from livekit.agents import function_tool, RunContext
# Switched from DuckDuckGo to Tavily
from tavily import AsyncTavilyClient

# Initialize Tavily (Ensure TAVILY_API_KEY is in your environment variables)
tavily_client = AsyncTavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

@function_tool()
async def get_weather(
    context: RunContext, 
    city: str) -> str:
    """
    Get the current weather for a given city.
    """
    try:
        response = requests.get(f"https://wttr.in/{city}?format=3")
        if response.status_code == 200:
            logging.info(f"Weather for {city}: {response.text.strip()}")
            return response.text.strip()   
        else:
            logging.error(f"Failed to get weather for {city}: {response.status_code}")
            return f"Could not retrieve weather for {city}."
    except Exception as e:
        logging.error(f"Error retrieving weather for {city}: {e}")
        return f"An error occurred while retrieving weather for {city}." 

@function_tool()
async def search_web(
    context: RunContext, 
    query: str) -> str:
    """
    Search the web using Tavily for real-time information and news.
    """
    try:
        # Using advanced search depth for more comprehensive results
        search_result = await tavily_client.search(query, search_depth="advanced", max_results=5)
        
        results = search_result.get("results", [])
        if not results:
            return f"No relevant information found for '{query}'."

        formatted_results = "\n".join([f"- {r['content']} (Source: {r['url']})" for r in results])
        logging.info(f"Tavily search successful for '{query}'")
        return f"I found the following information:\n{formatted_results}"
    except Exception as e:
        logging.error(f"Tavily search error: {e}")
        return f"An error occurred while searching for '{query}'."    

@function_tool()    
async def send_email(
    context: RunContext, 
    to_email: str,
    subject: str,
    message: str,
    cc_email: Optional[str] = None
) -> str:
    """
    Send an email through Gmail.
    """
    try:
        smtp_server = "smtp.gmail.com"
        smtp_port = 587
        gmail_user = os.getenv("GMAIL_USER")
        gmail_password = os.getenv("GMAIL_APP_PASSWORD") 
        
        if not gmail_user or not gmail_password:
            logging.error("Gmail credentials not found")
            return "Email failed: Credentials not configured."
        
        msg = MIMEMultipart()
        msg['From'] = gmail_user
        msg['To'] = to_email
        msg['Subject'] = subject
        
        recipients = [to_email]
        if cc_email:
            msg['Cc'] = cc_email
            recipients.append(cc_email)
        
        msg.attach(MIMEText(message, 'plain'))
        
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(gmail_user, gmail_password)
        server.sendmail(gmail_user, recipients, msg.as_string())
        server.quit()
        
        logging.info(f"Email sent successfully to {to_email}")
        return f"Email sent successfully to {to_email}"
    except Exception as e:
        logging.error(f"Error sending email: {e}")
        return f"An error occurred while sending email: {str(e)}"
