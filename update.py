from collections import namedtuple
import json
import secrets
import sqlite3
import sys


User = namedtuple('User', ['user_id', 'email', 'api_key'])


def init_db():
  """Initializes the database and creates the necessary tables."""
  conn = sqlite3.connect('userfiles.db')
  cursor = conn.cursor()
  cursor.execute('''
      CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY,
          email TEXT NOT NULL UNIQUE,
          api_key TEXT NOT NULL UNIQUE
      )
  ''')
  cursor.execute('''
      CREATE TABLE IF NOT EXISTS grants (
        id INTEGER PRIMARY KEY,
        -- If NULL, then all users have access
        user_id INTEGER,
        file_path TEXT NOT NULL,
        granted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, file_path)
      )
  ''')
  # Create a unique index that only applies to rows where user_id IS NULL.
  # This correctly enforces the uniqueness of public grants.
  cursor.execute('''
      CREATE UNIQUE INDEX IF NOT EXISTS unique_public_grant ON grants(file_path) WHERE user_id IS NULL;
  ''')
  conn.commit()
  return conn
  

def add_grant(conn, user_spec, file_path):
  """
  High-level function to ensure a user exists and then adds a grant for them.
  This is the main function to call for adding a file grant.
  """
  # If input is an email address, then we can try to create the user first.
  if '@' in user_spec:
    add_user_if_not_exists(conn, user_spec)
  add_grant_if_not_exists(conn, user_spec, file_path)


def add_user_if_not_exists(conn, email):
  """Inserts a new user only if their email doesn't already exist."""
  api_key = generate_api_key()
  cursor = conn.cursor()
  cursor.execute("INSERT OR IGNORE INTO users (email, api_key) VALUES (?, ?)", (email, api_key))
  conn.commit()
  if cursor.rowcount > 0:
    print(f"User '{email}' added successfully. Generated API Key: {api_key}")


def lookup_user(conn, user_spec):
  """
  Returns User tuple for the given user, specified by email or API key
  """
  cursor = conn.cursor()

  # Find the user's ID using their email.
  if '@' in user_spec:
    cursor.execute("SELECT id, email, api_key FROM users WHERE email = ?", (user_spec,))
    user_row = cursor.fetchone()
    if user_row:
      return User(*user_row)

  # Find the user's ID using their API key.
  if user_spec != 'all':
    cursor.execute("SELECT id, email, api_key FROM users WHERE api_key = ?", (user_spec,))
    user_row = cursor.fetchone()
    if user_row:
      return User(*user_row)


def add_grant_if_not_exists(conn, user_spec, filepath):
  """
  Adds a file access grant for a user only if it doesn't already exist.
  This function first finds the user's ID and then inserts the grant.
  """
  if user_spec == 'all':
    user_id = None
  else:
    user = lookup_user(conn, user_spec)
    if not user:
      print("Error: failed to add grant because user was unknown")
      return
    user_id = user.user_id

  cursor = conn.cursor()

  # Use INSERT OR IGNORE with the user ID to add the grant.
  # The UNIQUE(user_id, file_path) constraint will prevent duplicates.
  cursor.execute("INSERT OR IGNORE INTO grants (user_id, file_path) VALUES (?, ?)", (user_id, filepath))
  conn.commit()
  if cursor.rowcount > 0:
    print("Added grant")


def revoke_grant(conn, user_spec, filepath):
  """
  Removes a previously granted permission.
  """
  if user_spec == 'all':
    user = None
  else:
    user = lookup_user(conn, user_spec)
    if not user:
      print(f"Error: failed to remove grant because user was unknown")
      return

  cursor = conn.cursor()

  if user:
    # Delete rows by user id.
    cursor.execute("DELETE FROM grants WHERE user_id = ? AND file_path = ?", (user.user_id, filepath))
  else:
    # Delete rows where user id is null.
    cursor.execute("DELETE FROM grants WHERE user_id IS NULL AND file_path = ?", (filepath,))
  conn.commit() 
  
  if cursor.rowcount > 0:
    print("Successfully revoked grant")
  else:
    print("Error: failed to revoke grant")


def print_grants(conn):
  """
  Prints each grant as a line like this:
      Email, Api Key, File Path
  Also prints files which are accessible by everybody like this:
      NULL, NULL, File Path
  """
  cursor = conn.cursor()
  # Use LEFT JOIN to ensure public grants (with NULL user_id) are included.
  # The users.email and users.api_key will be NULL for public grants.
  cursor.execute('''
      SELECT u.email, u.api_key, g.file_path
      FROM grants AS g
      LEFT JOIN users AS u ON g.user_id = u.id
  ''')
  
  print("Email, Api Key, File Path")
  for email, api_key, file_path in cursor.fetchall():
    # Replace None values with the string 'NULL' for printing
    email_str = email if email is not None else 'NULL'
    api_key_str = api_key if api_key is not None else 'NULL'
    print(f"{email_str}, {api_key_str}, {file_path}")


