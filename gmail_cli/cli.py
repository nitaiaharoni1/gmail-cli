"""Gmail CLI - Main command-line interface."""

import click
import json
import sys
import logging
import os
from .auth import authenticate, get_credentials, check_auth
from .api import GmailAPI
from .utils import format_email_address, format_date, list_accounts, get_default_account, set_default_account, get_token_path
from .shared_auth import check_token_health, refresh_token
from .config import get_preference, set_preference
from .templates import list_templates, get_template, create_template, delete_template, render_template
from .history import add_operation, get_recent_operations, get_last_undoable_operation


@click.group(context_settings={"allow_interspersed_args": False})
@click.version_option(version="1.0.6")
@click.option("--account", "-a", help="Account name to use (default: current default account or GMAIL_ACCOUNT env var)")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose/debug logging")
@click.pass_context
def cli(ctx, account, verbose):
    """Gmail CLI - Command-line interface for Gmail."""
    ctx.ensure_object(dict)
    # Resolve account: CLI arg > env var > default
    if account is None:
        account = os.getenv("GMAIL_ACCOUNT")
    if account is None:
        account = get_default_account()
    ctx.obj["ACCOUNT"] = account
    
    # Setup logging
    if verbose or get_preference("verbose", False):
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        logging.getLogger("googleapiclient").setLevel(logging.DEBUG)
        ctx.obj["VERBOSE"] = True
    else:
        logging.basicConfig(level=logging.WARNING)
        ctx.obj["VERBOSE"] = False


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


@cli.group()
def auth():
    """Authentication management commands."""
    pass


@auth.command()
@click.option("--account", "-a", help="Check specific account (default: all accounts)")
def status(account):
    """Show token health status for account(s)."""
    from .auth import SCOPES
    
    accounts_to_check = [account] if account else list_accounts()
    
    if not accounts_to_check:
        click.echo("No accounts configured. Run 'gmail init' to add an account.")
        return
    
    for acc in accounts_to_check:
        health = check_token_health(acc, "gmail", SCOPES)
        status_icon = {
            "valid": "✅",
            "expired_refreshable": "⚠️",
            "expired": "❌",
            "scope_mismatch": "❌",
            "missing": "❌",
            "error": "❌"
        }.get(health["status"], "❓")
        
        click.echo(f"\n{status_icon} Account: {acc}")
        click.echo(f"   Status: {health['status']}")
        click.echo(f"   Message: {health.get('message', 'N/A')}")
        
        if health["status"] == "valid" and health.get("expires_in"):
            hours = health["expires_in"] // 3600
            days = hours // 24
            if days > 0:
                click.echo(f"   Expires in: {days} days, {hours % 24} hours")
            else:
                click.echo(f"   Expires in: {hours} hours")
        
        if health["status"] == "scope_mismatch":
            click.echo(f"   Current scopes: {', '.join(health.get('current_scopes', []))}")
            click.echo(f"   Required scopes: {', '.join(health.get('required_scopes', []))}")


@auth.command()
@click.option("--account", "-a", help="Refresh specific account (default: current default)")
@click.option("--all", is_flag=True, help="Refresh all accounts")
def refresh(account, all):
    """Refresh expired token(s)."""
    from .auth import SCOPES
    
    if all:
        accounts_to_refresh = list_accounts()
        if not accounts_to_refresh:
            click.echo("No accounts configured.")
            return
    else:
        accounts_to_refresh = [account or get_default_account()]
        if not accounts_to_refresh[0]:
            click.echo("❌ Error: No account specified and no default account set.")
            click.echo("Use --account <name> or run 'gmail init' first.")
            sys.exit(1)
    
    for acc in accounts_to_refresh:
        click.echo(f"\nRefreshing account: {acc}")
        creds = refresh_token(acc, "gmail", SCOPES)
        if creds:
            click.echo(f"✅ Token refreshed successfully for {acc}")
        else:
            click.echo(f"❌ Failed to refresh token for {acc}")
            click.echo("   Run 'gmail init --account {acc}' to re-authenticate.")


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


