# Gmail CLI

A powerful command-line interface for Gmail built with Python. Manage your emails directly from the terminal.

## Features

- 📧 **Read and list emails** from your mailbox
- ✉️ **Send emails** with optional attachments
- 🏷️ **Manage labels** and organize emails
- 🔍 **Search emails** with Gmail query syntax
- 🧵 **View email threads**
- ✅ **Mark messages as read** or archive them
- 🔐 **Secure OAuth 2.0 authentication**

## Installation

### Using Homebrew (macOS)

```bash
brew tap nitaiaharoni/gmail-cli
brew install gmail-cli
```

### Manual Installation

1. Clone the repository:
```bash
git clone https://github.com/nitaiaharoni/gmail-cli.git
cd gmail-cli
```

2. Install dependencies:
```bash
pip3 install -r requirements.txt
```

3. Install the package:
```bash
pip3 install -e .
```

Or use the installation script:
```bash
./install.sh
```

## Setup

### 1. Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the **Gmail API**:
   - Navigate to "APIs & Services" → "Library"
   - Search for "Gmail API"
   - Click "Enable"

### 2. Create OAuth 2.0 Credentials

1. Go to "APIs & Services" → "Credentials"
2. Click "Create Credentials" → "OAuth client ID"
3. If prompted, configure the OAuth consent screen:
   - Choose "External" (unless you have a Google Workspace)
   - Fill in required fields (App name, User support email, etc.)
   - Add your email to test users
   - Save and continue
4. Create OAuth client ID:
   - Application type: **Desktop app**
   - Name: Gmail CLI (or your preferred name)
   - Click "Create"
5. Download the credentials file:
   - Click the download icon next to your OAuth client
   - Save it as `credentials.json`
   - Place it in the current directory or your home directory (`~/`)

### 3. Authenticate

Run the initialization command:

```bash
gmail init
```

This will:
- Open a browser window for Google authentication
- Ask you to grant permissions to the Gmail API
- Save your refresh token securely in `~/.gmail_token.json`

## Usage

### Basic Commands

```bash
# Show authenticated user info
gmail me

# List recent emails (default: 10)
gmail list

# List more emails
gmail list --max 20

# List emails with a specific label
gmail list --label INBOX

# Search emails
gmail search "from:example@gmail.com"

# Read a specific email
gmail read <message-id>

# Send an email
gmail send recipient@example.com "Subject" --body "Email body text"

# Send email with attachment
gmail send recipient@example.com "Subject" --body "Body" --attach file.pdf

# List all labels
gmail labels

# List email threads
gmail threads

# Mark message as read
gmail mark-read <message-id>

# Archive a message
gmail archive <message-id>
```

### Advanced Usage

#### Search Queries

Gmail CLI supports Gmail's powerful search syntax:

```bash
# Search by sender
gmail search "from:example@gmail.com"

# Search by subject
gmail search "subject:meeting"

# Search unread emails
gmail search "is:unread"

# Search emails with attachments
gmail search "has:attachment"

# Combine queries
gmail search "from:boss@company.com is:unread"
```

#### Filter by Labels

```bash
# List emails in INBOX
gmail list --label INBOX

# List emails in SENT
gmail list --label SENT

# List emails in a custom label
gmail list --label "MyLabel"
```

## Command Reference

| Command | Description |
|---------|-------------|
| `gmail init` | Initialize and authenticate with Gmail API |
| `gmail me` | Show authenticated user information |
| `gmail list [--label LABEL] [--max N] [--query QUERY]` | List emails |
| `gmail read <message-id>` | Read full email content |
| `gmail send <to> <subject> [--body TEXT] [--attach FILE]` | Send email |
| `gmail labels` | List all labels |
| `gmail search <query> [--max N]` | Search emails |
| `gmail threads [--max N] [--query QUERY]` | List email threads |
| `gmail mark-read <message-id>` | Mark message as read |
| `gmail archive <message-id>` | Archive message |

## Examples

### Quick Email Check

```bash
# Check recent unread emails
gmail search "is:unread" --max 5
```

### Send a Quick Note

```bash
gmail send me@example.com "Reminder" --body "Don't forget the meeting at 3pm"
```

### Archive Old Emails

```bash
# First, find old emails
gmail search "older_than:30d" --max 50

# Then archive them (you'll need to do this one by one or script it)
gmail archive <message-id>
```

## Troubleshooting

### Authentication Issues

**"credentials.json not found"**
- Make sure you've downloaded the OAuth credentials from Google Cloud Console
- Place `credentials.json` in the current directory or your home directory

**"Not authenticated"**
- Run `gmail init` to authenticate
- Make sure you've granted all required permissions

**Token expired**
- The CLI automatically refreshes tokens, but if issues persist:
  - Delete `~/.gmail_token.json`
  - Run `gmail init` again

### API Errors

**"Quota exceeded"**
- Gmail API has rate limits
- Wait a few minutes and try again
- Consider reducing the number of API calls

**"Permission denied"**
- Make sure you've enabled the Gmail API in Google Cloud Console
- Check that your OAuth credentials are correct
- Verify you've granted the necessary scopes

## Requirements

- Python 3.8 or higher
- Google Cloud Project with Gmail API enabled
- OAuth 2.0 credentials

## Security

- Tokens are stored securely in `~/.gmail_token.json` with 600 permissions
- Never commit `credentials.json` or token files to version control
- Use environment variables for CI/CD if needed

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Author

Created by [Nitai Aharoni](https://github.com/nitaiaharoni)

## Support

For issues and feature requests, please use the [GitHub Issues](https://github.com/nitaiaharoni/gmail-cli/issues) page.

