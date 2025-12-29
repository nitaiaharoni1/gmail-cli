"""Gmail CLI - Main command-line interface."""

import click
import json
import sys
from .auth import authenticate, get_credentials, check_auth
from .api import GmailAPI
from .utils import format_email_address, format_date, list_accounts, get_default_account, set_default_account, get_token_path


@click.group()
@click.version_option(version="1.0.1")
@click.option("--account", "-a", help="Account name to use (default: current default account)")
@click.pass_context
def cli(ctx, account):
    """Gmail CLI - Command-line interface for Gmail."""
    ctx.ensure_object(dict)
    ctx.obj["ACCOUNT"] = account


# Account option decorator
_account_option = click.option("--account", "-a", help="Account name to use (default: current default account)")


@cli.command(name="help")
@click.argument("command", required=False)
@click.pass_context
def help_command(ctx, command):
    """Show help message. Use 'help <command>' for command-specific help."""
    if command:
        # Show help for a specific command
        try:
            cmd = ctx.parent.command.get_command(ctx.parent, command)
            if cmd:
                click.echo(cmd.get_help(ctx))
            else:
                click.echo(f"❌ Unknown command: {command}", err=True)
                click.echo(f"\nAvailable commands:")
                for name in sorted(ctx.parent.command.list_commands(ctx.parent)):
                    click.echo(f"  {name}")
        except Exception:
            click.echo(f"❌ Unknown command: {command}", err=True)
            click.echo(f"\nAvailable commands:")
            for name in sorted(ctx.parent.command.list_commands(ctx.parent)):
                click.echo(f"  {name}")
    else:
        # Show main help
        if ctx.parent:
            click.echo(ctx.parent.get_help())
        else:
            click.echo(ctx.get_help())


@cli.command()
@click.option("--account", "-a", help="Account name (optional, will use email if not provided)")
def init(account):
    """Initialize and authenticate with Gmail API."""
    click.echo("🔐 Setting up Gmail authentication...")
    creds = authenticate(account)
    
    if creds:
        try:
            # Get the actual account name that was used
            api = GmailAPI(account)
            profile = api.get_profile()
            email = profile.get('emailAddress', 'Unknown')
            click.echo(f"✅ Authenticated as: {email}")
            
            # Show account name if different from email
            from .utils import get_default_account
            default_account = get_default_account()
            if default_account and default_account != email:
                click.echo(f"   Account name: {default_account}")
        except Exception as e:
            click.echo(f"⚠️  Authentication saved but verification failed: {e}")
    else:
        sys.exit(1)


@cli.command()
def accounts():
    """List all configured accounts."""
    accounts_list = list_accounts()
    default = get_default_account()
    
    if not accounts_list:
        click.echo("No accounts configured. Run 'gmail init' to add an account.")
        return
    
    click.echo(f"Configured accounts ({len(accounts_list)}):\n")
    for acc in accounts_list:
        marker = " (default)" if acc == default else ""
        click.echo(f"  • {acc}{marker}")
    
    if default:
        click.echo(f"\nDefault account: {default}")


@cli.command()
@click.argument("account_name")
def use(account_name):
    """Set default account to use."""
    accounts_list = list_accounts()
    
    if account_name not in accounts_list:
        click.echo(f"❌ Error: Account '{account_name}' not found.")
        click.echo(f"Available accounts: {', '.join(accounts_list)}")
        click.echo("\nRun 'gmail init --account <name>' to add a new account.")
        sys.exit(1)
    
    set_default_account(account_name)
    click.echo(f"✅ Default account set to: {account_name}")


@cli.command()
@_account_option
@click.pass_context
def me(ctx, account):
    """Show authenticated user information."""
    account = account or ctx.obj.get("ACCOUNT")
    try:
        api = GmailAPI(account)
        profile = api.get_profile()
        click.echo(f"👤 Email: {profile.get('emailAddress', 'Unknown')}")
        click.echo(f"   Messages Total: {profile.get('messagesTotal', 0)}")
        click.echo(f"   Threads Total: {profile.get('threadsTotal', 0)}")
        if account:
            click.echo(f"   Account: {account}")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--label", "-l", help="Filter by label ID")