@cli.command(name="list")
@click.option("--label", "-l", help="Filter by label ID")
@click.option("--max", "-m", default=10, help="Maximum number of messages")
@click.option("--query", "-q", help="Search query")
@click.option("--output", "-o", type=click.Choice(["table", "json", "csv", "ids"]), default="table", help="Output format")
@_account_option
@click.pass_context
def list_messages(ctx, label, max, query, output, account):
    """List emails from your mailbox."""
    account = account or ctx.obj.get("ACCOUNT")
    try:
        api = GmailAPI(account)
        label_ids = [label] if label else None
        
        # Use batch fetching for better performance
        if output == "ids":
            # For IDs only, just get the list
            messages = api.list_messages(max_results=max, label_ids=label_ids, query=query)
            for msg in messages:
                click.echo(msg["id"])
            return
        
        # Fetch full details in batch
        messages = api.search_with_details(max_results=max, label_ids=label_ids, query=query, format="metadata")
        
        if not messages:
            if output == "json":
                click.echo("[]")
            else:
                click.echo("No messages found.")
            return
        
        # Filter out errors
        valid_messages = [msg for msg in messages if "error" not in msg]
        
        if output == "json":
            import json
            # Convert to serializable format
            output_data = []
            for msg in valid_messages:
                headers = msg.get("payload", {}).get("headers", [])
                output_data.append({
                    "id": msg.get("id"),
                    "from": next((h["value"] for h in headers if h["name"] == "From"), "Unknown"),
                    "subject": next((h["value"] for h in headers if h["name"] == "Subject"), "No Subject"),
                    "date": next((h["value"] for h in headers if h["name"] == "Date"), ""),
                    "snippet": msg.get("snippet", "")[:100],
                    "labels": msg.get("labelIds", [])
                })
            click.echo(json.dumps(output_data, indent=2, ensure_ascii=False))
        elif output == "csv":
            import csv
            import sys
            writer = csv.writer(sys.stdout)
            writer.writerow(["ID", "From", "Subject", "Date", "Labels", "Preview"])
            for msg in valid_messages:
                headers = msg.get("payload", {}).get("headers", [])
                writer.writerow([
                    msg.get("id", ""),
                    next((h["value"] for h in headers if h["name"] == "From"), "Unknown"),
                    next((h["value"] for h in headers if h["name"] == "Subject"), "No Subject"),
                    next((h["value"] for h in headers if h["name"] == "Date"), ""),
                    ", ".join(msg.get("labelIds", [])),
                    msg.get("snippet", "")[:100]
                ])
        else:
            # Table format (default)
            click.echo(f"Found {len(valid_messages)} messages:\n")
            for msg in valid_messages:
                headers = msg.get("payload", {}).get("headers", [])
                
                subject = next((h["value"] for h in headers if h["name"] == "Subject"), "No Subject")
                sender = next((h["value"] for h in headers if h["name"] == "From"), "Unknown")
                date = next((h["value"] for h in headers if h["name"] == "Date"), "")
                
                snippet = msg.get("snippet", "")[:100]
                labels = ", ".join(msg.get("labelIds", []))
                
                click.echo(f"📧 {msg.get('id')}")
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
@click.argument("to", required=False)
@click.argument("subject", required=False)
@click.option("--body", "-b", help="Email body text")
@click.option("--attach", multiple=True, help="Attachment file path (can specify multiple)")
@click.option("--cc", "-c", help="CC recipient email address")
@click.option("--template", "-t", help="Use email template (name)")
@click.option("--interactive", "-i", is_flag=True, help="Interactive mode - prompts for missing fields")
@click.option("--dry-run", is_flag=True, help="Show what would be sent without actually sending")
@_account_option
@click.pass_context
def send(ctx, to, subject, body, attach, cc, template, interactive, dry_run, account):
    """Send an email."""
    account = account or ctx.obj.get("ACCOUNT")
    
    # Interactive mode - prompt for missing fields
    if interactive or not to or not subject:
        if not to:
            to = click.prompt("To", type=str)
        if not subject:
            subject = click.prompt("Subject", type=str)
        if not body:
            body = click.prompt("Body", type=str)
        if not cc:
            cc_input = click.prompt("CC (optional, press Enter to skip)", default="", show_default=False)
            cc = cc_input if cc_input else None
    
    # Load template if specified
    if template:
        try:
            template_data = render_template(template, to=to, subject=subject)
            to = template_data.get("to") or to
            subject = template_data.get("subject") or subject
            body = template_data.get("body") or body
            cc = template_data.get("cc") or cc
        except Exception as e:
            click.echo(f"❌ Error loading template: {e}", err=True)
            sys.exit(1)
    
    if not body:
        body = click.prompt("Email body", type=str)
    
    if dry_run:
        click.echo("🔍 DRY RUN - Would send email:")
        click.echo(f"   To: {to}")
        if cc:
            click.echo(f"   CC: {cc}")
        click.echo(f"   Subject: {subject}")
        click.echo(f"   Body: {body[:100]}..." if len(body) > 100 else f"   Body: {body}")
        if attach:
            click.echo(f"   Attachments: {', '.join(attach)}")
        return
    
    try:
        api = GmailAPI(account)
        attachments = list(attach) if attach else None
        result = api.send_message(to, subject, body, attachments, cc)
        
        # Record in history (send is not undoable)
        add_operation("send", {
            "message_id": result.get("id"),
            "to": to,
            "subject": subject
        }, undoable=False)
        
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
@click.option("--output", "-o", type=click.Choice(["table", "json", "csv", "ids"]), default="table", help="Output format")
@_account_option
@click.pass_context
def search(ctx, query, max, from_, to, subject, has_attachment, label, is_unread, is_read, is_starred, before, after, newer_than, older_than, larger, smaller, output, account):
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
        
        # Use batch fetching for better performance
        if output == "ids":
            # For IDs only, just get the list
            messages = api.list_messages(max_results=max, label_ids=label_ids, query=query)
            for msg in messages:
                click.echo(msg["id"])
            return
        
        # Fetch full details in batch
        messages = api.search_with_details(max_results=max, label_ids=label_ids, query=query, format="metadata")
        
        if not messages:
            if output == "json":
                click.echo("[]")
            else:
                click.echo(f"No messages found for query: {query}")
            return
        
        # Filter out errors
        valid_messages = [msg for msg in messages if "error" not in msg]
        
        if output == "json":
            import json
            # Convert to serializable format
            output_data = []
            for msg in valid_messages:
                headers = msg.get("payload", {}).get("headers", [])
                labels = msg.get("labelIds", [])
                label_display = [l for l in labels if l not in ["INBOX", "UNREAD"]]
                output_data.append({
                    "id": msg.get("id"),
                    "from": next((h["value"] for h in headers if h["name"] == "From"), "Unknown"),
                    "subject": next((h["value"] for h in headers if h["name"] == "Subject"), "No Subject"),
                    "date": next((h["value"] for h in headers if h["name"] == "Date"), ""),
                    "snippet": msg.get("snippet", "")[:100],
                    "labels": label_display
                })
            click.echo(json.dumps(output_data, indent=2, ensure_ascii=False))
        elif output == "csv":
            import csv
            import sys
            writer = csv.writer(sys.stdout)
            writer.writerow(["ID", "From", "Subject", "Date", "Labels", "Preview"])
            for msg in valid_messages:
                headers = msg.get("payload", {}).get("headers", [])
                labels = msg.get("labelIds", [])
                label_display = ", ".join([l for l in labels if l not in ["INBOX", "UNREAD"]])
                writer.writerow([
                    msg.get("id", ""),
                    next((h["value"] for h in headers if h["name"] == "From"), "Unknown"),
                    next((h["value"] for h in headers if h["name"] == "Subject"), "No Subject"),
                    next((h["value"] for h in headers if h["name"] == "Date"), ""),
                    label_display,
                    msg.get("snippet", "")[:100]
                ])
        else:
            # Table format (default)
            click.echo(f"Found {len(valid_messages)} messages for '{query}':\n")
            for msg in valid_messages:
                headers = msg.get("payload", {}).get("headers", [])
                subject = next((h["value"] for h in headers if h["name"] == "Subject"), "No Subject")
                sender = next((h["value"] for h in headers if h["name"] == "From"), "Unknown")
                date = next((h["value"] for h in headers if h["name"] == "Date"), "")
                
                snippet = msg.get("snippet", "")[:100]
                labels = msg.get("labelIds", [])
                label_display = ", ".join([l for l in labels if l not in ["INBOX", "UNREAD"]])
                
                click.echo(f"📧 {msg.get('id')}")
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
@click.option("--from", "-f", "from_", help="Filter by sender email or name")
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
@click.option("--attach", multiple=True, help="Attachment file path (can specify multiple)")
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
@click.option("--cc", "-c", help="Additional CC recipient email address")
@_account_option
@click.pass_context
def reply(ctx, message_id, body, reply_all, cc, account):
    """Reply to a message."""
    account = account or ctx.obj.get("ACCOUNT")
    try:
        api = GmailAPI(account)
        result = api.reply_to_message(message_id, body, reply_all, cc)
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
@click.option("--dry-run", is_flag=True, help="Show what would be deleted without actually deleting")
@_account_option
@click.pass_context
def delete(ctx, message_id, force, dry_run, account):
    """Permanently delete a message (cannot be undone!)."""
    account = account or ctx.obj.get("ACCOUNT")
    
    if dry_run:
        click.echo(f"🔍 DRY RUN - Would permanently delete message {message_id}")
        return
    
    if not force:
        if not click.confirm(f"⚠️  Warning: This will permanently delete message {message_id}. This cannot be undone!\n   Do you want to continue?"):
            click.echo("Deletion cancelled.")
            return
    
    try:
        api = GmailAPI(account)
        api.delete_message(message_id)
        
        # Record in history (delete is not undoable)
        add_operation("delete", {
            "message_id": message_id
        }, undoable=False)
        
        click.echo(f"✅ Message {message_id} permanently deleted")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("message_id")
