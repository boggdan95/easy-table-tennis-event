<?php
/**
 * ETTEM License Server - Configuration
 *
 * Copy this file to config.php and fill in your values.
 * NEVER commit config.php to git!
 */

// MySQL Database
define('DB_HOST', 'localhost');
define('DB_NAME', 'your_db_name');       // e.g. boggdan_ettem_licenses
define('DB_USER', 'your_db_user');       // e.g. boggdan_ettem
define('DB_PASS', 'your_db_password');

// HMAC Secret Key (same as in Python licensing.py)
define('HMAC_SECRET', '572d0294f72e6afd3dc8b4b8510fdfe01f35ff4810818ee7e1d19cd07bf126cd');

// API Key (shared secret with the ETTEM desktop app)
define('API_KEY', 'change-this-to-a-random-32-char-string');

// Admin password (bcrypt hash) - generate with: php -r "echo password_hash('your_password', PASSWORD_BCRYPT);"
define('ADMIN_PASSWORD_HASH', '$2y$10$CHANGE_THIS_TO_YOUR_HASH');

// Rate limiting
define('RATE_LIMIT_MAX', 20);        // max requests
define('RATE_LIMIT_WINDOW', 60);     // per X seconds
