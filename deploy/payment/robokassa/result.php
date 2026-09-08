<?php
declare(strict_types=1);

require __DIR__ . '/../../config.php';

error_reporting(0);
ini_set('display_errors', '0');

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