@click.option("--dry-run", is_flag=True, help="Show what would be trashed without actually trashing")
@_account_option
@click.pass_context
def trash(ctx, message_id, dry_run, account):
    """Move a message to trash (can be recovered)."""
    account = account or ctx.obj.get("ACCOUNT")
    
    if dry_run:
        click.echo(f"🔍 DRY RUN - Would move message {message_id} to trash")
        return
    
    try:
        api = GmailAPI(account)
        api.trash_message(message_id)
        
        # Record in history (trash is undoable - can untrash)
        add_operation("trash", {
            "message_id": message_id
        }, undoable=True, undo_func="untrash")
        
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
@click.argument("message_ids", nargs=-1, required=False)
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
        elif not message_ids:
            click.echo("❌ Error: Provide message IDs or use --query option")
            sys.exit(1)
        
        result = api.batch_modify_messages(message_ids, remove_label_ids=["UNREAD"])
        click.echo(f"✅ Marked {result['modified']} message(s) as read")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("message_ids", nargs=-1, required=False)
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
        elif not message_ids:
            click.echo("❌ Error: Provide message IDs or use --query option")
            sys.exit(1)
        
        result = api.batch_modify_messages(message_ids, remove_label_ids=["INBOX"])
        click.echo(f"✅ Archived {result['modified']} message(s)")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("message_ids", nargs=-1, required=False)
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
        elif not message_ids:
            click.echo("❌ Error: Provide message IDs or use --query option")
            sys.exit(1)
        
        result = api.batch_modify_messages(message_ids, add_label_ids=["STARRED"])
        click.echo(f"✅ Starred {result['modified']} message(s)")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("message_ids", nargs=-1, required=False)
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
        
        elif not message_ids:
            click.echo("❌ Error: Provide message IDs or use --query option")
            sys.exit(1)
        
        result = api.batch_modify_messages(message_ids, remove_label_ids=["STARRED"])
        click.echo(f"✅ Unstarred {result['modified']} message(s)")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("message_ids", nargs=-1, required=False)
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
        
        elif not message_ids:
            click.echo("❌ Error: Provide message IDs or use --query option")
            sys.exit(1)
        
        result = api.batch_trash_messages(message_ids)
        click.echo(f"✅ Moved {result['trashed']} message(s) to trash")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("message_ids", nargs=-1, required=False)
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
        
        elif not message_ids:
            click.echo("❌ Error: Provide message IDs or use --query option")
            sys.exit(1)
        
        result = api.batch_untrash_messages(message_ids)
        click.echo(f"✅ Restored {result['untrashed']} message(s) from trash")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("message_ids", nargs=-1, required=False)
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
        
        elif not message_ids:
            click.echo("❌ Error: Provide message IDs or use --query option")
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
@click.option("--query", "-q", help="Search query - operate on matching messages instead of IDs")
@click.option("--max", "-m", default=100, help="Maximum number of messages when using --query")
@click.option("--add-label", multiple=True, help="Label ID to add (can specify multiple)")
@click.option("--remove-label", multiple=True, help="Label ID to remove (can specify multiple)")
@click.argument("message_ids", nargs=-1, required=False)
@_account_option
@click.pass_context
def batch_modify(ctx, query, max, add_label, remove_label, message_ids, account):
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
        
        elif not message_ids:
            click.echo("❌ Error: Provide message IDs or use --query option")
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
@click.argument("message_ids", nargs=-1, required=False)
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
        
        elif not message_ids:
            click.echo("❌ Error: Provide message IDs or use --query option")
            sys.exit(1)
        
        result = api.batch_modify_messages(message_ids, add_label_ids=["SPAM"], remove_label_ids=["INBOX"])
        click.echo(f"✅ Marked {result['modified']} message(s) as spam")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("message_ids", nargs=-1, required=False)
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
        
        elif not message_ids:
            click.echo("❌ Error: Provide message IDs or use --query option")
            sys.exit(1)
        
        result = api.batch_modify_messages(message_ids, remove_label_ids=["SPAM"], add_label_ids=["INBOX"])
        click.echo(f"✅ Removed spam label from {result['modified']} message(s)")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--query", "-q", default="is:unread", help="Search query to watch for (default: is:unread)")
