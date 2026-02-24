import logging
import os
import requests
import smtplib
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
        # Added include_answer=True for high-accuracy summaries
        response = tavily.search(
            query=query, 
            search_depth="advanced", 
            max_results=3, 
            include_answer=True
        )
        
        # Priority 1: Use the AI-generated direct answer for accuracy
        if response.get("answer"):
            return f"DIRECT SEARCH ANSWER: {response['answer']}"
        
        # Priority 2: Fallback to ranked results
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
    """Get the current weather for a specific city. Use this when the user asks 'how is the weather'."""
    try:
        # Using a more reliable weather format
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
    try:
        gmail_user = os.getenv("GMAIL_USER")
        gmail_password = os.getenv("GMAIL_APP_PASSWORD")
        
        if not gmail_user or not gmail_password:
            return "Email error: Credentials not configured in environment variables."

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
    except Exception as e:
        logging.error(f"Email failed: {e}")
        return f"Failed to send email: {str(e)}"