@click.option("--max", "-m", default=10, help="Maximum number of messages")
@click.option("--query", "-q", help="Search query")
@_account_option
@click.pass_context
def list(ctx, label, max, query, account):
    """List emails from your mailbox."""
    account = account or ctx.obj.get("ACCOUNT")
    try:
        api = GmailAPI(account)
        label_ids = [label] if label else None
        messages = api.list_messages(max_results=max, label_ids=label_ids, query=query)
        
        if not messages:
            click.echo("No messages found.")
            return
        
        click.echo(f"Found {len(messages)} messages:\n")
        
        for msg in messages:
            message = api.get_message(msg["id"], format="metadata")
            headers = message.get("payload", {}).get("headers", [])
            
            subject = next((h["value"] for h in headers if h["name"] == "Subject"), "No Subject")
            sender = next((h["value"] for h in headers if h["name"] == "From"), "Unknown")
            date = next((h["value"] for h in headers if h["name"] == "Date"), "")
            
            snippet = message.get("snippet", "")[:100]
            labels = ", ".join(message.get("labelIds", []))
            
            click.echo(f"📧 {msg['id']}")
            click.echo(f"   From: {sender}")
            click.echo(f"   Subject: {subject}")
            click.echo(f"   Date: {date}")
            click.echo(f"   Labels: {labels}")
            if snippet:
                click.echo(f"   Preview: {snippet}...")
            click.echo()
    
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("message_id")
@_account_option
@click.pass_context
def read(ctx, message_id, account):
    """Read full email content."""
    account = account or ctx.obj.get("ACCOUNT")
    try:
        api = GmailAPI(account)
        message = api.get_message(message_id, format="full")
        
        headers = message.get("payload", {}).get("headers", [])
        subject = next((h["value"] for h in headers if h["name"] == "Subject"), "No Subject")
        sender = next((h["value"] for h in headers if h["name"] == "From"), "Unknown")
        to = next((h["value"] for h in headers if h["name"] == "To"), "Unknown")
        date = next((h["value"] for h in headers if h["name"] == "Date"), "")
        
        click.echo(f"Subject: {subject}")
        click.echo(f"From: {sender}")
        click.echo(f"To: {to}")
        click.echo(f"Date: {date}")
        click.echo("-" * 60)
        
        # Extract body
        payload = message.get("payload", {})
        body = ""
        
        if "parts" in payload:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain":
                    data = part.get("body", {}).get("data")
                    if data:
                        import base64
                        body = base64.urlsafe_b64decode(data).decode("utf-8")
                        break
        else:
            if payload.get("mimeType") == "text/plain":
                data = payload.get("body", {}).get("data")
                if data:
                    import base64
                    body = base64.urlsafe_b64decode(data).decode("utf-8")
        
        click.echo(body)
    
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("to")
@click.argument("subject")
@click.option("--body", "-b", help="Email body text")
@click.option("--attach", "-a", multiple=True, help="Attachment file path (can specify multiple)")
@_account_option
@click.pass_context
def send(ctx, to, subject, body, attach, account):
    """Send an email."""
    account = account or ctx.obj.get("ACCOUNT")
    if not body:
        body = click.prompt("Email body", type=str)
    
    try:
        api = GmailAPI(account)
        attachments = list(attach) if attach else None
        result = api.send_message(to, subject, body, attachments)
        click.echo(f"✅ Email sent successfully!")
        click.echo(f"   Message ID: {result.get('id')}")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@_account_option
