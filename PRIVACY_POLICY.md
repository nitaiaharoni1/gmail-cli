# Privacy Policy for Gmail CLI

**Last Updated:** January 2025

## Overview

Gmail CLI is a command-line interface tool that allows users to manage their Gmail account directly from the terminal. This privacy policy explains how we handle your data.

## Data Collection and Usage

### What Data We Access

Gmail CLI requests the following permissions:
- **Read emails** (`gmail.readonly`) - To list and read your emails
- **Send emails** (`gmail.send`) - To send emails on your behalf
- **Modify emails** (`gmail.modify`) - To archive, delete, or modify emails
- **Manage settings** (`gmail.settings.basic`) - To create filters and manage labels

### How We Use Your Data

- **All data stays on your device** - Gmail CLI runs locally on your computer
- **No data transmission** - We do not send your emails or data to any external servers
- **No data storage** - We only store OAuth tokens locally on your device for authentication
- **No analytics** - We do not collect usage statistics or analytics

### Data Storage

- **OAuth tokens** are stored locally in `~/.google/tokens/` directory
- **Account preferences** are stored locally in `~/.google/preferences.json`
- **Templates** are stored locally in `~/.google/templates/`
- **Operation history** is stored locally in `~/.google/history.json`

All stored data is encrypted with file system permissions (600) and never leaves your device.

## Third-Party Services

Gmail CLI uses Google's Gmail API to access your Gmail account. Your use of Gmail CLI is also subject to Google's Privacy Policy: https://policies.google.com/privacy

## Security

- All OAuth tokens are stored securely with restricted file permissions
- No credentials or sensitive data are transmitted over the network except to Google's official APIs
- The application uses OAuth 2.0 for secure authentication

## Your Rights

- You can revoke access at any time by visiting: https://myaccount.google.com/permissions
- You can delete all local data by removing the `~/.google/` directory
- You can uninstall the application at any time

## Contact

For questions about this privacy policy, please contact: [Your Email]

## Changes to This Policy

We may update this privacy policy from time to time. The latest version will always be available at: https://github.com/nitaiaharoni1/gmail-cli/blob/main/PRIVACY_POLICY.md

