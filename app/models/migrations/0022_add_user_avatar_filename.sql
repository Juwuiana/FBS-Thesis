-- Store the per-user profile-photo filename; image data remains on disk.
ALTER TABLE users ADD COLUMN avatar_filename TEXT DEFAULT NULL;