@click.pass_context
def labels(ctx, account):
    """List all labels."""
    account = account or ctx.obj.get("ACCOUNT")
    try:
        api = GmailAPI(account)
        labels = api.list_labels()
        
        if not labels:
            click.echo("No labels found.")
            return
        
        click.echo(f"Found {len(labels)} labels:\n")
        for label in labels:
            click.echo(f"🏷️  {label.get('name')} (ID: {label.get('id')})")
            if label.get("messageListVisibility"):
                click.echo(f"   Visibility: {label.get('messageListVisibility')}")
            if label.get("type"):
                click.echo(f"   Type: {label.get('type')}")
            click.echo()
    
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("query", required=False)
@click.option("--max", "-m", default=10, help="Maximum number of results")
@click.option("--from", "-f", "from_", help="Search by sender email or name")
@click.option("--to", "-t", help="Search by recipient email or name")
@click.option("--subject", "-s", help="Search in subject line")
@click.option("--has-attachment", is_flag=True, help="Messages with attachments")
@click.option("--label", "-l", help="Filter by label ID")
@click.option("--is-unread", is_flag=True, help="Unread messages only")
@click.option("--is-read", is_flag=True, help="Read messages only")
@click.option("--is-starred", is_flag=True, help="Starred messages only")
@click.option("--before", help="Before date (YYYY/MM/DD or YYYY-MM-DD)")
@click.option("--after", help="After date (YYYY/MM/DD or YYYY-MM-DD)")
@click.option("--newer-than", help="Newer than (e.g., '7d', '1m', '1y')")
@click.option("--older-than", help="Older than (e.g., '7d', '1m', '1y')")
@click.option("--larger", help="Larger than size (e.g., '10M', '1G')")
@click.option("--smaller", help="Smaller than size (e.g., '10M', '1G')")
@_account_option
@click.pass_context
def search(ctx, query, max, from_, to, subject, has_attachment, label, is_unread, is_read, is_starred, before, after, newer_than, older_than, larger, smaller, account):
    """Search emails using Gmail search syntax or convenient options."""
    account = account or ctx.obj.get("ACCOUNT")
    
    # Build query from options if no direct query provided
    if not query:
        query_parts = []
        if from_:
            query_parts.append(f"from:{from_}")
        if to:
            query_parts.append(f"to:{to}")
        if subject:
            query_parts.append(f'subject:"{subject}"')
        if has_attachment:
            query_parts.append("has:attachment")
        if label:
            query_parts.append(f"label:{label}")
        if is_unread:
            query_parts.append("is:unread")
        if is_read:
            query_parts.append("is:read")
        if is_starred:
            query_parts.append("is:starred")
        if before:
            query_parts.append(f"before:{before}")
        if after:
            query_parts.append(f"after:{after}")
        if newer_than:
            query_parts.append(f"newer_than:{newer_than}")
        if older_than:
            query_parts.append(f"older_than:{older_than}")
        if larger:
            query_parts.append(f"larger:{larger}")
        if smaller:
            query_parts.append(f"smaller:{smaller}")
        
        if not query_parts:
            click.echo("❌ Error: Please provide a search query or use search options.")
            click.echo("\nExamples:")
            click.echo("  gmail search 'important'")
            click.echo("  gmail search --from sender@example.com")
            click.echo("  gmail search --subject 'meeting' --is-unread")
            click.echo("  gmail search --has-attachment --newer-than 7d")
            sys.exit(1)
        
        query = " ".join(query_parts)
    
    try:
        api = GmailAPI(account)
        label_ids = [label] if label else None
        messages = api.list_messages(max_results=max, label_ids=label_ids, query=query)
        
        if not messages:
            click.echo(f"No messages found for query: {query}")
            return
        
        click.echo(f"Found {len(messages)} messages for '{query}':\n")
        
        for msg in messages:
            message = api.get_message(msg["id"], format="metadata")
            headers = message.get("payload", {}).get("headers", [])
            subject = next((h["value"] for h in headers if h["name"] == "Subject"), "No Subject")
            sender = next((h["value"] for h in headers if h["name"] == "From"), "Unknown")
            date = next((h["value"] for h in headers if h["name"] == "Date"), "")
            
            snippet = message.get("snippet", "")[:100]
            labels = message.get("labelIds", [])
            label_display = ", ".join([l for l in labels if l not in ["INBOX", "UNREAD"]])
            
            click.echo(f"📧 {msg['id']}")
            click.echo(f"   From: {sender}")
            click.echo(f"   Subject: {subject}")
            click.echo(f"   Date: {date}")
            if label_display:
                click.echo(f"   Labels: {label_display}")
            if snippet:
                click.echo(f"   Preview: {snippet}...")
            click.echo()
    
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--max", "-m", default=10, help="Maximum number of threads")
@click.option("--query", "-q", help="Search query")
@_account_option
@click.pass_context
def threads(ctx, max, query, account):
    """List email threads."""
    account = account or ctx.obj.get("ACCOUNT")
    try:
        api = GmailAPI(account)
        threads = api.list_threads(max_results=max, query=query)
        
        if not threads:
            click.echo("No threads found.")
            return
        
        click.echo(f"Found {len(threads)} threads:\n")
        for thread in threads:
            click.echo(f"🧵 Thread ID: {thread['id']}")
    
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("message_id")
@_account_option
@click.pass_context
def mark_read(ctx, message_id, account):
    """Mark a message as read."""
    account = account or ctx.obj.get("ACCOUNT")
    try:
        api = GmailAPI(account)
        api.mark_as_read(message_id)
        click.echo(f"✅ Message {message_id} marked as read")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("message_id")
@_account_option
@click.pass_context
def archive(ctx, message_id, account):
    """Archive a message."""
    account = account or ctx.obj.get("ACCOUNT")
    try:
        api = GmailAPI(account)
        api.archive_message(message_id)
        click.echo(f"✅ Message {message_id} archived")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@_account_option