@click.option("--interval", "-i", default=30, type=int, help="Polling interval in seconds (default: 30)")
@click.option("--max", "-m", default=10, type=int, help="Maximum number of new messages to show per check")
@_account_option
@click.pass_context
def watch(ctx, query, interval, max, account):
    """Watch for new emails matching a query (polling mode)."""
    import time
    
    account = account or ctx.obj.get("ACCOUNT")
    click.echo(f"👀 Watching for emails matching: {query}")
    click.echo(f"   Polling every {interval} seconds")
    click.echo(f"   Press Ctrl+C to stop\n")
    
    api = GmailAPI(account)
    seen_message_ids = set()
    
    try:
        while True:
            try:
                messages = api.list_messages(max_results=max, query=query)
                new_messages = [msg for msg in messages if msg["id"] not in seen_message_ids]
                
                if new_messages:
                    click.echo(f"\n📬 Found {len(new_messages)} new message(s):")
                    for msg in new_messages:
                        message = api.get_message(msg["id"], format="metadata")
                        headers = message.get("payload", {}).get("headers", [])
                        subject = next((h["value"] for h in headers if h["name"] == "Subject"), "No Subject")
                        sender = next((h["value"] for h in headers if h["name"] == "From"), "Unknown")
                        click.echo(f"   📧 {subject} - From: {sender}")
                        seen_message_ids.add(msg["id"])
                    click.echo()
                else:
                    click.echo(".", nl=False, err=True)  # Progress indicator
                
                time.sleep(interval)
            except KeyboardInterrupt:
                click.echo("\n\n👋 Stopped watching.")
                break
            except Exception as e:
                click.echo(f"\n❌ Error: {e}", err=True)
                time.sleep(interval)
    except KeyboardInterrupt:
        click.echo("\n👋 Stopped watching.")


