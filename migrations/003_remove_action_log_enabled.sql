-- migrations/003_remove_action_log_enabled.sql
ALTER TABLE action_log_events DROP COLUMN IF EXISTS enabled;