@click.pass_context
def filters(ctx, account):
    """List all Gmail filters."""
    account = account or ctx.obj.get("ACCOUNT")
    try:
        api = GmailAPI(account)
        filters = api.list_filters()
        
        if not filters:
            click.echo("No filters found.")
            return
        
        click.echo(f"Found {len(filters)} filters:\n")
        for f in filters:
            click.echo(f"🔍 Filter ID: {f.get('id')}")
            
            criteria = f.get("criteria", {})
            if criteria:
                click.echo("   Criteria:")
                if criteria.get("from"):
                    click.echo(f"     From: {criteria.get('from')}")
                if criteria.get("to"):
                    click.echo(f"     To: {criteria.get('to')}")
                if criteria.get("subject"):
                    click.echo(f"     Subject: {criteria.get('subject')}")
                if criteria.get("query"):
                    click.echo(f"     Query: {criteria.get('query')}")
                if criteria.get("hasAttachment"):
                    click.echo(f"     Has Attachment: {criteria.get('hasAttachment')}")
            
            action = f.get("action", {})
            if action:
                click.echo("   Actions:")
                if action.get("addLabelIds"):
                    click.echo(f"     Add Labels: {', '.join(action.get('addLabelIds', []))}")
                if action.get("removeLabelIds"):
                    click.echo(f"     Remove Labels: {', '.join(action.get('removeLabelIds', []))}")
                if action.get("forward"):
                    click.echo(f"     Forward to: {action.get('forward')}")
            
            click.echo()
    
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--from", "-f", help="Filter by sender email or name")
@click.option("--to", "-t", help="Filter by recipient email or name")
@click.option("--subject", "-s", help="Filter by subject (case-insensitive)")
@click.option("--query", "-q", help="Gmail search query")
@click.option("--has-attachment", is_flag=True, help="Filter messages with attachments")
@click.option("--add-label", multiple=True, help="Label ID to add (can specify multiple)")
@click.option("--remove-label", multiple=True, help="Label ID to remove (can specify multiple)")
@click.option("--forward", help="Email address to forward matching messages to")
@_account_option
@click.pass_context
def create_filter(ctx, from_, to, subject, query, has_attachment, add_label, remove_label, forward, account):
    """Create a new Gmail filter."""
    account = account or ctx.obj.get("ACCOUNT")
    
    # Build criteria
    criteria = {}
    if from_:
        criteria["from"] = from_
    if to:
        criteria["to"] = to
    if subject:
        criteria["subject"] = subject
    if query:
        criteria["query"] = query
    if has_attachment:
        criteria["hasAttachment"] = True
    
    if not criteria:
        click.echo("❌ Error: At least one filter criterion is required.")
        click.echo("\nUse options like --from, --to, --subject, --query, or --has-attachment")
        sys.exit(1)
    
    # Build action
    action = {}
    if add_label:
        action["addLabelIds"] = list(add_label)
    if remove_label:
        action["removeLabelIds"] = list(remove_label)
    if forward:
        action["forward"] = forward
    
    if not action:
        click.echo("❌ Error: At least one filter action is required.")
        click.echo("\nUse options like --add-label, --remove-label, or --forward")
        sys.exit(1)
    
    try:
        api = GmailAPI(account)
        result = api.create_filter(criteria, action)
        click.echo(f"✅ Filter created successfully!")
        click.echo(f"   Filter ID: {result.get('id')}")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("filter_id")
@_account_option
@click.pass_context
def get_filter(ctx, filter_id, account):
    """Get details of a specific filter."""
    account = account or ctx.obj.get("ACCOUNT")
    try:
        api = GmailAPI(account)
        f = api.get_filter(filter_id)
        
        click.echo(f"🔍 Filter ID: {f.get('id')}\n")
        
        criteria = f.get("criteria", {})
        if criteria:
            click.echo("Criteria:")
            for key, value in criteria.items():
                click.echo(f"  {key}: {value}")
        
        action = f.get("action", {})
        if action:
            click.echo("\nActions:")
            for key, value in action.items():
                click.echo(f"  {key}: {value}")
    
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("filter_id")
@_account_option
@click.pass_context
def delete_filter(ctx, filter_id, account):
    """Delete a Gmail filter."""
    account = account or ctx.obj.get("ACCOUNT")
    try:
        api = GmailAPI(account)
        api.delete_filter(filter_id)
        click.echo(f"✅ Filter {filter_id} deleted successfully")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("message_id")
@_account_option
@click.pass_context
def spam(ctx, message_id, account):
    """Mark a message as spam."""
    account = account or ctx.obj.get("ACCOUNT")
    try:
        api = GmailAPI(account)
        api.mark_as_spam(message_id)
        click.echo(f"✅ Message {message_id} marked as spam")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("message_id")
@_account_option
@click.pass_context
def unspam(ctx, message_id, account):
    """Remove spam label from a message."""
    account = account or ctx.obj.get("ACCOUNT")
    try:
        api = GmailAPI(account)
        api.unmark_spam(message_id)
        click.echo(f"✅ Message {message_id} removed from spam")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("message_id")
@_account_option
@click.pass_context
def star(ctx, message_id, account):
    """Star a message."""
    account = account or ctx.obj.get("ACCOUNT")
    try:
        api = GmailAPI(account)
        api.star_message(message_id)
        click.echo(f"✅ Message {message_id} starred")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("message_id")
