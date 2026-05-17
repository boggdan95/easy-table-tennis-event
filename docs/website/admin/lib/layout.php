<?php
function admin_layout_header(string $page_title = 'Admin'): void
{
    $title = htmlspecialchars($page_title);
    echo <<<HTML
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex, nofollow">
  <link rel="icon" type="image/svg+xml" href="../favicon.svg">
  <title>ETTEM Admin · {$title}</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; min-height: 100vh; }
    a { color: #34d399; text-decoration: none; }
    a:hover { text-decoration: underline; }
    code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.85em; background: rgba(148,163,184,0.15); padding: 0.1rem 0.35rem; border-radius: 4px; }
    .topbar { background: #1e293b; border-bottom: 1px solid #334155; padding: 1rem 1.5rem; display: flex; justify-content: space-between; align-items: center; }
    .topbar h1 { font-size: 1rem; color: #f1f5f9; }
    .topbar h1 span { color: #34d399; }
    .topbar nav { display: flex; gap: 1.25rem; font-size: 0.875rem; }
    .topbar .active { color: #f1f5f9; font-weight: 600; }
    .container { max-width: 1100px; margin: 0 auto; padding: 2rem 1.5rem; }
    h2 { font-size: 1.5rem; color: #f1f5f9; margin-bottom: 0.25rem; }
    .subtitle { color: #94a3b8; font-size: 0.875rem; margin-bottom: 1.5rem; }
    .card { background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 1.5rem; margin-bottom: 1rem; }
    .card h3 { font-size: 1rem; margin-bottom: 0.75rem; color: #f1f5f9; }
    .form-group { display: flex; flex-direction: column; gap: 0.4rem; margin-bottom: 1rem; }
    label { font-size: 0.8rem; color: #cbd5e1; font-weight: 500; }
    input[type=text], input[type=email] { padding: 0.55rem 0.75rem; background: #0f172a; border: 1px solid #334155; border-radius: 6px; color: #f1f5f9; font-size: 0.9rem; font-family: inherit; }
    input:focus { outline: none; border-color: #34d399; }
    .btn { display: inline-block; padding: 0.55rem 1.25rem; background: #34d399; color: #064e3b; border: none; border-radius: 6px; font-weight: 600; cursor: pointer; font-size: 0.9rem; font-family: inherit; text-decoration: none; }
    .btn:hover { background: #10b981; }
    .btn-outline { background: transparent; color: #cbd5e1; border: 1px solid #334155; }
    .btn-outline:hover { background: #334155; }
    .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
    table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
    th { text-align: left; padding: 0.6rem 0.75rem; border-bottom: 1px solid #334155; color: #94a3b8; font-weight: 500; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; }
    td { padding: 0.75rem; border-bottom: 1px solid #1e293b; color: #e2e8f0; }
    .alert { padding: 0.85rem 1rem; border-radius: 6px; margin-bottom: 1rem; font-size: 0.875rem; }
    .alert-error { background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3); color: #fca5a5; }
    .alert-success { background: rgba(52,211,153,0.1); border: 1px solid rgba(52,211,153,0.3); color: #6ee7b7; }
    .muted { color: #94a3b8; }
    .badge { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 4px; font-size: 0.7rem; background: #334155; color: #cbd5e1; }
    .badge-warn { background: rgba(245,158,11,0.2); color: #fbbf24; }
  </style>
</head>
<body>
HTML;
}

function admin_layout_nav(string $current = ''): void
{
    $items = [
        'index' => ['Dashboard', 'index.php'],
        'tenants' => ['Tenants Cloud', 'tenants.php'],
    ];
    echo '<header class="topbar"><h1>ETTEM <span>Admin</span></h1><nav>';
    foreach ($items as $key => [$label, $href]) {
        $cls = $key === $current ? 'active' : '';
        $href = htmlspecialchars($href);
        $label = htmlspecialchars($label);
        echo "<a href=\"{$href}\" class=\"{$cls}\">{$label}</a>";
    }
    echo '<a href="logout.php">Salir</a></nav></header>';
}

function admin_layout_footer(): void
{
    echo '</body></html>';
}
