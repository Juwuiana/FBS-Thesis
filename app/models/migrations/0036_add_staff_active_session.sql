-- One active login per staff account: token is compared with the session cookie.
ALTER TABLE users ADD COLUMN active_session_token TEXT;
ALTER TABLE users ADD COLUMN active_session_last_seen TEXT;