@_account_option
@click.pass_context
def unstar(ctx, message_id, account):
    """Unstar a message."""
    account = account or ctx.obj.get("ACCOUNT")
    try:
        api = GmailAPI(account)
        api.unstar_message(message_id)
        click.echo(f"✅ Message {message_id} unstarred")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("name")
@click.option("--visibility", "-v", default="show", help="Message list visibility (show/hide)")
@click.option("--list-visibility", "-l", default="labelShow", help="Label list visibility (labelShow/labelHide)")
@click.option("--bg-color", help="Background color (hex, e.g., #4285f4)")
@click.option("--text-color", help="Text color (hex, e.g., #ffffff)")
@_account_option
@click.pass_context
def create_label(ctx, name, visibility, list_visibility, bg_color, text_color, account):
    """Create a new label."""
    account = account or ctx.obj.get("ACCOUNT")
    try:
        api = GmailAPI(account)
        color = None
        if bg_color or text_color:
            color = {}
            if bg_color:
                color["backgroundColor"] = bg_color
            if text_color:
                color["textColor"] = text_color
        
        result = api.create_label(name, visibility, list_visibility, color)
        click.echo(f"✅ Label created successfully!")
        click.echo(f"   Label ID: {result.get('id')}")
        click.echo(f"   Name: {result.get('name')}")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("label_id")
@_account_option
@click.pass_context
def delete_label(ctx, label_id, account):
    """Delete a label."""
    account = account or ctx.obj.get("ACCOUNT")
    try:
        api = GmailAPI(account)
        api.delete_label(label_id)
        click.echo(f"✅ Label {label_id} deleted successfully")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("label_id")
@click.option("--name", "-n", help="New label name")
@click.option("--visibility", "-v", help="Message list visibility (show/hide)")
@click.option("--list-visibility", "-l", help="Label list visibility (labelShow/labelHide)")
@click.option("--bg-color", help="Background color (hex)")
@click.option("--text-color", help="Text color (hex)")
@_account_option
@click.pass_context
def update_label(ctx, label_id, name, visibility, list_visibility, bg_color, text_color, account):
    """Update a label."""
    account = account or ctx.obj.get("ACCOUNT")
    try:
        api = GmailAPI(account)
        color = None
        if bg_color or text_color:
            color = {}
            if bg_color:
                color["backgroundColor"] = bg_color
            if text_color:
                color["textColor"] = text_color
        
        result = api.update_label(label_id, name, visibility, list_visibility, color)
        click.echo(f"✅ Label updated successfully!")
        click.echo(f"   Label ID: {result.get('id')}")
        click.echo(f"   Name: {result.get('name')}")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("label_id")
@_account_option
@click.pass_context
def get_label(ctx, label_id, account):
    """Get label details."""
    account = account or ctx.obj.get("ACCOUNT")
    try:
        api = GmailAPI(account)
        label = api.get_label(label_id)
        click.echo(f"🏷️  Label ID: {label.get('id')}")
        click.echo(f"   Name: {label.get('name')}")
        click.echo(f"   Message List Visibility: {label.get('messageListVisibility')}")
        click.echo(f"   Label List Visibility: {label.get('labelListVisibility')}")
        if label.get("color"):
            click.echo(f"   Background Color: {label.get('color', {}).get('backgroundColor')}")
            click.echo(f"   Text Color: {label.get('color', {}).get('textColor')}")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--max", "-m", default=10, help="Maximum number of drafts")
@_account_option
@click.pass_context
def drafts(ctx, max, account):
    """List draft messages."""
    account = account or ctx.obj.get("ACCOUNT")
    try:
        api = GmailAPI(account)
        drafts = api.list_drafts(max)
        
        if not drafts:
            click.echo("No drafts found.")
            return
        
        click.echo(f"Found {len(drafts)} drafts:\n")
        for draft in drafts:
            draft_id = draft.get("id")
            message = draft.get("message", {})
            message_id = message.get("id")
            click.echo(f"📝 Draft ID: {draft_id}")
            click.echo(f"   Message ID: {message_id}")
            click.echo()
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("to")
@click.argument("subject")
@click.option("--body", "-b", help="Email body text")
@click.option("--attach", "-a", multiple=True, help="Attachment file path (can specify multiple)")
@_account_option
@click.pass_context
def create_draft(ctx, to, subject, body, attach, account):
    """Create a draft message."""
    account = account or ctx.obj.get("ACCOUNT")
    if not body:
        body = click.prompt("Email body", type=str)
    
    try:
        api = GmailAPI(account)
        attachments = list(attach) if attach else None
        result = api.create_draft(to, subject, body, attachments)
        click.echo(f"✅ Draft created successfully!")
        click.echo(f"   Draft ID: {result.get('id')}")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("draft_id")
