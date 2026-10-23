<?php
declare(strict_types=1);

require __DIR__ . '/../../config.php';

error_reporting(0);
ini_set('display_errors', '0');

// Robokassa notifies from these addresses only (docs.robokassa.ru, "Уведомления и
// переадресация"); nginx serves PHP directly, so REMOTE_ADDR is the sender
$robokassa_ips = array('185.59.216.65', '185.59.217.65');
if (!in_array($_SERVER['REMOTE_ADDR'] ?? '', $robokassa_ips, true)) {
    http_response_code(403);
    echo "bad sign\n";
    exit;
}

$get_b64 = base64_encode(json_encode($_GET, JSON_FORCE_OBJECT));

$python = $bot_path . '/venv/bin/python';
$script = $bot_path . '/scripts/payment/subscription_income.py';
if (!is_file($python) || !is_file($script)) {
    http_response_code(500);
    echo "bad sign\n";
    exit;
}

$cmd = array($python, $script, $get_b64, $bot_path);
$desc = array(
    1 => array('pipe', 'w'),
    2 => array('pipe', 'w'),
);
$proc = proc_open($cmd, $desc, $pipes, $bot_path, null, array('bypass_shell' => true));
if (!is_resource($proc)) {
    http_response_code(500);
    echo "bad sign\n";
    exit;
}
$out = stream_get_contents($pipes[1]);
fclose($pipes[1]);
fclose($pipes[2]);
proc_close($proc);

echo $out;
