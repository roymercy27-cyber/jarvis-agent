import logging
from livekit.agents import function_tool, RunContext
import requests
from langchain_community.tools import DuckDuckGoSearchRun
import os
import smtplib
import webbrowser
from datetime import datetime
from email.mime.multipart import MIMEMultipart  
from email.mime.text import MIMEText
from typing import Optional

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
    Search the web using DuckDuckGo.
    """
    try:
        results = DuckDuckGoSearchRun().run(tool_input=query)
        logging.info(f"Search results for '{query}': {results}")
        return results
    except Exception as e:
        logging.error(f"Error searching the web for '{query}': {e}")
        return f"An error occurred while searching the web for '{query}'."     

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
            logging.error("Gmail credentials not found in environment variables")
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

@function_tool()
async def get_system_report(context: RunContext) -> str: # type: ignore
    """
    Provides a situational report including current time, date, and simulated system vitals.
    """
    now = datetime.now()
    report = (
        f"Current time is {now.strftime('%H:%M:%S')}, date: {now.strftime('%Y-%m-%d')}. "
        "Arc Reactor stability is at 98%. Core temperature is 32 degrees Celsius. "
        "All systems are nominal, sir."
    )
    logging.info("System report generated.")
    return report

@function_tool()
async def open_browser(
    context: RunContext, # type: ignore
    url: str) -> str:
    """
    Opens a specific URL or website in the default web browser.
    """
    try:
        # Ensure URL has a protocol
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
            
        webbrowser.open(url)
        logging.info(f"Opening browser to: {url}")
        return f"Protocol initiated. Opening {url} now."
    except Exception as e:
        logging.error(f"Failed to open browser: {e}")
        return "I was unable to access the browser interface."

@function_tool()
async def calculate_math(
    context: RunContext, # type: ignore
    expression: str) -> str:
    """
    Evaluates mathematical expressions for complex calculations.
    """
    try:
        # Using a safer eval approach or simple arithmetic
        result = eval(expression, {"__builtins__": None}, {})
        return f"The calculation is complete, sir. The result is {result}."
    except Exception:
        return "I encountered an error while processing that calculation."