@cli.group()
def template():
    """Email template management commands."""
    pass


@template.command("list")
def template_list():
    """List all email templates."""
    templates = list_templates()
    if not templates:
        click.echo("No templates found.")
        click.echo("\nCreate a template with: gmail template create <name>")
        return
    
    click.echo(f"Found {len(templates)} template(s):\n")
    for tmpl in templates:
        click.echo(f"📧 {tmpl['name']}")
        if tmpl.get("subject"):
            click.echo(f"   Subject: {tmpl['subject']}")
        if tmpl.get("to"):
            click.echo(f"   To: {tmpl['to']}")
        click.echo()


@template.command("create")
@click.argument("name")
@click.option("--to", help="Default recipient")
@click.option("--subject", help="Email subject")
@click.option("--body", help="Email body")
@click.option("--cc", help="CC recipient")
def template_create(name, to, subject, body, cc):
    """Create a new email template."""
    if not any([to, subject, body, cc]):
        click.echo("Creating template interactively...")
        to = to or click.prompt("To (optional)", default="", show_default=False)
        subject = subject or click.prompt("Subject (optional)", default="", show_default=False)
        body = body or click.prompt("Body (optional)", default="", show_default=False)
        cc = cc or click.prompt("CC (optional)", default="", show_default=False)
    
    template = create_template(name, to=to, subject=subject, body=body, cc=cc)
    click.echo(f"✅ Template '{name}' created successfully!")