@_account_option
@click.pass_context
def get_draft(ctx, draft_id, account):
    """Get draft details."""
    account = account or ctx.obj.get("ACCOUNT")
    try:
        api = GmailAPI(account)
        draft = api.get_draft(draft_id)
        message = draft.get("message", {})
        
        click.echo(f"📝 Draft ID: {draft.get('id')}")
        click.echo(f"   Message ID: {message.get('id')}")
        
        headers = message.get("payload", {}).get("headers", [])
        subject = next((h["value"] for h in headers if h["name"] == "Subject"), "No Subject")
        to = next((h["value"] for h in headers if h["name"] == "To"), "Unknown")
        
        click.echo(f"   To: {to}")
        click.echo(f"   Subject: {subject}")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("draft_id")
@click.argument("to")
@click.argument("subject")
@click.option("--body", "-b", help="Email body text")
@click.option("--attach", "-a", multiple=True, help="Attachment file path")
@_account_option
@click.pass_context
def update_draft(ctx, draft_id, to, subject, body, attach, account):
    """Update a draft message."""
    account = account or ctx.obj.get("ACCOUNT")
    if not body:
        body = click.prompt("Email body", type=str)
    
    try:
        api = GmailAPI(account)
        attachments = list(attach) if attach else None
        result = api.update_draft(draft_id, to, subject, body, attachments)
        click.echo(f"✅ Draft updated successfully!")
        click.echo(f"   Draft ID: {result.get('id')}")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("draft_id")
@_account_option
@click.pass_context
def delete_draft(ctx, draft_id, account):
    """Delete a draft."""
    account = account or ctx.obj.get("ACCOUNT")
    try:
        api = GmailAPI(account)
        api.delete_draft(draft_id)
        click.echo(f"✅ Draft {draft_id} deleted successfully")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("message_id")
@click.argument("body")
@click.option("--reply-all", is_flag=True, help="Reply to all recipients")
@_account_option
@click.pass_context
def reply(ctx, message_id, body, reply_all, account):
    """Reply to a message."""
    account = account or ctx.obj.get("ACCOUNT")
    try:
        api = GmailAPI(account)
        result = api.reply_to_message(message_id, body, reply_all)
        click.echo(f"✅ Reply sent successfully!")
        click.echo(f"   Message ID: {result.get('id')}")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("message_id")
@click.argument("to")
@click.option("--body", "-b", help="Forward message body")
@_account_option
@click.pass_context
def forward(ctx, message_id, to, body, account):
    """Forward a message."""
    account = account or ctx.obj.get("ACCOUNT")
    try:
        api = GmailAPI(account)
        result = api.forward_message(message_id, to, body)
        click.echo(f"✅ Message forwarded successfully!")
        click.echo(f"   Message ID: {result.get('id')}")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("email")
@_account_option
@click.pass_context
def block(ctx, email, account):
    """Block a sender (creates filter to mark as spam)."""
    account = account or ctx.obj.get("ACCOUNT")
    try:
        api = GmailAPI(account)
        result = api.block_sender(email)
        click.echo(f"✅ Sender {email} blocked successfully!")
        click.echo(f"   Filter ID: {result.get('id')}")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("message_id")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation prompt")
@_account_option
@click.pass_context
def delete(ctx, message_id, force, account):
    """Permanently delete a message (cannot be undone!)."""
    account = account or ctx.obj.get("ACCOUNT")
    
    if not force:
        if not click.confirm(f"⚠️  Warning: This will permanently delete message {message_id}. This cannot be undone!\n   Do you want to continue?"):
            click.echo("Deletion cancelled.")
            return
    
    try:
        api = GmailAPI(account)
        api.delete_message(message_id)
        click.echo(f"✅ Message {message_id} permanently deleted")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("message_id")
@_account_option
@click.pass_context
def trash(ctx, message_id, account):
    """Move a message to trash (can be recovered)."""
    account = account or ctx.obj.get("ACCOUNT")
    try:
        api = GmailAPI(account)
        api.trash_message(message_id)
        click.echo(f"✅ Message {message_id} moved to trash")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("message_id")
@_account_option
@click.pass_context
def untrash(ctx, message_id, account):
    """Remove a message from trash (restore to inbox)."""
    account = account or ctx.obj.get("ACCOUNT")
    try:
        api = GmailAPI(account)
        api.untrash_message(message_id)
        click.echo(f"✅ Message {message_id} restored from trash")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("message_ids", nargs=-1, required=True)
