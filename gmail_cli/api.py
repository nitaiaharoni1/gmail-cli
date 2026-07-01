"""Gmail API wrapper."""

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from .auth import get_credentials, check_auth
from .utils import format_email_address, format_date
from .retry import with_retry
import base64
import re
from html import unescape as _html_unescape
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import os
import tempfile
import mimetypes


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
    
    @with_retry()
    def get_profile(self):
        """Get user profile information."""
        try:
            profile = self.service.users().getProfile(userId=self.user_id).execute()
            return profile
        except HttpError as error:
            raise Exception(f"Failed to get profile: {error}")
    
    @with_retry()
    def get_language_setting(self):
        """Get user's language setting."""
        try:
            result = self.service.users().settings().getLanguage(userId=self.user_id).execute()
            return result.get('displayLanguage', 'en')
        except HttpError:
            return 'en'
    
    @with_retry()
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

    @with_retry()
    def list_messages_page(self, max_results=10, label_ids=None, query=None, page_token=None):
        """List messages with pagination cursor."""
        try:
            params = {"userId": self.user_id, "maxResults": max_results}
            if label_ids:
                params["labelIds"] = label_ids
            if query:
                params["q"] = query
            if page_token:
                params["pageToken"] = page_token
            results = self.service.users().messages().list(**params).execute()
            out = {"items": results.get("messages", [])}
            if results.get("nextPageToken"):
                out["nextPageToken"] = results["nextPageToken"]
            return out
        except HttpError as error:
            raise Exception(f"Failed to list messages: {error}")
    
    @with_retry()
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
    
    @with_retry()
    def get_messages_batch(self, message_ids, format="metadata"):
        """
        Fetch multiple messages in a single batch request.
        
        Args:
            message_ids: List of message IDs to fetch
            format: Format of the messages (full, metadata, minimal, raw)
        
        Returns:
            List of message dictionaries, preserving order
        """
        if not message_ids:
            return []
        
        try:
            batch = self.service.new_batch_http_request()
            results = {}
            errors = {}
            
            def callback(request_id, response, exception):
                if exception:
                    errors[request_id] = str(exception)
                else:
                    results[request_id] = response
            
            for msg_id in message_ids:
                batch.add(
                    self.service.users().messages().get(
                        userId=self.user_id, id=msg_id, format=format
                    ),
                    callback=callback,
                    request_id=msg_id
                )
            
            batch.execute()
            
            # Return results in original order
            ordered_results = []
            for msg_id in message_ids:
                if msg_id in results:
                    ordered_results.append(results[msg_id])
                elif msg_id in errors:
                    # Include error info in result
                    ordered_results.append({
                        "id": msg_id,
                        "error": errors[msg_id]
                    })
            
            return ordered_results
        except HttpError as error:
            raise Exception(f"Failed to batch get messages: {error}")
    
    @with_retry()
    def search_with_details(
        self, max_results=10, label_ids=None, query=None, format="metadata", page_token=None
    ):
        """
        Search messages and return full details in batch.

        Returns a page dict: {"items": [...], "nextPageToken": ... (optional)}.
        """
        try:
            page = self.list_messages_page(
                max_results=max_results, label_ids=label_ids, query=query, page_token=page_token
            )
            message_list = page.get("items", [])
            if not message_list:
                return {"items": []}
            message_ids = [msg["id"] for msg in message_list]
            items = self.get_messages_batch(message_ids, format=format)
            out = {"items": items}
            if page.get("nextPageToken"):
                out["nextPageToken"] = page["nextPageToken"]
            return out
        except HttpError as error:
            raise Exception(f"Failed to search with details: {error}")
    
    @with_retry()
    def send_message(self, to, subject, body, attachments=None, cc=None, html=False):
        """
        Send an email message.

        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body (plain text, or HTML when html=True)
            attachments: List of file paths to attach
            cc: CC recipient email address(es) (string or list)
            html: When True, send body as HTML (with a plain-text fallback)
        """
        try:
            if attachments:
                message = self._create_message_with_attachments(
                    to, subject, body, attachments, cc, html
                )
            else:
                message = self._create_message(to, subject, body, cc, html)
            
            sent_message = (
                self.service.users()
                .messages()
                .send(userId=self.user_id, body=message)
                .execute()
            )
            return sent_message
        except HttpError as error:
            raise Exception(f"Failed to send message: {error}")
    
    def _html_to_text(self, html_body):
        """Best-effort plain-text fallback derived from an HTML body."""
        text = re.sub(r"(?is)<(script|style).*?</\1>", "", html_body)
        text = re.sub(r"(?i)<br\s*/?>", "\n", text)
        text = re.sub(r"(?i)</(p|div|li|tr|h[1-6])\s*>", "\n", text)
        text = re.sub(r"<[^>]+>", "", text)
        text = _html_unescape(text)
        return re.sub(r"\n{3,}", "\n\n", text).strip()

    def _body_part(self, body, html=False):
        """Build the body MIME part.

        Plain text -> a single text/plain part. HTML -> a multipart/alternative
        carrying a derived text/plain fallback plus the text/html part, so
        clients that cannot render HTML still show readable text.
        """
        if not html:
            return MIMEText(body, "plain")
        alternative = MIMEMultipart("alternative")
        alternative.attach(MIMEText(self._html_to_text(body), "plain"))
        alternative.attach(MIMEText(body, "html"))
        return alternative

    def _create_message(self, to, subject, body, cc=None, html=False):
        """Create a message for sending."""
        message = self._body_part(body, html)
        message["to"] = to
        message["subject"] = subject
        if cc:
            message["cc"] = cc if isinstance(cc, str) else ", ".join(cc)
        return {"raw": base64.urlsafe_b64encode(message.as_bytes()).decode()}

    def _create_message_with_attachments(self, to, subject, body, attachments, cc=None, html=False):
        """Create a message with attachments."""
        message = MIMEMultipart()
        message["to"] = to
        message["subject"] = subject
        if cc:
            message["cc"] = cc if isinstance(cc, str) else ", ".join(cc)

        message.attach(self._body_part(body, html))
        self._attach_files(message, attachments)

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

    def list_threads_page(self, max_results=10, query=None, page_token=None):
        """List email threads with pagination cursor."""
        try:
            params = {"userId": self.user_id, "maxResults": max_results}
            if query:
                params["q"] = query
            if page_token:
                params["pageToken"] = page_token
            results = self.service.users().threads().list(**params).execute()
            out = {"items": results.get("threads", [])}
            if results.get("nextPageToken"):
                out["nextPageToken"] = results["nextPageToken"]
            return out
        except HttpError as error:
            raise Exception(f"Failed to list threads: {error}")

    def get_thread(self, thread_id, format="full"):
        """
        Get a whole thread (all its messages) by ID.

        Args:
            thread_id: The thread ID
            format: Format of the messages (full, metadata, minimal)
        """
        try:
            thread = (
                self.service.users()
                .threads()
                .get(userId=self.user_id, id=thread_id, format=format)
                .execute()
            )
            return thread
        except HttpError as error:
            raise Exception(f"Failed to get thread: {error}")
    
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
    
    def batch_modify_messages(self, message_ids, add_label_ids=None, remove_label_ids=None):
        """
        Batch modify multiple messages.
        
        Args:
            message_ids: List of message IDs to modify
            add_label_ids: List of label IDs to add
            remove_label_ids: List of label IDs to remove
        
        Returns:
            Dictionary with results
        """
        try:
            if not message_ids:
                return {"modified": 0, "errors": []}
            
            body = {"ids": message_ids}
            if add_label_ids:
                body["addLabelIds"] = add_label_ids
            if remove_label_ids:
                body["removeLabelIds"] = remove_label_ids
            
            result = (
                self.service.users()
                .messages()
                .batchModify(userId=self.user_id, body=body)
                .execute()
            )
            return {"modified": len(message_ids), "errors": []}
        except HttpError as error:
            raise Exception(f"Failed to batch modify messages: {error}")
    
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
    
    def create_draft(self, to, subject, body, attachments=None, cc=None, html=False):
        """
        Create a draft message.

        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body (plain text, or HTML when html=True)
            attachments: List of file paths to attach (optional)
            cc: CC recipient(s) (optional)
            html: When True, store body as HTML (with a plain-text fallback)
        """
        try:
            if attachments:
                message = self._create_message_with_attachments(to, subject, body, attachments, cc, html)
            else:
                message = self._create_message(to, subject, body, cc, html)

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

    def list_drafts_page(self, max_results=10, page_token=None):
        """List draft messages with pagination cursor."""
        try:
            params = {"userId": self.user_id, "maxResults": max_results}
            if page_token:
                params["pageToken"] = page_token
            results = self.service.users().drafts().list(**params).execute()
            out = {"items": results.get("drafts", [])}
            if results.get("nextPageToken"):
                out["nextPageToken"] = results["nextPageToken"]
            return out
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
    
    def send_draft(self, draft_id):
        """Send an existing draft as-is (threaded if it was a threaded draft)."""
        try:
            result = (
                self.service.users()
                .drafts()
                .send(userId=self.user_id, body={"id": draft_id})
                .execute()
            )
            return result
        except HttpError as error:
            raise Exception(f"Failed to send draft: {error}")

    def update_draft(self, draft_id, to=None, subject=None, body=None, attachments=None, cc=None, html=False):
        """
        Update a draft, preserving existing fields you don't override.

        Only the arguments you pass change. To/Subject/Body/Cc and existing
        attachments are read from the current draft and kept otherwise (so
        e.g. passing only `attachments` adds a file without wiping the rest).
        Pass attachments to replace the file set; omit it to keep existing ones.

        Args:
            draft_id: Draft ID to update
            to, subject, body, cc: override these (None = keep existing)
            attachments: list of file paths (None = keep existing attachments)
        """
        try:
            existing = self.get_draft(draft_id)
            emsg = existing.get("message", {})
            payload = emsg.get("payload", {})
            headers = payload.get("headers", [])

            def _h(name):
                return next((h["value"] for h in headers if h["name"].lower() == name.lower()), None)

            to = to if to is not None else (_h("To") or "")
            subject = subject if subject is not None else (_h("Subject") or "")
            cc = cc if cc is not None else _h("Cc")
            if body is None:
                body = self._extract_plain_body(payload)

            if attachments is not None:
                specs = list(attachments)  # file paths (replace set)
            else:
                specs = self._download_message_attachments(emsg.get("id"), payload)  # preserve

            if specs:
                msg = MIMEMultipart()
                msg.attach(self._body_part(body, html))
                for spec in specs:
                    if isinstance(spec, str):
                        self._attach_files(msg, [spec])
                    else:
                        self._attach_blob(msg, *spec)
            else:
                msg = self._body_part(body, html)
            msg["to"] = to
            msg["subject"] = subject
            if cc:
                msg["cc"] = cc if isinstance(cc, str) else ", ".join(cc)

            message = {"raw": base64.urlsafe_b64encode(msg.as_bytes()).decode()}
            draft = (
                self.service.users()
                .drafts()
                .update(userId=self.user_id, id=draft_id, body={"message": message})
                .execute()
            )
            return draft
        except HttpError as error:
            raise Exception(f"Failed to update draft: {error}")

    def _extract_plain_body(self, payload):
        """Return the text/plain body from a message payload (recursively)."""
        def walk(p):
            if p.get("mimeType") == "text/plain":
                data = p.get("body", {}).get("data")
                if data:
                    return base64.urlsafe_b64decode(data).decode("utf-8", "replace")
            for sub in p.get("parts", []) or []:
                t = walk(sub)
                if t:
                    return t
            return ""
        return walk(payload or {})

    def _download_message_attachments(self, message_id, payload):
        """Return a message's attachments as (filename, mimetype, bytes) tuples."""
        specs = []
        if not message_id:
            return specs

        def walk(p):
            filename = p.get("filename")
            body = p.get("body", {})
            if filename and body.get("attachmentId"):
                att = (
                    self.service.users().messages().attachments()
                    .get(userId=self.user_id, messageId=message_id, id=body["attachmentId"])
                    .execute()
                )
                data = base64.urlsafe_b64decode(att.get("data", ""))
                specs.append((filename, p.get("mimeType", "application/octet-stream"), data))
            for sub in p.get("parts", []) or []:
                walk(sub)

        walk(payload or {})
        return specs

    def _attach_blob(self, message, filename, mimetype, data):
        """Attach raw bytes as a file part (used to preserve existing attachments)."""
        maintype, _, subtype = (mimetype or "application/octet-stream").partition("/")
        if not subtype:
            maintype, subtype = "application", "octet-stream"
        part = MIMEBase(maintype, subtype)
        part.set_payload(data)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
        message.attach(part)

    def download_attachment(self, message_id, output_dir=None, attachment_id=None):
        """
        Save a message's attachment(s) to local disk and return their paths.

        Reuses _download_message_attachments to fetch the bytes, then writes each
        attachment to output_dir (defaults to the system temp dir; created if
        needed) using the attachment's own filename. If attachment_id is given,
        only that attachment is saved.

        Args:
            message_id: The message ID to pull attachments from
            output_dir: Directory to write files to (default: system temp dir)
            attachment_id: Optional attachment ID to restrict to a single file

        Returns:
            List of dicts: {"filename", "path", "mime_type", "size"}
        """
        try:
            message = self.get_message(message_id, format="full")
            payload = message.get("payload", {})

            if attachment_id:
                specs = self._download_attachments_by_id(message_id, payload, attachment_id)
            else:
                specs = self._download_message_attachments(message_id, payload)

            out_dir = output_dir or tempfile.gettempdir()
            os.makedirs(out_dir, exist_ok=True)

            saved = []
            for filename, mimetype, data in specs:
                filename = os.path.basename(filename)  # never write outside out_dir
                path = os.path.join(out_dir, filename)
                with open(path, "wb") as f:
                    f.write(data)
                saved.append({
                    "filename": filename,
                    "path": path,
                    "mime_type": mimetype,
                    "size": len(data),
                })
            return saved
        except HttpError as error:
            raise Exception(f"Failed to download attachment: {error}")

    def _download_attachments_by_id(self, message_id, payload, attachment_id):
        """Return only the attachment matching attachment_id as (filename, mimetype, bytes)."""
        specs = []
        if not message_id:
            return specs

        def walk(p):
            filename = p.get("filename")
            body = p.get("body", {})
            if filename and body.get("attachmentId") == attachment_id:
                att = (
                    self.service.users().messages().attachments()
                    .get(userId=self.user_id, messageId=message_id, id=attachment_id)
                    .execute()
                )
                data = base64.urlsafe_b64decode(att.get("data", ""))
                specs.append((filename, p.get("mimeType", "application/octet-stream"), data))
            for sub in p.get("parts", []) or []:
                walk(sub)

        walk(payload or {})
        return specs

    def delete_draft(self, draft_id):
        """Delete a draft."""
        try:
            (
                self.service.users()
                .drafts()
                .delete(userId=self.user_id, id=draft_id)
                .execute()
            )
            return {"id": draft_id, "deleted": True}
        except HttpError as error:
            raise Exception(f"Failed to delete draft: {error}")
    
    def _attach_files(self, message, attachments):
        """Attach a list of local file paths to a MIME multipart message.

        Guesses each file's MIME type (per the Gmail API docs) so e.g. a PDF is
        attached as application/pdf rather than a generic binary blob.
        """
        for filepath in attachments or []:
            if not os.path.exists(filepath):
                raise Exception(f"Attachment file not found: {filepath}")
            ctype, encoding = mimetypes.guess_type(filepath)
            if ctype is None or encoding is not None:
                ctype = "application/octet-stream"
            maintype, subtype = ctype.split("/", 1)
            with open(filepath, "rb") as f:
                part = MIMEBase(maintype, subtype)
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f'attachment; filename="{os.path.basename(filepath)}"',
            )
            message.attach(part)

    def reply_to_message(self, message_id, body, reply_all=False, additional_cc=None, attachments=None):
        """
        Reply to a message.

        Args:
            message_id: The message ID to reply to
            body: Reply body text
            reply_all: If True, reply to all recipients
            additional_cc: Additional CC recipient(s) to add
            attachments: Optional list of local file paths to attach
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

            # Create reply message (multipart only when there are attachments)
            if attachments:
                reply = MIMEMultipart()
                reply.attach(MIMEText(body, "plain"))
                self._attach_files(reply, attachments)
            else:
                reply = MIMEText(body)
            reply["to"] = from_email
            reply["subject"] = reply_subject

            # Handle CC recipients
            cc_list = []
            if reply_all and cc_email:
                cc_list.append(cc_email)
            if additional_cc:
                cc_list.append(additional_cc)
            
            if cc_list:
                reply["cc"] = ", ".join(cc_list)
            
            # Set In-Reply-To and References headers for threading
            message_id_header = next((h["value"] for h in headers if h["name"] == "Message-ID"), "")
            if message_id_header:
                reply["In-Reply-To"] = message_id_header
                reply["References"] = message_id_header
            
            # Get the thread ID from the original message
            thread_id = original.get("threadId")
            
            message = {
                "raw": base64.urlsafe_b64encode(reply.as_bytes()).decode(),
                "threadId": thread_id  # Add threadId to keep reply in same thread
            }
            
            sent_message = (
                self.service.users()
                .messages()
                .send(userId=self.user_id, body=message)
                .execute()
            )
            return sent_message
        except HttpError as error:
            raise Exception(f"Failed to reply to message: {error}")

    def draft_reply(self, message_id, body, reply_all=False, additional_cc=None, attachments=None):
        """
        Create a DRAFT reply that stays in the original thread.

        Identical threading to reply_to_message (In-Reply-To/References headers
        + threadId) but saves a draft instead of sending, so it can be reviewed
        in Gmail and sent later while still threading correctly.

        Args:
            message_id: The message ID to reply to
            body: Reply body text
            reply_all: If True, CC the original recipients
            additional_cc: Additional CC recipient(s) to add
            attachments: Optional list of local file paths to attach
        """
        try:
            # Get the original message
            original = self.get_message(message_id, format="full")
            headers = original.get("payload", {}).get("headers", [])

            # Extract original message details
            from_email = next((h["value"] for h in headers if h["name"] == "From"), "")
            subject = next((h["value"] for h in headers if h["name"] == "Subject"), "")
            cc_email = next((h["value"] for h in headers if h["name"] == "Cc"), "")

            # Build reply subject
            reply_subject = subject
            if not reply_subject.startswith("Re: "):
                reply_subject = f"Re: {reply_subject}"

            # Create reply message (multipart only when there are attachments)
            if attachments:
                reply = MIMEMultipart()
                reply.attach(MIMEText(body, "plain"))
                self._attach_files(reply, attachments)
            else:
                reply = MIMEText(body)
            reply["to"] = from_email
            reply["subject"] = reply_subject

            # Handle CC recipients
            cc_list = []
            if reply_all and cc_email:
                cc_list.append(cc_email)
            if additional_cc:
                cc_list.append(additional_cc)
            if cc_list:
                reply["cc"] = ", ".join(cc_list)

            # Set In-Reply-To and References headers for threading
            message_id_header = next((h["value"] for h in headers if h["name"] == "Message-ID"), "")
            if message_id_header:
                reply["In-Reply-To"] = message_id_header
                reply["References"] = message_id_header

            # Get the thread ID from the original message
            thread_id = original.get("threadId")

            message = {
                "raw": base64.urlsafe_b64encode(reply.as_bytes()).decode(),
                "threadId": thread_id,  # keep the draft in the same thread
            }

            draft = (
                self.service.users()
                .drafts()
                .create(userId=self.user_id, body={"message": message})
                .execute()
            )
            return draft
        except HttpError as error:
            raise Exception(f"Failed to create draft reply: {error}")

    def forward_message(self, message_id, to, body=None, attachments=None):
        """
        Forward a message.

        Args:
            message_id: The message ID to forward
            to: Recipient email address
            body: Optional forward message body
            attachments: Optional list of local file paths to attach
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
            
            # Create forward message (multipart only when there are attachments)
            if attachments:
                forward = MIMEMultipart()
                forward.attach(MIMEText(forward_body, "plain"))
                self._attach_files(forward, attachments)
            else:
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
    
    @with_retry()
    def delete_message(self, message_id):
        """
        Permanently delete a message. This cannot be undone!
        
        Args:
            message_id: The message ID to delete
        """
        try:
            (
                self.service.users()
                .messages()
                .delete(userId=self.user_id, id=message_id)
                .execute()
            )
        except HttpError as error:
            raise Exception(f"Failed to delete message: {error}")
    
    @with_retry()
    def trash_message(self, message_id):
        """
        Move a message to trash (can be recovered).
        
        Args:
            message_id: The message ID to trash
        """
        try:
            (
                self.service.users()
                .messages()
                .trash(userId=self.user_id, id=message_id)
                .execute()
            )
        except HttpError as error:
            raise Exception(f"Failed to trash message: {error}")
    
    def untrash_message(self, message_id):
        """
        Remove a message from trash (restore to inbox).
        
        Args:
            message_id: The message ID to untrash
        """
        try:
            (
                self.service.users()
                .messages()
                .untrash(userId=self.user_id, id=message_id)
                .execute()
            )
        except HttpError as error:
            raise Exception(f"Failed to untrash message: {error}")
    
    def batch_trash_messages(self, message_ids):
        """Batch trash multiple messages (using batchModify with TRASH label)."""
        try:
            if not message_ids:
                return {"trashed": 0, "errors": []}
            
            # Use batchModify to add TRASH label and remove INBOX
            result = self.batch_modify_messages(
                message_ids,
                add_label_ids=["TRASH"],
                remove_label_ids=["INBOX"]
            )
            return {"trashed": result["modified"], "errors": result.get("errors", [])}
        except HttpError as error:
            raise Exception(f"Failed to batch trash messages: {error}")
    
    def batch_untrash_messages(self, message_ids):
        """Batch untrash multiple messages (using batchModify to remove TRASH label)."""
        try:
            if not message_ids:
                return {"untrashed": 0, "errors": []}
            
            # Use batchModify to remove TRASH label and add INBOX back
            result = self.batch_modify_messages(
                message_ids,
                add_label_ids=["INBOX"],
                remove_label_ids=["TRASH"]
            )
            return {"untrashed": result["modified"], "errors": result.get("errors", [])}
        except HttpError as error:
            raise Exception(f"Failed to batch untrash messages: {error}")
    
    def batch_delete_messages(self, message_ids):
        """Batch permanently delete multiple messages."""
        try:
            if not message_ids:
                return {"deleted": 0, "errors": []}
            
            body = {"ids": message_ids}
            (
                self.service.users()
                .messages()
                .batchDelete(userId=self.user_id, body=body)
                .execute()
            )
            return {"deleted": len(message_ids), "errors": []}
        except HttpError as error:
            raise Exception(f"Failed to batch delete messages: {error}")

