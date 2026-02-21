import os
import asyncio
import logging
import base64
from datetime import datetime
from typing import List, Dict
import html

from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration from environment variables
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
GMAIL_TOKEN_PATH = 'token.json'  # Will be created during authentication
CHECK_INTERVAL = int(os.environ.get('CHECK_INTERVAL', 60))  # Seconds between checks

# Global variables
bot = None
gmail_service = None
processed_emails = set()  # Store processed email IDs
group_chats = []  # Will store group chat IDs where bot is admin

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type
    
    # Check if this is a group chat
    if chat_type in ['group', 'supergroup']:
        # Check if bot is admin
        bot_member = await context.bot.get_chat_member(chat_id, context.bot.id)
        if bot_member.status in ['administrator', 'creator']:
            if chat_id not in group_chats:
                group_chats.append(chat_id)
                logger.info(f"Added group {chat_id} to forwarding list")
                await update.message.reply_text(
                    "✅ This group has been registered to receive email notifications!\n\n"
                    "I'll forward new emails from the connected Gmail account here."
                )
            else:
                await update.message.reply_text("This group is already registered!")
        else:
            await update.message.reply_text(
                "❌ I need to be an admin in this group to forward emails.\n"
                "Please make me an admin first, then send /start again."
            )
    else:
        await update.message.reply_text(
            "👋 Hello! I'm a Gmail to Telegram forwarder bot.\n\n"
            "Add me to a group and make me admin, then send /start in the group to start receiving email notifications."
        )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check bot status"""
    status_msg = (
        f"🤖 **Bot Status**\n\n"
        f"📧 Gmail Connected: {'✅' if gmail_service else '❌'}\n"
        f"👥 Active Groups: {len(group_chats)}\n"
        f"⏱️ Check Interval: {CHECK_INTERVAL} seconds\n"
        f"📨 Processed Emails: {len(processed_emails)}"
    )
    await update.message.reply_text(status_msg, parse_mode='Markdown')

async def get_gmail_service():
    """Initialize Gmail API service"""
    global gmail_service
    
    try:
        if os.path.exists(GMAIL_TOKEN_PATH):
            creds = Credentials.from_authorized_user_file(
                GMAIL_TOKEN_PATH, 
                ['https://www.googleapis.com/auth/gmail.readonly']
            )
            
            # Refresh if expired
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                # Save refreshed credentials
                with open(GMAIL_TOKEN_PATH, 'w') as token:
                    token.write(creds.to_json())
            
            gmail_service = build('gmail', 'v1', credentials=creds)
            logger.info("Gmail service initialized successfully")
            return True
        else:
            logger.error("Gmail token.json not found! Run gmail_auth.py first.")
            return False
    except Exception as e:
        logger.error(f"Failed to initialize Gmail service: {e}")
        return False

async def check_new_emails():
    """Check for new emails and forward to groups"""
    global gmail_service, processed_emails
    
    if not gmail_service:
        logger.warning("Gmail service not available")
        return
    
    try:
        # Search for unread emails
        results = gmail_service.users().messages().list(
            userId='me',
            q='is:unread',
            maxResults=10
        ).execute()
        
        messages = results.get('messages', [])
        
        for message in messages:
            msg_id = message['id']
            
            # Skip if already processed
            if msg_id in processed_emails:
                continue
            
            # Get full message details
            msg = gmail_service.users().messages().get(
                userId='me', 
                id=msg_id,
                format='full'
            ).execute()
            
            # Extract email details
            headers = msg['payload']['headers']
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
            from_header = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown Sender')
            date = next((h['value'] for h in headers if h['name'] == 'Date'), 'Unknown Date')
            
            # Extract body
            body = extract_email_body(msg)
            
            # Format message for Telegram
            formatted_msg = format_email_message(subject, from_header, date, body)
            
            # Forward to all groups
            for chat_id in group_chats:
                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=formatted_msg,
                        parse_mode='HTML',
                        disable_web_page_preview=True
                    )
                    logger.info(f"Forwarded email {msg_id} to group {chat_id}")
                except Exception as e:
                    logger.error(f"Failed to send to group {chat_id}: {e}")
            
            # Mark as processed
            processed_emails.add(msg_id)
            
            # Optional: Mark email as read
            gmail_service.users().messages().modify(
                userId='me',
                id=msg_id,
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
            
    except Exception as e:
        logger.error(f"Error checking emails: {e}")

def extract_email_body(message):
    """Extract plain text body from email message"""
    try:
        if 'parts' in message['payload']:
            for part in message['payload']['parts']:
                if part['mimeType'] == 'text/plain':
                    data = part['body'].get('data', '')
                    if data:
                        return base64.urlsafe_b64decode(data).decode('utf-8')
        elif message['payload']['mimeType'] == 'text/plain':
            data = message['payload']['body'].get('data', '')
            if data:
                return base64.urlsafe_b64decode(data).decode('utf-8')
    except:
        pass
    return "No plain text content"

def format_email_message(subject, from_header, date, body):
    """Format email for Telegram"""
    # Truncate body if too long (Telegram limit: 4096 characters)
    if len(body) > 500:
        body = body[:500] + "...\n[Message truncated]"
    
    # Escape HTML characters
    subject = html.escape(subject)
    from_header = html.escape(from_header)
    body = html.escape(body)
    
    return (
        f"📧 <b>New Email</b>\n\n"
        f"<b>From:</b> {from_header}\n"
        f"<b>Subject:</b> {subject}\n"
        f"<b>Time:</b> {date}\n\n"
        f"<b>Preview:</b>\n{body}"
    )

async def email_monitor():
    """Background task to monitor emails"""
    while True:
        try:
            await check_new_emails()
        except Exception as e:
            logger.error(f"Monitor error: {e}")
        await asyncio.sleep(CHECK_INTERVAL)

async def post_init(application: Application):
    """Initialize services after bot starts"""
    global bot
    bot = application.bot
    
    # Initialize Gmail
    if await get_gmail_service():
        logger.info("Bot initialized successfully")
        
        # Start monitoring task
        asyncio.create_task(email_monitor())
    else:
        logger.error("Failed to initialize Gmail service")

def main():
    """Main function to run the bot"""
    # Create application
    application = Application.builder()\
        .token(TELEGRAM_BOT_TOKEN)\
        .post_init(post_init)\
        .build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status))
    
    # Start bot
    logger.info("Starting bot...")
    application.run_polling()

if __name__ == '__main__':
    main()