@template.command("delete")
@click.argument("name")
def template_delete(name):
    """Delete an email template."""
    if delete_template(name):
        click.echo(f"✅ Template '{name}' deleted successfully!")
    else:
        click.echo(f"❌ Template '{name}' not found.", err=True)
        sys.exit(1)


@template.command("show")
@click.argument("name")
def template_show(name):
    """Show template details."""
    template = get_template(name)
    if not template:
        click.echo(f"❌ Template '{name}' not found.", err=True)
        sys.exit(1)
    
    click.echo(f"📧 Template: {name}")
    if template.get("to"):
        click.echo(f"   To: {template['to']}")
    if template.get("subject"):
        click.echo(f"   Subject: {template['subject']}")
    if template.get("body"):
        click.echo(f"   Body: {template['body']}")
    if template.get("cc"):
        click.echo(f"   CC: {template['cc']}")


@cli.command()
@click.option("--limit", "-l", default=10, type=int, help="Number of operations to show")
def history(limit):
    """Show recent operation history."""
    operations = get_recent_operations(limit)
    
    if not operations:
        click.echo("No operations in history.")
        return
    
    click.echo(f"Recent operations (last {len(operations)}):\n")
    for op in reversed(operations):
        timestamp = op.get("timestamp", "")
        op_type = op.get("type", "unknown")
        details = op.get("details", {})
        undoable = "✓" if op.get("undoable") else "✗"
        
        click.echo(f"{undoable} [{timestamp[:19]}] {op_type}")
        if details:
            for key, value in details.items():
                if key != "message_id":  # Skip internal IDs for cleaner display
                    click.echo(f"   {key}: {value}")
        click.echo()


@cli.command()
@_account_option
@click.pass_context
def undo(ctx, account):
    """Undo the last undoable operation."""
    account = account or ctx.obj.get("ACCOUNT")
    
    last_op = get_last_undoable_operation()
    
    if not last_op:
        click.echo("❌ No undoable operation found.")
        return
    
    op_type = last_op.get("type")
    details = last_op.get("details", {})
    undo_func = last_op.get("undo_func")
    
    click.echo(f"Undoing: {op_type} at {last_op.get('timestamp', '')[:19]}")
    
    try:
        api = GmailAPI(account)
        
        if op_type == "trash" and undo_func == "untrash":
            message_id = details.get("message_id")
            if message_id:
                api.untrash_message(message_id)
                click.echo(f"✅ Message {message_id} restored from trash")
            else:
                click.echo("❌ Cannot undo: missing message ID")
        else:
            click.echo(f"❌ Cannot undo operation type: {op_type}")
    
    except Exception as e:
        click.echo(f"❌ Error undoing operation: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--shell", type=click.Choice(["bash", "zsh", "fish"]), required=True, help="Shell type for completion script")
def completion(shell):
    """Generate shell completion script. Add to your shell config file."""
    try:
        from click.shell_completion import get_completion_script
        
        # Get the completion script
        script = get_completion_script("gmail", "_GMAIL_COMPLETE", shell)
        click.echo(script)
        click.echo(f"\n# To install, run:", err=True)
        if shell == "fish":
            click.echo(f"# gmail completion --shell {shell} > ~/.config/fish/completions/gmail.fish", err=True)
        else:
            click.echo(f"# gmail completion --shell {shell} >> ~/.{shell}rc", err=True)
    except ImportError:
        click.echo("❌ Shell completion not available. Install click>=8.0", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Error generating completion script: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()

