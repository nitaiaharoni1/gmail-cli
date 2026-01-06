"""Google People API wrapper for contacts."""

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from .auth import get_credentials, check_auth
from .retry import with_retry
from typing import List, Dict, Optional


class PeopleAPI:
    """Wrapper for Google People API operations."""
    
    def __init__(self, account=None):
        """
        Initialize People API service.
        
        Args:
            account: Account name (optional). If None, uses default account.
        """
        creds = check_auth(account)
        if not creds:
            raise Exception("Not authenticated. Run 'gmail init' first.")
        
        self.service = build("people", "v1", credentials=creds)
        self.account = account
    
    @with_retry()
    def list_contacts(self, max_results=100):
        """
        List all contacts with names and email addresses.
        
        Args:
            max_results: Maximum number of contacts to return (default: 100)
        
        Returns:
            List of contact dictionaries with 'name' and 'email' keys
        """
        try:
            contacts = []
            page_token = None
            
            while len(contacts) < max_results:
                results = self.service.people().connections().list(
                    resourceName='people/me',
                    personFields='names,emailAddresses',
                    pageSize=min(100, max_results - len(contacts)),
                    pageToken=page_token
                ).execute()
                
                connections = results.get('connections', [])
                for person in connections:
                    name = None
                    emails = []
                    
                    # Extract name
                    names = person.get('names', [])
                    if names:
                        name = names[0].get('displayName') or names[0].get('givenName', '')
                    
                    # Extract emails
                    email_addresses = person.get('emailAddresses', [])
                    for email_obj in email_addresses:
                        email = email_obj.get('value')
                        if email:
                            emails.append(email)
                    
                    # Only include contacts with at least one email
                    if emails:
                        for email in emails:
                            contacts.append({
                                'name': name or email,
                                'email': email,
                                'resourceName': person.get('resourceName')
                            })
                
                page_token = results.get('nextPageToken')
                if not page_token:
                    break
            
            return contacts[:max_results]
        
        except HttpError as error:
            raise Exception(f"Failed to list contacts: {error}")
    
    @with_retry()
    def search_contacts(self, query: str, max_results=50):
        """
        Search contacts by name or email.
        
        Args:
            query: Search query (name or email)
            max_results: Maximum number of results to return (default: 50)
        
        Returns:
            List of matching contact dictionaries
        """
        try:
            query_lower = query.lower()
            all_contacts = self.list_contacts(max_results=500)
            
            matches = []
            for contact in all_contacts:
                name = (contact.get('name') or '').lower()
                email = contact.get('email', '').lower()
                
                if query_lower in name or query_lower in email:
                    matches.append(contact)
                    if len(matches) >= max_results:
                        break
            
            return matches
        
        except Exception as error:
            raise Exception(f"Failed to search contacts: {error}")
    
    def get_contact_email(self, name: str) -> Optional[str]:
        """
        Resolve a contact name to an email address.
        Returns the first matching email, or None if not found.
        
        Args:
            name: Contact name to resolve
        
        Returns:
            Email address if found, None otherwise
        """
        try:
            matches = self.search_contacts(name, max_results=1)
            if matches:
                return matches[0].get('email')
            return None
        except Exception:
            return None