@click.option("--query", "-q", help="Search query - operate on matching messages instead of IDs")
@click.option("--max", "-m", default=100, help="Maximum number of messages when using --query")
@_account_option
@click.pass_context
def batch_mark_read(ctx, message_ids, query, max, account):
    """Mark multiple messages as read."""
    account = account or ctx.obj.get("ACCOUNT")
    try:
        api = GmailAPI(account)
        
        if query:
            messages = api.list_messages(max_results=max, query=query)
            message_ids = [msg["id"] for msg in messages]
            if not message_ids:
                click.echo(f"No messages found for query: {query}")
                return
        
        if not message_ids:
            click.echo("❌ Error: No message IDs provided")
            sys.exit(1)
        
        result = api.batch_modify_messages(message_ids, remove_label_ids=["UNREAD"])
        click.echo(f"✅ Marked {result['modified']} message(s) as read")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("message_ids", nargs=-1, required=True)
@click.option("--query", "-q", help="Search query - operate on matching messages instead of IDs")
@click.option("--max", "-m", default=100, help="Maximum number of messages when using --query")
@_account_option
@click.pass_context
def batch_archive(ctx, message_ids, query, max, account):
    """Archive multiple messages."""
    account = account or ctx.obj.get("ACCOUNT")
    try:
        api = GmailAPI(account)
        
        if query:
            messages = api.list_messages(max_results=max, query=query)
            message_ids = [msg["id"] for msg in messages]
            if not message_ids:
                click.echo(f"No messages found for query: {query}")
                return
        
        if not message_ids:
            click.echo("❌ Error: No message IDs provided")
            sys.exit(1)
        
        result = api.batch_modify_messages(message_ids, remove_label_ids=["INBOX"])
        click.echo(f"✅ Archived {result['modified']} message(s)")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("message_ids", nargs=-1, required=True)
@click.option("--query", "-q", help="Search query - operate on matching messages instead of IDs")
@click.option("--max", "-m", default=100, help="Maximum number of messages when using --query")
@_account_option
@click.pass_context
def batch_star(ctx, message_ids, query, max, account):
    """Star multiple messages."""
    account = account or ctx.obj.get("ACCOUNT")
    try:
        api = GmailAPI(account)
        
        if query:
            messages = api.list_messages(max_results=max, query=query)
            message_ids = [msg["id"] for msg in messages]
            if not message_ids:
                click.echo(f"No messages found for query: {query}")
                return
        
        if not message_ids:
            click.echo("❌ Error: No message IDs provided")
            sys.exit(1)
        
        result = api.batch_modify_messages(message_ids, add_label_ids=["STARRED"])
        click.echo(f"✅ Starred {result['modified']} message(s)")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("message_ids", nargs=-1, required=True)
@click.option("--query", "-q", help="Search query - operate on matching messages instead of IDs")
@click.option("--max", "-m", default=100, help="Maximum number of messages when using --query")
@_account_option
@click.pass_context
def batch_unstar(ctx, message_ids, query, max, account):
    """Unstar multiple messages."""
    account = account or ctx.obj.get("ACCOUNT")
    try:
        api = GmailAPI(account)
        
        if query:
            messages = api.list_messages(max_results=max, query=query)
            message_ids = [msg["id"] for msg in messages]
            if not message_ids:
                click.echo(f"No messages found for query: {query}")
                return
        
        if not message_ids:
            click.echo("❌ Error: No message IDs provided")
            sys.exit(1)
        
        result = api.batch_modify_messages(message_ids, remove_label_ids=["STARRED"])
        click.echo(f"✅ Unstarred {result['modified']} message(s)")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("message_ids", nargs=-1, required=True)
@click.option("--query", "-q", help="Search query - operate on matching messages instead of IDs")
@click.option("--max", "-m", default=100, help="Maximum number of messages when using --query")
@_account_option
@click.pass_context
def batch_trash(ctx, message_ids, query, max, account):
    """Move multiple messages to trash."""
    account = account or ctx.obj.get("ACCOUNT")
    try:
        api = GmailAPI(account)
        
        if query:
            messages = api.list_messages(max_results=max, query=query)
            message_ids = [msg["id"] for msg in messages]
            if not message_ids:
                click.echo(f"No messages found for query: {query}")
                return
        
        if not message_ids:
            click.echo("❌ Error: No message IDs provided")
            sys.exit(1)
        
        result = api.batch_trash_messages(message_ids)
        click.echo(f"✅ Moved {result['trashed']} message(s) to trash")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("message_ids", nargs=-1, required=True)
@click.option("--query", "-q", help="Search query - operate on matching messages instead of IDs")
@click.option("--max", "-m", default=100, help="Maximum number of messages when using --query")
@_account_option
@click.pass_context
def batch_untrash(ctx, message_ids, query, max, account):
    """Restore multiple messages from trash."""
    account = account or ctx.obj.get("ACCOUNT")
    try:
        api = GmailAPI(account)
        
        if query:
            messages = api.list_messages(max_results=max, query=query)
            message_ids = [msg["id"] for msg in messages]
            if not message_ids:
                click.echo(f"No messages found for query: {query}")
                return
        
        if not message_ids:
            click.echo("❌ Error: No message IDs provided")
            sys.exit(1)
        
        result = api.batch_untrash_messages(message_ids)
        click.echo(f"✅ Restored {result['untrashed']} message(s) from trash")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("message_ids", nargs=-1, required=True)
