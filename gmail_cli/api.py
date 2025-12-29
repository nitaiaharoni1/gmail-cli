"""Gmail API wrapper."""

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from .auth import get_credentials, check_auth
from .utils import format_email_address, format_date
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import os


class GmailAPI:
    """Wrapper for Gmail API operations."""
    
    def __init__(self, account=None):
        """
        Initialize Gmail API service.
        
        Args:
            account: Account name (optional). If None, uses default account.
        """
        creds = check_auth(account)
        if not creds:
            raise Exception("Not authenticated. Run 'gmail init' first.")
        
        self.service = build("gmail", "v1", credentials=creds)
        self.user_id = "me"
        self.account = account
    
    def get_profile(self):
        """Get user profile information."""
        try:
            profile = self.service.users().getProfile(userId=self.user_id).execute()
            return profile
        except HttpError as error:
            raise Exception(f"Failed to get profile: {error}")
    
    def list_messages(self, max_results=10, label_ids=None, query=None):
        """
        List messages from the user's mailbox.
        
        Args:
            max_results: Maximum number of messages to return
            label_ids: List of label IDs to filter by
            query: Query string to search for
        """
        try:
            params = {"userId": self.user_id, "maxResults": max_results}
            
            if label_ids:
                params["labelIds"] = label_ids
            
            if query:
                params["q"] = query
            
            results = self.service.users().messages().list(**params).execute()
            messages = results.get("messages", [])
            return messages
        except HttpError as error:
            raise Exception(f"Failed to list messages: {error}")
    
    def get_message(self, message_id, format="full"):
        """
        Get a specific message by ID.
        
        Args:
            message_id: The message ID
            format: Format of the message (full, metadata, minimal, raw)
        """
        try:
            message = (
                self.service.users()
                .messages()
                .get(userId=self.user_id, id=message_id, format=format)
                .execute()
            )
            return message
        except HttpError as error:
            raise Exception(f"Failed to get message: {error}")
    
    def send_message(self, to, subject, body, attachments=None):
        """
        Send an email message.
        
        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body (plain text)
            attachments: List of file paths to attach
        """
        try:
            if attachments:
                message = self._create_message_with_attachments(
                    to, subject, body, attachments
                )
            else:
                message = self._create_message(to, subject, body)
            
            sent_message = (
                self.service.users()
                .messages()
                .send(userId=self.user_id, body=message)
                .execute()
            )
            return sent_message
        except HttpError as error:
            raise Exception(f"Failed to send message: {error}")
    
    def _create_message(self, to, subject, body):
        """Create a message for sending."""
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        return {"raw": base64.urlsafe_b64encode(message.as_bytes()).decode()}
    
    def _create_message_with_attachments(self, to, subject, body, attachments):
        """Create a message with attachments."""
        message = MIMEMultipart()
        message["to"] = to
        message["subject"] = subject
        
        message.attach(MIMEText(body, "plain"))
        
        for filepath in attachments:
            if not os.path.exists(filepath):
                raise Exception(f"Attachment file not found: {filepath}")
            
            with open(filepath, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f'attachment; filename= "{os.path.basename(filepath)}"',
            )
            message.attach(part)
        
        return {"raw": base64.urlsafe_b64encode(message.as_bytes()).decode()}
    
    def list_labels(self):
        """List all labels in the user's mailbox."""
        try:
            results = (
                self.service.users().labels().list(userId=self.user_id).execute()
            )
            labels = results.get("labels", [])
            return labels
        except HttpError as error:
            raise Exception(f"Failed to list labels: {error}")
    
    def list_threads(self, max_results=10, query=None):
        """
        List email threads.
        
        Args:
            max_results: Maximum number of threads to return
            query: Query string to search for
        """
        try:
            params = {"userId": self.user_id, "maxResults": max_results}
            
            if query:
                params["q"] = query
            
            results = self.service.users().threads().list(**params).execute()
            threads = results.get("threads", [])
            return threads
        except HttpError as error:
            raise Exception(f"Failed to list threads: {error}")
    
    def modify_message(self, message_id, add_label_ids=None, remove_label_ids=None):
        """
        Modify message labels.
        
        Args:
            message_id: The message ID
            add_label_ids: List of label IDs to add
            remove_label_ids: List of label IDs to remove
        """
        try:
            body = {}
            if add_label_ids:
                body["addLabelIds"] = add_label_ids
            if remove_label_ids:
                body["removeLabelIds"] = remove_label_ids
            
            message = (
                self.service.users()
                .messages()
                .modify(userId=self.user_id, id=message_id, body=body)
                .execute()
            )
            return message
        except HttpError as error:
            raise Exception(f"Failed to modify message: {error}")
    
    def mark_as_read(self, message_id):
        """Mark a message as read."""
        return self.modify_message(message_id, remove_label_ids=["UNREAD"])
    
    def archive_message(self, message_id):
        """Archive a message (remove INBOX label)."""
        return self.modify_message(message_id, remove_label_ids=["INBOX"])
    
    def create_filter(self, criteria, action):
        """
        Create a Gmail filter.
        
        Args:
            criteria: Dictionary with filter criteria (from, to, subject, query, etc.)
            action: Dictionary with filter actions (addLabelIds, removeLabelIds, forward)
        
        Returns:
            Created filter object with ID
        """
        try:
            filter_body = {
                "criteria": criteria,
                "action": action
            }
            
            result = (
                self.service.users()
                .settings()
                .filters()
                .create(userId=self.user_id, body=filter_body)
                .execute()
            )
            return result
        except HttpError as error:
            raise Exception(f"Failed to create filter: {error}")
    
    def list_filters(self):
        """List all Gmail filters."""
        try:
            results = (
                self.service.users()
                .settings()
                .filters()
                .list(userId=self.user_id)
                .execute()
            )
            filters = results.get("filter", [])
            return filters
        except HttpError as error:
            raise Exception(f"Failed to list filters: {error}")
    
    def get_filter(self, filter_id):
        """
        Get a specific filter by ID.
        
        Args:
            filter_id: The filter ID
        
        Returns:
            Filter object
        """
        try:
            result = (
                self.service.users()
                .settings()
                .filters()
                .get(userId=self.user_id, id=filter_id)
                .execute()
            )
            return result
        except HttpError as error:
            raise Exception(f"Failed to get filter: {error}")
    
    def delete_filter(self, filter_id):
        """
        Delete a Gmail filter.
        
        Args:
            filter_id: The filter ID to delete
        """
        try:
            (
                self.service.users()
                .settings()
                .filters()
                .delete(userId=self.user_id, id=filter_id)
                .execute()
            )
        except HttpError as error:
            raise Exception(f"Failed to delete filter: {error}")

