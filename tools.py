import logging
from livekit.agents import function_tool, RunContext
import requests
# CHANGED: Using Tavily instead of DuckDuckGo
from tavily import AsyncTavilyClient
import os
import smtplib
from email.mime.multipart import MIMEMultipart  
from email.mime.text import MIMEText
from typing import Optional

# Initialize Tavily Client (ensure TAVILY_API_KEY is in your .env)
tavily_client = AsyncTavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

@function_tool()
async def get_weather(
    context: RunContext,  # type: ignore
    city: str) -> str:
    """
    Get the current weather for a given city.
    """
    try:
        response = requests.get(
            f"https://wttr.in/{city}?format=3")
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
    context: RunContext,  # type: ignore
    query: str) -> str:
    """
    Search the web for real-time information, including stock prices, news, and time.
    """
    try:
        # Optimization: Use 'advanced' depth for financial/time-sensitive queries
        is_finance = any(word in query.lower() for word in ["stock", "price", "tesla", "market", "tsla"])
        search_depth = "advanced" if is_finance else "basic"
        
        response = await tavily_client.search(
            query, 
            search_depth=search_depth, 
            max_results=5,
            topic="finance" if is_finance else "general"
        )
        
        results = response.get("results", [])
        if not results:
            return f"I'm sorry, sir, but I couldn't find any live information regarding '{query}'."

        # Format results for the LLM to process
        formatted_results = "\n".join([f"- {r['content']} (Source: {r['url']})" for r in results])
        logging.info(f"Tavily {search_depth} search successful for: {query}")
        
        return f"Sir, I have found the following up-to-date information:\n{formatted_results}"
    except Exception as e:
        logging.error(f"Error searching Tavily for '{query}': {e}")
        return f"I apologize, sir, but an error occurred while searching the web: {str(e)}"

@function_tool()     
async def send_email(
    context: RunContext,  # type: ignore
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
            return "Email sending failed: Gmail credentials not configured."
        
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
        
        text = msg.as_string()
        server.sendmail(gmail_user, recipients, text)
        server.quit()
        
        logging.info(f"Email sent successfully to {to_email}")
        return f"Email sent successfully to {to_email}"
    except Exception as e:
        logging.error(f"Error sending email: {e}")
        return f"An error occurred while sending email: {str(e)}"
