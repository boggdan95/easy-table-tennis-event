<?php
/**
 * ETTEM Admin — Configuration template
 *
 * Copy this file to config.php and fill in the real values on the server.
 * config.php is gitignored and must NEVER be committed.
 *
 * The .htaccess in this directory denies direct HTTP access to config.php,
 * but it can still be read by PHP scripts here.
 */

return [
    // Admin login code. Strong + unique. Change it from this default.
    // Suggested format: ETTEM_ADMIN_<random 16 chars>
    'admin_code' => 'CHANGE_ME_TO_A_LONG_RANDOM_STRING',

    // Session cookie name + signing salt (any random string, just keep stable)
    'cookie_name' => 'ettem_admin',
    'cookie_salt' => 'CHANGE_ME_TOO_SOMETHING_UNIQUE',
    'session_ttl_seconds' => 86400, // 24 hours

    // Supabase project — find these in Project Settings → API
    'supabase_url' => 'https://YOUR_PROJECT_REF.supabase.co',
    'supabase_service_role_key' => 'eyJ...',

    // URL of the ETTEM Cloud portal (Next.js app on Vercel). Used as the
    // redirect destination for magic-link invites.
    //   Local dev: http://localhost:3000
    //   Production: https://app.ettem.boggdan.com
    'app_url' => 'http://localhost:3000',
];
