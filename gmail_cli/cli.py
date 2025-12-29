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
@click.argument("query")
@click.option("--max", "-m", default=10, help="Maximum number of results")
@_account_option
@click.pass_context
def search(ctx, query, max, account):
    """Search emails."""
    account = account or ctx.obj.get("ACCOUNT")
    try:
        api = GmailAPI(account)
        messages = api.list_messages(max_results=max, query=query)
        
        if not messages:
            click.echo(f"No messages found for query: {query}")
            return
        
        click.echo(f"Found {len(messages)} messages for '{query}':\n")
        
        for msg in messages:
            message = api.get_message(msg["id"], format="metadata")
            headers = message.get("payload", {}).get("headers", [])
            subject = next((h["value"] for h in headers if h["name"] == "Subject"), "No Subject")
            sender = next((h["value"] for h in headers if h["name"] == "From"), "Unknown")
            
            click.echo(f"📧 {msg['id']}: {subject} (from {sender})")
    
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


if __name__ == "__main__":
    cli()

