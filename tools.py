@function_tool()
async def send_smart_email(
    context: RunContext,
    recipient: str,
    subject: str,
    body: str
) -> str:
    """
    Sends an email using the n8n MCP pipeline. 
    Use this for more reliable delivery and formatting.
    """
    try:
        # This sends the data directly to your n8n MCP Trigger
        url = os.getenv("N8N_MCP_SERVER_URL")
        payload = {
            "action": "send_gmail",
            "to": recipient,
            "subject": subject,
            "message": body
        }
        
        # Using a background thread to keep Jarvis responsive
        def _send_to_n8n():
            return requests.post(url, json=payload, timeout=10)

        response = await asyncio.to_thread(_send_to_n8n)
        
        if response.status_code == 200:
            return f"Email successfully routed through the nexus flow, sir."
        else:
            return "The n8n uplink rejected the transmission. Check the logs."
            
    except Exception as e:
        return f"Sir, I've encountered a glitch in the n8n relay: {str(e)}"