def export_grants(conn):
  """
  Export grants in JSON for serving.
  """
  cursor = conn.cursor()
  # Use LEFT JOIN to ensure public grants (with NULL user_id) are included.
  cursor.execute('''
      SELECT u.api_key, g.file_path
      FROM grants AS g
      LEFT JOIN users AS u ON g.user_id = u.id
  ''')

  public_files = set()
  grants = list()
  
  for api_key, file_path in cursor.fetchall():
    if api_key is None:
      public_files.add(file_path)
    else:
      grants.append([api_key, file_path])

  # We also need to dump out all the API Keys, because even users without
  # a specific grant can still access the public files.
  cursor.execute('''SELECT api_key FROM users''')
  api_keys = [row[0] for row in cursor.fetchall()]
  
  return json.dumps({'api_keys': api_keys, 'public_files': list(public_files), 'grants': grants})


def print_export(conn):
  print(export_grants(conn))


def build_edge_function(conn):
  grants_json = export_grants(conn)
  with open('site/netlify/edge-functions/auth-check.ts.tmpl', 'r') as f:
    file_content = f.read()
  file_content = file_content.replace("{{EXPORTED}}", grants_json)
  with open('site/netlify/edge-functions/auth-check.ts', 'w') as f:
    f.write(file_content)


def new_key(conn, user_spec):
  """
  Generates a new key for the given user.
  """
  user = lookup_user(conn, user_spec)
  if not user:
    if '@' in user_spec:
      add_user_if_not_exists(conn, user_spec)
    else:
      print(f"Error: unknown user")
    return

  # Generate a new API key
  new_api_key = generate_api_key()
  
  # Update the user's record with the new key
  cursor = conn.cursor()
  cursor.execute("UPDATE users SET api_key = ? WHERE id = ?", (new_api_key, user.user_id))
  conn.commit()
  print(f"New key generated for user '{user.email}'. New API Key: {new_api_key}")


def generate_api_key():
  """Generates a secure, URL-safe random string to use as an API key."""
  return secrets.token_urlsafe(16)
  

def test(conn):
  add_grant(conn, "bob@example.com", "test1.csv")
  add_grant(conn, "alice@example.com", "test2.csv")
  add_grant(conn, "all", "test3.csv")


def help():
  print("""Commands:
  
  test
    Fills the db with fake data.

  print
    Print all the granted permissions in human readable format.
    Format is comma-separated values: Email, Api Key, File Path
    Note: files granted to all users will have NULL for Email and API Key
  
  add_grant [user_spec] [filepath]
    Grant permission for the specified user to read the file.

    user_spec can take on three values:
      1. Email address. If the user does not exist, then they will be added and an API key generated for them.
      2. API key. This must already exist in the users table.
      3. "all". Grants access to all users.

  revoke_grant [user_spec] [filepath]
    Revoke permission for the specified user to read the file.

    user_spec works same as above. If user_spec is "all" it will only remove *that* permission;
    existing grants for specific users will not be touched.

  new_key [user_spec]
    Generate a new key for the specified user, by email or existing API key
    
  export
    Export granted permissions for serving.

  build
    Build the site for serving, by updating the permissions data in edge function.
  """)
  

def main():
  args = sys.argv[1:]
  
  if not args or args[0] == 'help':
    help()
    sys.exit()
  
  conn = init_db()

  if args[0] == 'test':
    test(conn)
  elif args[0] == 'print':
    print_grants(conn)
  elif args[0] == 'export':
    print_export(conn)
  elif args[0] == 'build':
    build_edge_function(conn)
  elif args[0] == 'add_grant':
    if len(args) == 3:
      add_grant(conn, args[1], args[2])
    else:
      print("Error: add_grant takes 2 args")
  elif args[0] == 'revoke_grant':
    if len(args) == 3:
      revoke_grant(conn, args[1], args[2])
    else:
      print("Error: revoke_grant takes 2 args")
  elif args[0] == 'new_key':
    if len(args) == 2:
      new_key(conn, args[1])
    else:
      print("Error: new_key takes 1 arg")
  else:
    print("Error: unknown command")
    help()

  conn.close()


if __name__ == '__main__':
  main()