@click.option("--query", "-q", help="Search query - operate on matching messages instead of IDs")
@click.option("--max", "-m", default=100, help="Maximum number of messages when using --query")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation prompt")
@_account_option
@click.pass_context
def batch_delete(ctx, message_ids, query, max, force, account):
    """Permanently delete multiple messages (cannot be undone!)."""
    account = account or ctx.obj.get("ACCOUNT")
    
    try:
        api = GmailAPI(account)
        
        if query:
            messages = api.list_messages(max_results=max, query=query)
            message_ids = [msg["id"] for msg in messages]
            if not message_ids:
                click.echo(f"No messages found for query: {query}")
                return
        
        if not message_ids:
            click.echo("❌ Error: No message IDs provided")
            sys.exit(1)
        
        if not force:
            if not click.confirm(f"⚠️  Warning: This will permanently delete {len(message_ids)} message(s). This cannot be undone!\n   Do you want to continue?"):
                click.echo("Deletion cancelled.")
                return
        
        result = api.batch_delete_messages(message_ids)
        click.echo(f"✅ Permanently deleted {result['deleted']} message(s)")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("message_ids", nargs=-1, required=True)
@click.option("--query", "-q", help="Search query - operate on matching messages instead of IDs")
@click.option("--max", "-m", default=100, help="Maximum number of messages when using --query")
@click.option("--add-label", multiple=True, help="Label ID to add (can specify multiple)")
@click.option("--remove-label", multiple=True, help="Label ID to remove (can specify multiple)")
@_account_option
@click.pass_context
def batch_modify(ctx, message_ids, query, max, add_label, remove_label, account):
    """Batch modify labels on multiple messages."""
    account = account or ctx.obj.get("ACCOUNT")
    try:
        api = GmailAPI(account)
        
        if query:
            messages = api.list_messages(max_results=max, query=query)
            message_ids = [msg["id"] for msg in messages]
            if not message_ids:
                click.echo(f"No messages found for query: {query}")
                return
        
        if not message_ids:
            click.echo("❌ Error: No message IDs provided")
            sys.exit(1)
        
        add_label_ids = list(add_label) if add_label else None
        remove_label_ids = list(remove_label) if remove_label else None
        
        if not add_label_ids and not remove_label_ids:
            click.echo("❌ Error: At least one of --add-label or --remove-label is required")
            sys.exit(1)
        
        result = api.batch_modify_messages(message_ids, add_label_ids=add_label_ids, remove_label_ids=remove_label_ids)
        click.echo(f"✅ Modified {result['modified']} message(s)")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("message_ids", nargs=-1, required=True)
@click.option("--query", "-q", help="Search query - operate on matching messages instead of IDs")
@click.option("--max", "-m", default=100, help="Maximum number of messages when using --query")
@_account_option
@click.pass_context
def batch_spam(ctx, message_ids, query, max, account):
    """Mark multiple messages as spam."""
    account = account or ctx.obj.get("ACCOUNT")
    try:
        api = GmailAPI(account)
        
        if query:
            messages = api.list_messages(max_results=max, query=query)
            message_ids = [msg["id"] for msg in messages]
            if not message_ids:
                click.echo(f"No messages found for query: {query}")
                return
        
        if not message_ids:
            click.echo("❌ Error: No message IDs provided")
            sys.exit(1)
        
        result = api.batch_modify_messages(message_ids, add_label_ids=["SPAM"], remove_label_ids=["INBOX"])
        click.echo(f"✅ Marked {result['modified']} message(s) as spam")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("message_ids", nargs=-1, required=True)
@click.option("--query", "-q", help="Search query - operate on matching messages instead of IDs")
@click.option("--max", "-m", default=100, help="Maximum number of messages when using --query")
@_account_option
@click.pass_context
def batch_unspam(ctx, message_ids, query, max, account):
    """Remove spam label from multiple messages."""
    account = account or ctx.obj.get("ACCOUNT")
    try:
        api = GmailAPI(account)
        
        if query:
            messages = api.list_messages(max_results=max, query=query)
            message_ids = [msg["id"] for msg in messages]
            if not message_ids:
                click.echo(f"No messages found for query: {query}")
                return
        
        if not message_ids:
            click.echo("❌ Error: No message IDs provided")
            sys.exit(1)
        
        result = api.batch_modify_messages(message_ids, remove_label_ids=["SPAM"], add_label_ids=["INBOX"])
        click.echo(f"✅ Removed spam label from {result['modified']} message(s)")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()

