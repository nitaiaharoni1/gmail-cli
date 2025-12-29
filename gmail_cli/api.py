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
    
    def mark_as_spam(self, message_id):
        """Mark a message as spam."""
        return self.modify_message(message_id, add_label_ids=["SPAM"], remove_label_ids=["INBOX"])
    
    def unmark_spam(self, message_id):
        """Remove spam label from a message."""
        return self.modify_message(message_id, remove_label_ids=["SPAM"], add_label_ids=["INBOX"])
    
    def star_message(self, message_id):
        """Star a message."""
        return self.modify_message(message_id, add_label_ids=["STARRED"])
    
    def unstar_message(self, message_id):
        """Unstar a message."""
        return self.modify_message(message_id, remove_label_ids=["STARRED"])
    
    def create_label(self, name, message_list_visibility="show", label_list_visibility="labelShow", color=None):
        """
        Create a new label.
        
        Args:
            name: Label name
            message_list_visibility: "show" or "hide"
            label_list_visibility: "labelShow" or "labelHide"
            color: Dict with backgroundColor and textColor (optional)
        """
        try:
            label_body = {
                "name": name,
                "messageListVisibility": message_list_visibility,
                "labelListVisibility": label_list_visibility
            }
            if color:
                label_body["color"] = color
            
            result = (
                self.service.users()
                .labels()
                .create(userId=self.user_id, body={"label": label_body})
                .execute()
            )
            return result
        except HttpError as error:
            raise Exception(f"Failed to create label: {error}")
    
    def delete_label(self, label_id):
        """Delete a label."""
        try:
            (
                self.service.users()
                .labels()
                .delete(userId=self.user_id, id=label_id)
                .execute()
            )
        except HttpError as error:
            raise Exception(f"Failed to delete label: {error}")
    
    def update_label(self, label_id, name=None, message_list_visibility=None, label_list_visibility=None, color=None):
        """
        Update a label.
        
        Args:
            label_id: Label ID to update
            name: New name (optional)
            message_list_visibility: New visibility (optional)
            label_list_visibility: New list visibility (optional)
            color: New color dict (optional)
        """
        try:
            label_body = {}
            if name is not None:
                label_body["name"] = name
            if message_list_visibility is not None:
                label_body["messageListVisibility"] = message_list_visibility
            if label_list_visibility is not None:
                label_body["labelListVisibility"] = label_list_visibility
            if color is not None:
                label_body["color"] = color
            
            result = (
                self.service.users()
                .labels()
                .patch(userId=self.user_id, id=label_id, body={"label": label_body})
                .execute()
            )
            return result
        except HttpError as error:
            raise Exception(f"Failed to update label: {error}")
    
    def get_label(self, label_id):
        """Get a specific label by ID."""
        try:
            result = (
                self.service.users()
                .labels()
                .get(userId=self.user_id, id=label_id)
                .execute()
            )
            return result
        except HttpError as error:
            raise Exception(f"Failed to get label: {error}")
    
    def create_draft(self, to, subject, body, attachments=None):
        """
        Create a draft message.
        
        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body (plain text)
            attachments: List of file paths to attach (optional)
        """
        try:
            if attachments:
                message = self._create_message_with_attachments(to, subject, body, attachments)
            else:
                message = self._create_message(to, subject, body)
            
            draft = (
                self.service.users()
                .drafts()
                .create(userId=self.user_id, body={"message": message})
                .execute()
            )
            return draft
        except HttpError as error:
            raise Exception(f"Failed to create draft: {error}")
    
    def list_drafts(self, max_results=10):
        """List draft messages."""
        try:
            results = (
                self.service.users()
                .drafts()
                .list(userId=self.user_id, maxResults=max_results)
                .execute()
            )
            drafts = results.get("drafts", [])
            return drafts
        except HttpError as error:
            raise Exception(f"Failed to list drafts: {error}")
    
    def get_draft(self, draft_id):
        """Get a specific draft by ID."""
        try:
            result = (
                self.service.users()
                .drafts()
                .get(userId=self.user_id, id=draft_id)
                .execute()
            )
            return result
        except HttpError as error:
            raise Exception(f"Failed to get draft: {error}")
    
    def update_draft(self, draft_id, to, subject, body, attachments=None):
        """
        Update a draft message.
        
        Args:
            draft_id: Draft ID to update
            to: Recipient email address
            subject: Email subject
            body: Email body (plain text)
            attachments: List of file paths to attach (optional)
        """
        try:
            if attachments:
                message = self._create_message_with_attachments(to, subject, body, attachments)
            else:
                message = self._create_message(to, subject, body)
            
            draft = (
                self.service.users()
                .drafts()
                .update(userId=self.user_id, id=draft_id, body={"message": message})
                .execute()
            )
            return draft
        except HttpError as error:
            raise Exception(f"Failed to update draft: {error}")
    
    def delete_draft(self, draft_id):
        """Delete a draft."""
        try:
            (
                self.service.users()
                .drafts()
                .delete(userId=self.user_id, id=draft_id)
                .execute()
            )
        except HttpError as error:
            raise Exception(f"Failed to delete draft: {error}")
    
    def reply_to_message(self, message_id, body, reply_all=False):
        """
        Reply to a message.
        
        Args:
            message_id: The message ID to reply to
            body: Reply body text
            reply_all: If True, reply to all recipients
        """
        try:
            # Get the original message
            original = self.get_message(message_id, format="full")
            headers = original.get("payload", {}).get("headers", [])
            
            # Extract original message details
            from_email = next((h["value"] for h in headers if h["name"] == "From"), "")
            subject = next((h["value"] for h in headers if h["name"] == "Subject"), "")
            to_email = next((h["value"] for h in headers if h["name"] == "To"), "")
            cc_email = next((h["value"] for h in headers if h["name"] == "Cc"), "")
            
            # Build reply subject
            reply_subject = subject
            if not reply_subject.startswith("Re: "):
                reply_subject = f"Re: {reply_subject}"
            
            # Create reply message
            reply = MIMEText(body)
            reply["to"] = from_email
            reply["subject"] = reply_subject
            
            if reply_all and cc_email:
                reply["cc"] = cc_email
            
            # Set In-Reply-To and References headers for threading
            message_id_header = next((h["value"] for h in headers if h["name"] == "Message-ID"), "")
            if message_id_header:
                reply["In-Reply-To"] = message_id_header
                reply["References"] = message_id_header
            
            message = {"raw": base64.urlsafe_b64encode(reply.as_bytes()).decode()}
            
            sent_message = (
                self.service.users()
                .messages()
                .send(userId=self.user_id, body=message)
                .execute()
            )
            return sent_message
        except HttpError as error:
            raise Exception(f"Failed to reply to message: {error}")
    
    def forward_message(self, message_id, to, body=None):
        """
        Forward a message.
        
        Args:
            message_id: The message ID to forward
            to: Recipient email address
            body: Optional forward message body
        """
        try:
            # Get the original message
            original = self.get_message(message_id, format="full")
            headers = original.get("payload", {}).get("headers", [])
            
            # Extract original message details
            subject = next((h["value"] for h in headers if h["name"] == "Subject"), "")
            from_email = next((h["value"] for h in headers if h["name"] == "From"), "")
            date = next((h["value"] for h in headers if h["name"] == "Date"), "")
            
            # Build forward subject
            forward_subject = subject
            if not forward_subject.startswith("Fwd: "):
                forward_subject = f"Fwd: {forward_subject}"
            
            # Build forward body
            forward_body = body or ""
            forward_body += f"\n\n---------- Forwarded message ----------\n"
            forward_body += f"From: {from_email}\n"
            forward_body += f"Date: {date}\n"
            forward_body += f"Subject: {subject}\n"
            forward_body += f"To: {to}\n\n"
            
            # Extract original body
            payload = original.get("payload", {})
            original_body = ""
            if "parts" in payload:
                for part in payload["parts"]:
                    if part.get("mimeType") == "text/plain":
                        data = part.get("body", {}).get("data")
                        if data:
                            original_body = base64.urlsafe_b64decode(data).decode("utf-8")
                            break
            else:
                if payload.get("mimeType") == "text/plain":
                    data = payload.get("body", {}).get("data")
                    if data:
                        original_body = base64.urlsafe_b64decode(data).decode("utf-8")
            
            forward_body += original_body
            
            # Create forward message
            forward = MIMEText(forward_body)
            forward["to"] = to
            forward["subject"] = forward_subject
            
            message = {"raw": base64.urlsafe_b64encode(forward.as_bytes()).decode()}
            
            sent_message = (
                self.service.users()
                .messages()
                .send(userId=self.user_id, body=message)
                .execute()
            )
            return sent_message
        except HttpError as error:
            raise Exception(f"Failed to forward message: {error}")
    
    def block_sender(self, email):
        """
        Block a sender by creating a filter that marks their emails as spam.
        
        Args:
            email: Email address to block
        """
        try:
            criteria = {"from": email}
            action = {"addLabelIds": ["SPAM"], "removeLabelIds": ["INBOX"]}
            return self.create_filter(criteria, action)
        except HttpError as error:
            raise Exception(f"Failed to block sender: {error}")

